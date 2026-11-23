"""Agent run loop. The default role is a natural assistant; @agent mentions and /skill mentions shape it.
Tools are called with the provider's native function calling when the model supports it, otherwise with a
text tag protocol. Failed commands switch the next turn to the debugger role. Progress is published as run
events so the chat shows a collapsible activity trace."""
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
from . import ledger
from ..tools import undo
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
from .checks import plan_steps, request_steps, request_parts, error_playbook, NOT_FOUND, LANG_NAMES, SCRIPTS, TR_CHARS, TR_WORDS, EN_WORDS, _CJK, _load_intents, INTENTS, intent_alt, _extend, _lang_rx, LANG_WORD_RX, _lang_counts, reply_language, SMALL_TALK, ACTION, WORK, QUESTION, CORE_TOOLS, WEB_WORDS, GROUP_TOOLS, GROUPED, GROUP_WORDS, tool_groups, STRONG_BROWSER, BROWSER_WORDS, CODE_NOT_RUN, HOWTO, SHELL_FENCES, FENCE, CMD_START, fenced_commands, is_small_talk, FILE_NAME, _unread_files, CURRENT_INFO, needs_research, is_knowledge_question, ANNOUNCE, PROMISE, VISUAL_ASK, is_promise, is_announcement, FILE_CLAIM, ACTION_ECHO, CHANGE_REQUEST, CHANGE_CLAIM, FILE_EDIT_ASK, FILE_REF, DELIVER_VERB, DELIVERABLES, CLAIMED_FILE, _shown_files, tool_hint, missing_deliverables, fix_claimed_names, FOREIGN_SCRIPT, TRANSLATE_HINT, LATIN_LANGS, CONTINUE_WORDS, wrong_language, _LANG_FILES, ui_text, think_reply_reminder, language_rule  # noqa: F401
# Parts split into their own modules (round 2026-11-20); the names stay available here.
from .learning import CTX_RATIO, LAST_REAL, _RATIO_FILE, _ratio_file, _learn_ratio, _BACKGROUND, SPEED, SLOW_MS_PER_1K, _SPEED_FILE, _speed_file, _learn_speed, is_slow, lean_for, _shown_tokens  # noqa: F401
from .runstate import Run, PERF, _timing, RUNS, _emit, _step, TOOL_TITLES, ACTION_KINDS  # noqa: F401
from .guards import PAGE_TOOLS, PAGE_ERR, page_state, output_checked, failed_outputs, failure_signature, _UNIT, _loop_cut, _babble_cut, _SALAD_WORD, _salad_cut  # noqa: F401
from .history import OLD_STEP_MARK, KEEP_RECENT, _short, _gone_body, READ_TOOLS, CHANGE_TOOLS, _RESULT_BLOCK, _READ_HEAD, _TAG_CALL, _pkey, _kept_reads, shrink_old_steps, _tag_call, _for_model, estimate_tokens, SHRUNK, shrink_messages, COMPRESS_PROMPT, compress, context_breakdown, OVERFLOW_DIGEST, DIGEST_TAG, _overflow, _history, _action, _action_log  # noqa: F401
from .continuity import without_todo_line  # noqa: E402
from .checks import OWN_DATA, GOOGLE_ACT, asks_for, printed_code, admits_failure  # noqa: E402  (not in checks' star export)
from .continuity import cap_chars, RUN_STATE, RESUME_TAG, _calls_done, _team_board, _checkpoint, _results_kept, PARTIAL, WRITERS, _file_loop_check, _partial_call, _persist_partial, save_partial, _salvage, _drop_partial_file, RECORD_TAG, CONTINUE_TAG, THINK_CARRY, CARRY_MAX, _carry_thinking, LOOK_TOOLS, _ledger, _load_checkpoint, _drop_checkpoint, resume_note, recover_interrupted, HANDOVER, _handover, SPLIT_HINT_HEAD, _split_rule, split_hint, todo_board, todo_line, _short_desc, EVIDENCE_TOOLS  # noqa: F401
from .prompting import BROWSER_GUIDE, TEAM_GUIDE, ABILITIES, ABILITY_TASKS, _abilities_load, _abilities_open, _abilities_save, _system_prompt, _parse_mentions  # noqa: F401
from .streaming import TOOL_NAMES, PREP_NAME, _stream_turn, TRANSIENT, SILENT_TOOL_LIMIT, THINK_CAP, MIDCALL_STALL, PATH_IN_ARGS, _partial_target, _call_open  # noqa: F401
from .tooling import VERIFY_ASK, VERIFY_TOOLS, TEST_CMD, REPEAT_GUARD, _verified, _served, PLAN_GATED, MEDIA_CAP, BOOKKEEPING, STUCK_WARN, PARALLEL_SAFE, TODO_DOC, TODO_RUN, TODO_START, TODO_FILE, _auto_todo, PARALLEL_WRITE, _job_path, _run_jobs, _exec, _merge_team_calls, _run_tool, _wait_online, RUN_ASK, MD_WORDS, OPENS_URL, _close_visible_browser, _readable  # noqa: F401


RETRY_WAITS = (5, 15, 30, 60, 90, 120)
SKILL_BASE = {"todo", "use_skill", "need_tools", "read_file", "list_dir", "write_file", "edit_file", "run",
              "system_info"}


BUDGET_NOTE = {"tr": "Adım sınırına ulaşıldı ({n} adım) ve görev henüz bitmedi. Kaldığı yerden sürdürmek için "
                     "\"devam et\" yazın; sınırı Ayarlar > Ajan bölümünden artırabilirsiniz.",
               "en": "The step limit was reached ({n} steps) before the task finished. Type \"continue\" to resume "
                     "where it stopped; the limit can be raised in Settings > Agent."}
# Trace notes the app writes itself follow the reply language like everything else the user sees.
NOTES = {
    "no_native": {"tr": "Model yerel araç çağrısını desteklemiyor; metin protokolüne geçildi: {e}",
                  "en": "Native tool calling not supported; switched to the text protocol: {e}"},
    "leak": {"tr": "Çalıştırılmamış araç sözdizimi gizlendi; modelden çağrıyı doğru biçimde yinelemesi istendi.",
             "en": "Unparsed tool syntax was hidden; the model was asked to retry the call."},
    "open_todos": {"tr": "Model yanıtı yazdı ama planlanan {n} madde hâlâ açık; kalanları tamamlaması isteniyor.",
                   "en": "The model wrote its answer while {n} planned items are still open; it is asked to finish them."},
    "unresolved": {"tr": "Son komut başarısız oldu ama model bitti diyordu; önce düzeltmesi isteniyor.",
                   "en": "The last command failed but the model was finishing; it is asked to fix it first."},
    "unresolved_final": {"tr": "⚠️ Son komut hâlâ başarısız: bu cevaptaki ilgili adım tamamlanmamış olabilir.",
                         "en": "⚠️ The last command still fails: the related step in this answer may not be done."},
    "code_run": {"tr": "Model komutu çalıştırmak yerine kod bloğu olarak yazdı; komut şimdi gerçekten çalıştırılıyor.",
                 "en": "The model wrote the command as a code block instead of running it; it is being run for real now."},
    "code_not_run": {"tr": "Bir komut yazılmış ama çalıştırılmamıştı; gerçek araçlarla yeniden yapılıyor.",
                     "en": "A command was written but not executed; redoing it with the real tools."},
    "not_delivered": {"tr": "Cevap bir dosyadan bitmiş gibi söz ediyor ama diskte yok ({files}); modelden gerçekten oluşturması isteniyor.",
                      "en": "The answer presents a file that is not on disk ({files}); the model is asked to really create it."},
    "not_delivered_final": {"tr": "⚠️ Bu dosya oluşturulmadı, diskte yok: {files}. Aşağıdaki cevapta hazır deniyorsa doğru değil.",
                            "en": "⚠️ This file was not created and is not on disk: {files}. If the answer below says it is ready, that is not true."},
}
PROGRESS_TAG = "[Progress so far in this task (earlier steps summarized to save context)]"


def _same_as_before(text: str, history: list[dict]) -> bool:
    """The reply is (nearly) the previous assistant answer of this chat."""
    import difflib
    prev = next((m.get("content") for m in reversed(history) if m.get("role") == "assistant"
                 and isinstance(m.get("content"), str) and len(m.get("content")) > 120), "")
    if not prev:
        return False
    a, b = re.sub(r"\s+", " ", text).strip()[:3000], re.sub(r"\s+", " ", prev).strip()[:3000]
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    return sm.quick_ratio() > 0.9 and sm.ratio() > 0.8


# A tool a skill / agent lists brings the tools it is used together with.
SKILL_COMPANIONS = {"make_doc": {"doc_template", "read_document"}, "doc_template": {"read_document", "inspect_media"}, "write_file": {"edit_file"},
                    "read_file": {"read_document"}}


async def _summarize_progress(run: Run, model: str, messages: list[dict], first: int, opts: dict,
                              system: dict, est: int) -> int:
    """Still too large after trimming: the older steps of the running task become one summary message
    (the latest steps stay verbatim). Returns the new estimate."""
    keep = 4
    old = messages[first:len(messages) - keep]
    if len(old) < 3:
        return est
    sid = _step(run, "compress", "context", "running")
    task = (messages[first - 1].get("content") or "")[:3000] if first else ""
    lines = [f"TASK: {task}"] if task else []
    for m in old:
        calls = "; ".join(f"{c['name']}({', '.join(f'{k}={str(v)[:80]}' for k, v in c['arguments'].items())})"
                          for c in m.get("tool_calls") or [])
        lines.append(f"{m['role'].upper()}: {(m.get('content') or '')[:1500]}" + (f"\nCALLS: {calls}" if calls else ""))
        for c in m.get("tool_calls") or []:
            a = c["arguments"] if isinstance(c["arguments"], dict) else {}
            what = a.get("path") or a.get("url") or a.get("query") or a.get("command") or a.get("name") or ""
            run.done_calls.append(f"{c['name']} {str(what)[:100]}".strip())
    try:
        with _side(run):
            summary = (await router.complete(model, [
                {"role": "system", "content": COMPRESS_PROMPT},
                {"role": "user", "content": "\n\n".join(lines)}], opts, run.cancel)).strip()
    except ProviderError:
        summary = ""
    if not summary:  # fall back to a mechanical log of the steps
        summary = "\n".join(l[:300] for l in lines)
    # Never larger than what it replaces: a fallback log (or a rambling summary) once made the context grow
    # (19.7K -> 24.9K) and the next turn summarized again, in a loop. At most a quarter of the old size, keeping the
    # task line and the latest steps.
    cap = max(3000, int(sum(len(str(m.get("content") or "")) for m in old) * 0.25))
    if len(summary) > cap:
        head = lines[0][:600] + "\n" if lines and lines[0].startswith("TASK:") and not summary.startswith("TASK:") else ""
        summary = head + "...\n" + summary[-(cap - len(head)):]
    if run.done_calls:  # the exact record of what already ran, whatever the summary says: never redo or invent steps
        summary += "\n\nTool calls already made in this task (do not repeat them):\n" + "\n".join(
            f"- {d}" for d in run.done_calls[-80:])
        # Every file this task wrote, however long ago (the call list above keeps only the latest 80): they exist on
        # disk, so a later step never thinks one is missing and writes it again - read_file / edit_file them.
        written = list(dict.fromkeys(d.split(" ", 1)[1] for d in run.done_calls
                                     if d.startswith(("write_file ", "edit_file ")) and " " in d))
        if written:
            summary += ("\n\nFiles written in this task - they EXIST on disk with the content you gave them (change "
                        "them with edit_file after read_file, never write them again from memory):\n"
                        + "\n".join(f"- {w}" for w in written[-200:]))
    if run.todos:  # where the plan stands: the summary must not send the model back to finished items
        summary += "\n\nTo-do list now: " + "; ".join(
            f"[{'x' if t['status'] == 'completed' else '>' if t['status'] == 'in_progress' else ' '}] {t['content']}"
            for t in run.todos) + "\nContinue with the first item not marked [x]."
    # Keep provider message rules valid: the kept tail must not start with an orphan tool result.
    tail = messages[len(messages) - keep:]
    while tail and tail[0]["role"] == "tool":
        tail = tail[1:]
    messages[first:] = [{"role": "user", "content": f"{PROGRESS_TAG}\n{summary}\n\nContinue the task."}] + (
        [{"role": "assistant", "content": "OK."}] if tail and tail[0]["role"] == "user" else []) + tail
    after = estimate_tokens([system] + messages)
    _step(run, "compress", "context", "done",
          json.dumps({"before": _shown_tokens(est, model), "after": _shown_tokens(after, model), "mode": "summary"}),
          step_id=sid)
    run.summarized_at = len(messages)
    return after


LANG_FIX_PROMPT = (
    "Rewrite the text below entirely in {language}. Keep its meaning, Markdown, lists, tables, links, code blocks, "
    "file names, paths, product and model names exactly; translate every word or phrase that is in another language "
    "or script. Output only the rewritten text, nothing else.")


class _side:
    """Times a side call (summary, language fix, compression) of a task."""

    def __init__(self, run: Run):
        self.run = run

    def __enter__(self):
        self.t = time.monotonic()

    def __exit__(self, *exc):
        self.run.perf["side_ms"] += (time.monotonic() - self.t) * 1000


# A code example / snippet asked for (or a lookup through an MCP tool the user picked): code in the answer is the
# answer, not a project to write to files ("C# dosya okuma" with a Microsoft Learn tool became 26 steps: files,
# dotnet, csc, a debug run).

def _ui(lang: str) -> str:
    """The language of the app's own notes in the chat: the interface language (Settings > language), not the
    language of the user's message (an English prompt in a Turkish interface showed English notes)."""
    return load_settings().get("language") or lang or "en"

CODE_EXAMPLE_ASK = re.compile(r"\b(örne[kğ]\w*|ornek\w*|example|snippet|sample|kod\s+parças|nasıl\s+okunur|"
                              r"nasıl\s+yaz)", re.I)


def _mcp_picked(text: str) -> bool:
    from .. import mcp_client
    return bool(mcp_client.picked_tools(text))


async def _fix_lines(run: Run, model: str, text: str, lang: str) -> str | None:
    """A few stray foreign-script words (a Chinese / Cyrillic word inside a Turkish answer): only the lines that hold
    them are translated, in parallel short calls; the rest of the answer stays exactly as written (rewriting the whole
    answer looked like the reply being written again from the start). None when there are too many such lines."""
    lines = text.split("\n")
    fence = False
    bad = []
    for i, ln in enumerate(lines):
        if ln.lstrip().startswith("```"):
            fence = not fence
            continue
        if not fence and FOREIGN_SCRIPT.search(re.sub(r"`[^`]*`|https?://\S+", " ", ln)):
            bad.append(i)
    if not bad or len(bad) > 6:
        return None
    sid = _step(run, "note", "language", "running", ui_text(_ui(lang), "ai_note_lang", "Fixing the reply language."))

    async def one(i: int) -> None:
        try:
            out = await asyncio.wait_for(router.complete(model, [
                {"role": "system", "content": LANG_FIX_PROMPT.format(language=LANG_NAMES.get(lang, lang))},
                {"role": "user", "content": lines[i]}], {"think": False, "temperature": 0.2}, run.cancel), 30)
        except Exception:  # noqa: BLE001  the line stays as it was
            return
        out = re.sub(r"<think>.*?</think>", "", out or "", flags=re.S).strip()
        if out and "\n" not in out and not FOREIGN_SCRIPT.search(out) and len(out) >= len(lines[i]) * 0.4:
            lead = re.match(r"\s*", lines[i]).group(0)
            lines[i] = lead + out.lstrip()

    with _side(run):
        await asyncio.gather(*(one(i) for i in bad))
    fixed = "\n".join(lines)
    good = fixed != text
    _step(run, "note", "language", "done", ui_text(_ui(lang), "ai_note_lang_done" if good else "ai_note_lang_kept",
                                                   "Words in another language were translated." if good else
                                                   "The reply language could not be fixed; the reply is kept."),
          step_id=sid)
    return fixed if good else text


async def _fix_language(run: Run, model: str, text: str, lang: str) -> str | None:
    """A finished reply with words in another language or script: one short call that sees only the reply (not
    the conversation) and rewrites it without thinking, instead of a second full turn (no second thinking, nothing
    added to the context, the answer not written twice). None when it fails or still drifts."""
    sid = _step(run, "note", "language", "running", ui_text(_ui(lang), "ai_note_lang", "Fixing the reply language."))
    out = ""
    timer = _side(run)
    timer.__enter__()
    for opts in ({"think": False, "temperature": 0.2}, {}):  # some APIs reject the thinking switch: once without it
        try:
            out = await asyncio.wait_for(router.complete(model, [
                {"role": "system", "content": LANG_FIX_PROMPT.format(language=LANG_NAMES.get(lang, lang))},
                {"role": "user", "content": text}], opts, run.cancel), 90)
            break
        except ProviderError as e:
            if e.code != "bad_request":
                break
        except asyncio.TimeoutError:
            break
    timer.__exit__()
    out = re.sub(r"<think>.*?</think>", "", out or "", flags=re.S).strip()
    good = bool(out) and len(out) >= len(text) * 0.4 and not wrong_language(out, lang)
    _step(run, "note", "language", "done", ui_text(_ui(lang), "ai_note_lang_done" if good else "ai_note_lang_kept",
                                                   "Words in another language were translated." if good else
                                                   "The reply language could not be fixed; the reply is kept."),
          step_id=sid)
    return out if good else None


OVERFLOW_SIZES = re.compile(r"\((\d+) tokens\) exceeds the available context size \((\d+) tokens\)|"
                            r"requested (\d+) tokens.*?context (?:length|window) (?:is|of) (\d+)", re.I | re.S)
# A 400 that really is about function calling (not a context overflow or another bad request).
NATIVE_REJECT = re.compile(r"\btools?\b|function[_ ]call|tool_choice|does not support", re.I)


async def _grow_local_window(run: "Run", model_id: str, info: dict, fixed: int, lang: str,
                             need: int | None = None) -> dict | None:
    """Smallest window (4K steps, at least 16K) that holds the fixed prompt, the conversation's share and a reply
    (or `need` real tokens: a conversation that no longer fits). Saved like a choice in the model picker, so later
    tasks do not reload the model at another size."""
    if not (info.get("local") and info.get("adjustable")):
        return None
    memguard.forget_steady(model_id.partition(":")[2])  # the new size is taken as asked
    conv = need is not None
    need = need or int(fixed * CTX_RATIO.get(model_id, 1.0) / 0.55) + 4096
    new = min(info["max"], max(16384, -(-need // 4096) * 4096))
    if new <= info["current"]:
        return None
    from ..config import save_settings
    save_settings({"context": {"num_ctx": {model_id: new}}})
    grown = await router.context_info(model_id)
    _step(run, "note", "context", "done", ui_text(
        lang, "ai_note_ctx_grown_conv", "The task no longer fit the context window ({old}) and there was nothing left "
        "to compress; it was raised to {new} for this model so nothing is cut off (change it in the model picker or "
        "Settings > Context).", old=f"{info['current'] // 1024}K", new=f"{new // 1024}K") if conv else ui_text(
        lang, "ai_note_ctx_grown", "The context window ({old}) could not hold the instructions and tools; it was raised "
        "to {new} for this model (change it in the model picker or Settings > Context).",
        old=f"{info['current'] // 1024}K", new=f"{new // 1024}K"))
    bus.publish("model", "context", {"model": model_id, "current": grown["current"]})
    return grown


BUSY_CODES = {"overloaded", "rate_limit", "server", "bad_gateway", "timeout", "stalled"}


def _model_listed(model_id: str) -> bool:
    pname, _, mid = model_id.partition(":")
    data = (router._MODEL_CACHE.get(pname) or (0, {}))[1]
    return any(m.get("id") == mid for m in (data.get("models") or []))


async def _busy_alternative(model: str, exclude: set[str], need_tokens: int) -> str | None:
    """Where a task goes when its cloud model is busy (503, rate limit, stalled): the fallback model of Settings >
    Models, the pool's most available model, or the provider's own router (evren:auto) - never a local model (a
    cloud task moved onto the CPU would fill the RAM). Waiting 15-30 s again and again on the same busy model was the
    slowest possible answer."""
    s = load_settings()
    # The fallback model only with the user's explicit switch (Settings > Models > cloud fallback): it used to be
    # taken here even when that switch was off.
    cands = [(s.get("fallback_model") or "") if s.get("cloud_fallback") else ""]
    if (s.get("multi_model") or {}).get("enabled"):
        alt, _ = await router.pick(None, need_tokens, exclude)
        cands.append(alt or "")
    pname = model.partition(":")[0]
    if not model.endswith(":auto"):
        cands.append(f"{pname}:auto")
    for c in cands:
        if not c or c in exclude or ":" not in c or router.is_local(c) or not router.availability(c)[0]:
            continue
        if c.endswith(":auto") and not _model_listed(c):
            continue
        return c
    return None


def _budget(info: dict) -> float:
    """Tokens a task may fill before trimming: the threshold share of the window, minus room for the reply
    (a whole file)."""
    n = info["current"]
    share = info["threshold"] if 0 < info["threshold"] < 100 else 90
    if info.get("local"):
        # A CPU reads every prompt token on every turn: a local task keeps its prompt short (trim/summarize early)
        # instead of filling the window, which made each turn slower and the KV cache (RAM) bigger.
        share = min(share, 65)
    return n * share / 100 - min(8192, n // 5)


async def execute(run: Run, user_text: str, opts: dict) -> None:
    failed: dict = {}
    _ratio_file()  # learned real-token ratios from earlier runs
    settings = load_settings()
    limits = settings["agent"]
    session = run.session
    project = workspace.get_project(session.get("project_id"))
    root = workspace.session_root(session)
    sdir = sessions.path(session["id"])
    model = opts.get("model") or settings["active_model"]
    mode = opts.get("permission_mode") or settings["permission_mode"]
    forced_role, skill_names, clean_text = _parse_mentions(user_text)
    extra_agents = [a for a in dict.fromkeys(re.findall(r"(?<!\S)@([\w-]+)", user_text))
                    if a != forced_role and a in catalog.agents()]
    ctx = ToolContext(run.id, root, mode, run.cancel, session_dir=sdir, owner=f"{session['id']}:{run.id}", project=project,
                      step=lambda kind, data: _step(run, kind, kind, "done", _readable(data), data),
                      live=lambda kind, title, status, data, step_id=None: _step(run, kind, title, status, "", data, step_id))
    run.live_ctx = ctx  # a file streaming in is written into the real file as it comes (see continuity._live_write)
    # errors earlier tasks of this chat already hit: the same one coming back is named (tooling.recurring_error)
    run.prior_errs = {f["sig"]: f.get("task") for f in ledger.load(session["id"]).get("failures") or [] if f.get("sig")}
    visible: list[str] = []
    # Images/pages that exist already are not this task's outputs (a folder walk: off the event loop, so other
    # chats keep streaming while a large project folder is scanned).
    before = await asyncio.to_thread(workspace.output_files, root)
    # The whole folder as it is now, taken in a worker thread while the model writes its first reply: at the end
    # every change shows in the review card, also those made by commands, scripts and formatters.
    from .. import changes as changes_mod
    run.folder_snap = asyncio.create_task(asyncio.to_thread(changes_mod.take, root))
    changed: dict | None = None
    best = ""  # the last real answer: kept if a later rewrite or continuation comes back empty
    status = "ok"
    lang = opts.get("ui_lang") or settings.get("language") or "en"  # set from the request below; also used in finally
    messages: list[dict] = []
    first_run_msg = 0
    clean_text = user_text
    _emit(run, "started", model=model, mode=mode)
    if opts.get("skip_user_msg"):  # a follow-up made of messages sent while the last task was finishing
        for part in opts.get("steer_parts") or [user_text]:
            _step(run, "note", "steer", "done", part)
    proc_manager.hold(f"{session['id']}:")  # this chat's servers stay up while it works again
    try:
        ctx_info = await router.context_info(model)
        if ctx_info["local"] and (ram := ctx_info.get("ram") or {}).get("short") and memguard.load_check() == "warn":
            _step(run, "note", "tools", "done", "⚠️ " + ui_text(lang, "ai_warn_no_ram", router.NO_RAM_WARN, model=model,
                  need=ram["weights_gb"], free=ram["free_gb"], total=ram["total_gb"]))
        elif ctx_info["local"] and (ram := ctx_info.get("ram") or {}).get("short"):
            # The weights alone do not fit in the free RAM: loading would swap the computer to a halt (or crash
            # it). Stop before anything is sent, and say what to do.
            raise ProviderError("no_memory", ui_text(
                lang, "ai_err_no_ram", "{model} needs about {need} GB of RAM for its weights alone, but only {free} GB "
                "is free (of {total} GB, with a safety reserve). It was not loaded, to protect the computer. Close "
                "other programs, or pick a smaller local model or a cloud model.", model=model, need=ram["weights_gb"],
                free=ram["free_gb"], total=ram["total_gb"], parallel=ram["parallel"]))
        if ctx_info["local"] and (ram := ctx_info.get("ram") or {}).get("parallel", 1) > 1 and ram["max"] < 32768:
            _step(run, "note", "context", "done", ui_text(
                lang, "ai_note_parallel_ram", "Ollama keeps {parallel} parallel slots, each with its own context "
                "memory: the window was limited to {ctx} so the computer does not run out of RAM. Set parallel "
                "requests to 1 (Settings > Providers > Ollama) for a larger window.", parallel=ram["parallel"],
                ctx=f"{ctx_info['current'] // 1024}K"))
        # Side calls (plan, summaries) carry no window of their own: the router gives every request to a local model
        # the same one, also after the task grew it or the RAM guard made it smaller.
        base_opts: dict = {}
        window = LOCAL_HISTORY if ctx_info["local"] else HISTORY_MESSAGES
        if _overflow(session["id"], run.user_msg_id, window) >= window:
            # A long chat: the messages that left the history window join the chat summary now (one call per
            # `window` messages), so nothing said earlier is ever dropped unsummarized. If the call fails, the task
            # still runs: those messages stay in the short digest _history adds.
            sid = _step(run, "compress", "context", "running")
            try:
                with _side(run):
                    res = await compress(session["id"], model, run.cancel, keep_recent=window, before_id=run.user_msg_id)
                _step(run, "compress", "context", "done", json.dumps(res), step_id=sid)
            except ProviderError as e:
                _step(run, "compress", "context", "error", str(e)[:400], step_id=sid)
        history = _history(session["id"], run.user_msg_id, window)
        limit = ctx_info["current"] * ctx_info["threshold"] / 100
        # The real size: the provider's own prompt count of the last request in this chat (usage), or the estimate
        # scaled by the ratio learned from that provider's counts; whichever is larger.
        real_now = max(estimate_tokens(history) * CTX_RATIO.get(model, 1.0) + 2500,
                       LAST_REAL.get(session["id"], ("", 0))[1] if LAST_REAL.get(session["id"], ("",))[0] == model else 0)
        if 0 < ctx_info["threshold"] < 100 and real_now > limit:
            sid = _step(run, "compress", "context", "running")
            try:
                with _side(run):
                    res = await compress(session["id"], model, run.cancel, before_id=run.user_msg_id, target=limit * 0.4)
                _step(run, "compress", "context", "done", json.dumps(res), step_id=sid)
            except ProviderError as e:
                # A summary that failed (busy provider, a model that returned nothing) no longer ends the task
                # before it starts: the in-task trimming below keeps the request inside the window.
                _step(run, "compress", "context", "error", str(e)[:400], step_id=sid)
            history = _history(session["id"], run.user_msg_id, window)

        plan = None
        if forced_role == "planner" or opts.get("plan_mode"):
            sid = _step(run, "plan", "planner", "running")
            plan = (await router.complete(router.agent_model("planner", model), [
                {"role": "system", "content": catalog.agents()["planner"]["prompt"]
                 + ("\n\n# Project files\n" + workspace.summarize_tree(root, 60) if project else "")
                 + "\n\n" + language_rule(reply_language(clean_text, opts.get("ui_lang")))},
                *history[-6:], {"role": "user", "content": clean_text}], base_opts, run.cancel)).strip()
            plan = None if not plan or "NO_PLAN" in plan else plan
            _step(run, "plan", "planner", "done", plan or "-", step_id=sid)
            if forced_role == "planner":
                visible.append(plan or "")
                _emit(run, "delta", text=plan or "")
                return

        role = forced_role or DEFAULT_ROLE
        native = router.native_tools(model, ctx_info)
        chat_only = is_small_talk(clean_text) and not skill_names and not forced_role and "#" not in clean_text
        # Plain knowledge questions in a chat without earlier work get read-only tools (no unrequested files).
        allowed = None
        from .. import connections as _conn
        google_on = _conn.google_connected()
        if chat_only:
            allowed = set()
        elif (not skill_names and not forced_role and not project and is_knowledge_question(clean_text)
              and not MD_WORDS.search(clean_text) and not GROUP_WORDS["media"].search(clean_text)
              and not sessions.state_file(session["id"]).exists()):
            # (browser_* only when the question is about acting on a site: ~1K tokens of definitions otherwise)
            # Word lists only guess: the limit is soft. need_tools stays offered, and calling it lifts the limit
            # (the model's own judgement wins over a keyword match - "neden çalışmıyor, düzelt" is work).
            allowed = (set(READ_ONLY) - (set() if BROWSER_WORDS.search(clean_text) else BROWSER_TOOLS)) | {"need_tools"}
            run.soft_gate = True
        if allowed is not None and not chat_only:
            from .. import mcp_client
            if mcp_client.picked_tools(clean_text) or mcp_client.available_tools():
                # a connected MCP server is the model's to use whenever it helps, a plain question too ("saat kaç?"
                # -> time/get_current_time, a library question -> context7 / deepwiki)
                # the user picked an MCP tool (#server/tool chip): a "question" ("saat kaç?") still gets the mcp tool
                # (it was left out with the read-only set, and the model answered without the tool it was given)
                allowed |= {"mcp", "mcp_add"}
            if google_on:
                allowed |= {"google"}  # "bu haftaki takvimim?" reads like a question but needs the account
        # A conversation reply (small talk, a plain question): the UI streams it straight into the chat as the answer
        # instead of the work-note slot under the steps (it showed there first, then jumped into the chat).
        _emit(run, "reply_mode", chat=chat_only or (allowed is not None and not allowed - set(READ_ONLY) - {"mcp", "mcp_add"}))
        # An agent or skill with a 'tools:' list gets only those tools (fewer tool definitions, fewer tokens).
        skill_limited = False
        chosen = ([catalog.agents().get(forced_role)] if forced_role else []) + [catalog.skills().get(s) for s in skill_names] \
            + [catalog.agents().get(a) for a in extra_agents]
        if limit := {t for item in chosen if item for t in item.get("tools") or [] if t in TOOLS}:
            # A listed tool brings the tools it cannot work without (the /docs skill listed make_doc but not
            # doc_template: "Template Creator" asked for doc_template action=create and the model never had it).
            for t in list(limit):
                limit |= SKILL_COMPANIONS.get(t, set())
            limit &= set(TOOLS)
            # The basic file / command tools stay with every skill: /google "make a PDF of this PC and put it on
            # Drive" needed run and list_dir, the google skill listed neither, and every call was refused.
            allowed = (set(TOOLS) if allowed is None else allowed | limit) & (limit | SKILL_BASE)
            skill_limited = True  # need_tools / a grouped call can still open what the list left out
        lang = reply_language(clean_text, opts.get("ui_lang"))
        # No skill is loaded by trigger words any more (user request, 2026-11-20): a word in the prompt ("android",
        # "docs", "test") loaded unrelated skills. Only /skill loads one by itself; otherwise the model reads the
        # skill and agent list with their purposes and picks the one that fits - or none (see _system_prompt).
        ctx.lang = lang
        ctx.goal = clean_text[:2000]
        # A short reminder on the latest turn keeps small local models from drifting into English (not stored).
        reminder = think_reply_reminder(lang)
        skill_note = "".join(f"\n[Skill /{s} invoked: do this request with that skill's instructions.]"
                             for s in skill_names)
        if forced_role and forced_role != DEFAULT_ROLE and clean_text.strip() not in ("", f"@{forced_role}"):
            # Weak models answered an agent request with a list of questions instead of doing it.
            skill_note += (f"\n[Agent @{forced_role} invoked: you ARE this agent now (see # Instructions). Deliver its "
                           "result in this task with its tools: infer sensible defaults from the request, state them "
                           "briefly, and ask a question only if the request cannot be done at all without the answer.]")
        if extra_agents:
            skill_note += ("\n[Agents invoked in order: " + ", ".join(f"@{a}" for a in [forced_role, *extra_agents])
                           + ". Do each one's part of the request in that order, following its section under "
                             "# Also invoked agents, in this same task.]")
        if opts.get("goal_mode"):
            skill_note += ("\n[Goal mode: this is a goal to reach autonomously. Keep a to-do list, work through every "
                           "item, verify the result yourself and finish only when the goal is fully achieved.]")
        skill_note += tool_hint(clean_text)
        user_msg = {"role": "user", "content": f"{clean_text}{skill_note}\n\n{reminder}"}
        if opts.get("images"):
            user_msg["images"] = opts["images"]
            vision = settings.get("vision_model") or ""
            if not router.supports_images(model) and vision and vision != model:
                # The chat model cannot see pictures: the vision model of Settings > Models describes them and the
                # description goes with the request (the pictures themselves are not sent to a model that drops them).
                sid_v = _step(run, "visual", vision, "running")
                try:
                    with _side(run):
                        seen = await asyncio.wait_for(router.complete(vision, [{"role": "user", "images": opts["images"],
                            "content": "Describe these images exactly and completely for someone who cannot see them: "
                                       "all visible text (verbatim), numbers, tables, UI elements, layout, colours and "
                                       f"anything relevant to this request: {clean_text[:600]}"}]), 120)
                    user_msg["content"] += f"\n\n[Attached image(s), described by the vision model {vision}]\n{seen.strip()}"
                    user_msg.pop("images", None)
                    _step(run, "visual", vision, "done", seen[:4000], step_id=sid_v)
                except (ProviderError, asyncio.TimeoutError) as e:
                    _step(run, "visual", vision, "error", str(e)[:400], step_id=sid_v)
            if "images" in user_msg and not router.supports_images(model):
                # No vision model (or it failed): the app looks at the pictures itself - text (OCR), colours, light,
                # sharpness, faces, EXIF - so even a text-only model knows what was attached.
                sid_v = _step(run, "visual", "local", "running")
                try:
                    from ..tools import media_inspect
                    parts = []
                    tmp_dir = sdir / "uploads"
                    tmp_dir.mkdir(parents=True, exist_ok=True)
                    for k, b64 in enumerate(user_msg["images"][:6]):
                        f = tmp_dir / f"attached-{run.id}-{k + 1}.png"
                        f.write_bytes(base64.b64decode(b64.split(",", 1)[-1]))
                        res = await media_inspect.inspect(f, root, "", clean_text[:300], lang, transcript=False)
                        parts.append(media_inspect.report(res))
                    seen = "\n\n".join(parts)
                    user_msg["content"] += ("\n\n[Attached image(s), inspected by the app (you cannot see images: use "
                                            "only these facts, never guess)]\n" + seen)
                    user_msg.pop("images", None)
                    _step(run, "visual", "local", "done", seen[:4000], step_id=sid_v)
                except Exception as e:
                    _step(run, "visual", "local", "error", str(e)[:400], step_id=sid_v)
        prior = _load_checkpoint(session["id"])
        if prior and prior.get("run_id") != run.id and prior.get("status") != "ok" and (prior.get("calls") or prior.get("files")):
            last = db.query("SELECT MAX(id) AS m FROM messages WHERE session_id=? AND role='user' AND id<?",
                            (session["id"], run.user_msg_id))
            if last and prior.get("user_msg_id") == last[0]["m"]:
                # The task right before this one stopped early (crash, power cut, provider failure, stop button):
                # its exact progress goes with this request, so a "continue" picks up where it stopped.
                user_msg["content"] = resume_note(prior) + "\n\n" + user_msg["content"]
                run.carried_calls = list(prior.get("calls") or [])[-100:]
                run.carried_results = list(prior.get("results") or [])
                run.carried_team = [c for c in prior.get("team") or [] if isinstance(c, dict)]
                ctx.team_prior = run.carried_team
                ctx.evidence |= registry_figures("\n".join(r.get("output", "") for r in run.carried_results))
                ctx.sourced = ctx.sourced or bool(run.carried_results)
                if CONTINUE_WORDS.search(clean_text) and any(t.get("status") != "completed" for t in prior.get("todos") or []):
                    run.todos = prior["todos"]
                    _emit(run, "todos", todos=run.todos)
                _step(run, "note", "resume", "done", ui_text(_ui(lang), "ai_note_resume",
                      "Continuing from the record of the interrupted task ({n} steps already done).",
                      n=len(prior.get("calls") or [])))
        messages = history + [user_msg]
        ctx.evidence |= registry_figures("\n".join(m.get("content") or "" for m in messages if isinstance(m.get("content"), str)))
        first_run_msg = len(messages)  # messages after this index belong to the current task
        # The request plus the latest earlier ones ("continue" after a map task still needs the map tools).
        recent_text = clean_text + "\n" + "\n".join(m["content"][:2000] for m in history[-4:] if m["role"] == "user")
        topics = rule_topics(recent_text)
        budget = _budget(ctx_info)
        debug_attempts, last_failure, leak_retries, lang_retry, nudges, used_tools = 0, None, 0, False, 0, False
        ran_ok, last_err_count = False, None  # progress since the last failure (see the debug cap below)
        same_rounds = 0  # the same failure in a row (each one forces a different route)
        empty_retries = 0
        round_sigs: dict[str, int] = {}  # the set of calls of each tool round -> how often it was made
        off_calls = 0  # tool calls sent after the tools were closed for this task
        net_waits = 0  # waits for this computer's internet to come back (DNS failing for every host)
        files_nudged = False  # project code printed in the answer instead of written: sent back once
        tool_turns = 0  # tool rounds so far (a big job without a to-do list is asked for one once)
        verify_nudged = False  # a run-and-test request answered without running anything was sent back once
        repeat_nudged = False  # a reply that repeated the previous answer word for word was sent back once
        source_nudged = False  # a sourced-answer agent was told once to research instead of answering from memory
        data_nudged = False  # an answer about the user's own account data written without a single tool call
        # A sourced-answer skill / agent (researcher, web-research...) - not one that merely may research (/docs lists
        # research for documents that need facts: "explain how templates work" was sent back to research, then the
        # whole answer was written again "with sources").
        needs_sources = any(item and {"research", "web_search"} & set(item.get("tools") or [])
                            and (not {"make_doc", "write_file", "edit_file", "run"} & set(item.get("tools") or [])
                                 or needs_research(clean_text))
                            for item in chosen)
        truncations = 0
        force_compact = False  # short tool definitions after a "request too large for the per-minute cap" error
        tpm_cap = 10 ** 9  # that cap (tokens per request), once a provider named it
        printed_retry = False  # code printed instead of run: asked once to really do it
        unresolved = ""  # output of the last failed command not followed by a successful one
        unresolved_asked = False  # the model was told once not to report a failed step as done
        code_runs = 0  # fenced shell commands of a tool-less reply run for the model (a weak model's "do it")
        code_nudges = 0  # "you wrote a command instead of running it" reminders (bounded: no endless loop)
        promise_retries = 0  # "I'll do it / it is being created" with no tool call
        visual_retry = False  # a chart/image was asked, the document has none: corrected once
        claim_retry = read_retry = research_retry = edit_retry = False
        degenerate = 0  # replies that turned into one repeated token (see the 'degenerate' error)
        deliver_retries = 0  # "the PDF is ready" while no PDF exists: asked twice at most to really make it
        pending_nudges = 0  # a "summary" while planned items were never started: sent back to work (bounded)
        missing_files: list[str] = []
        held_answer, held_turn = "", -1  # a complete answer an app check sent back (see keep_held)
        broken_syntax: dict[str, str] = {}  # written files that do not parse (path -> the write result's error lines)

        def track_syntax(name: str, res) -> str:
            """A file written or edited with a syntax error stays an open failure until a later write of that file
            parses: the answer must not call the task done while it is broken. Returns the new 'unresolved'."""
            path = (res.data or {}).get("path") if name in ("write_file", "edit_file") else None
            if path:
                if "SYNTAX ERROR -" in (res.output or ""):
                    broken_syntax[path] = res.output[res.output.index("SYNTAX ERROR -"):][:700]
                else:
                    broken_syntax.pop(path, None)
            cur = unresolved
            if ": SYNTAX ERROR -" in cur and cur.split(": SYNTAX ERROR -", 1)[0] not in broken_syntax:
                cur = ""  # that file was fixed
            if broken_syntax and not cur:
                p, err = next(iter(broken_syntax.items()))
                cur = f"{p}: {err}"
            return cur

        def keep_held(text: str) -> None:
            """An app check (run-and-test, sources, open items) sent a complete answer back, and the model did nothing
            with tools after it - it judged the check not to apply ("no web server was started in this conversation")
            and wrote a short note instead. That note must not replace the full answer the user was reading (a 40-line
            GitHub project list was wiped for three lines, seen with nemotron): the full answer comes back."""
            if held_answer and tool_turns == held_turn and len(text.strip()) < len(held_answer) * 0.6:
                visible[:] = [held_answer]
                _emit(run, "reset_text")
                _emit(run, "delta", text=held_answer)

        def flag_unresolved() -> None:
            """The answer ends the task while the last command still fails (or the promised file still does not
            exist): the user sees that first."""
            # A file named with other letters than on disk (the answer says alışveriş_tanitim.mp4, the tool wrote
            # alısveris_tanitim.mp4): the answer gets the real path, so its links open and no false "missing" note
            # follows (a model was told its file did not exist and then forgot it had made it).
            if (answer := "".join(visible)).strip():
                fixed = fix_claimed_names(answer, root)
                if fixed != answer:
                    visible[:] = [fixed]
            if deliver_retries >= 2 and missing_files and "".join(visible).strip():
                still = missing_deliverables(clean_text, "".join(visible), root, run.started)
                if still:
                    warning = ui_text(_ui(lang), "ai_note_not_delivered_final", NOTES["not_delivered_final"]["en"],
                                      files=_shown_files(still))
                    _step(run, "note", "tools", "done", warning)
                    visible[:] = [f"> {warning}\n\n" + "".join(visible).strip()]
                    _emit(run, "reset_text")
                    _emit(run, "delta", text=visible[0])
                    return
            if (unresolved and unresolved_asked and used_tools and "".join(visible).strip()
                    and not admits_failure("".join(visible))):
                warning = ui_text(_ui(lang), "ai_note_unresolved_final", NOTES["unresolved_final"]["en"])
                _step(run, "note", "tools", "done", warning)
                visible[:] = [f"> {warning}\n\n" + "".join(visible).strip()]
                _emit(run, "reset_text")
                _emit(run, "delta", text=visible[0])

        async def fix_language(text: str) -> None:
            """The final answer drifted into another language: fix only the reply (see _fix_language), once.
            Runs after the other checks, so a reply that is retried for another reason is not translated first."""
            nonlocal lang_retry
            if text and not lang_retry and wrong_language(text, lang, clean_text):
                lang_retry = True
                # stray foreign-script words: only their lines; a reply in another language altogether: all of it
                fixed = await _fix_lines(run, ctx.model, text, lang)
                if fixed is None:
                    fixed = await _fix_language(run, ctx.model, text, lang)
                if fixed and fixed != text:
                    visible[:] = [fixed]
                    _emit(run, "reset_text")
                    _emit(run, "delta", text=fixed)
        ctx_relief = 0  # context-window errors answered by trimming/summarizing (at most twice per task)
        fake_claims = 0  # replies that claim changes in a turn where no tool ran
        search_closed = False  # web tools closed after repeated identical calls
        retries = 0  # consecutive transient provider errors
        need_record = False  # a break happened (drop, model switch, smaller window): the app's record goes along once
        resume_text = ""  # the part of an answer written before the connection dropped (continued, not rewritten)

        def broke() -> None:
            """A turn broke off or the task moves to another model: nothing done so far is lost or done twice. The
            written part of an answer is kept and continued; the app's exact record goes with the next request."""
            nonlocal need_record, resume_text
            need_record = True
            text = "".join(visible)
            part = run.partial or {}
            if len(text.strip()) >= 300 and not part.get("chars") and "<tool" not in text[-200:]:
                if resume_text and len(messages) >= 2 and str(messages[-1].get("content") or "").startswith(CONTINUE_TAG):
                    del messages[-2:]  # the earlier, shorter part of the same answer
                resume_text = text if text[-1:].isspace() else text + " "
                messages.extend([
                    {"role": "assistant", "content": text},
                    {"role": "user", "content": f"{CONTINUE_TAG} What you wrote above is kept and already shown to the "
                     "user. Continue EXACTLY where it stopped, starting with the next word; do not repeat, summarize or "
                     "rewrite any of it."}])
                run.hold = False
            else:
                run.hold = bool(text)
            if _carry_thinking(run, messages):  # the reasoning done before the break goes along (not redone)
                _step(run, "note", "memory", "done", ui_text(
                    lang, "ai_note_thinking_kept", "The request broke off after the model had reasoned; its "
                    "reasoning ({n} characters) was kept and the model continues from it instead of thinking "
                    "everything through again.", n=len(run.carry_thinking)))
        prompts: dict = {}
        # Multi-model (cloud pool): per-agent models, automatic switch when a quota runs out, ask_model.
        multi = router.multi_settings()
        from .. import mcp_client
        if mcp_client.servers_cfg():
            try:  # connected MCP servers: started once, then reused by every chat
                # started at app start: a task waits a moment at most (a slow server joins the next task)
                await asyncio.wait_for(asyncio.shield(mcp_client.ensure()), 2)
            except asyncio.TimeoutError:
                pass
        has_mcp = bool(mcp_client.available_tools())
        infos: dict[str, tuple[dict, bool]] = {model: (ctx_info, native)}
        agent_off: set[str] = set()  # roles whose assigned model failed in this task
        switches = 0
        busy_tried: set[str] = set()  # models left because they were busy (never switched back to in this task)
        offer = allowed
        run.restricted = allowed is not None and not skill_limited  # a read-only / chat-only task: tools outside it stay closed
        work_mode = allowed is None or skill_limited  # a real task (a skill only narrows its tools): the delivery checks apply
        chat_memory = _abilities_open(_abilities_load(session["id"])) if allowed is None else {}
        run.unlocked |= set(chat_memory.get("groups") or [])  # opened earlier in this chat: open from the start
        prompt_mode = str(limits.get("prompt_mode") or "auto")

        async def model_info(m: str) -> tuple[dict, bool]:
            if m not in infos:
                i = await router.context_info(m)
                infos[m] = (i, router.native_tools(m, i))
            return infos[m]

        cool = usage_cooldown(model) if not router.is_local(model) else None
        if cool and cool.get("code") in BUSY_CODES | {"unavailable"} and not multi.get("enabled"):
            # The chosen model was busy moments ago (503 / rate limit): start on the fallback / provider router
            # instead of meeting the same overload again.
            if alt := await _busy_alternative(model, {model}, estimate_tokens(messages)):
                _step(run, "fallback", alt, detail=f"{model}: {cool.get('message') or cool.get('code')}",
                      data={"from": model, "to": alt, "reason": cool.get("code")})
                model = alt
                ctx_info, native = await model_info(model)
                base_opts, budget = {}, _budget(ctx_info)
        if multi.get("enabled") and multi.get("auto_switch", True) and not router.availability(model)[0]:
            # The chosen model is known to be out of quota: start on the most available pool model.
            alt, _ = await router.pick(None, estimate_tokens(messages), {model})
            if alt:
                _step(run, "fallback", alt, detail=f"{model}: {router.availability(model)[1]}",
                      data={"from": model, "to": alt, "reason": "quota"})
                model = alt
                ctx_info, native = await model_info(model)
                base_opts, budget = {}, _budget(ctx_info)
        # Unlimited steps (Settings > Agent): the task runs until it finishes, the user stops it or it repeats itself.
        for iteration in (itertools.count() if limits.get("unlimited_iterations") else range(limits["max_iterations"])):
            if run.cancel.is_set():
                raise asyncio.CancelledError
            run.role = role
            _emit(run, "agent", role=role, iteration=iteration)
            visible.clear()
            run.noted = False
            run.thinking_blocks = None
            run.partial = run.truncated = None
            if run.steer:
                # The user wrote while the task runs: guidance for this same task. All messages that came in are given
                # at once, clearly fenced as the user's own words, with the to-do list as the app keeps it and a clear
                # way to fold the guidance into the plan. (One bare note per message, next to an old carried plan and
                # an old list, made weak models mix both plans, babble and loop.)
                hints, run.steer[:] = list(run.steer), []
                for h in hints:
                    _step(run, "note", "steer", "done", h)
                # A reasoning plan carried over from a break belongs to the old direction: it is dropped, the new
                # guidance wins.
                run.carry_thinking, run.no_think = "", False
                messages[:] = [m for m in messages if not str(m.get("content") or "").startswith(THINK_CARRY)]
                quoted = "\n".join(f"<user_message>\n{h.strip()}\n</user_message>" for h in hints)
                board = (f"\nThe to-do list now (exact, kept by the app): {todo_board(run)}\n" if run.todos else "\n")
                note = ("[App note: the user sent this while you were working - it is the user's own words and it has "
                        f"priority over your earlier plan]\n{quoted}{board}"
                        "Decide first what it means for the plan, in one short sentence (no long reasoning):\n"
                        "- a correction or extra wish for the same task -> keep the finished work, change only what it "
                        "asks (edit_file, never rewrite finished files) and, if it adds work, todo add=[\"...\"];\n"
                        "- a new direction -> todo with the new list (finished items stay [x], items it cancels are "
                        "left out), then go on with the new first item;\n"
                        "- a question -> answer it in one or two sentences, then continue the task.\n"
                        "Never start over and never repeat finished steps. Answers you already wrote are shown to the "
                        "user as they are: build on them instead of writing them again.")
                if messages and messages[-1].get("role") == "user" and isinstance(messages[-1].get("content"), str) \
                        and messages[-1]["content"].startswith("Tool results:"):
                    messages[-1] = {**messages[-1], "content": messages[-1]["content"] + "\n\n" + note}
                else:
                    messages.append({"role": "user", "content": note})
            if need_record:
                need_record = False
                messages[:] = [m for m in messages if not str(m.get("content") or "").startswith(RECORD_TAG)]
                if record := _ledger(run):
                    at = len(messages)
                    if resume_text and at >= 2 and str(messages[-1].get("content") or "").startswith(CONTINUE_TAG):
                        at -= 2  # before the answer being continued: its continuation note stays the last message
                    messages.insert(max(at, first_run_msg), {"role": "user", "content": record})
            if resume_text:  # the kept part stays on screen; the continuation is added to it
                visible.append(resume_text)
                run.hold = False
                _emit(run, "reset_text")
                _emit(run, "delta", text=resume_text)
            _checkpoint(run, messages, first_run_msg, clean_text)  # survives a crash / power cut (see resume)
            turn_model = model if role in agent_off else router.agent_model(role, model)
            t_info, t_native = (ctx_info, native) if turn_model == model else await model_info(turn_model)
            if turn_model != model and estimate_tokens(messages) > t_info["max"] * 0.8:
                turn_model, t_info, t_native = model, ctx_info, native  # the task no longer fits that model
            ctx.model = turn_model
            pool_others = [e for e in router.pool() if e["model"] != turn_model] if multi.get("enabled") else []
            if run.gate_lifted:
                # The request looked like a plain question by its words, but the model judged that it needs real work
                # (need_tools): the word-based read-only limit is lifted for the rest of the task.
                run.gate_lifted, allowed = False, None
                prompts.clear()
                _emit(run, "reply_mode", chat=False)
            if allowed is not None and skill_limited and run.unlocked:
                # A skill's own list plus the groups the model opened itself (need_tools)
                offer = set(allowed) | set().union(*(GROUP_TOOLS[g] for g in run.unlocked if g in GROUP_TOOLS))
            if allowed is None:
                # Tools follow the conversation: the core set, plus each group the request (or the recent
                # conversation, or this task's own steps) is about. The model can open another group itself with
                # need_tools. Sending every definition with every turn crowded small models and filled the context.
                used_now = {s.get("data", {}).get("tool") for s in run.steps}
                avail = {"team": bool(pool_others and multi.get("delegate", True)), "mcp": has_mcp or bool(mcp_client.available_tools()), "project": bool(project),
                         "google": google_on}
                offer = set(CORE_TOOLS) | (set(TOOLS) - GROUPED)  # tools of no group are always there
                for g, (names, words) in tool_groups(clean_text).items():
                    if not avail.get(g, True):
                        continue
                    lean_now = lean_for(turn_model, t_info, prompt_mode)
                    # The lean prompt opens a group for the words of THIS request only (not the earlier messages'),
                    # and the 14 browser tools only when the request is about acting in a page; everything else is one
                    # need_tools call away (the capability index says so).
                    words_in = clean_text if lean_now else recent_text
                    hit = words is not None and words.search(words_in)
                    if hit and lean_now and g == "browser" and not STRONG_BROWSER.search(clean_text):
                        hit = False
                    if g == "google" and google_on:
                        # one small definition: always there while Google is connected. "ekledim, tekrar dene" has no
                        # Google word, the tool was left out and the model fell back to the failing google-* MCP calls.
                        hit = True
                    if g in run.unlocked or names & used_now or hit:
                        offer |= names
                offer &= set(TOOLS)
            if run.repeats >= 3:  # looping over the same searches/pages: answer with what was found
                if not search_closed:
                    search_closed = True
                    messages.append({"role": "user", "content": "You repeated the same searches or page reads several "
                                     "times. Searching is closed for this task: write the answer now from what you "
                                     "already found, and say what could not be verified."})
                offer = (set(TOOLS) if offer is None else set(offer)) - REPEAT_GUARD
            if run.todo_closed:  # looped on the list: not offered any more (the app keeps it)
                offer = (set(TOOLS) if offer is None else set(offer)) - {"todo"}
            if run.tools_off:  # stuck: no tools at all any more, only the answer (what was done, what blocks it)
                offer = set()
            # Built once per role and task: an unchanged prompt prefix lets local servers (Ollama, llama.cpp,
            # LM Studio) and cloud prompt caches reuse it, instead of re-reading everything after each file write.
            # Small windows (local models, 16-32K): tool definitions go out in their short form. They ride along with
            # every turn, and the full ones alone took 6-7K tokens.
            # A greeting or thanks never needs the long prompt, on any model.
            lean = chat_only or lean_for(turn_model, t_info, prompt_mode)
            compact = lean or t_info["current"] <= 32768 or force_compact
            # How much of a file one read_file call returns: ~15% of the window (12K-40K characters), so a normal
            # source file comes in one read instead of being re-read part by part.
            ctx.read_limit = max(12000, min(40000, int((t_info["current"] or 32768) * 0.6)))
            key = (role, t_native, turn_model, frozenset(offer) if offer is not None else None, topics, lean)
            if key not in prompts and (offer is None or "mcp" in offer):
                from .. import mcp_client  # an MCP tool the user picked: its server started before the prompt lists it
                for srv in dict.fromkeys(s for s, _ in mcp_client.picked_tools(clean_text) if s in mcp_client.servers_cfg()):
                    try:
                        await asyncio.wait_for(mcp_client.ensure(srv), 25)
                    except Exception:  # noqa: BLE001  shown to the model as not available
                        pass
            if key not in prompts:
                # Built in a worker thread: the project tree, code map and token counts of a large project would
                # otherwise hold up every other chat's stream for that time.
                prompts[key] = await asyncio.to_thread(_system_prompt, role, root, session["id"], project, skill_names,
                                                       plan, t_native, turn_model.partition(":")[2], lang, offer, compact,
                                                       extra_agents, topics, lean, clean_text, chat_memory)
            sys_text, sys_sizes = prompts[key]
            if (offer is None or "write_file" in offer) and (cc := cap_chars(turn_model, run.tps)):
                # Measured: this provider ends every request after ~N s. A file longer than fits is written in parts
                # from the start, instead of being cut at the limit and started over (5 minutes lost each time).
                sys_text += (f"\n\n# Request time limit of this provider\nIt ends every request after about {cc[0]} s "
                             f"(measured), about {cc[1]:,} characters at this model's speed. Write a file longer than "
                             f"that in parts: the first write_file plain, then write_file append=true for each next "
                             f"part of up to ~{cc[1]:,} characters, every part ending at a line end. Never restart a "
                             "file you are writing in parts.")
            system = {"role": "system", "content": sys_text}
            # Live context accounting before every model turn; relieve it inside long tasks. Native tool definitions
            # are part of the prompt the provider counts, so they are counted here too.
            schemas = tool_schemas(offer, compact, lean) if t_native and offer != set() else None
            tool_tok = tokens.count(json.dumps(schemas, ensure_ascii=False)) if schemas else 0
            # Files read and not changed since stay whole in the history: about a quarter of the window (in characters,
            # ~3.5 per token), at least 8K and at most 90K characters.
            shrink_old_steps(messages, first_run_msg,
                             max(8000, min(90000, int((t_info["current"] or 32768) * 3.5 * 0.25))))
            est = estimate_tokens([system] + messages) + tool_tok
            # Only the conversation can shrink; the fixed part (system prompt + tool definitions) cannot. When the fixed
            # part alone is near the budget, compressing again and again freed nothing and looped (80% -> 69% ->
            # 80%...): the budget then leaves the conversation a fair share, up to the window's hard limit.
            fixed = estimate_tokens([system]) + tool_tok
            # A local window that cannot even hold the fixed prompt plus a reply (8K with the tool rules) only fails
            # or loops: grow it once to the smallest size that works, before the request is sent.
            if t_info["local"] and fixed * CTX_RATIO.get(turn_model, 1.0) > t_info["current"] * 0.6:
                if grown := await _grow_local_window(run, turn_model, t_info, fixed, lang):
                    t_info = grown
                    infos[turn_model] = (grown, t_native)
                    if turn_model == model:
                        ctx_info = grown
                    budget = _budget(grown)
            # Limits are in the provider's real tokens; estimates are scaled by the ratio learned from the usage
            # the provider reported for this model (prompt_eval_count / usage.prompt_tokens / input_tokens), so
            # trimming and summaries follow the real context size, not our tokenizer's guess.
            # Anchored on the real count: the provider's own size of the previous request plus the change since then
            # (in this model's units), so the meter and every limit follow the provider's numbers, not a fresh guess.
            ratio = CTX_RATIO.get(turn_model, 1.0)
            anchor = run.anchor if run.anchor and run.anchor[0] == turn_model else None

            def real_of(e: int) -> int:
                return (max(int(e * ratio * 0.5), anchor[2] + int((e - anchor[1]) * ratio)) if anchor
                        else int(e * ratio))

            eff = max(0.3, real_of(est) / max(est, 1))
            reply_room = min(8192, t_info["current"] // 5)
            hard = min(t_info["current"] - reply_room, tpm_cap) / eff
            limit_now = min(max(budget / eff, fixed + budget / eff * 0.35), hard)
            if est > limit_now and shrink_messages(messages, keep_last=4):
                ctx.read_seen.clear()
                est2 = estimate_tokens([system] + messages) + tool_tok
                # Trim well below the limit (not just under it), so the next tool result does not trigger it again
                # at once: a trim on every turn with tiny gains looked like an endless compression loop.
                if est2 > limit_now * 0.75 and shrink_messages(messages, keep_last=2):
                    est2 = estimate_tokens([system] + messages) + tool_tok
                if est2 < est * 0.92:  # a step only when it really made room
                    _step(run, "compress", "context", "done",
                          json.dumps({"before": real_of(est), "after": real_of(est2), "mode": "trim"}))
                est = est2
            # A summary again only after 8 new messages (sooner when the request would not fit the window at all:
            # a local server then cuts the oldest messages itself, the user's request with them).
            due = len(messages) - max(first_run_msg, run.summarized_at) > (3 if est > hard else 8)
            if est > limit_now and due and est - fixed > limit_now * 0.2:
                ctx.read_seen.clear()
                est = await _summarize_progress(run, model, messages, first_run_msg, base_opts, system,
                                                est - tool_tok) + tool_tok
            # Still larger than a local window after trimming and summaries (one big file in a short task leaves
            # nothing to compress): the local server would silently cut the start of the prompt, the task with it.
            # Grow the window to fit instead (the model reloads once at the new size).
            if (t_info["local"] and real_of(est) > t_info["current"] - reply_room
                    and len(messages) - max(first_run_msg, run.summarized_at) > 2 and est - fixed > 2000):
                # Locally a summary comes before a bigger window: a new window size reloads the model (tens of
                # seconds on a CPU) and makes its KV cache (RAM) larger for the rest of the chat.
                ctx.read_seen.clear()
                est = await _summarize_progress(run, model, messages, first_run_msg, base_opts, system,
                                                est - tool_tok) + tool_tok
            if t_info["local"] and real_of(est) > t_info["current"] - reply_room:
                if grown := await _grow_local_window(run, turn_model, t_info, fixed, lang,
                                                     need=real_of(est) + reply_room + 2048):
                    t_info = grown
                    infos[turn_model] = (grown, t_native)
                    if turn_model == model:
                        ctx_info = grown
                    budget = _budget(grown)
            run.prompt_est = est
            run.session["context_used"] = shown = real_of(est); run.ctx_peak = max(run.ctx_peak, shown)
            _emit(run, "context", used=shown)
            t_opts = {"num_ctx": t_info["current"]} if t_info["local"] else {}
            if t_info["local"]:
                # A local server that reaches the end of its window while writing drops the oldest half of the
                # prompt (the instructions and the request with it) and keeps writing nonsense. The reply is limited
                # to the room that is really left; a cut answer or file is then continued (see 'truncated').
                room = max(2048, t_info["current"] - shown - 256)
                prof = router.profile(turn_model).get("max_tokens")
                t_opts["max_tokens"] = min(int(prof), room) if prof else room
            if degenerate or run.file_loops:  # the model looped (one token, or one block in a file): punish repeats
                t_opts.update(repeat_penalty=1.18, repeat_last_n=256, temperature=0.4)
            if run.no_think:  # right after a break: the carried reasoning is the plan (see _carry_thinking)
                t_opts["no_think"] = True
            turn_opts = {**t_opts, "tools": schemas} if schemas else t_opts
            try:
                run.session["usage_input"] = None
                raw, tag_blocks, calls = await _stream_turn(run, turn_model, [system] + _for_model(messages, turn_model, t_native),
                                                            visible, turn_opts)
                resume_text = ""  # the turn came through: the answer is whole again
                run.no_think = False  # the carried plan was acted on; later turns reason normally again
                if run.whole_calls and t_native:
                    # This turn's calls run as they are; from the next turn on the model writes with the text
                    # protocol, which streams the file live and can be continued after a drop (remembered for later
                    # tasks too).
                    run.whole_calls = False
                    router.disable_native_tools(turn_model, persist=True)
                    infos[turn_model] = (t_info, False)
                    if turn_model == model:
                        native = False
                    prompts.clear()
                    _step(run, "note", "tools", "done", ui_text(_ui(lang), "ai_note_stream_tags",
                          "This provider sends a tool call only when it is complete; switched to the text "
                          "protocol so files stream and nothing is lost if the connection drops."))
                sizes = {**sys_sizes, "tools": sys_sizes.get("tools", 0) + tool_tok}
                run.stats = context_breakdown(sizes, messages + ([{"role": "assistant", "content": raw}] if raw else []),
                                              run.session.get("usage_input"))
            except ProviderError as e:
                if e.code == "degenerate":
                    # The reply turned into one repeated token ("@@@@..."), and the server stopped it. The garbage
                    # is never shown or stored; one more try with a repeat penalty, then a clear error (asking the
                    # same thing five more times only gave the same garbage).
                    degenerate += 1
                    visible.clear()
                    _emit(run, "reset_text")
                    if degenerate <= 1:
                        _step(run, "note", "tools", "done", ui_text(_ui(lang), "ai_note_degenerate",
                              "The model's output turned into a repeated character; trying once more with a repeat penalty."))
                        continue
                    raise ProviderError("degenerate", ui_text(_ui(lang), "err_degenerate_detail",
                                        "The model keeps producing a repeated character instead of text. This usually means "
                                        "the local runtime or GPU backend is broken for this model: try another model, or "
                                        "turn the GPU option (e.g. Vulkan) off in Settings > Providers > Ollama.")) from e
                if e.code == "memory":
                    # The RAM guard asked for memory back. Nothing is unloaded and nothing is forgotten: the part of
                    # a file being written is saved, the window of this model is halved (its KV cache with it), the
                    # older steps are summarized to fit, and the same task goes on.
                    name = turn_model.partition(":")[2]
                    memguard.ack(name)
                    _salvage(run, ctx, messages)
                    run.memory_relief += 1
                    broke()
                    old_ctx = t_info["current"]
                    new_ctx = memguard.shrink(name, old_ctx) if run.memory_relief <= 3 else None
                    if new_ctx:
                        # LM Studio fixes the window at load time: the same model is loaded again at the new size
                        # (Ollama takes it with the next request). Only this model; the task waits for it.
                        await router.reload_local(turn_model, new_ctx)
                        small = await router.context_info(turn_model)
                        infos[turn_model] = (small, t_native)
                        if turn_model == model:
                            ctx_info = small
                        budget = _budget(small)
                        bus.publish("model", "context", {"model": turn_model, "current": small["current"]})
                        _step(run, "note", "memory", "done", ui_text(
                            lang, "ai_note_ram_shrunk", "Free memory ran critically low: the context window of this "
                            "model was reduced from {old} to {new} to give memory back. The model stays loaded and the "
                            "task continues; nothing of the chat is lost.", old=f"{old_ctx // 1024}K",
                            new=f"{small['current'] // 1024}K"))
                    else:
                        _step(run, "note", "memory", "done", ui_text(
                            lang, "ai_note_ram_floor", "Free memory is critically low and the context window is "
                            "already at its smallest ({ctx}). Close other programs; the task continues.",
                            ctx=f"{old_ctx // 1024}K"))
                    if run.memory_relief <= 5:
                        continue
                if t_native and not "".join(visible) and (e.code == "no_tools" or (
                        e.code == "bad_request" and NATIVE_REJECT.search(str(e)))):
                    # The model/server rejected function calling: remember it and use the tag protocol.
                    router.disable_native_tools(turn_model)
                    infos[turn_model] = (t_info, False)
                    if turn_model == model:
                        native = False
                    _step(run, "note", "tools", "done", ui_text(_ui(lang), "ai_note_no_native", NOTES["no_native"]["en"], e=e))
                    continue
                if e.code == "context_length" and not "".join(visible):
                    # The server says the real size: "request (9297 tokens) exceeds ... (8192 tokens)". It corrects
                    # the token estimate for this model, and a local window too small for the fixed prompt is grown.
                    if m := OVERFLOW_SIZES.search(str(e)):
                        real = int(m.group(1))
                        if est > 0 and real > est:
                            _learn_ratio(turn_model, min(1.6, real / est))
                    grown = await _grow_local_window(run, turn_model, t_info, fixed, lang)
                    if grown:
                        t_info = grown
                        infos[turn_model] = (grown, t_native)
                        if turn_model == model:
                            ctx_info = grown
                        budget = _budget(grown)
                        continue
                if e.code in ("context_length", "too_large") and ctx_relief < 2 and not "".join(visible):
                    # The model's real window is smaller than reported (or the request too big): trim the task's
                    # older tool traffic, then summarize it, and send again instead of ending the task.
                    ctx_relief += 1
                    est = estimate_tokens([system] + messages)
                    budget = min(budget, int(est * 0.6))
                    # A per-minute token cap smaller than the request (Groq free: "TPM: Limit 8000, Requested 11733")
                    # never passes by waiting: fit the request under it (short tool definitions, trimmed history).
                    tpm = re.search(r"Limit\s+(\d+),\s*Requested\s+(\d+)", str(e))
                    if tpm and not force_compact:
                        tpm_cap = int(int(tpm.group(1)) * 0.8)
                        budget = min(budget, tpm_cap)
                        force_compact = True
                        prompts.clear()
                    shrink_messages(messages, keep_last=2)
                    ctx.read_seen.clear()
                    est2 = estimate_tokens([system] + messages)
                    if est2 > budget and len(messages) - first_run_msg > 4:
                        est2 = await _summarize_progress(run, model, messages, first_run_msg, base_opts, system, est2)
                    if est2 < est or (tpm and ctx_relief == 1):  # the shorter tool definitions alone may be enough
                        _step(run, "compress", "context", "done",
                              json.dumps({"before": _shown_tokens(est, turn_model), "after": _shown_tokens(est2, turn_model), "mode": "trim"}))
                        continue
                # A provider that cannot be reached at all (connection refused, DNS) is not busy: two short retries,
                # and switching only to models of another provider (the same server is down for all its models).
                unreachable = e.code == "unavailable" and "unreachable" in str(e)
                max_retries = 2 if unreachable else max(1, int(limits.get("provider_retries") or len(RETRY_WAITS)))
                part = run.partial or {}
                # A long tool call was being written: its streamed size is known, or (providers that send tool
                # arguments only at the end, e.g. NVIDIA NIM) it was a long silent "preparing tool" phase.
                big_call = (part.get("chars", 0) > 4000 and part.get("name") in ("write_file", "make_doc", "edit_file", None)) \
                    or (part.get("name") in ("tool", "write_file", "make_doc", "edit_file") and part.get("seconds", 0) >= 60)
                if e.code in TRANSIENT:
                    saved = _salvage(run, ctx, messages)
                    if saved:
                        try:
                            kept = (Path(root) / saved[0]).read_text(encoding="utf-8", errors="replace")
                        except OSError:
                            kept = ""
                        # The saved part is a write of its own: the changes card counts its lines (+N) and shows the
                        # file as new, like the live counter of a file streaming in.
                        _step(run, "note", "salvage", "done", ui_text(_ui(lang), "ai_note_salvaged",
                              "The connection dropped while {path} was being written; the {n} characters already "
                              "written were saved and the model continues from there.", path=saved[0], n=saved[1]),
                              data={"tool": "write_file", "path": saved[0], "created": True,
                                    "added": kept.count("\n") + 1 if kept else 0, "removed": 0,
                                    "diff": "@@ saved part @@\n" + "\n".join("+" + x for x in kept.splitlines()[:4000])})
                        run.split_hint = True
                    if run.silent_writer and t_native:
                        # This provider sent nothing while the model wrote the call, so a long file always hits
                        # the stall limit and is lost. The text protocol streams the file as it is written.
                        router.disable_native_tools(turn_model, persist=not router.is_local(turn_model))
                        infos[turn_model] = (t_info, False)
                        if turn_model == model:
                            native = False
                        prompts.clear()
                        _step(run, "note", "tools", "done", ui_text(_ui(lang), "ai_note_stream_tags",
                              "This provider sends a tool call only when it is complete; switched to the text "
                              "protocol so files stream and nothing is lost if the connection drops."))
                if (e.code in TRANSIENT or e.code == "unavailable") and not router.is_local(turn_model) \
                        and netwatch.looks_like_network(e) and not await netwatch.check_now():
                    # This computer lost its internet (not a busy provider): no retries against the quota, no switch
                    # to another model (a handover loses the model's own train of thought), no "write it in parts"
                    # hint. The task waits as long as it takes - the user can stop it - and then goes on with the same
                    # model and the same conversation; a half-written file was saved above and is continued.
                    net_waits += 1
                    sid = _step(run, "retry", "offline", "running", str(e), data={"attempt": net_waits, "until_online": True})
                    t_wait = time.monotonic()
                    back = await netwatch.wait_online(run.cancel)
                    gone = int(time.monotonic() - t_wait)
                    run.perf["retry_ms"] = run.perf.get("retry_ms", 0.0) + gone * 1000
                    _step(run, "retry", "offline", "done", str(e),
                          data={"attempt": net_waits, "until_online": True, "seconds": gone}, step_id=sid)
                    if back:
                        broke()  # a half-written reply is kept and continued
                        retries = 0
                        _step(run, "note", "online", "done", ui_text(_ui(lang), "ai_note_back_online",
                              "The internet connection is back after {s} s; the task continues where it stopped.", s=gone))
                        continue
                    raise
                if e.code in ("timeout", "unavailable", "server", "bad_gateway") and big_call and not run.split_hint:
                    # The connection dropped while the model was writing a long tool call (a whole file or document):
                    # the same giant call would stall again. Ask for the content in parts this time; the steps done
                    # so far stay in the conversation, so nothing is redone.
                    run.split_hint = True
                    messages.append({"role": "user", "content": split_hint(run.model or "", run.tps)})
                out_of_quota = e.code in ("quota", "payment", "auth", "plan_required") or (e.code in TRANSIENT and retries >= 2)
                # A rate limit that needs a long wait (a per-minute token cap): with the pool on, a free model
                # continues at once instead of the task sitting out the window again and again.
                if e.code == "rate_limit" and multi.get("enabled") and multi.get("auto_switch", True)                         and (e.retry_at or 0) - time.time() > 8:
                    out_of_quota = True
                if out_of_quota and turn_model != model:
                    # The agent's own model is out: this role continues on the main model.
                    agent_off.add(role)
                    messages.append({"role": "user", "content": _handover(run)})
                    _step(run, "fallback", model, detail=f"{turn_model}: {e}",
                          data={"from": turn_model, "to": model, "reason": e.code})
                    retries = 0
                    continue
                if out_of_quota and multi.get("enabled") and multi.get("auto_switch", True) and switches < 3:
                    down = {x["model"] for x in router.pool()
                            if x["model"].partition(":")[0] == model.partition(":")[0]} if unreachable else set()
                    alt, why = await router.pick(None, estimate_tokens([system] + messages), {model} | down)
                    if alt:
                        # Quota/credits ran out (or the provider keeps failing): continue on the most available
                        # pool model with the same conversation, instead of ending the task.
                        switches += 1
                        retries = 0
                        broke()
                        _step(run, "fallback", alt, detail=f"{model}: {e}",
                              data={"from": model, "to": alt, "reason": e.code})
                        model = alt
                        messages.append({"role": "user", "content": _handover(run)})
                        ctx_info, native = await model_info(model)
                        base_opts, budget = {}, _budget(ctx_info)
                        prompts.clear()
                        continue
                if (e.code in ("quota", "payment", "plan_required") and switches < 3 and turn_model == model
                        and not router.is_local(turn_model)):
                    # Quota / credits ran out and no pool picked a model (or the pool is off): the task used to end
                    # here. The fallback model, the pool, or the provider's own router takes over with the same
                    # conversation; everything done and written so far is kept.
                    alt = await _busy_alternative(model, {model} | busy_tried, estimate_tokens([system] + messages))
                    if alt:
                        busy_tried.add(model)
                        switches += 1
                        retries = 0
                        broke()
                        _step(run, "fallback", alt, detail=f"{model}: {e}",
                              data={"from": model, "to": alt, "reason": e.code})
                        model = alt
                        messages.append({"role": "user", "content": _handover(run)})
                        ctx_info, native = await model_info(model)
                        base_opts, budget = {}, _budget(ctx_info)
                        prompts.clear()
                        continue
                # A stall while the model was writing a file: its part is saved and the same model continues from there
                # (it knows the file it was writing). Jumping at once to another (often smaller) model made it start the
                # file again from zero; the same model gets two more tries first.
                mid_write = big_call or bool(run.partial and run.partial.get("chars"))
                # A pause (timeout / stall) is retried on the same model twice before switching: with the reasoning
                # and the written part carried over, a retry costs seconds, while another model starts cold.
                if (e.code in BUSY_CODES and not unreachable and switches < 3 and not router.is_local(turn_model)
                        and turn_model == model and (retries >= 2 if mid_write or e.code in ("timeout", "stalled") else
                                                     (retries >= 1 or run.stalls >= 2 or (e.retry_at or 0) - time.time() > 10))):
                    # Busy twice in a row (or told to wait long): continue at once on another model instead of
                    # sitting out 15-30 s waits on the same overloaded one. The busy model rests a little
                    # (usage cooldown), so the next tasks start elsewhere too.
                    alt = await _busy_alternative(model, {model} | busy_tried, estimate_tokens([system] + messages))
                    if alt:
                        busy_tried.add(model)
                        switches += 1
                        retries = 0
                        broke()
                        _step(run, "fallback", alt, detail=f"{model}: {e}",
                              data={"from": model, "to": alt, "reason": e.code})
                        model = alt
                        messages.append({"role": "user", "content": _handover(run)})
                        ctx_info, native = await model_info(model)
                        base_opts, budget = {}, _budget(ctx_info)
                        prompts.clear()
                        continue
                if e.code in TRANSIENT and retries < max_retries:
                    wait = RETRY_WAITS[min(retries, len(RETRY_WAITS) - 1)]
                    if e.code in BUSY_CODES and retries == 0:
                        wait = min(wait, 5)  # one short retry first: a momentary 503 often passes in seconds
                    if retries == 0 and "connection lost" in str(e):
                        wait = 1  # a dropped stream (ReadError) is a network blip, not a busy server: resume at once
                    if e.code == "looping" or (e.code == "stalled" and "connection check" in str(e)):
                        wait = 1  # the app itself ended a repetition / a lost stream of a healthy provider
                    if e.retry_at:  # the provider said when: wait that long (at most 2 minutes), not less
                        wait = int(min(120, max(wait, e.retry_at - time.time() + 1)))
                    retries += 1
                    broke()  # a half-written reply is kept and continued; the app's record goes with the retry
                    sid = _step(run, "retry", e.code, "running", str(e), data={"seconds": wait, "attempt": retries})
                    t_wait = time.monotonic()
                    try:
                        await asyncio.wait_for(run.cancel.wait(), wait)
                    except asyncio.TimeoutError:
                        pass
                    run.perf["retry_ms"] = run.perf.get("retry_ms", 0.0) + (time.monotonic() - t_wait) * 1000
                    _step(run, "retry", e.code, "done", str(e), data={"seconds": wait, "attempt": retries}, step_id=sid)
                    continue
                if unreachable and net_waits < 2 and re.search(r"getaddrinfo|Name or service|nodename|No address|"
                                                               r"network is unreachable|10051|10065|ConnectError", str(e), re.I):
                    # This computer lost its internet (DNS fails for every host): the task ended after two quick retries.
                    # Wait for the connection to come back (up to 5 minutes), then go on where it stopped.
                    net_waits += 1
                    sid = _step(run, "retry", "offline", "running", str(e), data={"seconds": 300, "attempt": net_waits})
                    back = await netwatch.wait_online(run.cancel, 300)
                    _step(run, "retry", "offline", "done", str(e), data={"seconds": 300, "attempt": net_waits}, step_id=sid)
                    if back:
                        retries = 0
                        continue
                raise
            retries = 0
            if run.truncated and not run.truncated.get("name") and not calls and not tag_blocks and truncations < 3 \
                    and "".join(visible).strip():
                # A plain answer hit the output limit: keep what was written and let the model finish it.
                truncations += 1
                messages += [{"role": "assistant", "content": raw},
                             {"role": "user", "content": "[App note] Your answer was cut off by the output limit. Continue "
                              "exactly where it stopped; do not repeat what you already wrote."}]
                kept = "".join(visible)
                run.truncated = None
                try:
                    raw2, tag_blocks, calls = await _stream_turn(run, turn_model, [system] + _for_model(messages, turn_model, t_native),
                                                                 visible, turn_opts)
                except ProviderError:
                    raw2 = ""  # the first part stands; the answer is simply shorter
                del messages[-2:]
                raw = raw + raw2
                if not "".join(visible).startswith(kept):
                    visible.insert(0, kept)
            if run.truncated and run.truncated.get("name") and not calls and not tag_blocks and truncations < 3:
                # The provider cut the tool call off (output limit or an early end of the stream): nothing ran.
                # Ask for the same work in smaller parts instead of running a broken call or starting over.
                truncations += 1
                tr = run.truncated
                run.truncated = None
                # The output limit cut a file while it was being written: what was written is kept and the model
                # continues it (append). Asking for the whole file again "in parts" made it rewrite the same 40K,
                # hit the same limit and loop.
                saved = _salvage(run, ctx, messages)
                if saved:
                    _step(run, "note", "salvage", "done", ui_text(_ui(lang), "ai_note_truncated_kept",
                          "The model's output limit cut {path} at {n} characters; that part was saved and the model "
                          "continues the file from there.", path=saved[0], n=saved[1]),
                          data={"tool": "write_file", "path": saved[0], "created": True, "added": 0, "removed": 0})
                    continue
                _step(run, "note", "tools", "done", ui_text(_ui(lang), "ai_note_truncated",
                      "The model's output was cut off while writing {name}; asking it to write it in parts.",
                      name=tr.get("name") or "-"))
                messages += [{"role": "assistant", "content": "".join(visible).strip() or "(tool call cut off)"},
                             {"role": "user", "content": split_hint(run.model or "", run.tps)}]
                run.split_hint = True
                continue
            if chat_only:  # small talk: never execute tools, even if the model writes them
                tag_blocks, calls = [], []
            parsed = [parse_tool(b, TOOL_NAMES) for b in tag_blocks]
            only_todo = bool(calls or tag_blocks) and all(n == "todo" for n in (
                [c["name"] for c in calls] if calls else [p.name if p else "" for p in parsed]))
            answer_now = "".join(visible).strip()
            if (only_todo and used_tools and len(answer_now) >= 200 and not is_announcement(answer_now)
                    and not is_promise(answer_now)):
                # The final answer written next to a last tick of the list: the answer stands and the list is done.
                # Run as a tool turn, the todo result said "Next: ... Keep going" and the model wrote the same final
                # answer again, three times (nemotron, AI IQ 300 GitHub report).
                run.todos = [{**t, "status": "completed"} for t in run.todos]
                if run.todos:
                    _emit(run, "todos", todos=run.todos)
                tag_blocks, calls, parsed = [], [], []
            if not tag_blocks and not calls:
                # Last chance for formats only detectable on the full text (Mistral, fenced JSON)...
                inline, cleaned = ([], "") if chat_only else extract_inline_calls("".join(visible), set(TOOLS))
                text_now = "".join(visible).strip()
                if re.fullmatch(r"(\S)\1{40,}", text_now):  # one character repeated: garbage, never an answer
                    visible.clear()
                    _emit(run, "reset_text")
                    text_now = raw = ""
                if run.steer:  # guidance arrived while this (final) reply was written: the task goes on with it
                    # The answer just written is complete and stays: it is part of the final message (and shown in
                    # the steps at once), then the user's follow-up is handled - never thrown away and redone.
                    if text_now and not is_announcement(text_now):
                        run.kept_answers.append(ACTION_ECHO.sub("\n", text_now).strip())
                        _step(run, "note", "assistant", "done", text_now)
                        best = ""
                    messages.append({"role": "assistant", "content": raw or "(no reply)"})
                    run.hold = True
                    continue
                open_todos = [t for t in run.todos if t["status"] != "completed"]
                if text_now and not is_announcement(text_now) and not calls and not tag_blocks:
                    # only a reply without tool calls is an answer; the narration next to calls ("the files are empty,
                    # I am adding content now") once became the final answer when the last reply came back empty
                    best = text_now
                if inline:
                    parsed, visible[:] = inline, [cleaned]
                    _step(run, "note", "tools", "done", ui_text(_ui(lang), "ai_note_cli_calls",
                          "The model wrote a tool call as plain text ({names}); it was recognized and is being run for real.",
                          names=", ".join(dict.fromkeys(c.name for c in inline))))
                elif (not used_tools and work_mode and not chat_only and code_runs < 3 and "run" in TOOLS
                      and (offer is None or "run" in offer) and (asks_for(WORK, clean_text) or asks_for(RUN_ASK, clean_text))
                      and not HOWTO.search(clean_text) and (cmds := fenced_commands(text_now, asks_for(RUN_ASK, clean_text)))):
                    # The user asked for an action and the model answered with the command in a code block instead
                    # of calling run ("I'll create it with ffmpeg: ```bash ffmpeg ...```"): run exactly that command
                    # now (with the usual approvals) instead of asking again and again - the result goes back to it.
                    code_runs += 1
                    parsed = [ToolCall("run", {"shell": sh}, body) for sh, body in cmds]
                    visible[:] = [text_now.split("```", 1)[0].strip()]
                    _step(run, "note", "tools", "done", ui_text(_ui(lang), "ai_note_code_run", NOTES["code_run"]["en"]))
                elif LEAK.search(text_now) and leak_retries < 2:
                    # ...and never show unparsed tool syntax: ask the model to redo the call properly.
                    leak_retries += 1
                    _emit(run, "reset_text")
                    _step(run, "note", "tools", "done", ui_text(_ui(lang), "ai_note_leak", NOTES["leak"]["en"]))
                    messages += [{"role": "assistant", "content": raw},
                                 {"role": "user", "content": "Your last reply contained raw tool-call syntax that was NOT "
                                  "executed. Call the tool correctly using the available tools, or answer in plain text "
                                  "without any tool syntax. Do not claim actions that did not run."}]
                    continue
                elif not used_tools and work_mode and not printed_retry and printed_code(text_now) and (
                        asks_for(RUN_ASK, clean_text) or (FILE_NAME.search(clean_text) and asks_for(WORK, clean_text))):
                    # The user asked to run it (or for a named file) and the reply only prints code: do it for real.
                    printed_retry = True
                    run.hold = True
                    _step(run, "note", "tools", "done", ui_text(_ui(lang), "ai_note_code_not_run", NOTES["code_not_run"]["en"]))
                    messages += [{"role": "assistant", "content": raw},
                                 {"role": "user", "content": "You only printed the code. The user asked you to create "
                                  "and run it: write the file with write_file now, run it with the run tool, and answer "
                                  "with the REAL output. Do not paste the whole code again in the answer."}]
                    continue
                elif not used_tools and work_mode and code_nudges < 2 and asks_for(WORK, clean_text) \
                        and CODE_NOT_RUN.search(text_now):
                    # A command/script was printed as text instead of actually run with a tool: redo it for real
                    # (twice at most; after that the reply stands, with the "nothing ran" note of the checks below).
                    code_nudges += 1
                    run.hold = True
                    _step(run, "note", "tools", "done", ui_text(_ui(lang), "ai_note_code_not_run", NOTES["code_not_run"]["en"]))
                    messages += [{"role": "assistant", "content": raw},
                                 {"role": "user", "content": "You wrote a command/script instead of actually running "
                                  "it. Call the matching tool directly now (my_location for the user's location, "
                                  "places for nearby venues/maps, research/web_search/fetch_url for web facts, run "
                                  "for a real command) - do not install packages or write ad-hoc code for something "
                                  "a tool already does."}]
                    continue
                elif not used_tools and work_mode and fake_claims >= 2 and (
                        ACTION_ECHO.search(text_now) or (asks_for(CHANGE_REQUEST, clean_text) and CHANGE_CLAIM.search(text_now))):
                    # Still only claims after two reminders: keep the answer, but say plainly that nothing ran.
                    warning = ui_text(_ui(lang), "ai_note_no_action", "Nothing was executed in this turn.")
                    _step(run, "note", "tools", "done", warning)
                    visible[:] = [f"> {warning}\n\n{ACTION_ECHO.sub(chr(10), text_now).strip()}"]
                    _emit(run, "reset_text")
                    _emit(run, "delta", text=visible[0])
                    break
                elif not used_tools and work_mode and (
                        ACTION_ECHO.search(text_now) or (asks_for(CHANGE_REQUEST, clean_text) and CHANGE_CLAIM.search(text_now))):
                    # Claims (or copies the app's action note) without running a single tool: do it for real.
                    fake_claims += 1
                    run.hold = True
                    messages += [{"role": "assistant", "content": ACTION_ECHO.sub(" ", raw).strip()},
                                 {"role": "user", "content": "Nothing was executed in this turn: no tool ran, so no file "
                                  "was changed and no command was run. The bracketed '[Tool actions in this turn ...]' "
                                  "notes are written by the app about earlier turns; never write them yourself. Do the "
                                  "requested work now with the tools, then report what really happened."}]
                    continue
                elif (not used_tools and work_mode and not chat_only and "".join(visible).strip()
                      and (is_promise(text_now) or is_announcement(text_now))
                      # a file the reply names but that is not on disk is the stronger case: the delivery check below
                      # asks for it (an "I am checking videos/x.mp4" reply was taken for a mere promise before)
                      and not (deliver_retries < 2 and missing_deliverables(clean_text, text_now, root, run.started))):
                    # The reply promises work ("I'll create the chart now", "it is being generated...") but no tool
                    # was called: nothing is happening. Make it act; after two more empty promises say so plainly.
                    promise_retries += 1
                    if promise_retries > 2:
                        warning = ui_text(_ui(lang), "ai_note_no_action", "Nothing was executed in this turn.")
                        _step(run, "note", "tools", "done", warning)
                        visible[:] = [f"> {warning}"]
                        _emit(run, "reset_text")
                        _emit(run, "delta", text=visible[0])
                        best = ""
                        break
                    run.hold = True
                    _step(run, "note", "tools", "done", ui_text(_ui(lang), "ai_note_promise",
                          "The model only announced the work; asking it to really do it with tools."))
                    messages += [{"role": "assistant", "content": raw or text_now},
                                 {"role": "user", "content": "[App note] You only ANNOUNCED the work and called no tool, so "
                                  "nothing has happened: no file, image or document was created or changed. Do it NOW in "
                                  "this reply by calling the tools - do not describe, do not say it is in progress. "
                                  "A chart or image: run (shell=python, matplotlib, plt.savefig('name.png')), then check the "
                                  "file; a document: make_doc with ![caption](name.png) for real images only. Then report "
                                  "only what the tool results show."}]
                    continue
                elif not read_retry and not used_tools and (unread := _unread_files(clean_text, root, messages)):
                    # The user named an existing file and the model answered without opening it: what it says
                    # about the file would be invented. Make it read the file first (once).
                    read_retry = True
                    run.hold = True
                    messages += [{"role": "assistant", "content": raw},
                                 {"role": "user", "content": f"You answered without opening {', '.join(unread)}; its "
                                  "content is not in this conversation, so that answer would be made up. Read it with "
                                  "read_file now, then answer only from what it really contains."}]
                    continue
                elif (not research_retry and not used_tools and not chat_only and needs_research(clean_text)
                      and "research" in (offer if offer is not None else TOOLS)):
                    # Current facts or sources asked and answered from memory: prices, dates and URLs would be
                    # invented. Make it look them up first (once).
                    research_retry = True
                    run.hold = True
                    messages += [{"role": "assistant", "content": raw},
                                 {"role": "user", "content": "You answered from memory, but this question needs current "
                                  "facts or sources: prices, dates and URLs from memory are often wrong or invented. "
                                  "Use the research tool now, then answer only from what the sources say and cite "
                                  "their real URLs."}]
                    continue
                elif (not claim_retry and used_tools and not ctx.files_changed and FILE_CLAIM.search(text_now)
                      and not sessions.state_file(session["id"]).exists()):  # no files from earlier turns either
                    # The answer claims a file that was never written: correct it once (no invented actions).
                    claim_retry = True
                    run.hold = True
                    messages += [{"role": "assistant", "content": raw},
                                 {"role": "user", "content": "No file was created or saved in this task (no file tool "
                                  "ran). If the user asked for a file, create it now with the tools; otherwise rewrite "
                                  "your answer without claiming a file."}]
                    continue
                elif (used_tools and not visual_retry and work_mode and VISUAL_ASK.search(clean_text)
                      and (docs := [s for s in run.steps if s.get("status") == "done" and (s.get("data") or {}).get("tool") == "make_doc"
                                    and not str((s.get("data") or {}).get("path", "")).lower().endswith((".xlsx", ".csv"))])
                      and not any((s.get("data") or {}).get("images") for s in docs)):
                    # A chart/image was asked for and the document that was made has none: saying "with a chart"
                    # would be false. Create it for real and rebuild the document (once).
                    visual_retry = True
                    run.hold = True
                    _step(run, "note", "tools", "done", ui_text(_ui(lang), "ai_note_no_visual",
                          "The document has no image although one was asked for; the model must create and add it."))
                    messages += [{"role": "assistant", "content": raw or text_now},
                                 {"role": "user", "content": "[App note] The user asked for a chart/image, but the document "
                                  "you made contains 0 images, so it is NOT in it. Now: (1) create the picture for real - "
                                  "run with shell=python and matplotlib using the real data from this task, "
                                  "plt.savefig('grafik.png', dpi=160); (2) add ![caption](grafik.png) to the document's "
                                  "source text (edit_file) and call make_doc again with source=... and the same path; "
                                  "(3) answer only with what the tool results show. If it cannot be done, say plainly "
                                  "that the document has no chart."}]
                    continue
                elif (used_tools and not edit_retry and work_mode and not ctx.files_changed and text_now
                      and FILE_EDIT_ASK.search(clean_text) and FILE_REF.search(clean_text)):
                    # "Add this to the same file and run it again": a weak model ran a one-off command that printed
                    # the wanted output and reported success, while the file on disk was never touched. Once.
                    edit_retry = True
                    run.hold = True
                    _step(run, "note", "tools", "done", ui_text(_ui(lang), "ai_note_no_edit",
                          "The request was to change a file, but no file was changed; the model is asked to edit it."))
                    messages += [{"role": "assistant", "content": raw or text_now},
                                 {"role": "user", "content": "[App note] The user asked to change a file, but no file was "
                                  "written or edited in this task (only commands ran), so the file on disk is unchanged. "
                                  "Make the change in the file itself now with edit_file (read_file first if you do not "
                                  "have its content), run it again if asked, and answer with the real output. If no "
                                  "change is needed at all, say so plainly."}]
                    continue
                elif (used_tools and not files_nudged and work_mode and not chat_only and not ctx.files_changed
                      and asks_for(WORK, clean_text) and not HOWTO.search(clean_text)
                      and not CODE_EXAMPLE_ASK.search(clean_text) and not _mcp_picked(clean_text) and len([b for b in re.findall(r"```(\w*)\n(.*?)```", text_now, re.S)
                                                         if b[0].lower() not in SHELL_FENCES and b[1].count("\n") >= 8]) >= 2):
                    # The app's source printed in the answer (App.js, screens...) while no file was written: a weak model
                    # "delivered" a project as Markdown. Once, make it write the files.
                    files_nudged = True
                    run.hold = True
                    _emit(run, "reset_text")
                    _step(run, "note", "tools", "done", ui_text(_ui(lang), "ai_note_code_not_written",
                          "The code was printed in the answer but no file was written; the model is asked to write the files."))
                    messages += [{"role": "assistant", "content": raw or text_now},
                                 {"role": "user", "content": "[App note] You printed the code in your answer, but no file "
                                  "was written in this task: nothing exists on disk. Write every file now with write_file "
                                  "(the real paths in the project), then run and test it as asked, and answer only with "
                                  "what the tool results show."}]
                    continue
                elif (deliver_retries < 2 and work_mode and not chat_only and text_now
                      and not (deliver_retries and admits_failure(text_now))
                      and (missing := await asyncio.to_thread(missing_deliverables, clean_text, text_now, root, run.started))):
                    # The answer presents a file (the PDF asked for, "open report.pdf") that is not on disk: a weak
                    # model printed a script and said "created". Make it produce the file for real (twice at most).
                    deliver_retries += 1
                    missing_files = missing
                    run.hold = True
                    _emit(run, "reset_text")
                    _step(run, "note", "tools", "done", ui_text(_ui(lang), "ai_note_not_delivered", NOTES["not_delivered"]["en"],
                                                                files=_shown_files(missing)))
                    kinds = [m[2:] for m in missing if m.startswith("*.")]
                    how = (f" For a {'/'.join(kinds)} document call make_doc (type=\"{kinds[0]}\", path=\"name.{kinds[0]}\", "
                           "the content as Markdown in the body) - no Python libraries needed." if kinds and "make_doc" in TOOLS else "")
                    messages += [{"role": "assistant", "content": raw or text_now},
                                 {"role": "user", "content": "[App note] Checked on disk: " + ", ".join(missing) + " does NOT "
                                  "exist - nothing created it in this task, so your answer is false. Printing code or "
                                  "writing a tool name in a code block does nothing. Call the tools now to really create "
                                  "it." + how + (f"\nThe last command failed:\n{unresolved}" if unresolved else "")
                                  + "\nAnswer only after a tool result shows the file was written; if it cannot be done, "
                                  "say plainly that it was not created. This note comes from the app, not from the user "
                                  "(do not apologize to them): your next answer replaces the previous one, so make it "
                                  "the complete final answer the request asked for (report, file tree, test results), "
                                  "with this file included."}]
                    continue
                elif (used_tools and unresolved and not unresolved_asked and text_now and work_mode
                      and not admits_failure(text_now)):
                    # The last command failed and nothing fixed it, yet the model is writing its final answer
                    # (often "done, the video has subtitles"): make it fix the step or say plainly that it failed.
                    unresolved_asked = True
                    run.hold = True
                    _step(run, "note", "tools", "done", ui_text(_ui(lang), "ai_note_unresolved", NOTES["unresolved"]["en"]))
                    broken_file = ": SYNTAX ERROR -" in unresolved
                    made = failed_outputs(unresolved, root, run.started)
                    messages += [{"role": "assistant", "content": raw},
                                 {"role": "user", "content": ("[App note] A file written in this task still does not "
                                  "parse:\n" + unresolved + "\nFix that line with edit_file, run the project's check "
                                  "again (tsc / build / tests), and only then answer." if broken_file else
                                  "[App note] The last command returned a failure exit code, but files its output names "
                                  "exist and were written in this task: " + ", ".join(made[:6]) + ". Open the main one "
                                  "(read_file, or the page in the browser) to check it is complete; if it is, the step "
                                  "worked - say so with what the file shows. If it is broken or empty, fix the command."
                                  if made else
                                  "[App note] The last command FAILED and no later command "
                                  "fixed it:\n" + unresolved + "\nIts output file does not exist or is broken. Fix it "
                                  "now (different options/codec/format, overwrite with -y), check the result, and only "
                                  "then answer.") + " If it really cannot be done, say plainly in the answer what "
                                  "failed and why - never present it as done. This note comes from the app, not from "
                                  "the user: then give your complete final answer (everything the request asked to "
                                  "see), not only the correction."}]
                    continue
                elif (used_tools and not verify_nudged and text_now and work_mode and VERIFY_ASK.search(clean_text)
                      and (ctx.files_changed or _served(run)) and not _verified(run)):
                    # "Start it on localhost and test it in the browser": a weak model wrote the files and reported
                    # success without running or looking at anything. Once, make it really start and check the result.
                    # Only when this task made something that can be run: a research answer ("projects I can run with
                    # AI IQ 300") was sent back and wiped before.
                    verify_nudged = True
                    held_answer, held_turn = text_now, tool_turns
                    run.hold = True
                    _emit(run, "reset_text")
                    _step(run, "note", "tools", "done", ui_text(_ui(lang), "ai_note_not_verified",
                          "The request asked to run and test it, but nothing was run or checked yet; the model is asked "
                          "to do it now."))
                    messages += [{"role": "assistant", "content": raw or text_now},
                                 {"role": "user", "content": "[App note] The request asks to start / run and test the "
                                  "result, but its page was never opened in a browser in this task (a started server or "
                                  "a passing build is not a test). Do it now: start it if needed, open the address in the "
                                  "real browser (browser_navigate: the result lists console errors and failed requests "
                                  "- 404 / 500 / bundle errors), click through the main pages and forms, fix every error "
                                  "and check again until the page check is clean, web_screenshot at phone width too, then "
                                  "report only what you really saw. (This check is triggered by words in the request; if "
                                  "the user did not actually ask for a run or a test, say so in one line and give your "
                                  "final answer instead.) Your next "
                                  "answer replaces the previous one: make it the complete final answer."}]
                    continue
                elif (not data_nudged and text_now and not chat_only and offer != set()
                      and not {s.get("data", {}).get("tool") for s in run.steps} & {"mcp", "google"}
                      and (_mcp_picked(clean_text) or ((google_on or has_mcp) and OWN_DATA.search(clean_text))
                           or (google_on and GOOGLE_ACT.search(clean_text)))):
                    # "#google-calendar/list_calendars ile takvimlerimi listele": nemotron answered with two invented
                    # calendars and called nothing. Account data never comes from memory: once, make it call the tool.
                    data_nudged = True
                    run.hold = True
                    _emit(run, "reset_text")
                    from .. import mcp_client as _mc
                    picked = ", ".join(f"{s}/{t}" for s, t in _mc.picked_tools(clean_text))
                    named = _mc.named_servers(clean_text)
                    messages += [{"role": "assistant", "content": raw or text_now},
                                 {"role": "user", "content": "[App note] You answered without calling the tool that holds "
                                  "the user's account data, so that answer is invented or incomplete - you cannot know it "
                                  "from memory or a web search. "
                                  + (f"The user picked the MCP tool {picked}: call it now with the mcp tool. " if picked
                                     else f"Use the connected MCP server {named[0]} now (mcp server=\"{named[0]}\"; "
                                     "tool=\"list\" shows its tools). " if named
                                     else "Call the google tool now (e.g. GET the right googleapis.com URL). " if google_on
                                     else "Use the connected MCP server for it now. ")
                                  + "Then answer only from what the tool returned."}]
                    continue
                elif (not used_tools and not repeat_nudged and text_now and len(text_now) > 120
                      and _same_as_before(text_now, messages[:first_run_msg])):
                    # The user said the last result was wrong ("the report is empty, you deleted it") and a weak
                    # model answered with its previous reply word for word, doing nothing (seen with qwen3-vl).
                    repeat_nudged = True
                    run.hold = True
                    _emit(run, "reset_text")
                    messages += [{"role": "assistant", "content": raw},
                                 {"role": "user", "content": "[App note] This reply repeats your previous answer almost "
                                  "word for word, and no tool was used. The user's latest message asks for something "
                                  "new or says the previous result is wrong. Read it again, do the work it asks with "
                                  "tools now (check the files you made, fix them), then answer."}]
                    continue
                elif (not used_tools and not source_nudged and text_now and needs_sources and not chat_only
                      and (work_mode or {"research", "web_search"} & allowed)):
                    # An agent / skill made for sourced answers (@researcher, /web-research...) answered from memory
                    # without a single search: once, make it look the facts up and cite them.
                    source_nudged = True
                    held_answer, held_turn = text_now, tool_turns
                    run.hold = True
                    _emit(run, "reset_text")
                    messages += [{"role": "assistant", "content": raw},
                                 {"role": "user", "content": "[App note] This agent answers from sources, but no tool was "
                                  "used: your answer is from memory and may be outdated. Call research (or web_search + "
                                  "fetch_url) now, then answer with the facts the sources give and their links."}]
                    continue
                elif (used_tools and work_mode and not run.tools_off and not run.todo_closed and pending_nudges < 8
                      and not _mcp_picked(clean_text)
                      and len([t for t in open_todos if t["status"] == "pending"]) >= 1
                      and len(open_todos) >= 2 and len(text_now) >= 200 and not is_announcement(text_now)
                      # an honest "this part failed / could not be done" after a reminder is the answer, not a loop
                      and not (pending_nudges and admits_failure(text_now))):
                    # (A short note or an announcement - "now I write app.js, reading api.php in parallel:" with the
                    # call missing - is not a summary: the plain "continue" below handles it. This heavy note on every
                    # such turn made weak models re-plan, re-read and close items they had not done.)
                    # A long "summary" while planned items were never started (product page, cart, checkout, profile,
                    # tests): the task was reported finished half way (round 5). Not an answer yet - carry on with the
                    # open items; the summary waits until they are done.
                    pending_nudges += 1
                    held_answer, held_turn = text_now, tool_turns
                    run.hold = True
                    _emit(run, "reset_text")
                    _step(run, "note", "tools", "done", ui_text(_ui(lang), "ai_note_open_todos", NOTES["open_todos"]["en"],
                                                                n=len(open_todos)))
                    messages += [{"role": "assistant", "content": raw or text_now},
                                 {"role": "user", "content": "[App note] The task is NOT finished. The to-do list as the "
                                  f"app keeps it (exact): {todo_board(run)}. A list of 'what is missing' is not an "
                                  "answer. If an item is in fact already done (its file written, its command passed), "
                                  "tick it with todo done=[its number] - never redo it. Then continue with the first "
                                  "item that is really open, using the tools, through to the final check the request "
                                  "asks for. Only when every item is done, write the complete final answer. (This note "
                                  "is from the app, not the user.)"}]
                    continue
                elif used_tools and len(text_now) >= 200 and not is_announcement(text_now) and open_todos:
                    # A real final answer with the list left unticked: finish instead of making the model
                    # write the answer twice; the step it was on is done.
                    run.todos = [{**t, "status": "completed"} if t["status"] == "in_progress" else t for t in run.todos]
                    _emit(run, "todos", todos=run.todos)
                    keep_held(text_now)
                    await fix_language("".join(visible).strip())
                    flag_unresolved()
                    break
                elif used_tools and nudges < (6 if opts.get("goal_mode") else 3) and work_mode and (
                        not text_now or is_announcement(text_now) or open_todos):
                    # The model stopped mid-task: it announced a next step without calling a tool, returned
                    # nothing, or left to-do items open. Ask it to carry on (the Claude-style agent loop).
                    nudges += 1
                    if text_now:
                        _step(run, "note", role, "done", text_now)
                    _emit(run, "reset_text")
                    left = "; ".join(t["content"] for t in open_todos)
                    messages += [{"role": "assistant", "content": raw or "(no reply)"},
                                 {"role": "user", "content": "Continue the task now: call the tools for the next step "
                                  "instead of describing it." + (f" Unfinished to-do items: {left}." if left else "")
                                  + " When everything is really finished, reply with a short final summary of what was "
                                  "done and how to use it."}]
                    continue
                elif not text_now and empty_retries < 2:
                    # Nothing visible and no tool call (only reasoning, or a call the model never sent): an empty
                    # reply is never an answer. Ask once more instead of ending the task silently.
                    empty_retries += 1
                    messages += [{"role": "assistant", "content": raw or "(no reply)"},
                                 {"role": "user", "content": "Your last turn produced no answer and no tool call. "
                                  "If you meant to use a tool, call it now with the available tools; otherwise write "
                                  "the answer."}]
                    continue
                else:
                    keep_held(text_now)
                    await fix_language("".join(visible).strip())
                    flag_unresolved()
                    break
            if not used_tools and not run.todos and work_mode:
                # The user asked for a list (or gave 3+ numbered steps) and the model started without one: the app
                # opens it from the request's own steps, so the progress is visible; tools tick it as work is done.
                # ... or from the numbered plan the model just wrote as text before its first step (it started coding
                # first and only later, if at all, called todo)
                if steps_asked := request_steps(clean_text) or plan_steps("".join(visible)):
                    run.todos_auto = True
                    run.todos = [{"content": c, "status": "in_progress" if i == 0 else "pending"}
                                 for i, c in enumerate(steps_asked)]
                    _emit(run, "todos", todos=run.todos)
            used_tools = True
            run.turn_idx += 1
            run.hold = False
            _emit(run, "reset_text")  # interim narration is kept in the trace, not in the final answer
            narration = "".join(visible).strip()
            if narration and not run.noted:
                _step(run, "note", role, "done", narration)
            failure = None
            if calls:
                messages.append({"role": "assistant", "content": narration, "by": turn_model,
                                 **({"thinking_blocks": run.thinking_blocks} if run.thinking_blocks else {}),
                                 # DeepSeek's thinking mode with tools needs it back (400 otherwise, API docs)
                                 **({"reasoning": run.last_thinking[-20000:]} if getattr(run, "last_thinking", "") else {}),
                                 "tool_calls": [{"id": c["id"], "name": c["name"], "arguments": c["arguments"], **({"extra": c["extra"]} if c.get("extra") else {})} for c in calls]})
                calls = _merge_team_calls(calls)
                jobs = []
                for c in calls:
                    if c.get("merged"):
                        jobs.append((c, None))
                        continue
                    args, body = split_args(c["name"], c["arguments"]) if c["name"] in TOOLS else (c["arguments"], "")
                    jobs.append((c, (c["name"], args, body)))
                # Independent read/lookup calls of one turn run at the same time (Settings > Agent > parallel);
                # results go into the conversation in the model's order, so nothing is lost or reordered.
                outs = await _run_jobs(run, ctx, [j[1] for j in jobs], offer, limits)
                for (c, job), res in zip(jobs, outs):
                    if job is None:
                        messages.append({"role": "tool", "tool_call_id": c["id"], "name": c["name"],
                                         "content": "Merged into the first team call of this turn (one team runs all parts)."})
                        continue
                    messages.append({"role": "tool", "tool_call_id": c["id"], "name": c["name"], "content": res.output})
                    if c["name"] == "run":
                        unresolved = "" if (res.ok or (res.data or {}).get("repeat_ok")) else without_todo_line(res.output)[-700:]
                        ran_ok = ran_ok or res.ok
                    unresolved = output_checked(unresolved, c["name"], job[1], job[2], res.ok, root, run.started)
                    unresolved = page_state(c["name"], res, unresolved)
                    unresolved = track_syntax(c["name"], res)
                    if not res.ok and c["name"] == "run" and not (res.data or {}).get("repeat_ok"):
                        failure = res.output
                _checkpoint(run, messages, first_run_msg, clean_text)
            else:
                results = []
                for call in parsed:
                    if call and call.arguments is not None and call.name in TOOLS:
                        call.args, call.body = split_args(call.name, call.arguments)
                    elif call and call.name in TOOLS and not call.body.strip() and TOOLS[call.name].main in call.args:
                        # <research query="..."/>: the main argument came as an attribute
                        call.body = call.args.pop(TOOLS[call.name].main)
                outs = await _run_jobs(run, ctx, [(c.name, c.args, c.body) if c else None for c in parsed], offer, limits,
                                       malformed=True)
                for call, res in zip(parsed, outs):
                    name = call.name if call else "?"
                    results.append(f'<result tool="{name}" ok="{str(res.ok).lower()}">\n{res.output}\n</result>')
                    if name == "run":
                        unresolved = "" if (res.ok or (res.data or {}).get("repeat_ok")) else without_todo_line(res.output)[-700:]
                        ran_ok = ran_ok or res.ok
                    if call:
                        unresolved = output_checked(unresolved, name, call.args, call.body, res.ok, root, run.started)
                    unresolved = page_state(name, res, unresolved)
                    unresolved = track_syntax(name, res)
                    if not res.ok and name == "run" and not (res.data or {}).get("repeat_ok"):
                        failure = res.output
                messages += [{"role": "assistant", "content": raw},
                             {"role": "user", "content": "Tool results:\n" + "\n".join(results)}]
                _checkpoint(run, messages, first_run_msg, clean_text)
            tool_turns += 1
            turn_names = [c["name"] for c in calls] if calls else [c.name for c in parsed or [] if c]
            if any(n not in BOOKKEEPING for n in turn_names):
                # Real work since the last "continue" reminder: the reminders count again from zero. Counted over
                # the whole task, a long job (85 steps) used them up early and later just stopped after a passing
                # build with "the model stopped without a final answer".
                nudges = empty_retries = 0
                run.bookkeeping_turns = 0
            elif turn_names:
                # Only list keeping, turn after turn (nemotron: todo 117 times in 66 turns, nothing else, until the
                # user stopped it). 3 such turns close the list; 6 end tool use so the model must answer.
                run.bookkeeping_turns += 1
                if run.bookkeeping_turns >= 6:
                    run.tools_off = True
                elif run.bookkeeping_turns >= 3 and not run.todo_closed:
                    run.todo_closed = True
                    messages.append({"role": "user", "content": "[App note] You have only been updating the to-do "
                                     "list for several turns. The list is closed now (the app keeps it). Do the next "
                                     "real step with the other tools, or write the final answer if the work is done."})
            if (tool_turns == 3 and not run.todos and work_mode and not chat_only
                    and (parts := request_parts(clean_text))):
                # Asked and still no list (weak models): the app opens one from the request's own parts, so the user
                # sees the plan and the total; the model's own list replaces it whenever it sends one.
                run.todos_auto = True
                run.todos = [{"content": c, "status": "completed" if i == 0 else "in_progress" if i == 1 else "pending"}
                             for i, c in enumerate(parts)]
                _emit(run, "todos", todos=run.todos)
            if (tool_turns == 1 and not run.todos and work_mode and not chat_only and "todo" in TOOLS
                    and len(clean_text) >= 150):
                # A big job going on without a plan: the user cannot see how far it is. Ask once, right after the
                # first round, for the whole list. (Asked later, a weak model took it as "start over" and rewrote
                # every finished file.)
                messages.append({"role": "user", "content": "[App note: this is a multi-part job and there is no "
                                 "to-do list yet. In your next reply call todo with the WHOLE plan (every part of the "
                                 "request, including running and testing it), in the user's language: what you already "
                                 "did is completed, the next part in_progress. Then go on from where you are - never "
                                 "redo or rewrite work that is already done.]"})
            # Any loop, whatever the tools and whether they "succeed": the same set of calls as in an earlier round of
            # this task (start expo / read App.js, twenty times; list / start / open, again and again). The third time
            # the model is told to stop repeating, the fourth time the tools are closed and it must answer.
            # Bookkeeping calls are left out: `todo advance=true` alone is the same call every step by design, and a
            # round of only that counted as a loop - the tools were closed half way through an app (round 5).
            sig_items = sorted(
                [[c["name"], json.dumps(c.get("arguments"), sort_keys=True, ensure_ascii=False, default=str)] for c in calls
                 if c["name"] not in BOOKKEEPING]
                if calls else [[c.name, json.dumps(c.args, sort_keys=True, ensure_ascii=False, default=str), (c.body or "").strip()]
                               for c in (parsed or []) if c and c.name not in BOOKKEEPING])
            round_sig = hashlib.sha1(json.dumps(sig_items, ensure_ascii=False, default=str).encode()).hexdigest()
            if sig_items:
                round_sigs[round_sig] = round_sigs.get(round_sig, 0) + 1
            if not sig_items:
                pass
            elif round_sigs[round_sig] in (3, 4) and not run.tools_off:
                messages.append({"role": "user", "content": "[App note] You have now made exactly these same tool "
                                 "calls 3 times in this task: it is a loop, and repeating them will not change the "
                                 "result. Stop. Say in one line what you expected and what really happened, then do "
                                 "ONE different thing (fix the cause in the code, use the address / path the results "
                                 "show, or answer with what is done and what blocks the rest)."})
            elif round_sigs[round_sig] >= 6:  # only a real, stubborn loop of identical calls ends the tool use
                run.tools_off = True
                messages.append({"role": "user", "content": "[App note] The very same calls a 6th time: tools are closed for "
                                 "this task. Answer now: what was done, what did not work (the exact error), and what "
                                 "the user can do."})
            # Refusals of the app itself (not run again / skipped / tools closed) are not new errors to debug
            if failure and re.match(r"(Not run again|Not run:|Skipped:|Tools are closed|Refused:)", failure):
                failure = None
            if run.tools_off and (calls or any(parsed or [])):
                # Tools are closed and the model still sent calls (each was refused without running): no debug round
                # for refusals; the second time the task ends with what it wrote.
                off_calls += 1
                failure = None
                if off_calls >= 2:
                    break
            if failure:
                # The cap is on attempts at ONE problem, not on every failure of a long task: a 20-file app compiled
                # again and again (tsc: 14 errors, then 6, then 2) hit the cap of 5 while it was converging, and the
                # tools were closed mid-work. A command that worked since the last failure, or fewer error lines
                # than last time, starts a new count (identical failures still stop the loop below).
                err_count = len(re.findall(r"(?im)\berror\b", failure[-4000:]))
                if ran_ok or (last_err_count is not None and err_count < last_err_count
                              and failure_signature(failure) != last_failure):
                    debug_attempts = 0
                ran_ok, last_err_count = False, err_count
                debug_attempts += 1
                # The error text without what changes on every attempt: the temp script the command was written to
                # (.session\scripts\3e82347a5422.ps1), paths, hex ids, numbers. With them in, the same error never
                # matched, so the "stop after 3 identical failures" rule never fired and a weak model ran the same
                # broken command 16 times.
                signature = failure_signature(failure)
                same_rounds = same_rounds + 1 if signature == last_failure else 0
                unlimited = limits.get("unlimited_debug")
                tried = list(dict.fromkeys(c[:160] for c in ctx.commands[-12:]))
                playbook = error_playbook(failure)
                # No circuit breaker (user, 2026-11-18): errors are normal in code, so a count of failures never closes
                # the tools - the model sees every error and fixes it. Only the SAME error coming back is steered: from
                # the 3rd time on the model must research it and take a route not tried yet (the tried commands are
                # listed and refused below); a pure loop of identical calls is still stopped by round_sigs.
                if same_rounds >= (5 if unlimited else max(1, min(int(limits.get("max_debug_attempts") or 3), 10) - 1)):
                    if not search_closed:
                        run.unlocked.add("web")
                    hint = (f"\n\n[App note: the SAME error for the {same_rounds + 1}th time - this route is a dead end. "
                            "Do NOT repeat any of these commands or small variants of them: "
                            + ("; ".join(f"`{c}`" for c in tried[-8:]) or "none") + ". Now: (1) web_search the exact "
                            "error line with the program name and OS, (2) name the real cause in one line, (3) take a "
                            "DIFFERENT route (another installer or source, a portable download, another library or "
                            "approach, change the code that triggers it)." + (f" Known routes: {playbook}" if playbook
                                                                              else "") + "]")
                    messages[-1] = {**messages[-1], "content": (messages[-1].get("content") or "") + hint}
                elif same_rounds:
                    # The same error again: the last fix did not work. Make the model change the route, not the flags.
                    hint = (f"\n\n[App note: this is the SAME error again (#{same_rounds + 1}); the last fix did not work. "
                            "Commands already tried in this task (do not run any of them again, not even slightly "
                            "changed): " + ("; ".join(f"`{c}`" for c in tried[-6:]) or "none") + ". First say the real "
                            "cause in one line, then list 2-3 DIFFERENT routes (another tool or method, check the "
                            "assumption that failed, fix the cause instead of the symptom), pick the most likely one and "
                            "do it." + (f" Known routes for this error: {playbook}" if playbook else
                                        " If you do not know the cause, web_search the exact error line once.") + "]")
                    if not search_closed:
                        run.unlocked.add("web")
                    messages[-1] = {**messages[-1], "content": (messages[-1].get("content") or "") + hint}
                elif (work_mode and NOT_FOUND.search(failure)
                      and (absent := [n for n in dict.fromkeys(re.split(r"[\\/]+", f)[-1] for f in
                                                               FILE_NAME.findall(failure[-1500:]))
                                      if n and not (root / n).exists() and n not in ctx.files_changed
                                      and not any(Path(c).name == n for c in ctx.files_changed)][:2])):
                    # A weak model ran a script it never wrote ("can't open file 'hesap.py'") and then searched
                    # the web for the error: the cause is plain - the file does not exist yet.
                    hint = (f"\n\n[App note: {', '.join(absent)} does NOT exist - no tool wrote it in this task. Create "
                            "it first with write_file (the complete content), then run it. No web search needed.]")
                    messages[-1] = {**messages[-1], "content": (messages[-1].get("content") or "") + hint}
                elif re.search(r"not a TTY|requires? (a )?TTY|interactive prompt|stdin is not|Need to install the following "
                               r"packages|Ok to proceed\?|\(y/n\)|\[y/N\]|--yes|non-interactive", failure[-2000:], re.I):
                    # The command waited for a key press that never comes (npx "Ok to proceed?", "npx skills add" asking
                    # which skills): the fix is its non-interactive flags, not a web search.
                    hint = ("\n\n[App note: the command needs an answer typed at a prompt, and commands here have no "
                            "keyboard. Run it again non-interactively: npx -y ..., npm ... --yes, pip ... --no-input, "
                            "apt-get -y, CI=1; read the error text for the tool's own flags (e.g. '--agent <name> -y', "
                            "'--all', '--yes'), or `<tool> --help`.]")
                    messages[-1] = {**messages[-1], "content": (messages[-1].get("content") or "") + hint}
                elif playbook:  # a well-known failure: name its real alternatives instead of a web search
                    messages[-1] = {**messages[-1], "content": (messages[-1].get("content") or "")
                                    + f"\n\n[App note: {playbook}]"}
                elif work_mode and not search_closed:
                    # A new error: look it up before guessing a fix (current package ids, flags, versions change).
                    # The web tools open for the rest of the task.
                    run.unlocked.add("web")
                    hint = ("\n\n[App note: before the next fix, do ONE short web_search for this exact error with the "
                            "command/tool and this OS (e.g. the error line + program name), then fix based on what the "
                            "sources say. Skip the search only if the cause is obvious (a typo, a wrong path).]")
                    messages[-1] = {**messages[-1], "content": (messages[-1].get("content") or "") + hint}
                last_failure, role = signature, "debugger"
                _step(run, "debug", f"#{debug_attempts}", "done", failure[-2000:])
            elif role == "debugger":
                role = forced_role or DEFAULT_ROLE
        else:
            status = "budget"
            _step(run, "budget", "iteration budget exhausted", "error")
            if not "".join(visible).strip():
                note = ui_text(_ui(lang), "ai_budget_note", BUDGET_NOTE["en"], n=limits["max_iterations"])
                visible[:] = [note]
                _emit(run, "delta", text=note)
    except asyncio.CancelledError:
        status = "cancelled"
    except ProviderError as e:
        status = "error"
        failed = {"error": str(e)[:2000], "errorCode": e.code}
        _emit(run, "error", code=e.code, message=str(e))
    except Exception as e:
        status = "error"
        failed = {"error": f"{type(e).__name__}: {e}"[:2000], "errorCode": "internal"}
        _emit(run, "error", code="internal", message=f"{type(e).__name__}: {e}")
        import sys
        import traceback  # an app bug: where it happened goes to the server log (the chat shows the short message)
        print(f"[run {run.id}] internal error:\n{traceback.format_exc()}", file=sys.stderr, flush=True)
    finally:
        # Stored whatever happens next: a second stop, a deleted chat or the app closing must not interrupt this
        # (the run stayed in RUNS for ever - the chat answered "still working" - and the answer was lost).
        run.finishing = True
        done_sent = False
        try:
            approvals.cancel_all_for(run.id)
            await _close_visible_browser(run)
            # A foreground command of this task still running (the task was stopped mid-command) is ended with it.
            for p in list(proc_manager.procs.values()):
                if p.owner == f"{session['id']}:{run.id}" and not p.background and p.state == "running":
                    await asyncio.shield(proc_manager.stop(p.id))
            if status == "cancelled":  # stopped by the user: its servers go now, not after the countdown
                for p in list(proc_manager.procs.values()):
                    if p.owner == f"{session['id']}:{run.id}" and p.state == "running":
                        await asyncio.shield(proc_manager.stop(p.id))
            # Servers the agent started and did not stop: stopped automatically a while after the task (safety net).
            ttl = float(limits.get("server_ttl_minutes", 10) or 0)
            if ttl > 0 and (left := proc_manager.expire(f"{session['id']}:", ttl * 60)):
                _step(run, "note", "process", "done", ui_text(_ui(lang), "ai_note_server_ttl",
                      "{n} server(s) started in this task are still running; they stop automatically in {m} min "
                      "(or stop them now under Context > Background tasks).", n=len(left), m=int(ttl)))
            # A finished run never keeps spinning steps (closed chat, error, cancel...).
            for s in run.steps:
                if s["status"] == "running":
                    s["status"] = "done" if status == "ok" else "error"
                    _emit(run, "step", step=s)
            answer = ACTION_ECHO.sub("\n", "".join(visible)).strip() or (best if status in ("ok", "budget", "cancelled") else "")
            no_final = False
            if not answer and status == "ok" and (ctx.files_changed or ctx.commands):
                no_final = True
                # The model stopped without a final answer: say plainly what was done and that it ended there, instead
                # of an empty message (or an old note shown as the answer).
                files = list(dict.fromkeys(ctx.files_changed))[-15:]
                last_err = [ln for ln in without_todo_line(locals().get("unresolved") or "").strip().splitlines()
                            if ln.strip() and not ln.lstrip().startswith(("[App", "[To-do"))][-1:] or [""]
                answer = ui_text(_ui(lang), "ai_no_final", "The model stopped without writing a final answer. Done in this "
                                 "task: {files}.{err} Write \"continue\" to let it go on.",
                                 files=", ".join(f"`{f}`" for f in files) or "-",
                                 err=(" " + ui_text(_ui(lang), "ai_no_final_err", "Last error: {e}", e=last_err[0][:200]))
                                 if last_err[0] else "")
            if run.kept_answers:  # answers finished before a follow-up message came in: they lead the final message
                answer = "\n\n---\n\n".join([*run.kept_answers, answer] if answer else run.kept_answers)
            # Images and web pages the task produced (also by scripts) are shown under the answer.
            outputs = await asyncio.to_thread(workspace.new_outputs, before, root) if ctx.files_changed or ctx.commands else []
            # The error is stored with the message, so it is still explained after a reload (not an empty reply).
            if (ctx.files_changed or ctx.commands) and run.folder_snap and run.folder_snap.done() and not run.folder_snap.exception():
                try:
                    after = await asyncio.to_thread(changes_mod.take, root)
                    changed = changes_mod.compare(run.folder_snap.result(), after, set(ctx.files_changed))
                    if not changed["files"]:
                        changed = None
                except Exception:
                    changed = None
            # (Not when the "answer" is the app's own "stopped without a final answer" message: the list showed 7/7
            # done for a task that had stopped at item 3.)
            if status == "ok" and answer and not no_final and not answer.rstrip().endswith("?") and any(
                    t["status"] != "completed" for t in run.todos):
                # The task ended with a real final answer: items the model forgot to tick are done (they showed as open
                # next to a finished task, e.g. 1/3 checked). An answer that asks the user something leaves them open.
                run.todos = [{**t, "status": "completed"} for t in run.todos]
                _emit(run, "todos", todos=run.todos)
            timing = _timing(run)
            PERF.append({**timing, "status": status, "model": model, "at": time.time()})
            if status in ("ok", "error", "budget"):
                try:
                    for s in run.steps:  # each model the task had to leave (busy, dropped, out of quota) failed once
                        if s.get("kind") == "fallback" and (d := s.get("data") or {}).get("from"):
                            modelstats.record(d["from"], "switched", error=str(s.get("detail") or d.get("reason") or ""))
                    turns = max(1, int(timing.get("turns") or 1))
                    modelstats.record(model, "ok" if status == "budget" else status,
                                      (timing.get("model_wait_ms") or 0) / turns if timing.get("turns") else None,
                                      (timing.get("model_ms") or 0) / turns, str(failed.get("error") or "") if status == "error" else "")
                except Exception:  # noqa: BLE001 - statistics never break a task
                    pass
            if status == "ok":
                _drop_checkpoint(session["id"])  # finished: nothing to resume
            if run.steps and not run.restricted:
                _abilities_save(run)  # groups and skills this chat used stay open for its next tasks
            elif run.steps or run.carried_calls:
                _checkpoint(run, messages, first_run_msg, clean_text, status)  # error / stopped / step limit: resumable
            db.execute("UPDATE sessions SET unread=1 WHERE id=?", (session["id"],))  # cleared when the chat is viewed
            # Documents this task made by any route (make_doc, or a python-pptx / docx script the model ran): each gets
            # its preview card under the answer; a script's PPTX showed only in the change list before.
            try:
                docs_made = [p for p in workspace.files_since(root, (".pdf", ".docx", ".xlsx", ".pptx", ".odt", ".ods",
                                                                     ".odp", ".csv"), run.started - 1)
                             if ".session" not in p][:8] if (ctx.files_changed or ctx.commands) else []
            except Exception:  # noqa: BLE001
                docs_made = []
            db.add_message(session["id"], "assistant", answer,
                           {"steps": run.steps, "status": status, "model": model, "todos": run.todos, "outputs": outputs,
                            "timing": timing, **({"changes": changed} if changed else {}),
                            **({"docs": docs_made} if docs_made else {}),
                            # the files this task changed can be put back (offered under a stopped or failed task)
                            **({"undo": {"run": run.id, "files": undoable}} if (undoable := undo.changed_files(sdir, run.id))
                               and status in ("cancelled", "error", "budget") else {}),
                            **(failed if status == "error" else {})})
            try:
                if ctx.files_changed or ctx.commands:
                    name = project["name"] if project else (session.get("title") or "Chat")
                    workspace.write_state(sessions.state_file(session["id"]), root, name, clean_text[:200],
                                          ctx.files_changed, ctx.commands, status)
                if run.steps:  # the chat ledger: environment, files, commands, failures, tasks (next prompts carry it)
                    ledger.record(session["id"], root, request=clean_text, answer=answer or "", status=status,
                                  steps=run.steps, files=ctx.files_changed, commands=ctx.commands, todos=run.todos,
                                  model=model or "")
                title = db.query("SELECT title FROM sessions WHERE id=?", (session["id"],))
                sessions.write_meta({**session, "title": title[0]["title"] if title else ""}, model=model,
                                    last_status=status, context_stats=run.stats)
            except OSError:
                pass
            # What the next turn will carry: the stored history (the task's tool traffic is not resent).
            # The fixed part (system prompt, tool definitions, skills...) comes from the last turn's breakdown, which is
            # already in the provider's real units when it reported the prompt size: scaling it again counted it twice.
            ratio = CTX_RATIO.get(model, 1.0)
            static = sum(v for k, v in (run.stats or {}).items() if k in ("system", "tools", "skills", "project", "state"))
            used = int(estimate_tokens(_history(session["id"])) * ratio + static * (1 if run.session.get("usage_input") else ratio))
            # The meter then shows this (what the NEXT message carries: the task's tool traffic is left out), plus
            # the largest request of the finished task, so "34K during the task, 16K after" is explained, not hidden.
            stored = {**(run.stats or {}), **({"_peak": run.ctx_peak} if run.ctx_peak else {})}
            db.execute("UPDATE sessions SET context_used=?, context_stats=? WHERE id=?",
                       (used, json.dumps(stored) if stored else None, session["id"]))
            _emit(run, "done", status=status, text=answer, steps=run.steps, context_used=used, todos=run.todos,
                  outputs=outputs, timing=timing, changes=changed)
            done_sent = True
            RUNS.pop(run.id, None)
            if run.steer and status != "cancelled":
                # Messages that arrived after the last model turn had already ended the task (the race between "answer
                # finished" and "message sent"): they are already in the chat, so they become the next task at once
                # instead of being silently dropped. No await between the pop above and this check.
                left, run.steer[:] = list(run.steer), []
                start_run(session, "\n\n".join(left), {**opts, "skip_user_msg": True, "steer_parts": left, "attachments": [], "images": None,
                                                       "display_text": None})
            if status == "ok" and answer:  # the chat's first answer names it (a title typed by the user stays)
                task = asyncio.create_task(_make_title(session["id"], model, clean_text, answer, lang))
                _BACKGROUND.add(task)
                task.add_done_callback(_BACKGROUND.discard)
            if project and (ctx.files_changed or ctx.commands):
                # The time-machine snapshot runs after the answer is shown, so the user never waits for git.
                task = asyncio.create_task(_snapshot(root, f"aiiq: {clean_text[:80]}"))
                _BACKGROUND.add(task)  # keep a reference until it finishes
                task.add_done_callback(_BACKGROUND.discard)
        except BaseException as e:  # noqa: BLE001 - a failure while storing the result: the chat is never left busy
            if not done_sent:
                _emit(run, "error", code="internal", message=f"{type(e).__name__}: {e}")
                _emit(run, "done", status="error", text="".join(visible), steps=run.steps, context_used=0,
                      todos=run.todos, outputs=[], timing={}, changes=None)
            if isinstance(e, asyncio.CancelledError):
                raise
        finally:
            RUNS.pop(run.id, None)


async def _snapshot(root, message: str) -> None:
    try:
        await workspace.git_snapshot(root, message)
    except Exception:  # a failed snapshot never affects the chat
        pass


TITLE_PROMPT = ("Write a short title (2 to 6 words) for the conversation below, in {language}. Plain text only: no "
                "quotes, no Markdown, no emoji, no final period. Output only the title.")


async def _make_title(session_id: str, model: str, user_text: str, answer: str, lang: str) -> None:
    """After the first answer the chat gets a title that says what it is about (the first 60 characters of the
    message stood there before). A title the user typed is never touched."""
    try:
        row = db.query("SELECT title_auto FROM sessions WHERE id=?", (session_id,))
        # 1 = still the first words of the message; 2 = already named by a model (it was renamed on every later
        # answer, so the title kept changing); 0 = typed by the user.
        if not row or row[0]["title_auto"] != 1:
            return
        if router.is_local(model):
            # A local server runs one request at a time: a title call there (20-40 s on a CPU) would delay the
            # user's next message and push the chat out of the server's prompt cache. A cloud model the user set up
            # writes it instead; without one, the request's own first words are the title (no model call).
            model = router.side_model()
            if not model:
                return
        prompt = [{"role": "system", "content": TITLE_PROMPT.format(language=LANG_NAMES.get(lang, lang))},
                  {"role": "user", "content": f"USER: {user_text[:600]}\n\nASSISTANT: {answer[:600]}"}]
        title = ""
        # A reasoning model (gemma-4, qwen3...) can spend a small token budget on thinking and answer nothing: the chat
        # then kept the request's raw first words. Retry with room to think, then on the side model.
        tries = [(model, 200), (model, 1500)]
        if (side := router.side_model()) and side != model:
            tries.append((side, 300))
        for m_id, cap in tries:
            try:
                raw = await asyncio.wait_for(router.complete(m_id, prompt, {"max_tokens": cap, "think": False,
                                                                           "lane": "side"}), 120)
            except Exception:  # noqa: BLE001 - busy / out of quota: the next try
                continue
            raw = re.sub(r"<think>.*?</think>", "", raw or "", flags=re.S).strip()
            title = clean_title(raw.splitlines()[0] if raw else "")
            if 2 <= len(title) <= 70:
                break
        row = db.query("SELECT title_auto FROM sessions WHERE id=?", (session_id,))
        if 2 <= len(title) <= 70 and row and row[0]["title_auto"] == 1:
            db.execute("UPDATE sessions SET title=?, title_auto=2 WHERE id=?", (title, session_id))
            bus.publish("run", "title", {"session_id": session_id, "title": title})
    except Exception:  # noqa: BLE001 - the first words of the message stay as the title
        pass


def clean_title(text: str) -> str:
    """No Markdown or quotes in a chat title."""
    t = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text or "")
    t = re.sub(r"[*_`#>~\"“”«»]+", "", t)
    return re.sub(r"\s+", " ", t).strip(" .:-")[:70]


def steer(session_id: str, text: str, display: str | None = None) -> Run | None:
    """A message sent while the chat's task runs: stored in the chat and handed to the running task as guidance."""
    run = next((r for r in RUNS.values() if r.session["id"] == session_id), None)
    if not run:
        return None
    db.add_message(session_id, "user", display or text, {"steer": True})
    run.steer.append(text)
    return run


def start_run(session: dict, text: str, opts: dict) -> Run:
    run = Run(uuid.uuid4().hex[:12], session)
    RUNS[run.id] = run
    if opts.get("skip_user_msg"):  # a follow-up of messages already stored in the chat (see the end of execute)
        last = db.query("SELECT id FROM messages WHERE session_id=? AND role='user' ORDER BY id DESC LIMIT 1",
                        (session["id"],))
        run.user_msg_id = last[0]["id"] if last else 0
    else:
        run.user_msg_id = db.add_message(session["id"], "user", opts.get("display_text") or text,
                                         {"attachments": opts.get("attachments", []),
                                          **({"chips": opts["chips"][:6]} if opts.get("chips") else {})})
    run.task = asyncio.create_task(execute(run, text, opts))
    return run


def active_run(session_id: str) -> dict | None:
    return next((r.snapshot() for r in RUNS.values() if r.session["id"] == session_id), None)


def live_context(session_id: str) -> dict | None:
    """While a task runs, the meter's live numbers (the stored ones are from the end of the last task): what the
    running turn holds, the model it runs on and that turn's breakdown."""
    run = next((r for r in RUNS.values() if r.session["id"] == session_id), None)
    if not run or not run.model or run.session.get("context_used") is None:
        return None  # before the first model turn: the stored count (a 0 here made the meter jump to empty)
    return {"used": run.session["context_used"], "model": run.model, "stats": run.stats}


def any_run_active() -> bool:
    return bool(RUNS)


async def cancel_run(run_id: str) -> bool:
    run = RUNS.get(run_id)
    if not run:
        return False
    again = run.cancel.is_set()
    run.cancel.set()
    approvals.cancel_all_for(run_id)
    # Cancelled once: a second stop (double click, the chat deleted right after, the app closing) must not interrupt
    # the task while it stores its answer and leaves RUNS.
    if run.task and not again and not run.finishing:
        run.task.cancel()
    return True


async def cancel_session(session_id: str, wait: float = 8.0) -> None:
    """Stops the chat's task and waits until it has stored its result: whoever deletes or moves the chat next must not
    race with that (a deleted chat got its folder and an orphan message back)."""
    runs = [r for r in RUNS.values() if r.session["id"] == session_id]
    for r in runs:
        await cancel_run(r.id)
    tasks = [r.task for r in runs if r.task and not r.task.done()]
    if tasks:
        await asyncio.wait(tasks, timeout=wait)


async def shutdown(wait: float = 6.0) -> None:
    """The app is closing: every task is stopped and given a moment to write its checkpoint and its message."""
    tasks = [r.task for r in RUNS.values() if r.task and not r.task.done()]
    for run_id in list(RUNS):
        await cancel_run(run_id)
    if tasks:
        await asyncio.wait(tasks, timeout=wait)
