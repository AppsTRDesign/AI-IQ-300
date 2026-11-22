"""One model turn as it streams: reasoning, text, tool calls (native or tag protocol), live steps, stalls, loops and very long reasoning.

Split out of orchestrator.py (round 2026-11-20); every name here is re-exported there."""
from __future__ import annotations

import asyncio
import base64
import itertools
import hashlib
import json
import re
import time
import uuid
from collections import deque
from pathlib import Path
from dataclasses import dataclass, field

from .. import approvals, db, netwatch, sessions, tokens, workspace
from ..config import load_settings, redact
from ..process_manager import manager as proc_manager
from ..events import bus
from ..llm import memguard, modelstats, router
from ..llm.usage import cooldown as usage_cooldown
from ..llm.providers import ProviderError
from ..tools.symbols import project_map
from ..tools.registry import figures as registry_figures
from ..tools.registry import READ_ONLY, TOOLS, ToolContext, ToolResult, clip, split_args, todo_patch, tool_schemas, tools_prompt
from ..tools.browser_tools import BROWSER_TOOLS, label as _browser_label
from . import catalog
from .stream_parser import LEAK, THINK_OPENERS, StreamSplitter, ToolCall, attrs, extract_inline_calls, parse_tool

# Prompt texts and the intent/check rules live in their own modules; their names are re-exported here.
from .prompts import *  # noqa: F401,F403
from .checks import *  # noqa: F401,F403
from .prompts import HISTORY_MESSAGES, LOCAL_HISTORY, OS_NAME, SHELLS, SUMMARY_TAG, DEFAULT_ROLE, SYSTEM_CORE, CAP_HEAD, CAPABILITIES, WORK_TOOLS, WORK_RULES_LEAN, CAP_HEAD_LEAN, CAPABILITIES_LEAN, CHAT_NOTE, ABILITY_ASK, RULE_TOPICS_LEAN, BROWSER_GUIDE_LEAN, WEB_TOOLS, WORK_RULES, RULE_TOPICS, SCREENSHOT_RULE, ENV_SECTION, rule_topics, WEB_RULES, TAG_PROTOCOL  # noqa: F401
from .checks import plan_steps, request_steps, request_parts, error_playbook, NOT_FOUND, LANG_NAMES, SCRIPTS, TR_CHARS, TR_WORDS, EN_WORDS, _CJK, _load_intents, INTENTS, intent_alt, _extend, _lang_rx, LANG_WORD_RX, _lang_counts, reply_language, SMALL_TALK, ACTION, WORK, QUESTION, CORE_TOOLS, WEB_WORDS, GROUP_TOOLS, GROUPED, GROUP_WORDS, tool_groups, STRONG_BROWSER, BROWSER_WORDS, CODE_NOT_RUN, HOWTO, SHELL_FENCES, FENCE, CMD_START, fenced_commands, is_small_talk, FILE_NAME, _unread_files, CURRENT_INFO, needs_research, is_knowledge_question, ANNOUNCE, PROMISE, VISUAL_ASK, is_promise, is_announcement, FILE_CLAIM, ACTION_ECHO, CHANGE_REQUEST, CHANGE_CLAIM, FILE_EDIT_ASK, FILE_REF, DELIVER_VERB, DELIVERABLES, CLAIMED_FILE, _shown_files, tool_hint, missing_deliverables, FOREIGN_SCRIPT, TRANSLATE_HINT, LATIN_LANGS, CONTINUE_WORDS, wrong_language, _LANG_FILES, ui_text, think_reply_reminder, language_rule  # noqa: F401
from .learning import CTX_RATIO, LAST_REAL, _learn_ratio, _learn_speed, _shown_tokens  # noqa: F401
from .runstate import Run, _emit, _step  # noqa: F401
from .guards import _loop_cut  # noqa: F401
from .continuity import _drop_partial_file, _file_loop_check, _persist_partial  # noqa: F401


TOOL_NAMES = frozenset(TOOLS)  # also recognized when a model writes a tool as its own tag


PREP_NAME = re.compile(r'<function=([\w.-]+)|<tool\s+name="([\w.-]+)"|"name"\s*:\s*"([\w.-]+)"')


async def _stream_turn(run: Run, model: str, messages: list[dict], visible: list[str],
                       opts: dict) -> tuple[str, list[str], list[dict]]:
    """Stream one model turn. Returns (raw_text, tag_tool_blocks, native_tool_calls)."""
    splitter, raw, tags, calls = StreamSplitter(TOOL_NAMES), [], [], []
    run.model = model
    think_id = None
    thinking: list[str] = []
    think_at = [0.0]  # last time the live reasoning step was sent
    prep_id, prep_at = None, 0.0

    got_output = False  # anything received yet (else silence = prompt processing / model loading)
    thinking_live = False
    think_span = [0.0, 0.0]  # first / last reasoning chunk of this turn
    t_req = time.monotonic()
    if run.perf["prep_ms"] is None:
        run.perf["prep_ms"] = (t_req - run.t0) * 1000
    turn = {"model": model, "wait_ms": None, "total_ms": 0.0}
    # Output speed (tokens per second): characters written since the first token, ~3.5 per token, replaced by the
    # provider's own output count at the end. Cheap: a counter per event, no tokenizer on the stream.
    gen = {"chars": 0, "t1": None, "out": None}

    def tps_now() -> float | None:
        if not gen["t1"] or gen["chars"] < 40:
            return None
        secs = time.monotonic() - gen["t1"]
        return round(gen["chars"] / 3.5 / secs, 2) if secs > 0.5 else None
    # Live context: the prompt plus what the model has written so far that the next request will carry (text, tool
    # arguments), so the meter moves during a long file instead of jumping at the end. Reasoning is left out: it is
    # not sent again, so counting it made the meter fall back (6K -> 5K) when the next request's real size arrived.
    base = run.session.get("context_used") or 0
    out = {"native_think": [], "tool": 0, "at": 0.0, "real": False, "n": 0, "done": [0, 0]}

    def grow() -> None:
        now = time.monotonic()
        if now - gen.get("sent", 0.0) >= 1.0 and (v := tps_now()):  # live speed meter: one tiny event a second
            gen["sent"] = now
            _emit(run, "speed", tps=v)
        if out["real"] or now - out["at"] < 0.5:
            return
        out["at"] = now
        # Counted incrementally (only the pieces that arrived since the last update): re-tokenizing the whole
        # output twice a second made long answers and file writes slower the longer they got.
        for i, parts in enumerate((raw, thinking)):  # all text, minus the <think> part of it
            if len(parts) > out["done"][i]:
                out["n"] += (1 if i == 0 else -1) * tokens.count("".join(parts[out["done"][i]:]))
                out["done"][i] = len(parts)
        written = out["n"] + out["tool"] * 2 // 7  # streamed tool arguments (JSON/code): ~3.5 characters per token
        used = base + int(written * CTX_RATIO.get(model, 1.0))
        if used != run.session.get("context_used"):
            run.session["context_used"] = used; run.ctx_peak = max(run.ctx_peak, used)
            _emit(run, "context", used=used)

    def prepare(name: str | None, chars: int = 0, seconds: int = 0, force: bool = False) -> None:
        """Live 'preparing <tool>' step while the model is still writing a tool call (throttled)."""
        nonlocal prep_id, prep_at
        now = time.monotonic()
        if prep_id and not force and now - prep_at < 0.35:
            return
        prep_at = now
        run.partial = {"name": name, "chars": chars, "seconds": seconds}
        # What the model is doing right now, for the live step: waiting for the first token (the provider reads the
        # prompt), thinking, writing a tool call whose text streams in, or writing one the provider sends at the end.
        phase = ("first" if not got_output else "tool_stream" if chars else
                 ("tool_silent" if opts.get("tools") and not router.streams_tool_args(model) else "stalled")
                 if name == "tool" else "writing")
        if phase == "stalled" and thinking and not "".join(visible).strip() and not _mid_sentence("".join(thinking)):
            # Silence right after the reasoning is the model composing its answer / call (EVREN sends a call only when
            # complete), not a busy provider: "it may be busy" while it was thinking confused the user.
            phase = "after_think"
        elif phase == "stalled" and thinking and not "".join(visible).strip():
            phase = "think_stalled"  # the reasoning stopped mid-sentence: shown as such, not as "finished thinking"
        if phase == "tool_silent" and seconds >= 45 and not _call_open(run):
            run.silent_writer = True
        # The user must always see what is going on: the file being written and its size so far, or for a provider
        # that sends the call only at the end, how long nothing has come and when the app switches to streaming.
        target = _partial_target(run)
        switch_in = None  # the turn is no longer cut after SILENT_TOOL_LIMIT (see the idle branch below)
        # An overloaded provider can pause for minutes and still finish: it is not cut early (that only made it think
        # again from the start); the step says how long nothing came and when the stream timeout would retry.
        stall_in = (max(0, int(router.silence_limits(False)[1]) - seconds)
                    if phase in ("stalled", "after_think", "think_stalled") and not router.is_local(model) else None)
        prep_id = _step(run, "prepare", name or "tool", "running",
                        data={"tool": name, "chars": chars, "seconds": int(now - t_req), "idle": seconds, "phase": phase,
                              "prompt_tokens": _shown_tokens(run.prompt_est, model), "model": model,
                              "thought": sum(len(x) for x in thinking), "target": target, "switch_in": switch_in, "stall_in": stall_in,
                              "probe": getattr(run, "probe", None), "tps": tps_now(),
                              "local": router.is_local(model)}, step_id=prep_id)

    def end_thinking() -> None:
        nonlocal thinking_live
        if think_id and thinking_live:
            thinking_live = False
            _step(run, "thinking", "thinking", "done", "".join(thinking)[-30000:], step_id=think_id,
                  data={"tps": tps_now()})  # the whole thought when it ends (its speed stays for the steps export)

    def handle(kind: str, text: str) -> None:
        nonlocal think_id, thinking_live
        if kind == "visible":
            end_thinking()
            if run.hold:
                run.hold = False
                _emit(run, "reset_text")
            visible.append(text)
            _emit(run, "delta", text=text)
        elif kind == "thinking":
            thinking.append(text)
            thinking_live = True
            out["think_len"] = out.get("think_len", 0) + len(text)
            if (opts.get("tools") and out["think_len"] > THINK_CAP and run.overthought < 2 and not tags and not calls
                    and not "".join(visible).strip()):
                # Reasoning for many minutes without acting (40-60K characters: the same version question weighed
                # again and again, "you think too much" from the user). The plan so far is carried over and the
                # next request goes without reasoning, so the model acts on it now.
                run.overthought += 1
                _step(run, "note", "loop", "done", ui_text(
                    opts.get("lang") or load_settings().get("language") or "en", "ai_note_overthink",
                    "The model reasoned for a very long time without acting; its plan so far was kept and it is asked "
                    "to act on it now."))
                raise ProviderError("looping", "very long reasoning without an action; continuing from its plan")
            think_span[1] = time.monotonic()
            think_span[0] = think_span[0] or think_span[1]
            # At most 4 updates a second: joining the whole reasoning and sending 6 KB on every token made long
            # thinking (deepseek: thousands of tokens) slower and slower, on the server and in the browser.
            now = time.monotonic()
            if think_id is None or now - think_at[0] >= 0.1:  # 10 updates a second: fast models read live
                think_at[0] = now
                think_id = _step(run, "thinking", "thinking", "running", "".join(thinking)[-6000:], step_id=think_id,
                                 data={"tps": tps_now()})
        elif kind in ("tool", "tool_incomplete"):
            tags.append(text)
        elif kind == "retract":  # what was shown was reasoning (a lone </think> arrived): take it back
            visible.clear()
            _emit(run, "reset_text")

    # Connection check while the stream is silent (the user's "is it still working or did it drop?"): see router.ping.
    probe = {"task": None, "res": None, "idle": 0, "gap": 0.0, "last": time.monotonic()}

    async def _liveness(secs: int, keepalive: int | None = None) -> None:
        if router.is_local(model):
            return  # a local server is silent while it reads a long prompt on the CPU; nothing to probe
        if secs < probe["idle"]:  # data came in between: a new silence, a new probe
            if probe["task"] and not probe["task"].done():
                probe["task"].cancel()
            probe.update(task=None, res=None)
        probe["idle"] = secs
        if probe["task"] is None:
            if secs >= (wd("probe_after") if got_output else wd("probe_first")):
                probe["task"] = asyncio.create_task(router.ping(model))
                run.probe = {"state": "checking", "ms": 0}
            return
        if probe["res"] is None:
            if not probe["task"].done():
                return
            probe["res"] = probe["task"].result()
            probe["res_at"] = time.monotonic()
            run.probe = {"state": probe["res"]["state"], "ms": probe["res"]["ms"]}
        res = probe["res"]
        if res["state"] == "down":
            if not await netwatch.check_now():
                raise ProviderError("network", "this computer lost its internet connection (connection lost)")
            raise ProviderError("unavailable", f"{model}: unreachable - a new request does not get through either "
                                               f"({res['error'][:160]})")
        if res["state"] == "sick":
            raise ProviderError("server", f"{model}: the provider answers a new request with a server error "
                                          f"({res['error'][:160]}); this stream will not come back")
        # The model is still working only if the provider is slow too, or it sends this request's tool call whole at
        # the end (then silence is normal while it writes). A provider that answers at once while every part of this
        # stream would arrive live has lost the stream: continue where it stopped instead of waiting 300 s.
        streams_all = not opts.get("tools") or router.streams_tool_args(model)
        if keepalive is not None and keepalive < 30:
            # The server keeps sending keep-alives on THIS connection: the request is open and queued / generating
            # on its side, so it is not lost (cutting it only made the model start over).
            return
        # A live stream's own pace decides: EVREN sends a file's arguments in batches 5-12 s apart and pauses longer
        # under load; 4 x the longest gap (48 s) cut healthy streams, and every retry re-read the whole prompt.
        pcut = wd("probe_cut")
        cut = max(pcut, min(240.0, probe["gap"] * 8)) if got_output else max(pcut, PROBE_CUT_FIRST)
        if got_output and probe.get("kind") == "thinking":
            # Reasoning arrives token by token: a thought frozen mid-sentence for a minute while a new request is
            # answered has lost its stream (90 s of a frozen half sentence looked like a crashed app).
            cut = max(min(60.0, pcut), min(120.0, probe.get("tgap", 0.0) * 6))
        elif got_output and probe.get("kind") == "text":
            # The final answer: EVREN pauses 45 s+ in the middle of an answer and then goes on (a 45 s cut showed
            # "the stream stopped, continuing" twice on one answer). Its own pace x 6, at least PROBE_CUT (90 s).
            cut = max(pcut, min(150.0, probe.get("tgap", 0.0) * 6))
        # A provider that sends a tool call whole may be silent while it writes one: it gets 3 x longer (at most
        # 90 s, not the 300 s stream timeout) before the lost stream is continued.
        if res["state"] == "alive" and secs >= (cut if streams_all else min(cut * 3, 240)):
            if time.monotonic() - probe.get("res_at", 0) > 15:
                # The "alive" answer is older than this silence's end: ask again right before cutting, so a provider
                # that just became slow (busy, still generating for us) is not taken for a lost stream.
                probe.update(task=asyncio.create_task(router.ping(model)), res=None)
                run.probe = {"state": "checking", "ms": 0}
                return
            run.stalls += 1
            raise ProviderError("stalled", f"{model}: this stream sent nothing for {secs} s while the provider "
                                           f"answered a new request in {res['ms'] / 1000:.1f} s - the stream was lost "
                                           "(connection check); continuing where it stopped")

    loop_check = [0]
    local_name = model.partition(":")[2] if router.is_local(model) else ""
    stream = router.stream_chat(model, messages, opts, cancel=run.cancel,
                                on_fallback=lambda m: _step(run, "fallback", m, detail="cloud fallback"))
    try:
        async for evt in stream:
            t = evt["type"]
            if local_name and memguard.pressure(local_name):
                # RAM (or VRAM) is critically low: this request stops here, what was written is kept, and the task
                # goes on in a smaller window (see the 'memory' branch in execute). The model stays loaded.
                raise ProviderError("memory", "free memory is critically low; the task continues in a smaller window")
            if t == "idle":
                if (got_output and evt["seconds"] >= CAP_QUIET and (cap := router.request_cap(model))
                        and probe["last"] - t_req >= cap * 0.9):
                    # This provider ends every request after ~cap s (measured on earlier requests) and this one has
                    # reached it: the stream will not come back. Continued at once instead of after 90 s of silence.
                    run.stalls += 1
                    raise ProviderError("stalled", f"{model}: the provider ends a request after about {int(cap)} s "
                                                   f"(measured) and this one reached it; continuing where it stopped")
                if evt["seconds"] >= 6 and not router.is_local(model) and not netwatch.is_online():
                    # The background watcher saw this computer go offline: a stream that went silent will not come
                    # back (it used to hang until the stall limit or the general timeout). What was written is kept;
                    # the task waits for the connection and continues on the same model (see execute).
                    raise ProviderError("network", "this computer lost its internet connection (connection lost)")
                await _liveness(evt["seconds"], evt.get("keepalive"))
                # Silence: either the prompt is still being processed, or the model is writing a tool call
                # (local servers stream nothing for those). Show it live instead of a frozen "thinking".
                # Once the answer started, a pause shorter than this stream's own rhythm is not news: closing the
                # live reasoning after 4 s cut it mid-sentence on screen, and "no data, it may be busy" showed on
                # every normal 5-12 s batch gap.
                quiet = 4 if not got_output else max(15, min(45, int(probe["gap"] * 2)))
                if evt["seconds"] >= quiet:
                    end_thinking()
                    streaming_args = bool(run.partial_args) and _call_open(run)
                    if streaming_args:
                        last = run.partial_args[max(run.partial_args)]
                        prepare(last.get("name"), out["tool"], seconds=evt["seconds"], force=True)
                    else:
                        prepare("tool" if got_output else "model", seconds=evt["seconds"], force=True)
                if (got_output and evt["seconds"] >= wd("silent_tool_limit") and opts.get("tools") and not _call_open(run)
                        and not router.is_local(model) and not router.streams_tool_args(model)):
                    # A cloud provider that sends a tool call only when it is complete. The turn is NOT cut here any
                    # more: cutting it threw away the call that was being generated (minutes of work), the retry
                    # thought everything through again, and the user saw "timeout, then it starts writing". The
                    # generation goes on (the stream timeout in Settings > Agent still catches a real hang); once
                    # this call arrives whole, the next turns use the streamed text protocol (see whole_calls), and
                    # if the provider does drop, the switch happens at the retry (silent_writer).
                    run.silent_writer = True
                ka = evt.get("keepalive")
                if (got_output and evt["seconds"] >= wd("midcall_stall") and (_call_open(run) or run.partial_tag)
                        and not router.is_local(model) and not (ka is not None and ka < 30)):
                    # The file was streaming and the provider stopped in the middle of it (evren/deepseek waited
                    # 300 s for the general timeout). What was written is kept and the model continues from there.
                    run.stalls += 1
                    # (The protocol is not switched here: the arguments were streaming, so this provider streams
                    # tool calls; a pause mid-way is on its side and the text protocol pauses the same way. Switching
                    # rebuilt the whole prompt and made the model re-read and re-plan everything.)
                    raise ProviderError("stalled", f"the provider stopped for {int(evt['seconds'])} s in the middle "
                                                   "of a file; the written part is kept and continued")
                continue
            if got_output:  # the stream's own pace: its longest pause between real events so far
                _now = time.monotonic()
                if t in ("thinking", "text") and probe.get("kind") in ("thinking", "text"):
                    probe["tgap"] = max(probe.get("tgap", 0.0), _now - probe["last"])  # pace of plain tokens
                probe["gap"] = max(probe["gap"], _now - probe["last"])
                probe["last"] = _now
            else:
                probe["last"] = time.monotonic()
            if t in ("thinking", "text"):
                probe["kind"] = t
            elif t in ("tool_call_start", "tool_call_progress", "tool_call"):
                probe["kind"] = "tool"
            if probe["task"] is not None:  # data came: the silence is over
                if not probe["task"].done():
                    probe["task"].cancel()
                probe.update(task=None, res=None, idle=0)
                run.probe = None
            if not got_output and t in ("thinking", "text", "tool_call", "tool_call_start"):
                now = time.monotonic()
                turn["wait_ms"] = (now - t_req) * 1000
                if run.perf["first_ms"] is None:
                    run.perf["first_ms"] = (now - run.t0) * 1000
            got_output = got_output or t in ("thinking", "text", "tool_call", "tool_call_start")
            if t in ("thinking", "text"):
                gen["chars"] += len(evt.get("text") or "")
                gen["t1"] = gen["t1"] or time.monotonic()
            elif t in ("tool_call_start", "tool_call_progress"):
                gen["chars"] += len(evt.get("delta") or "")
                gen["streamed"] = gen.get("streamed") or bool(evt.get("delta"))
                gen["t1"] = gen["t1"] or time.monotonic()
            elif t == "tool_call" and not gen.get("streamed"):
                # A provider that sends the call whole at the end (EVREN): its arguments are output too, or the speed
                # of a turn that only wrote a file showed nothing (or only the speed of its few words of text).
                gen["chars"] += len(json.dumps(evt.get("arguments") or {}, ensure_ascii=False))
                gen["t1"] = gen["t1"] or turn.get("t_first") or time.monotonic()
            if t == "thinking_blocks":
                run.thinking_blocks = evt["blocks"]
            elif t == "truncated":
                # A text-protocol file cut by the output limit counts as a cut tool call (its written part is kept)
                run.truncated = evt if evt.get("name") or not run.partial_tag else {**evt, "name": "write_file"}
            elif t == "thinking":
                out["native_think"].append(evt["text"])
                handle("thinking", evt["text"])
                grow()
            elif t == "tool_call":
                calls.append(evt)
            elif t in ("tool_call_start", "tool_call_progress"):
                if evt.get("delta"):  # the call's arguments as they stream in: kept, so a dropped connection loses nothing
                    if t == "tool_call_progress":  # a second piece of the same call: this provider streams calls
                        router.mark_streams_tool_args(model)
                    slot = run.partial_args.setdefault(evt.get("index", 0), {"name": evt.get("name"), "args": []})
                    slot["name"] = evt.get("name") or slot["name"]
                    slot["args"].append(evt["delta"])
                    _persist_partial(run)
                    _file_loop_check(run, loop_check)
                out["tool"] = max(out["tool"], evt.get("chars") or 0)
                grow()
                end_thinking()
                narration = "".join(visible).strip()
                if narration and not run.noted:  # the text is a step note, not the answer: move it now
                    run.noted = True
                    run.hold = False
                    _emit(run, "reset_text")
                    _step(run, "note", run.role, "done", narration)
                prepare(evt.get("name"), evt.get("chars", 0))
            elif t == "usage" and (evt.get("input") or evt.get("output")):
                if evt.get("input"):  # the provider's own prompt count replaces the estimate
                    # Tokenizers differ by about +-40%; a much smaller count is a cached prompt (only new tokens
                    # evaluated, e.g. Ollama), which says nothing about the size: keep the scaled estimate then.
                    # Ollama ("partial") counts only the part it did not reuse from its cache: such a count is a
                    # lower bound. The real ratio is then the largest one seen (a cached count can only be smaller),
                    # and a count below it is a cache hit, sized with that ratio.
                    r = evt["input"] / run.prompt_est if run.prompt_est else 1.0
                    known = CTX_RATIO.get(model)
                    cached = run.prompt_est > 500 and (r < 0.55 or (evt.get("partial") and known and r < known * 0.95))
                    if cached:
                        run.session["usage_input"] = base = int(run.prompt_est * (known or 1.0))
                    else:
                        run.session["usage_input"] = base = evt["input"]
                        LAST_REAL[run.session["id"]] = (model, evt["input"])
                        run.anchor = (model, run.prompt_est, evt["input"])
                        if run.prompt_est > 500 and r <= 1.6 and not (evt.get("partial") and known and r < known):
                            _learn_ratio(model, r)
                if evt.get("output"):  # final count: no more estimates for this turn
                    out["real"] = True
                    gen["out"] = evt["output"]
                output = evt.get("output") or 0
                # Reasoning is not sent again, so it is not part of the next request: left out (reported by the
                # provider, else the streamed thinking in this model's units).
                think_tok = evt.get("reasoning") or int(tokens.count("".join(out["native_think"]) + "".join(thinking))
                                                        * CTX_RATIO.get(model, 1.0))
                if output:
                    output -= think_tok
                used = (run.session.get("usage_input") or 0) + max(0, output)
                run.session["context_used"] = used; run.ctx_peak = max(run.ctx_peak, used)
                _emit(run, "context", used=used)
            elif t == "text":
                raw.append(evt["text"])
                grow()
                for kind, text in splitter.feed(evt["text"]):
                    handle(kind, text)
                # A model stuck in a loop writes the same paragraph again and again (dozens of times, minutes of
                # tokens): checked every ~800 new characters; the stream is ended and the repeats are removed.
                size = sum(map(len, visible)) + sum(map(len, thinking))
                if size - loop_check[0] > 800:
                    loop_check[0] = size
                    looped = False
                    for part in (visible, thinking):
                        cut = _loop_cut("".join(part))
                        if cut is not None:
                            looped = True
                            part[:] = [cut]
                            if part is visible:
                                _emit(run, "reset_text")
                                _emit(run, "delta", text=cut)
                    if looped:
                        run.file_loops += 1  # the next request goes with a repeat penalty (see the request options)
                        lang_ = opts.get("lang") or load_settings().get("language") or "en"
                        if opts.get("tools") and not tags and not calls and run.file_loops <= 4:
                            # In a task the loop is not the end of the work: ending the answer there made the app ask
                            # for the open to-dos, and the model, confused, closed them or looped again. The repeats
                            # are gone; the request is redone like a pause - the sound reasoning is carried over,
                            # the written part of the answer is kept, and the next request has a repeat penalty.
                            _step(run, "note", "loop", "done", ui_text(
                                lang_, "ai_note_loop_retry", "The model began repeating itself; the repeats were "
                                "removed and it continues from its last sound point (with a repeat penalty)."))
                            raise ProviderError("looping", "the model's output turned into a repetition / word salad; "
                                                           "the repeats were removed and it continues from before them")
                        _step(run, "note", "loop", "done", ui_text(
                            lang_, "ai_note_loop",
                            "The model began repeating the same text; the repeats were removed and its answer was "
                            "ended there."))
                        break  # ends the stream (the request is closed)
                if splitter.open and splitter.open[0] not in THINK_OPENERS:
                    # The model has stopped reasoning and writes a call (a file streaming in the text protocol): the
                    # live thought closes now. It stayed "thinking" for the whole 5-minute file before, and its time
                    # then counted the file writing as thinking.
                    end_thinking()
                    m = PREP_NAME.search(splitter.buf[:600])  # the tool name is at the start: not the whole file every chunk
                    prepare(next((g for g in m.groups() if g), None) if m else None, len(splitter.buf))
                    run.partial_tag = splitter.buf  # a tag call being written (text protocol): kept for a drop
                    _persist_partial(run)
                    _file_loop_check(run, loop_check)
        if calls and not run.partial_args and not router.is_local(model):
            # The provider sent a big tool call (a whole file) only when it was complete: every such call is minutes
            # of silence that a dropped connection throws away. Learned at once, not after the next 75 s stall.
            size = max(len(json.dumps(c.get("arguments") or {}, ensure_ascii=False)) for c in calls)
            if size > 1500:
                run.whole_calls = True
        if not (run.truncated and run.truncated.get("name")):
            if run.partial_args or run.partial_tag:  # the call arrived complete: nothing to recover
                _drop_partial_file(run.session["id"])
            run.partial_tag = ""
            run.partial_args = {}
        # (an output limit cut the call: its streamed part stays for _salvage, which keeps the written file)
        for kind, text in splitter.flush():
            handle(kind, text)
        if not tags and not calls and (out["native_think"] or thinking) and not "".join(visible).strip():
            # Some models (GLM on Cloudflare) write the tool call into the reasoning channel and send nothing
            # else: take the call from there instead of ending the turn with an empty reply. Also inside a <think>
            # block of the text (EVREN / NVIDIA in the text protocol: "my last replies were empty", eight times).
            inner = StreamSplitter(TOOL_NAMES)
            found = [x for k, x in inner.feed("".join(out["native_think"]) or "".join(thinking)) + inner.flush()
                     if k == "tool"]
            tags.extend(b for b in found if parse_tool(b, TOOL_NAMES))
            if found and think_id:  # the shown reasoning keeps its words, not the raw call syntax
                shown = "".join(thinking)
                for b in found:
                    shown = shown.replace(b, "")
                _step(run, "thinking", "thinking", "done", shown.strip()[-30000:], step_id=think_id,
                      data={"tps": turn.get("tps") or tps_now()})
    except ProviderError as e:
        # A long stream that broke off (silence cut, connection closed): how long it had streamed is noted, so a
        # provider that ends every request after a fixed time is recognised (see router.request_cap).
        if e.code in ("stalled", "unavailable", "server", "timeout") and got_output and gen["chars"] > 8000:
            router.note_request_break(model, probe["last"] - t_req)
        raise
    finally:  # never leave a spinning step behind, also when the turn fails or is cancelled
        if probe["task"] is not None and not probe["task"].done():
            probe["task"].cancel()
        run.probe = None
        try:
            await stream.aclose()  # a stream left early (loop guard) closes its request and frees its slot now
        except Exception:
            pass
        turn["total_ms"] = (time.monotonic() - t_req) * 1000
        if turn["wait_ms"] is None:
            turn["wait_ms"] = turn["total_ms"]
        if gen["t1"]:
            gen_s = max(0.001, time.monotonic() - gen["t1"])
            out_tok = gen["out"] or int(gen["chars"] / 3.5)
            if out_tok >= 8 and gen_s >= 0.3:
                turn["out_tokens"], turn["gen_ms"] = out_tok, gen_s * 1000
                turn["tps"] = round(out_tok / gen_s, 2)
                run.tps = turn["tps"]
        elif got_output:
            _learn_speed(model, turn["wait_ms"], int(run.prompt_est * CTX_RATIO.get(model, 1.0)))
        run.perf["turns"].append(turn)
        if prep_id:  # the real tool steps replace the placeholder
            run.steps = [s for s in run.steps if s["id"] != prep_id]
            _emit(run, "step_remove", step_id=prep_id)
        end_thinking()
        # Kept for a retry if this turn broke off (see _carry_thinking): the plan is not thought out a second time.
        run.last_thinking = "".join(thinking)
        run.think_secs = (think_span[1] - think_span[0]) if think_span[0] else 0.0
    return "".join(raw), tags, calls


# A busy or briefly failing provider (HTTP 503/429/5xx, timeouts) is retried with growing waits instead of
# ending a long task; quota/auth errors are not transient and end the run at once.
TRANSIENT = {"overloaded", "rate_limit", "server", "bad_gateway", "timeout", "network", "unavailable", "stalled",
             "looping"}


# Seconds a cloud provider may stay silent while it writes a native tool call before the turn is redone with the
# streamed text protocol (Settings > Agent > stream timeout still applies to everything else).
SILENT_TOOL_LIMIT = 75


THINK_CAP = 48000  # characters of reasoning in one turn with no action before it is cut and acted on (twice per task)


MIDCALL_STALL = 150  # a file that was streaming and stopped this long mid-way: salvaged and continued (EVREN pauses 60 s+ under load)
CAP_QUIET = 12  # silence (s) that ends a stream which reached its provider's measured request time limit

# Connection check of a silent cloud stream (router.ping): probe after this much silence, and if the provider answers
# a new request at once while this stream (which would arrive live) stays silent, continue where it stopped after
# PROBE_CUT s (at least 4 x the stream's own longest pause) - not after the 300 s stream timeout.
PROBE_AFTER = int(__import__("os").environ.get("AIIQ_PROBE_AFTER") or 30)  # silence once the answer started (s)
PROBE_FIRST = 45  # before the first token (the provider may still be reading a long prompt)
PROBE_CUT = int(__import__("os").environ.get("AIIQ_PROBE_CUT") or 90)
PROBE_CUT_FIRST = 90

# The defaults above; Settings > Agent > model connection overrides them (an AIIQ_PROBE_* variable wins, for tests).
_WD = {"silent_tool_limit": ("SILENT_TOOL_LIMIT", 20), "midcall_stall": ("MIDCALL_STALL", 30),
       "probe_after": ("PROBE_AFTER", 5), "probe_first": ("PROBE_FIRST", 10), "probe_cut": ("PROBE_CUT", 10)}


def wd(key: str) -> float:
    """A silence watchdog in seconds: the setting (agent.<key>), else the module default."""
    name, floor = _WD[key]
    default = float(globals()[name])
    env = {"probe_after": "AIIQ_PROBE_AFTER", "probe_cut": "AIIQ_PROBE_CUT"}.get(key)
    if env and __import__("os").environ.get(env):
        return default
    try:
        from ..config import load_settings
        v = (load_settings().get("agent") or {}).get(key)
        return max(float(floor), float(v)) if v not in (None, "", 0) else default
    except Exception:  # noqa: BLE001 - a broken setting never stops a stream
        return default


def _mid_sentence(text: str) -> bool:
    """The reasoning stopped in the middle of a sentence (no closing punctuation): it did not finish, it stalled."""
    tail = text.rstrip()[-1:] if text.strip() else "."
    return tail not in ".!?:;)]}\"'`*>" and not text.rstrip().endswith("```")


PATH_IN_ARGS = re.compile(r'"(?:path|file|filename|output)"\s*:\s*"([^"]{1,200})"|\b(?:path|file)="([^"]{1,200})"')


def _partial_target(run: "Run") -> str:
    """The file a tool call being written is about (from its streamed arguments or tag), for the live step."""
    src = run.partial_tag or ("".join(run.partial_args[max(run.partial_args)]["args"]) if run.partial_args else "")
    # Usually at the start; a model may also write the content first and the path last (then it shows once it came).
    m = PATH_IN_ARGS.search(src[:2000]) or PATH_IN_ARGS.search(src[-600:])
    return (m.group(1) or m.group(2)) if m else ""


def _call_open(run: "Run") -> bool:
    """A streamed tool call is still being written (its arguments are not complete JSON yet). A call that already
    arrived whole in this turn (a short todo before a big write_file) does not count: the silence after it is the
    next call being written silently, and the stall guard must still work."""
    if not run.partial_args:
        return False
    last = run.partial_args[max(run.partial_args)]
    try:
        json.loads("".join(last["args"]) or "x")
        return False
    except ValueError:
        return True
