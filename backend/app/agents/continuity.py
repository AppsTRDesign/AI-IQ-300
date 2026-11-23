"""Nothing done is lost or done twice: checkpoints and resume after a stop, saved parts of files cut off, reasoning carried over a break, the app's record (ledger), model handover with the to-do list, and how long files are written after a break.

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

from .. import approvals, db, sessions, tokens, workspace
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



# --- crash-safe progress (run_state.json) ---------------------------------------------------------------------
# A task's real progress (tool calls with their results, the to-do list, files written) is written to the chat folder
# before every model turn. When the computer loses power, the app is closed, the provider keeps failing or the
# context is compressed, the next task in the chat gets this exact record, so "continue" resumes where it stopped
# and never redoes finished steps (the stored answer alone said nothing about the steps of an interrupted task).
RUN_STATE = "run_state.json"


RESUME_TAG = "[Unfinished earlier task - the app's exact record of what already ran]"


def _calls_done(messages: list[dict], first: int) -> list[str]:
    """One line per tool call of this task, with the start of its result (native calls and the tag protocol)."""
    out: list[str] = []
    results = {m.get("tool_call_id"): (m.get("content") or "") for m in messages[first:] if m["role"] == "tool"}
    for m in messages[first:]:
        for c in m.get("tool_calls") or []:
            a = c["arguments"] if isinstance(c.get("arguments"), dict) else {}
            what = a.get("path") or a.get("url") or a.get("query") or a.get("command") or a.get("name") or ""
            res = re.sub(r"\s+", " ", results.get(c.get("id"), ""))[:160]
            out.append(f"{c['name']} {str(what)[:120]} -> {res or 'no result'}".strip())
        if m["role"] == "user" and (m.get("content") or "").startswith("Tool results:"):
            for name, ok, body in re.findall(r'<result tool="([\w.-]+)" ok="(\w+)">\n?(.{0,160})', m["content"], re.S):
                out.append(f"{name} -> {'ok' if ok == 'true' else 'FAILED'}: {re.sub(r'\s+', ' ', body)}")
    return out


def _team_board(run: "Run") -> list[dict]:
    """Every team part of this task with its state, files and report: a resumed task skips the finished ones."""
    out: dict[str, dict] = {c.get("title"): c for c in run.carried_team if c.get("title")}
    for st in run.steps:
        for c in ((st.get("data") or {}).get("members") or []) if st.get("kind") == "team" else []:
            if c.get("title"):
                out[c["title"]] = {"title": c["title"], "task": c.get("task", ""), "state": c.get("state"),
                                   "model": c.get("model"), "stage": c.get("stage", 1), "files": c.get("files") or [],
                                   "report": (c.get("report") or "")[:1500], "steps": c.get("steps", 0)}
    return list(out.values())


def _checkpoint(run: "Run", messages: list[dict], first: int, request: str, status: str = "running") -> None:
    try:
        f = sessions.path(run.session["id"]) / RUN_STATE
        files = list(dict.fromkeys(s["data"].get("path") for s in run.steps
                                   if (s.get("data") or {}).get("path") and s.get("status") == "done"
                                   and (s.get("data") or {}).get("tool") in ("write_file", "edit_file", "make_doc", "delete_file")))
        state = {"run_id": run.id, "session_id": run.session["id"], "user_msg_id": run.user_msg_id, "status": status,
                 "ts": time.time(), "request": request[:4000], "model": run.model, "todos": run.todos,
                 "team": _team_board(run),
                 "calls": (run.carried_calls + run.done_calls + _calls_done(messages, first))[-150:],
                 "results": _results_kept(run.carried_results, messages, first),
                 "files": files[-80:],
                 "steps": [{k: s.get(k) for k in ("id", "kind", "title", "status", "ts")} | {
                     "detail": (s.get("detail") or "")[:400], "data": {k: v for k, v in (s.get("data") or {}).items()
                                                                        if isinstance(v, (str, int, float, bool))}}
                           for s in run.steps if s["kind"] not in ("thinking", "prepare")][-80:]}
        tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        tmp.replace(f)  # atomic: a power cut never leaves half a file
    except (OSError, ValueError, TypeError):
        pass


def _results_kept(carried: list, messages: list[dict], first: int, budget: int = 9000) -> list[dict]:
    """What the task's lookups returned (searches, pages, files read, command output), newest first within a
    budget: a resumed task - also on another model - works from these instead of fetching everything again."""
    found: list[dict] = list(carried)
    names = {c.get("id"): (c["name"], c.get("arguments") if isinstance(c.get("arguments"), dict) else {})
             for m in messages[first:] for c in m.get("tool_calls") or []}
    for m in messages[first:]:
        if m["role"] == "tool" and m.get("tool_call_id") in names:
            name, a = names[m["tool_call_id"]]
            if name in EVIDENCE_TOOLS and (m.get("content") or "").strip():
                what = a.get("path") or a.get("url") or a.get("query") or a.get("command") or ""
                found.append({"call": f"{name} {str(what)[:120]}".strip(), "output": (m["content"] or "")[:2500]})
        elif m["role"] == "user" and (m.get("content") or "").startswith("Tool results:"):
            for name, ok, body in re.findall(r'<result tool="([\w.-]+)" ok="(\w+)">\n?(.*?)\n?</result>', m["content"], re.S):
                if name in EVIDENCE_TOOLS and ok == "true" and body.strip():
                    found.append({"call": name, "output": body[:2500]})
    out, used = [], 0
    for r in reversed(found):
        if used + len(r["output"]) > budget:
            break
        out.append(r)
        used += len(r["output"])
    return list(reversed(out))


PARTIAL = "partial_call.json"


WRITERS = ("write_file", "make_doc")


# Tools whose arguments are a few words: thousands of characters streaming into one of them is a loop.
TINY_ARGS = frozenset({"my_location", "system_info", "hardware_info", "software_info", "mobile_info","need_tools", "web_search", "research", "fetch_url", "read_file",
                       "list_dir", "delete_file", "stop", "process", "browser_navigate", "browser_click", "browser_key",
                       "browser_scroll", "browser_wait", "browser_tabs", "browser_snapshot", "browser_screenshot",
                       "web_screenshot", "stock_photo", "places", "read_document"})
# Calls with a JSON body that is small in practice (an API request, MCP arguments, a to-do list): cut far later than
# the tiny ones. nemotron streamed one google call for 9 minutes (280K characters) before anything stopped it.
SMALL_ARGS = {"google": 24000, "mcp": 24000, "todo": 12000, "need_tools": 3000, "use_skill": 3000}


def _file_loop_check(run: "Run", loop_check: list) -> None:
    """A file streaming in that turned into one block repeated again and again (a generation loop: 30K characters of
    the same <script>): stop it early. The salvage keeps the written part with the repeats removed and the model
    continues from there, instead of writing the loop for minutes and handing it over as the file."""
    size = len(run.partial_tag) + sum(len(x) for s in run.partial_args.values() for x in s["args"])
    for slot in run.partial_args.values():
        n = sum(len(x) for x in slot["args"])
        if slot.get("name") in TINY_ARGS and n > 3000:
            # A call with a few short arguments (my_location, a search, a click) that keeps streaming: a generation
            # loop inside the arguments (seen live: "preparing my_location" growing for minutes). Cut now.
            run.file_loops += 1
            raise ProviderError("looping", f"the model kept writing the arguments of {slot['name']} ({n} characters "
                                           "for a call that takes a few words); call it again with short arguments")
        if n > SMALL_ARGS.get(slot.get("name") or "", 10 ** 9):
            run.file_loops += 1
            raise ProviderError("looping", f"the model kept writing one {slot['name']} call ({n} characters, a "
                                           "generation loop); call it again with a short body")
    tag_m = re.match(r'<(?:tools?\s+name="([\w.-]+)"|([\w.-]+)[\s>])', run.partial_tag) if run.partial_tag else None
    tag_name = (tag_m.group(1) or tag_m.group(2)) if tag_m else ""
    if len(run.partial_tag) > SMALL_ARGS.get(tag_name, 10 ** 9):
        run.file_loops += 1
        raise ProviderError("looping", f"the model kept writing one {tag_name} call ({len(run.partial_tag)} "
                                       "characters, a generation loop); call it again with a short body")
    if len(run.partial_tag) > 3000 and (m := tag_m) and (m.group(1) or m.group(2)) in TINY_ARGS:
        run.file_loops += 1
        raise ProviderError("looping", f"the model kept writing one {m.group(1) or m.group(2)} call "
                                       f"({len(run.partial_tag)} characters); call it again with short arguments")
    if len(loop_check) < 2:
        loop_check.append(0)
    if size - loop_check[1] < 3000:
        return
    loop_check[1] = size
    got = _partial_call(run)
    if not got:
        return
    from ..tools.editing import collapse_repeats
    _, removed = collapse_repeats(got[1].get("content", "")[-30000:])
    if removed >= 9:
        run.file_loops += 1
        raise ProviderError("looping", f"the model repeated the same block {removed} times while writing "
                                       f"{got[1].get('path')}; the written part is kept once and continued")


def _partial_call(run: "Run") -> tuple[str, dict, bool] | None:
    """The file-writing call that was streaming when a turn broke off: (tool, {path, content}, append)."""
    if run.partial_tag:
        m = re.match(r'<(?:tool|tools)\b[^>]*?name="(write_file|make_doc)"([^>]*)>(.*)', run.partial_tag, re.S) or \
            re.match(r"<(write_file|make_doc)\b([^>]*)>(.*)", run.partial_tag, re.S)
        if m:
            from .stream_parser import attrs as _attrs
            attrs = _attrs(m.group(2))
            return m.group(1), {"path": attrs.get("path", ""), "content": m.group(3)}, attrs.get("append") == "true"
    for slot in run.partial_args.values():
        if slot.get("name") not in WRITERS:
            continue
        raw = "".join(slot["args"])
        path = re.search(r'"path"\s*:\s*"((?:[^"\\]|\\.)*)"', raw)
        body = re.search(r'"content"\s*:\s*"', raw)
        if not (path and body):
            continue
        text = raw[body.end():]
        content = None
        for cut in range(0, 8):  # a cut escape sequence at the end: drop a few characters until it decodes
            try:
                content = json.loads('"' + (text[:len(text) - cut] if cut else text).rstrip("\\") + '"')
                break
            except ValueError:
                continue
        if content is None:
            continue
        append = bool(re.search(r'"append"\s*:\s*(true|"true")', raw))
        return slot["name"], {"path": json.loads('"' + path.group(1) + '"'), "content": content}, append
    return None


def _live_write(run: "Run", got: tuple[str, dict, bool]) -> None:
    """The file a model is writing goes into its real path while it streams (every 2 s, whole lines): the user sees
    it grow in the files pane, and if the stream breaks the written part is already on disk. Only where the app may
    write without asking (Settings > Agent > access), and only new files or continuations of a file this task wrote;
    an existing file is never replaced before its call has finished."""
    ctx = run.live_ctx
    tool, args, append = got
    if ctx is None or tool != "write_file" or not args.get("path"):
        return
    try:
        root = Path(ctx.root).resolve()
        target = (root / args["path"]).resolve()
        if root not in target.parents:
            return
        from ..tools.verify import is_binary_name
        if is_binary_name(target):
            return
        live = getattr(ctx, "live_files", None)
        if live is None:
            live = ctx.live_files = {}
        key = str(target)
        if key not in live:
            from .. import policy
            if policy.decide_file_write(target, root, ctx.mode).action != "allow":
                return
            if target.exists() and not append:
                # An existing file is replaced only when the whole new version has arrived: a rewrite streamed into
                # it live emptied it first, and a break then left only the cut-off rewrite (80K -> 0 seen live).
                return
            live[key] = target.read_text(encoding="utf-8", errors="replace") if target.exists() else None
        content = args.get("content") or ""
        if "\n" in content:
            content = content[:content.rfind("\n") + 1]
        base = live[key] or ""  # what the file held before this call: restored by live_restore
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(base + content, encoding="utf-8", newline="")
    except (OSError, ValueError):
        pass


def _persist_partial(run: "Run") -> None:
    """Every few seconds the call being written goes to disk too: after a power cut it is recovered."""
    now = time.time()
    if run.live_ctx is not None and now - run.live_at >= 2:
        run.live_at = now
        if got := _partial_call(run):
            _live_write(run, got)
    if now - run.partial_saved_at < 8:
        return
    run.partial_saved_at = now
    got = _partial_call(run)
    if not got or len(got[1]["content"]) < 300:
        return
    try:
        f = sessions.path(run.session["id"]) / PARTIAL
        tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps({"tool": got[0], "append": got[2], **got[1]}, ensure_ascii=False), encoding="utf-8")
        tmp.replace(f)
    except (OSError, ValueError):
        pass


def save_partial(root, tool: str, args: dict, append: bool) -> tuple[str, int] | None:
    """Writes a cut-off file body: into the file itself (write_file), or as the document's source text (make_doc),
    whole lines only. Returns (path written, characters)."""
    from ..tools import safe_io
    content = safe_io.clean_tail(args.get("content") or "")  # never end on a half character
    if "\n" in content:
        content = content[:content.rfind("\n") + 1]  # never keep half a line
    from ..tools.editing import collapse_repeats
    content = collapse_repeats(content)[0]  # a call cut off inside a generation loop keeps the loop once
    if len(content) < 200 or not args.get("path"):
        return None
    try:
        target = (Path(root) / args["path"]).resolve()
        if Path(root).resolve() not in target.parents:
            return None
        if tool == "make_doc":
            target = target.parent / ".doc-sources" / f"{target.name}.partial.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        old = target.read_text(encoding="utf-8", errors="replace") if target.is_file() else ""
        rel = target.relative_to(Path(root).resolve()).as_posix()
        if old.strip() and not append:
            from ..tools.file_tools import starts_over
            if not starts_over(old, content):
                append = True  # the next part sent as a plain write: it goes after what the file holds
            elif len(content) < len(old):
                # A rewrite of the file from its start, cut off shorter than the file already is: the file stays as
                # it was (a second break wiped 36K of game.js down to the 10K of the cut rewrite, seen live). The cut
                # part is kept beside it, never over it.
                side = target.with_name(target.name + ".cut-rewrite.txt")
                safe_io.atomic_write_text(side, content)
                return rel, len(old), "kept"
            else:
                _backup(target, old)
        if append and old:
            from ..tools.file_tools import trim_overlap
            content = trim_overlap(old, content)[0]
            # old + the saved part, swapped in whole and checked (an append in place left a half-written file when
            # the power went during the append itself)
            try:
                exact = target.read_bytes().decode("utf-8")  # strict: a file with foreign bytes keeps them as they are
            except UnicodeDecodeError:
                exact = None
            if exact is None:
                with open(target, "a", encoding="utf-8", newline="") as fh:
                    fh.write(("" if old.endswith("\n") else "\n") + content)
            else:
                safe_io.atomic_write_text(target, exact + ("" if exact.endswith("\n") else "\n") + content)
            return rel, len(content), "appended"
        safe_io.atomic_write_text(target, content)
        return rel, len(content), "written"
    except (OSError, ValueError):  # WriteError is an OSError: the earlier content was restored
        return None


def _backup(target: Path, text: str) -> None:
    """The previous version of a file about to be replaced: kept in .aiiq/backups next to the project."""
    try:
        root = next((p for p in [target.parent, *target.parents] if (p / ".aiiq").is_dir()), target.parent)
        bdir = root / ".aiiq" / "backups"
        bdir.mkdir(parents=True, exist_ok=True)
        (bdir / f"{target.name}.{time.strftime('%Y%m%d-%H%M%S')}").write_text(text, encoding="utf-8")
    except OSError:
        pass


def _salvage(run: "Run", ctx, messages: list[dict]) -> tuple[str, int] | None:
    """A turn broke off while a file was being written: keep what was written and tell the model to go on from
    there (append), instead of losing it and writing it all again."""
    got = _partial_call(run)
    run.partial_args, run.partial_tag = {}, ""
    if not got:
        return None
    if got[1].get("path"):  # the live copy goes back to how it was; the saved part is written once below
        from ..tools.file_tools import live_restore
        live_restore(ctx, Path(ctx.root) / got[1]["path"])
    saved = save_partial(ctx.root, *got)
    if not saved:
        return None
    path, n, mode = saved
    ctx.files_changed.append(path)
    _unclaim(run)
    full = (Path(ctx.root) / path).read_text(encoding="utf-8", errors="replace") if (Path(ctx.root) / path).is_file() else ""
    if mode == "kept":
        messages.append({"role": "user", "content": (
            f"[App note] The connection dropped while you were writing {got[1]['path']} again from its beginning. "
            f"That rewrite was cut off SHORTER than the file already is, so it was NOT applied: {path} still holds "
            f"its complete earlier version ({len(full)} characters). Its last lines are:\n...{full[-1500:]}\n\n"
            "Do not start the file over. Change only what must change with edit_file, or add what is missing with "
            f"write_file path=\"{path}\" append=true after that end. {_split_rule(True, run.model or '', run.tps)}")})
        _drop_partial_file(run.session["id"])
        return path, n
    saved = (path, n)
    # write_file to this path without append=true is joined to the saved part when it does not restart the file
    # (see registry.write_file): a model (or the next model after a switch) that "continued" with a plain write
    # wiped the saved 10K characters before.
    pend = getattr(ctx, "salvaged", None)
    if pend is None:
        pend = ctx.salvaged = {}
    pend[path] = full or got[1]["content"][:n]
    # The real end of the file on disk (not of the cut call): after an append it is the end of everything written,
    # and the model continues exactly from there instead of from what it remembers.
    tail = (full or got[1]["content"][:n])[-1200:]
    n = len(full) or n
    how = (f"continue writing it with write_file path=\"{path}\" append=true" if got[0] == "write_file" else
           f"continue the document's source with write_file path=\"{path}\" append=true, then make_doc "
           f"source=\"{path}\" path=\"{got[1]['path']}\"")
    messages.append({"role": "user", "content": f"[App note] The connection dropped while you were writing "
                     f"{got[1]['path']}. The {n} characters you had written are SAVED in {path} - do not write them "
                     f"again. It ends with:\n...{tail}\n\nNow {how}, starting right after that end (never write the "
                     f"file from its beginning again: that is the part already saved). "
                     f"{_split_rule(True, run.model or '', run.tps)} Do not read the file first."})
    _drop_partial_file(run.session["id"])
    return saved


def _unclaim(run: "Run") -> None:
    """The model ticked items "done" in the same reply that started a file, and the file was cut off before anything
    finished: those ticks are taken back (the list showed step 1 done while index.html had not been written)."""
    from .tooling import work_done
    from .runstate import _emit
    claims = run.todo_claims
    if not claims or not claims.get("items") or not run.todos or work_done(run) != claims.get("work"):
        return
    back = set(claims["items"])
    run.todo_claims = None
    for t in run.todos:
        if t["content"] in back and t["status"] == "completed":
            t["status"] = "pending"
    cur = next((t for t in run.todos if t["status"] != "completed"), None)
    for t in run.todos:
        if t["status"] == "in_progress" and t is not cur:
            t["status"] = "pending"
    if cur:
        cur["status"] = "in_progress"
    run.todos = [dict(t) for t in run.todos]
    _emit(run, "todos", todos=run.todos)


def _drop_partial_file(session_id: str) -> None:
    try:
        (sessions.path(session_id, create=False) / PARTIAL).unlink(missing_ok=True)
    except (OSError, ValueError):
        pass


RECORD_TAG = "[App record of this task so far - kept by the app, exact]"


CONTINUE_TAG = "[App note: connection dropped]"


THINK_CARRY = "[App note: your reasoning before the break]"


CARRY_MAX = 14000  # characters of carried reasoning (the start of the plan + its latest part)


def _carry_thinking(run: "Run", messages: list[dict]) -> bool:
    """A turn broke off (provider pause, timeout, drop, model switch) after the model had reasoned, often for minutes
    on a slow cloud model. That reasoning used to be thrown away, and every retry thought the whole task through again
    (18 minutes in "thinking" after a few drops). It goes into the next request instead, as the model's own plan, and
    that request is sent without reasoning where the provider allows it (run.no_think), so the model acts on it."""
    new = (run.last_thinking or "").strip()
    old = run.carry_thinking
    if len(new) < 400:
        text = old  # the broken turn barely thought (it broke early): the earlier carried plan stays
    elif old and new[:300] not in old:
        text = old + "\n[...continued after another break...]\n" + new
    else:
        text = new
    run.last_thinking = ""
    if len(text) < 400:
        return False
    if len(text) > CARRY_MAX:
        text = text[:3500] + "\n[...]\n" + text[-(CARRY_MAX - 3500):]
    run.carry_thinking = text
    secs = int(run.think_secs or 0)
    note = (f"{THINK_CARRY} The request broke off (provider pause / timeout / drop) after you had already reasoned"
            + (f" for about {secs // 60} min {secs % 60} s" if secs >= 30 else "") + ". That reasoning is below: it is "
            "your own plan and still valid, and every step above it is done and kept. Do NOT think the task through "
            "again and do not start over. Act on it now: make the tool call(s) it leads to, continuing from the first "
            "step that is not done yet (if it stopped mid-thought, finish that thought in a sentence or two, then act)."
            f"\n<previous_reasoning>\n{text}\n</previous_reasoning>")
    messages[:] = [m for m in messages if not str(m.get("content") or "").startswith(THINK_CARRY)]
    at = len(messages)
    if at >= 2 and str(messages[-1].get("content") or "").startswith(CONTINUE_TAG):
        at -= 2  # a half-written answer being continued keeps its note last
    messages.insert(at, {"role": "user", "content": note})
    run.no_think = len(text) >= 1500  # a real plan: the retry acts on it instead of reasoning for minutes again
    return True


LOOK_TOOLS = {"web_search", "research", "fetch_url", "web_screenshot", "stock_photo", "generate_image", "inspect_media",
              "places", "use_skill", "search_code", "list_dir", "symbols", "impact", "ask_model", "mcp"}


def _ledger(run: "Run") -> str:
    """What this task has really done, from the app's own step list (not from the conversation): files written and
    read, commands and lookups, the to-do list. Given to the model at every break - a dropped connection, a switch to
    another model, a smaller window, a resumed task - so no model writes, reads or runs the same thing again, whoever
    did it first."""
    files: dict[str, str] = {}
    reads: list[str] = []
    cmds: list[str] = []
    looks: list[str] = []
    for st in run.steps:
        d = st.get("data") or {}
        tool, ok, path = d.get("tool"), st.get("status") == "done", str(d.get("path") or "")
        if tool in ("write_file", "edit_file", "make_doc") and ok and path:
            files[path] = "edited" if tool == "edit_file" and files.get(path) != "written" else "written"
        elif tool == "delete_file" and ok and st.get("title"):
            files[str(st["title"])] = "deleted"
        elif tool in ("read_file", "read_document") and ok and path and path not in reads:
            reads.append(path)
        elif tool in ("run", "start") and st.get("status") in ("done", "error"):
            cmd = re.sub(r"\s+", " ", str(d.get("command") or st.get("title") or ""))[:110]
            cmds.append(f"{cmd} -> {'ok' if ok else 'FAILED'}")
        elif tool in LOOK_TOOLS and ok:
            looks.append(f"{tool} {str(st.get('title') or '')[:70]}".strip())
        elif tool == "team" and d.get("members"):
            looks.append("team: " + ", ".join(f"{c.get('title')} [{c.get('state')}]" for c in d["members"]))
    lines = []
    if run.carried_calls:
        lines.append("Done by the interrupted earlier task (still valid): " + "; ".join(run.carried_calls[-25:]))
    if files:
        lines.append("Files (on disk now): " + ", ".join(f"{p} ({how})" for p, how in list(files.items())[-40:]))
    if reads:
        lines.append("Files already read: " + ", ".join(reads[-25:]))
    if cmds:
        lines.append("Commands: " + "; ".join(cmds[-15:]))
    if looks:
        lines.append("Lookups: " + "; ".join(looks[-15:]))
    if run.todos:
        lines.append("To-do: " + "; ".join(
            f"[{'x' if t['status'] == 'completed' else '>' if t['status'] == 'in_progress' else ' '}] {t['content']}"
            for t in run.todos))
    if not lines:
        return ""
    return (f"{RECORD_TAG}\n" + "\n".join(lines)[:3500] + "\nAll of this is DONE and stays valid. Do not write, read, "
            "run or look up any of it again; change a written file only with edit_file. Go on with the first step that "
            "is not done yet.")


def _load_checkpoint(session_id: str) -> dict | None:
    try:
        return json.loads((sessions.path(session_id, create=False) / RUN_STATE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _drop_checkpoint(session_id: str) -> None:
    try:
        (sessions.path(session_id, create=False) / RUN_STATE).unlink(missing_ok=True)
    except (OSError, ValueError):
        pass


def resume_note(state: dict) -> str:
    """The record of an unfinished task, added to the next request (language-neutral, for the model)."""
    mark = {"completed": "x", "in_progress": ">"}
    todos = "  ".join(f"{i}. [{mark.get(t.get('status'), ' ')}] {t.get('content')}"
                      for i, t in enumerate(state.get("todos") or [], 1))
    if todos:  # the list is carried into the new task as it is: tick what the record shows done, never start over
        todos += (" ([x] done, [>] was in progress. If the record above shows an open item already finished, tick it "
                  "with todo done=[n] instead of doing it again; then continue with the first item really open.)")
    calls = "\n".join(f"- {c}" for c in (state.get("calls") or [])[-60:])
    files = ", ".join(state.get("files") or [])
    team_done = [c for c in state.get("team") or [] if c.get("state") == "done"]
    team = ("Team parts already FINISHED (never start them again; a new team call skips them by itself): " + "; ".join(
        f"{c['title']} ({c.get('model') or '?'}; files: {', '.join(c.get('files') or []) or '-'})" for c in team_done)
        + "\n") if team_done else ""
    results = "\n\n".join(f"### {r['call']}\n{r['output']}" for r in state.get("results") or [])
    return (f"{RESUME_TAG}\nRequest of that task: {state.get('request', '')[:1500]}\n"
            f"It stopped early ({state.get('status')}; it may have run on another model - the record is the same). "
            f"Steps that already ran (do NOT repeat them; their files exist):\n"
            f"{calls or '- none'}\n" + (f"Files written (they exist on disk): {files}\n" if files else "")
            + (f"To-do list: {todos}\n" if todos else "") + team
            + (f"\nResults those steps already returned - use them, do NOT search or fetch the same things again:\n"
               f"{results}\n\n" if results else "")
            + "If the latest message asks to continue (or is about that task): go on from the first unfinished step with "
              "what is above. Written files are read with read_file and reused (a written .md/.html source only needs "
              "make_doc source=<that file>); never rewrite or re-research what is already there. Otherwise ignore this "
              "record and answer the latest message.")


def recover_interrupted() -> int:
    """At start: a task that was running when the app stopped (power cut, crash, closed window) gets its message in
    the chat with the steps it had done, marked interrupted, so the user sees it and the next task can resume it."""
    n = 0
    for f in sessions.CHAT_DIR.glob(f"*/{sessions.SESSION}/{RUN_STATE}"):
        try:
            state = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if state.get("status") != "running":
            continue
        sid = state.get("session_id") or ""
        pf = f.parent / PARTIAL
        if pf.exists():  # a file was being written when the power went: its written part is kept
            try:
                part = json.loads(pf.read_text(encoding="utf-8"))
                row = db.query("SELECT project_id FROM sessions WHERE id=?", (sid,))
                if row:
                    root = workspace.session_root({"id": sid, "project_id": row[0]["project_id"]})
                    saved = save_partial(root, part.get("tool", "write_file"), part, bool(part.get("append")))
                    if saved:
                        state.setdefault("files", []).append(saved[0])
                        state.setdefault("calls", []).append(
                            f"{part.get('tool')} {part.get('path')} -> CUT OFF by the interruption: the first {saved[1]} "
                            f"characters are saved in {saved[0]}; read its end and continue with write_file append=true")
            except (OSError, ValueError):
                pass
            pf.unlink(missing_ok=True)
        if not db.query("SELECT 1 FROM sessions WHERE id=?", (sid,)):
            f.unlink(missing_ok=True)
            continue
        later = db.query("SELECT 1 FROM messages WHERE session_id=? AND role='assistant' AND id>?",
                         (sid, state.get("user_msg_id") or 0))
        if not later:
            lang = reply_language(state.get("request", ""), load_settings().get("language"))
            note = ui_text(lang, "ai_interrupted", "The task was interrupted (the app or computer stopped). The steps "
                           "it completed are kept; type \"continue\" to resume where it stopped.")
            steps = [{**s, "status": "error" if s.get("status") == "running" else s.get("status")} for s in state.get("steps") or []]
            db.add_message(sid, "assistant", note, {"steps": steps, "status": "interrupted", "model": state.get("model"),
                                                    "todos": state.get("todos") or []})
        state["status"] = "interrupted"
        try:
            from ..config import atomic_write
            atomic_write(f, json.dumps(state, ensure_ascii=False))
        except OSError:
            pass
        n += 1
    return n


HANDOVER = ("[App note: you are taking over this task from another model mid-way. Everything above (files written, "
            "commands run, the to-do list) is that model's work and stays: keep its files, structure, names and style, "
            "continue with the next open step, and finish a half-written file from where it ends (append). Do not "
            "rewrite or redesign files that are finished or nearly finished unless they are really broken - read "
            "them first if you need to change something.]")


def _short_desc(item: dict, n: int) -> str:
    d = str(item.get("description_en") or item.get("description") or item.get("title_en") or item.get("title") or "")
    d = re.sub(r"\s+", " ", d).strip()
    return d if len(d) <= n else d[:n - 1].rsplit(" ", 1)[0] + "…"


def _handover(run: "Run") -> str:
    """HANDOVER plus the to-do list as the app keeps it: the new model saw the old list only somewhere far up (or
    shortened), did not update it and did the whole job again from item 1."""
    if not run.todos:
        return HANDOVER
    cur = next((i for i, t in enumerate(run.todos, 1) if t.get("status") == "in_progress"), None) or \
        next((i for i, t in enumerate(run.todos, 1) if t.get("status") != "completed"), None)
    return (HANDOVER[:-1] + f" The to-do list (exact, kept by the app): {todo_board(run)}. Items marked [x] are DONE - "
            "do not redo them. " + (f"Continue with item {cur}; when it is finished: todo advance=true." if cur else
                                    "Every item is done: check the result once and give the final answer.") + "]")


SPLIT_HINT_HEAD = ("[App note: your previous tool call was cut off or the connection dropped while you were writing it, so "
                   "it did NOT run. Everything before it did run and is kept above - do not redo those steps. ")


def cap_chars(model: str, tps: float | None = None) -> tuple[int, int] | None:
    """(request limit s, characters that fit in it) for a provider that ends every request after a fixed time."""
    from ..llm import router
    cap = router.request_cap(model) if model else None
    if not cap:
        return None
    speed = max(15.0, min(200.0, float(tps or 35.0)))
    # 70% of the limit (the reasoning and the prompt reading come first), ~3.5 characters per token
    return int(cap), int(max(8000, min(60000, cap * 0.7 * speed * 3.5)) // 1000 * 1000)


def _split_rule(cont: bool = False, model: str = "", tps: float | None = None) -> str:
    """How long files are written after a break, from Settings > Agent > split writing. Off (the default) means one
    call however large: an app note that said "this provider drops long calls, write ~8,000-character parts for the
    rest of the task" overrode that setting after any single timeout, and the parts it caused (unclosed objects,
    half switch blocks, a syntax error after every part) broke files again and again. A MEASURED request time limit
    is different: there one call cannot be longer, so the parts are sized to fit it."""
    if got := cap_chars(model, tps):
        secs, chars = got
        return (f"This provider ends every request after about {secs} s (measured on this task's breaks), about "
                f"{chars:,} characters at this model's speed - one call cannot be longer. Send "
                + ("the rest" if cont else "the file") + f" in consecutive write_file append=true calls of up to "
                f"~{chars:,} characters each, every part ending at a line end; never start the file over. A file that "
                "is not finished yet may show a syntax error until its last part is written - that is expected.")
    split = int((load_settings().get("agent") or {}).get("split_write_chars") or 0)
    if split > 0:
        return (f"Send the rest in consecutive write_file append=true calls of up to ~{split:,} characters each "
                "(Settings > Agent > split writing); a file that is not finished yet may show a syntax error until "
                "its last part is written - that is expected, do not 'fix' it.")
    return ("Send " + ("the rest" if cont else "the file") + " in ONE call, however long (split writing is off in "
            "Settings > Agent; there is no size limit). The break was a network / provider pause, not a size limit.")


def split_hint(model: str = "", tps: float | None = None) -> str:
    return SPLIT_HINT_HEAD + _split_rule(False, model, tps) + " For documents, make_doc from a file you wrote (source=...).]"


EVIDENCE_TOOLS = {"research", "web_search", "fetch_url", "read_file", "read_document", "run", "places", "mcp",
                  "ask_model", "search_code"}


def todo_board(run: "Run") -> str:
    """The whole list with numbers and states, e.g. '1. [x] Write api.php  2. [>] Write app.js  3. [ ] Test' - the
    single source of truth given to a model that takes over or has lost track."""
    mark = {"completed": "x", "in_progress": ">", "pending": " "}
    return "  ".join(f"{i}. [{mark.get(t.get('status'), ' ')}] {t['content']}" for i, t in enumerate(run.todos, 1))


TODO_TRAILER = re.compile(r"\n?\[To-do \d+/\d+ done; now: .*?\]\s*$", re.S)


def without_todo_line(text: str) -> str:
    """A tool output without the to-do state the app added at its end: that line is no error (the stop message said
    'Last error: [To-do 2/7 done; now: ...]' after a build had passed)."""
    return TODO_TRAILER.sub("", text or "")


def todo_line(run: "Run") -> str:
    """The list's current state, added to tool results so every model (single or in a team) works along it."""
    if not run.todos or all(t["status"] == "completed" for t in run.todos):
        return ""
    cur = next((t["content"] for t in run.todos if t["status"] == "in_progress"), None) or \
        next((t["content"] for t in run.todos if t["status"] != "completed"), "")
    done = sum(t["status"] == "completed" for t in run.todos)
    return (f"\n[To-do {done}/{len(run.todos)} done; now: {cur}. When this item is finished: todo advance=true "
            "(never retype the list; add=[...] for new work found on the way).]")
