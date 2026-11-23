"""Running the tools a model called: parallel jobs, guards against repeats and closed tools, the live to-do list kept in step, team calls.

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
from .runstate import RUNS, Run, TOOL_TITLES, _emit, _step  # noqa: F401
from .guards import PAGE_TOOLS  # noqa: F401
from .continuity import EVIDENCE_TOOLS, todo_line  # noqa: F401


REPEAT_GUARD = {"fetch_url", "web_search", "research", "use_skill"}


# The request asks to run / test the result; tools that really did that
VERIFY_ASK = re.compile(r"test\s*et|\btest\b|dene(yin|yip|)\b|çalıştır(?!abil|ıl|ma[ksz])|başlat|doğrula|tarayıcıda|run it|start it|verify|"
                        r"in the browser|try it", re.I)


WEB_FILE = re.compile(r"\.(?:html?|php|jsx?|tsx?|vue|svelte|css|astro)$|(?:^|[\\/])package\.json$", re.I)


VERIFY_TOOLS = {"start", "web_screenshot", "browser_check", "browser_navigate", "browser_batch", "mobile_env",
                "browser_snapshot"}


# A run that checks something (an install or mkdir is not a test): tests, linters, requests to a page, the program itself
TEST_CMD = re.compile(r"\b(test|tests|pytest|jest|vitest|phpunit|unittest|mocha|playwright|cypress|curl|wget|"
                      r"Invoke-WebRequest|iwr|php\s+-l|lint|tsc|flutter\s+test|gradlew\s+\w*test|xcodebuild\s+test|"
                      r"node\s+\S+\.m?js|python\s+\S+\.py|php\s+\S+\.php)\b", re.I)


async def _wait_online(cancel: asyncio.Event, limit: float) -> bool:
    """Polls until names resolve and a well-known host answers again (this computer is back online), at most limit
    seconds or until the task is stopped."""
    import socket

    def online() -> bool:
        try:
            socket.getaddrinfo("one.one.one.one", 443)
            with socket.create_connection(("1.1.1.1", 443), timeout=3):
                return True
        except OSError:
            return False
    end = time.monotonic() + limit
    while time.monotonic() < end and not cancel.is_set():
        if await asyncio.to_thread(online):
            return True
        try:
            await asyncio.wait_for(cancel.wait(), 10)
        except asyncio.TimeoutError:
            pass
    return False


def _served(run) -> bool:
    """A server was started in this task (start tool)."""
    return any(isinstance(s.get("data"), dict) and s["data"].get("tool") == "start" for s in run.steps)


def _verified(run) -> bool:
    """Something was really run or looked at: a page opened, or a command that checks. A started server alone is not
    a test: an Expo app whose bundle answered 500 was reported as running because `start` printed its address, so
    once a server ran, only opening its page in a browser tool (console + network are reported there) counts.
    A task with no page at all (no server, no web file written: a CLI analysing a video, a script) is tested by
    running it: a rea-video survey/decompose run that worked was told "nothing was run or checked yet"."""
    served = tested = web = ran = False
    for s in run.steps:
        d = s.get("data") or {}
        if not isinstance(d, dict):
            continue
        tool = d.get("tool")
        if tool in PAGE_TOOLS or tool == "mobile_env":
            return True
        if tool == "start":
            served = True
        elif tool in VERIFY_TOOLS or (tool == "run" and TEST_CMD.search(str(d.get("command") or ""))):
            tested = True
        elif tool == "run" and s.get("status") == "done":
            ran = True
        if tool in ("write_file", "edit_file") and WEB_FILE.search(str((d.get("args") or {}).get("path") or d.get("path") or "")):
            web = True
    return (tested or (ran and not web)) and not served


PLAN_GATED = {"write_file", "edit_file", "run", "start", "make_doc", "generate_image", "delete_file"}


MEDIA_CAP = {"generate_image": 6, "stock_photo": 10, "generate_video": 4, "animate_image": 4, "web_screenshot": 16,
             "browser_screenshot": 16, "browser_check": 16}


BOOKKEEPING = {"todo", "need_tools", "use_skill", "remember"}  # never part of a loop signature

TODO_KEYS = {"advance", "done", "start", "add"}
_DONE_WORDS = {"completed", "complete", "done", "finished", "finish", "closed", "ok", "true", "x", "[x]", "✓", "✅"}
_START_WORDS = {"in_progress", "in progress", "inprogress", "started", "start", "doing", "active", "current", "working"}


def _item_no(current: list[dict], ref) -> int | None:
    """1-based number of the item a model means: a number, '#2', 'step 2', or (part of) its text."""
    s = str(ref or "").strip()
    if not s:
        return None
    if m := re.fullmatch(r"(?:#|step\s*|item\s*|madde\s*|adım\s*)?(\d{1,3})\.?", s, re.I):
        n = int(m.group(1))
        return n if 1 <= n <= len(current) else None
    import difflib
    key = re.sub(r"\W+", " ", s.lower()).strip()
    best, score = None, 0.0
    for i, t in enumerate(current, 1):
        c = re.sub(r"\W+", " ", t["content"].lower()).strip()
        r = 1.0 if key and (key in c or c in key) else difflib.SequenceMatcher(None, key, c).ratio()
        if r > score:
            best, score = i, r
    return best if score >= 0.8 else None


def todo_intent(spec: dict, body, current: list[dict]):
    """Every shape a model uses to tick its list, turned into advance / done / start (the call is changed in place;
    returns the body to use). The calculator, Google and Playwright runs sent {"id": 2, "status": "completed"},
    {"content": "<item>", "status": "completed"}, {"completed": [2]}, {"status": "done"} and a single item object as
    the body: none matched, every call answered "No change" and nemotron called todo 117 times in 66 turns."""
    if not current:
        return body
    obj = None
    if isinstance(body, str) and body.strip():
        try:
            from ..tools.agent_tools import loose_json
            obj = loose_json(body)
        except ValueError:
            obj = None
    # one object (or a list of objects) that names existing items with a status = ticks, not a new plan
    objs = [obj] if isinstance(obj, dict) and not (obj.get("items") or obj.get("todos")) else (
        obj if isinstance(obj, list) and obj and all(isinstance(o, dict) for o in obj) else [])
    # The body is an update only when every object in it names an item the list already has (a new plan that shares
    # a word or two with the old one is still a new plan).
    if objs and not all(any(o.get(k) not in (None, "") for k in ("id", "index", "item", "number", "num", "n", "step",
                                                                   "position", "task", "no", "completed", "tick"))
                        or _item_no(current, o.get("content") or o.get("title") or o.get("text") or "")
                        for o in objs):
        return body
    src = [spec] + objs
    done, start, used_body = [], [], False
    for o in src:
        status = str(o.get("status") or o.get("state") or "").strip().lower()
        ref = next((o[k] for k in ("id", "index", "item", "number", "num", "n", "step", "position", "task", "no")
                    if o.get(k) not in (None, "")), None)
        if ref is None and o is not spec:
            ref = o.get("content") or o.get("title") or o.get("text")
        nums = [n for n in (_item_no(current, r) for r in (ref if isinstance(ref, list) else [ref])) if n] if ref is not None else []
        if nums and status in _DONE_WORDS:
            done += nums
        elif nums and status in _START_WORDS:
            start += nums[:1]
        elif not nums and status in _DONE_WORDS and o is spec:
            spec["advance"] = True  # "status": "completed" alone: the item in progress is finished
        for k in ("completed", "complete", "finished", "finish", "tick", "check", "mark_done", "done_items", "checked"):
            v = o.get(k)
            if v not in (None, "", False, [], "false"):
                vals = v if isinstance(v, list) else re.split(r"[,;]\s*", str(v)) if not isinstance(v, bool) else []
                done += [n for n in (_item_no(current, x) for x in vals) if n]
        if o is not spec and (nums or any(k in o for k in ("completed", "complete", "tick", "mark_done"))):
            used_body = True
    if objs and len(objs) == len(current) and all(isinstance(o.get("content"), str) for o in objs) and not used_body:
        return body  # a whole list with statuses: the normal new-list path handles it
    if objs and used_body and len(objs) < len(current):
        body = ""  # the body was the update, not a plan
    elif objs and used_body and all(_item_no(current, o.get("content") or "") for o in objs):
        body = ""  # the same items again with new statuses: applied as ticks below
    if done:
        prev = spec.get("done")
        spec["done"] = list(dict.fromkeys(([prev] if prev and not isinstance(prev, list) else prev or []) + done))
    if start and "start" not in spec:
        spec["start"] = start[0]
    return body


def todo_noop(run, text: str) -> ToolResult:
    """A todo call that changed nothing. Twice in a row: the list is closed for the task (the app ticks it from the
    work done and at the final answer) and the model is told to move on - it never loops on the list again."""
    run.todo_noops = getattr(run, "todo_noops", 0) + 1
    if run.todo_noops >= 2:
        run.todo_closed = True
        return ToolResult(True, "No change again. The to-do list is now closed for this task and the app updates it "
                          "itself. Do not call todo again: continue with the next real step using the other tools, or "
                          "if everything is done, write the final answer now.")
    return ToolResult(True, text)


STUCK_WARN = 4  # failed tool rounds in a row: every 4th one the model is told to change the approach (never stopped)


# Tools that only read or look things up: several of them in one turn can run at the same time.
PARALLEL_SAFE = {"research", "web_search", "fetch_url", "read_file", "list_dir", "search_code", "symbols", "impact",
                 "read_document", "web_screenshot", "places", "my_location", "ask_model", "use_skill", "mcp",
                 "stock_photo", "inspect_media"}


TODO_DOC = {"pdf": ("pdf",), "docx": ("word", "docx"), "pptx": ("sunum", "powerpoint", "pptx", "slayt", "slide", "presentation"),
            "xlsx": ("excel", "xlsx", "tablo", "spreadsheet"), "html": ("html", "web"),
            "any": ("rapor", "report", "belge", "document", "doküman")}


TODO_RUN = re.compile(r"[çc]al[ıi][şs]t[ıi]r|test|dene|do[ğg]rula|kontrol|run|execute|verify|check|demo", re.I)


# A server / emulator started with `start` finishes the item that says so ("php -S ... sunucusunu başlat")
TODO_START = re.compile(r"ba[şs]lat|sunucu|server|serve|start|launch|emülatör|emulator|localhost", re.I)


TODO_FIX = re.compile(r"d[üu]zelt|onar|gider|iyile[şs]tir|\bfix|repair|debug|resolve|improve|polish", re.I)
TODO_BROWSER = re.compile(r"taray[ıi]c|browser|ekran|g[öo]rsel|\bui\b|aray[üu]z|oyna|play", re.I)

TODO_FILE = re.compile(r"[\w./\\-]+\.(?:[a-z]{1,5})\b", re.I)

WORK_KINDS = {"file", "edit", "command", "process", "document", "image_gen", "video_gen", "video_edit", "speech", "photo"}


def work_done(run: "Run") -> int:
    """Finished real actions so far (files, commands, documents, media): a to-do claim is backed by one of these."""
    return sum(1 for s in run.steps if s.get("status") == "done" and s.get("kind") in WORK_KINDS)


def _auto_todo(run: "Run", name: str, args: dict, res: ToolResult) -> None:
    """Keeps the live to-do list in step with what really happened, also when a model forgets to tick it: a written
    file ticks the item that names it, a successful command the item about running/testing; the next item starts."""
    if not run.todos or not res.ok or name == "todo":
        return
    open_items = [t for t in run.todos if t["status"] != "completed"]
    if not open_items:
        return
    hit = None
    path = str((res.data or {}).get("path") or (args or {}).get("path") or "")
    if path and name in ("write_file", "edit_file", "make_doc"):
        base = Path(path).name.lower()
        run.written_names.add(base)
        if re.search(r"SYNTAX ERROR|does not parse|JavaScript error", res.output or "", re.I):
            return  # a file that does not parse yet (its first part of several, or broken) is not a finished item

        def covered(t: dict) -> bool:
            # "index.php, style.css ve app.js yaz": the item is done when every file it names is written, not
            # after the first one (the list showed 1/9 done while data_helper.php had only its first part).
            named = {Path(x).name.lower() for x in TODO_FILE.findall(t["content"])}
            return base in t["content"].lower() and (len(named) <= 1 or named <= run.written_names)
        hit = next((t for t in open_items if base and covered(t)), None)
        ext = Path(path).suffix.lower().lstrip(".")
        words = TODO_DOC.get(ext, ()) + TODO_DOC["any"]
        if not hit and name == "make_doc":  # "prepare the PDF report" is done when the PDF exists
            hit = next((t for t in open_items if any(w in t["content"].lower() for w in words)), None)
        elif not hit and name == "write_file":  # "write report.html" while the file is called rapor.html
            hit = next((t for t in open_items if t["status"] == "in_progress"
                        and any(w in t["content"].lower() for w in words)), None)
        if hit:  # earlier steps the model left open are behind it now (it collected the data, then wrote)
            for t in run.todos:
                if t is hit:
                    break
                if t["status"] == "in_progress":
                    t["status"] = "completed"
    elif name in ("run", "start"):
        # Only the item being worked on now: any successful command ("php -v") used to tick the first open item that
        # mentions running / testing, even item 6 while item 1 was still in progress, so the list showed later steps
        # finished out of order.
        # A started server only finishes an item about starting it; "test in the browser and fix the errors" was ticked
        # the moment `python -m http.server` ran, while the testing and fixing had not begun. An item that also asks
        # to fix / debug, or to check in the browser, is never closed by a command: only the model knows it is done.
        def fits(t: dict) -> bool:
            c = t["content"]
            if TODO_FIX.search(c):
                return False
            if name == "start":
                return bool(TODO_START.search(c)) and not TODO_BROWSER.search(c)
            return bool(TODO_RUN.search(c)) and not TODO_BROWSER.search(c)
        hit = next((t for t in open_items if t["status"] == "in_progress" and fits(t)), None)
    if not hit:
        return
    hit["status"] = "completed"
    run.auto_ticked += 1
    if not any(t["status"] == "in_progress" for t in run.todos):
        nxt = next((t for t in run.todos if t["status"] == "pending"), None)
        if nxt:
            nxt["status"] = "in_progress"
    run.todos = [dict(t) for t in run.todos]
    _emit(run, "todos", todos=run.todos)


# Calls that write a file: several in one turn run at the same time when each writes a different file.
PARALLEL_WRITE = {"write_file", "edit_file", "make_doc"}


def _job_path(job) -> str:
    a = job[1] if isinstance(job[1], dict) else {}
    return str(a.get("path") or "").replace("\\", "/").lower()


def _mcp_server(job) -> str:
    a = job[1] if job and isinstance(job[1], dict) else {}
    return str(a.get("server") or "").lower() if job and job[0] == "mcp" else ""


def _job_files(job) -> set[str]:
    """Every file a call touches: its path and the source it reads (make_doc source=). A make_doc reading the .md that
    a write_file of the same reply writes ran at the same moment, read the half-written file and said 'No content'."""
    a = job[1] if isinstance(job[1], dict) else {}
    return {str(a.get(k) or "").replace("\\", "/").lower().lstrip("./") for k in ("path", "source")} - {""}


async def _run_jobs(run: "Run", ctx: ToolContext, jobs: list, offer, limits: dict, malformed: bool = False) -> list:
    """Runs one turn's tool calls. With parallel work on, consecutive read/lookup calls run together (results keep
    the call order); anything that changes files or runs commands runs alone, in order."""
    out: list = [None] * len(jobs)
    parallel = limits.get("parallel_tools", True)
    i = 0
    while i < len(jobs):
        job = jobs[i]
        if job is None:
            out[i] = ToolResult(False, "Malformed tool call.") if malformed else None
            i += 1
            continue
        group = [i]
        if parallel and (job[0] in PARALLEL_SAFE or job[0] in PARALLEL_WRITE):
            paths = _job_files(job)
            wrote = job[0] in PARALLEL_WRITE
            while len(group) < 8 and group[-1] + 1 < len(jobs) and jobs[group[-1] + 1]:
                nxt = jobs[group[-1] + 1]
                # A look at something written earlier in the same reply (write a page, then screenshot it) waits for
                # the write: run together, the screenshot found no file yet.
                if nxt[0] in PARALLEL_SAFE and wrote and nxt[0] in ("web_screenshot", "read_file", "list_dir",
                                                                     "search_code", "read_document"):
                    break
                if _mcp_server(nxt) and _mcp_server(nxt) in {_mcp_server(jobs[k]) for k in group}:
                    # Two calls to one MCP server (playwright: one browser page) at the same moment raced each
                    # other - navigate and read the console of a page not loaded yet. One server, one call at a time.
                    break
                if nxt[0] in PARALLEL_SAFE and not (nxt[0] == "read_file" and _job_files(nxt) & paths):
                    group.append(group[-1] + 1)
                elif nxt[0] in PARALLEL_WRITE and _job_path(nxt) and not (_job_files(nxt) & paths):
                    paths |= _job_files(nxt)  # a different file: written at the same time
                    wrote = True
                    group.append(group[-1] + 1)
                else:
                    break
        if len(group) == 1:
            out[i] = await _exec(run, ctx, *job, offer)
        else:
            res = await asyncio.gather(*(_exec(run, ctx, *jobs[k], offer) for k in group), return_exceptions=True)
            for k, r in zip(group, res):
                out[k] = r if isinstance(r, ToolResult) else ToolResult(False, f"{type(r).__name__}: {r}")
        for k in group:
            _auto_todo(run, jobs[k][0], jobs[k][1], out[k])
            if out[k].ok and jobs[k][0] in EVIDENCE_TOOLS:  # what was really read: the base of later fact checks
                ctx.evidence |= registry_figures(out[k].output)
                ctx.sourced = True
        i = group[-1] + 1
    # The last result of the turn carries the list's state (the model sees where the plan stands every turn).
    if (line := todo_line(run)) and out and isinstance(out[-1], ToolResult) and jobs[-1] and jobs[-1][0] != "todo":
        out[-1] = ToolResult(out[-1].ok, out[-1].output + line, out[-1].data)
    return out


async def _exec(run: Run, ctx: ToolContext, name: str, args: dict, body: str,
                allowed: set[str] | None = None) -> ToolResult:
    """Run a tool call; a call that keeps failing with the same error (a model stuck in a loop) is stopped."""
    if name in run.blocked:
        return ToolResult(False, f"'{name}' is switched off for this task after failing the same way 3 times. "
                                 "Do this part another way (for example write the files yourself), then finish.")
    # One reply generating calls in a loop (write images/gallery1.jpg ... gallery45.jpg, each refused): after the same
    # kind of failure 4 times in this turn, or 30 calls in one turn, the rest is skipped without running or tracing.
    turn_calls = run.turn_counts.get(run.turn_idx, 0) + 1
    run.turn_counts = {run.turn_idx: turn_calls}
    sig_hits = {k: v for k, v in run.turn_fail_sigs.items() if k[0] == run.turn_idx}
    if turn_calls > 30 or any(v >= 4 and k[1] == name for k, v in sig_hits.items()):
        return ToolResult(False, "Skipped: this reply repeated the same failing call (or made more than 30 calls); "
                                 "nothing more of it was run. Read the last error and do ONE different step.")
    # Media tools made in a loop (menu_card1.jpg ... menu_card27.jpg, each a new AI image taking seconds to minutes):
    # every call succeeds and has new arguments, so nothing else sees it. A page needs a handful; past the cap the
    # model is told to use what it has.
    if (name in PLAN_GATED and not run.todos and allowed is None
            and len(parts := request_parts(ctx.goal or "")) >= 3):
        # The system works plan-first (SYSTEM_CONTRACT rule 1): a multi-part job does not start writing or running
        # before its plan exists. Twice the model is shown the exact call; then the app opens the plan itself from the
        # request's own parts, so the job never stalls on this rule.
        run.plan_refusals += 1
        if run.plan_refusals <= 2:
            example = json.dumps([{"content": p, "status": "in_progress" if i == 0 else "pending"}
                                  for i, p in enumerate(parts[:4])], ensure_ascii=False)
            return ToolResult(False, f"Refused: plan first. This job has several parts and there is no to-do list yet. "
                                     f"Call todo now with the WHOLE plan in the user's language, e.g. todo {example} "
                                     "(all parts, including running and testing), then do this step again.")
        run.todos_auto = True
        run.todos = [{"content": c, "status": "in_progress" if i == 0 else "pending"} for i, c in enumerate(parts)]
        _emit(run, "todos", todos=run.todos)
    if name not in ("todo", "read_file", "list_dir", "search_code", "edit_file"):
        # The same call with only a number changing (menu_card1.jpg, menu_card2.jpg ... gallery45.jpg): a counting
        # loop of a weak model, whatever the tool. Six are allowed, then it is stopped.
        pattern = f"{name}:" + re.sub(r"\d+", "#", json.dumps(args, sort_keys=True, ensure_ascii=False, default=str)
                                      + (body or "")[:200])
        if re.search(r"\d", json.dumps(args, ensure_ascii=False, default=str)):
            run.counted[pattern] = run.counted.get(pattern, 0) + 1
            if run.counted[pattern] > 6:
                return ToolResult(False, f"Not run: {name} was already called 6 times with only a number changing "
                                         "(file1, file2, ...) - that is a counting loop. Reuse what you made and go on "
                                         "with the next step of the plan.")
    if (cap := MEDIA_CAP.get(name)) is not None:
        run.media_calls[name] = run.media_calls.get(name, 0) + 1
        if run.media_calls[name] > cap:
            return ToolResult(False, f"Not run: {name} was already used {cap} times in this task - that is enough. "
                                     "Reuse the images already made (the same picture may appear on several cards), "
                                     "and go on with the next step of the plan.")
    if name in ("run", "start"):
        # The exact command that already failed twice with the same error is not run a third time (a weak model sent
        # the same broken sqlite3 "..." line nine times): the result cannot change, only the route can.
        ckey = f"{name}:{json.dumps(args, sort_keys=True, ensure_ascii=False)}:{body.strip()}"
        prev = run.outcomes.get(ckey)
        if prev and prev[1] >= 2 and prev[2] is False:
            hint = error_playbook(prev[3]) if prev[3] else ""
            return ToolResult(False, "Not run again: this exact command already failed "
                                     f"{prev[1]} times with the same error (shown above). Change the route, not the "
                                     "flags: " + (hint or "another tool, a script file run with its interpreter, or "
                                     "check the assumption that failed."))
    if run.tools_off:  # no failure count closes the tools (user: no circuit breaker); only a pure repeat loop does
        return ToolResult(False, "Tools are closed for this task (the same failures kept coming back). Nothing was run. "
                                 "Write the answer now: what was done, the exact error that blocks the rest, and what "
                                 "the user can do (a missing program, a permission, another source).")
    if run.folder_snap and not run.folder_snap.done() and name not in READ_ONLY:
        try:  # the "before" picture must be complete before anything can change a file
            await asyncio.shield(run.folder_snap)
        except Exception:
            pass
    t = time.monotonic()
    res = await _run_tool(run, ctx, name, args, body, allowed)
    run.perf["tools"].append({"name": name, "ms": (time.monotonic() - t) * 1000, "ok": res.ok})
    # Different calls failing one after another (unzip a file that is not there, list, unzip again...) are a loop too:
    # the per-error count above never sees two equal errors. Make the model change the approach, then stop it.
    # Counted per model turn: ten write_file calls of one turn refused for the same mistake (photos written as text)
    # are one wrong idea, and pausing every tool for it left the model unable to use the right tool.
    ckey = f"{name}:{json.dumps(args, sort_keys=True, ensure_ascii=False, default=str)}:{(body or '').strip()}"
    if changes_state(name, args, body):
        # Something was changed since (a daemon restarted, a config edited): the same status poll giving the same
        # answer afterwards is news ("still not running"), not a loop - counted again from 1. A run polled `ruflo
        # task status` between restarts and `daemon stop` itself got "same result 4 times" and a debug turn.
        for k, v in list(run.outcomes.items()):
            if k != ckey:
                run.outcomes[k] = (v[0], 0, *v[2:])
    if name in ("run", "start", "browser_check", "web_screenshot", "edit_file", "read_file", "browser_snapshot"):
        # The same call giving the same result again and again (run create_db.php / read the .db, 15 times): each
        # one "succeeds", so no failure counter sees the loop. The third identical result is turned into a failure.
        digest = hashlib.sha1(re.sub(r"\d{2}:\d{2}:\d{2}|\b\d{9,}\b|process_id=\w+", "", res.output).encode()).hexdigest()
        prev = run.outcomes.get(ckey)
        count = prev[1] + 1 if prev and prev[0] == digest else 1
        run.outcomes[ckey] = (digest, count, res.ok, res.output[-1500:])
        if count >= 3:
            res = ToolResult(False, res.output + f"\n\n[App note] This exact call has now given the same result {count} "
                             "times: repeating it changes nothing. Work out why the result is not what you expect "
                             "(a script name run alone may only open the file - run it with its interpreter, e.g. "
                             "php create_db.php; a file may be written somewhere else; the error may be in another "
                             "file), say it in one line, then do something different.",
                             # the command itself worked: a loop, not a failure - the final answer must not be held
                             # as "the last command failed" (a status poll repeated 6 times was)
                             {**(res.data or {}), "repeat_ok": True} if res.ok else res.data)
    if not res.ok:
        sig = (run.turn_idx, name, re.sub(r"[\w./\\-]+\.\w{1,5}\b|\d+", "#", res.output)[:160])
        run.turn_fail_sigs = {k: v for k, v in run.turn_fail_sigs.items() if k[0] == run.turn_idx}
        run.turn_fail_sigs[sig] = run.turn_fail_sigs.get(sig, 0) + 1
        res = recurring_error(run, name, args, body, res)
    bumped = False
    if res.ok:
        run.fail_streak = 0
    elif run.fail_turn != run.turn_idx:
        run.fail_streak += 1
        run.fail_turn, bumped = run.turn_idx, True
    if bumped and run.fail_streak % STUCK_WARN == 0:
        res = ToolResult(False, res.output + f"\n\n[App note] {run.fail_streak} tool calls in a row failed: you are stuck. "
                         "Do not repeat or slightly vary the same step. Read the error text, say its cause in one "
                         "line, then take a DIFFERENT route: the exact paths list_dir showed, download with fetch_url "
                         "save=..., install or use the missing program, another source. Never overwrite a project "
                         f"file you could not read. If you do not know the cause, web_search the exact error line first.", res.data)
    # Reading tools are never switched off: without read_file a model "checked" a file by overwriting it.
    # Nor the tools every project needs: write_file switched off after three refused photo writes left a weak model
    # unable to write any file at all.
    if not res.ok and name not in ("run", "start", "read_file", "list_dir", "search_code", "read_document",
                                   "write_file", "edit_file", "todo"):
        key = f"{name}:{res.output[:200]}"
        run.failures[key] = run.failures.get(key, 0) + 1
        if run.failures[key] >= 3:
            run.blocked.add(name)
            res = ToolResult(False, res.output + f"\n\nThis failed 3 times with the same error, so '{name}' is now "
                                                  "switched off for this task. Do the work another way.", res.data)
    return res


def _merge_team_calls(calls: list[dict]) -> list[dict]:
    """Models often send each team part as its own parallel 'team' call: run them as one team instead."""
    teams = [c for c in calls if c["name"] == "team" and isinstance(c.get("arguments"), dict)]
    if len(teams) < 2:
        return calls
    members = []
    for c in teams:
        a = c["arguments"]
        members += a["members"] if isinstance(a.get("members"), list) else [a] if a.get("task") else []
    first = teams[0]
    return [({**c, "arguments": {"members": members}} if c is first else {**c, "merged": True}) if c in teams else c
            for c in calls]


# Tools that need the internet (a browser / fetch on localhost does not: see _needs_net)
NET_TOOLS = {"web_search", "research", "places", "my_location", "stock_photo", "generate_image", "generate_video",
             "animate_image", "mcp_search", "text_to_speech", "ask_model"}
URL_TOOLS = {"fetch_url", "browser_navigate", "web_screenshot"}
LOCAL_URL = re.compile(r"^(?:https?://)?(?:localhost|127\.|0\.0\.0\.0|\[::1\]|[\w.-]+\.(?:localhost|test)\b)|^file:", re.I)


def _needs_net(name: str, args: dict) -> bool:
    if name in NET_TOOLS:
        return True
    if name in URL_TOOLS:
        url = str(args.get("url") or args.get("href") or "")
        return bool(url) and not LOCAL_URL.search(url.strip())
    return False


async def _hold_offline(run: Run) -> bool:
    """This computer is offline: wait (a live step, the user can stop the task) until it is back. True when back."""
    from .. import netwatch
    sid = _step(run, "retry", "offline", "running", "", data={"attempt": 1, "until_online": True})
    t0 = time.monotonic()
    back = await netwatch.wait_online(run.cancel)
    _step(run, "retry", "offline", "done", "", step_id=sid,
          data={"attempt": 1, "until_online": True, "seconds": int(time.monotonic() - t0)})
    return back


async def _run_tool(run: Run, ctx: ToolContext, name: str, args: dict, body: str,
                    allowed: set[str] | None = None) -> ToolResult:
    """Runs one tool call. A call that needs the internet while this computer is offline waits for the connection
    instead of failing: a failed web search used to go into the model's history as "nothing found" and the repeat
    guard then refused the same search once the connection was back."""
    from .. import netwatch
    net = _needs_net(name, args)
    if net and not netwatch.is_online() and not await _hold_offline(run):
        return ToolResult(False, "Not run: this computer is offline and the task was stopped.")
    res = await _run_tool_once(run, ctx, name, args, body, allowed)
    if net and not res.ok and netwatch.looks_like_network(res.output) and not await netwatch.check_now():
        run.seen.discard(f"{name}:{json.dumps(args, sort_keys=True, ensure_ascii=False)}:{(body or '').strip()}")
        if await _hold_offline(run):
            res = await _run_tool_once(run, ctx, name, args, body, allowed)
    return res


def mcp_route(name: str, args: dict, body: str):
    """An MCP server's tool called by its own name ("github/search_repositories", "github__search_repositories",
    "github.search_repositories") instead of through mcp: the app answered "Unknown tool", the model concluded the
    GitHub tools were off and fell back to web searches. Routed to mcp when that server is connected."""
    m = re.fullmatch(r"([\w-]+?)(?:/|__|\.|:)([\w.-]+)", name or "")
    if not m:
        return None
    try:
        from .. import mcp_client
        servers = set(mcp_client.servers_cfg() or {})
    except Exception:  # noqa: BLE001
        return None
    server = next((s for s in servers if s.lower() == m.group(1).lower()), None)
    if not server:
        return None
    inner = {k: v for k, v in (args or {}).items() if k != "_raw"}
    arguments = body.strip() if body and body.strip().startswith("{") else json.dumps(inner, ensure_ascii=False)
    return "mcp", {"server": server, "tool": m.group(2), "arguments": arguments}, ""


def _query_words(q: str) -> frozenset:
    return frozenset(w for w in re.findall(r"\w+", q.lower()) if len(w) > 1 or w.isdigit())


def near_duplicate_search(run, query: str) -> str | None:
    """The third search that is only a reshuffle of earlier ones ("AI IQ 300 GitHub", "AI IQ 300 model GitHub",
    "GitHub AI IQ 300 model repository"...: seven in a row, the same results each time) is not sent: the model gets
    told to change the route. Word sets overlapping 60 % or more count as the same search."""
    words = _query_words(query)
    if not words:
        return None
    same = sum(1 for w in run.queries if len(words & w) / len(words | w) >= 0.6)
    run.queries.append(words)
    if same < 2:
        return None
    hint = ""
    if "github" in words or "repo" in words or "repository" in words:
        hint = (" For GitHub use the GitHub route instead: `gh search repos \"<name>\" --limit 10`, `gh repo view "
                "<owner>/<repo>`, or fetch_url https://api.github.com/search/repositories?q=<name> (skill github).")
    return ("Not searched: this is the same search as earlier ones with the words reshuffled, and those found nothing "
            "new. Change the route (another source, a site's own search or API, a different angle) or answer with what "
            "the results above show and say what could not be found." + hint)


PATH_ALIASES = ("file_path", "filepath", "filePath", "file_name", "filename", "fileName", "file", "target_file",
                "output_path", "output", "out", "dest", "destination")


def path_alias(name: str, args: dict) -> dict:
    """A tool that takes `path` called with another name for it (write_file file_path=..., filename=...): the call
    failed with "Missing required argument 'path'" while the step title already showed the file (nemotron)."""
    spec = TOOLS.get(name)
    if not spec or "path" not in spec.params or str(args.get("path") or "").strip():
        return args
    for k in PATH_ALIASES:
        if k not in spec.params and isinstance(args.get(k), str) and args[k].strip():
            out = {kk: vv for kk, vv in args.items() if kk != k}
            out["path"] = args[k].strip()
            return out
    return args


def _unwrap_args(name: str, args: dict, body: str) -> tuple[dict, str]:
    """A call whose body is '<arguments>{"owner": ..}</arguments>' (nemotron, every GitHub call in a row): the wrapper
    goes. A JSON object inside becomes the tool's arguments, except for mcp / google, whose body is that JSON. Values
    that are only the wrapper's opening tag (fetch_url url="<arguments>") are dropped."""
    from ..tools.agent_tools import unwrap_arg
    inner = unwrap_arg(body or "")
    if inner is body or not isinstance(inner, str):
        return args, body
    args = {k: v for k, v in args.items() if not re.fullmatch(r"\s*</?(arguments?|parameters?|args?)\b[^>]*>?\s*", str(v))}
    from .continuity import TINY_ARGS
    if name in TINY_ARGS and inner.startswith("{"):  # short-argument tools only: a file body stays a file body
        try:
            obj = json.loads(inner)
        except ValueError:
            obj = None
        if isinstance(obj, dict):
            return {**{k: v if isinstance(v, str) else json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict))
                       else str(v) for k, v in obj.items()}, **args}, ""
    return args, inner


async def _run_tool_once(run: Run, ctx: ToolContext, name: str, args: dict, body: str,
                         allowed: set[str] | None = None) -> ToolResult:
    if name not in TOOLS and (routed := mcp_route(name, args, body)):
        name, args, body = routed
    if name not in TOOLS:
        return ToolResult(False, f"Unknown tool '{name}'. Available: {', '.join(TOOLS)}")
    args = path_alias(name, args)
    if allowed is not None and name not in allowed and not run.restricted:
        # The model knows the tool from the capability map and called it before opening its group: open the group
        # and run the call, instead of an error that made it give up ("I have no text-to-speech tool"). A skill's
        # tools: list only narrows what is offered, so a tool outside it runs too (permissions still apply).
        run.unlocked |= {g for g, names in GROUP_TOOLS.items() if name in names}
        allowed = None
    if allowed is not None and name not in allowed:
        if run.soft_gate:
            return ToolResult(False, f"Tool '{name}' is not open yet: this request looked like a question. If the user "
                                     "really asks for work (files, commands, a fix), call need_tools groups=\"files\" "
                                     "first and then this tool; otherwise answer in chat.")
        return ToolResult(False, f"Tool '{name}' is not available for this request (the user asked a question; "
                                 "answer in chat, and only change files when asked).")
    if "_raw" in args:
        return ToolResult(False, "Invalid JSON arguments for this tool call. Send a valid JSON object.")
    args, body = _unwrap_args(name, args, body)
    # The same read-only call twice in one task (a model looping over the same page) is answered from memory.
    key = f"{name}:{json.dumps(args, sort_keys=True, ensure_ascii=False)}:{body.strip()}"
    if name in REPEAT_GUARD and key in run.seen:
        run.repeats += 1
        return ToolResult(True, "You already ran this exact call in this task; its result is above. Do not repeat it: "
                                "use what you have, try a different source, or give the answer now.")
    if name in REPEAT_GUARD:
        run.seen.add(key)
    if name in ("web_search", "research") and (msg := near_duplicate_search(run, str(args.get("query") or body or ""))):
        run.repeats += 1
        return ToolResult(False, msg)
    if name in ("list_dir", "read_file", "search_code"):
        # Nothing was written or run since the same call: its answer cannot have changed (a weak model listed two
        # folders in turn 40 times). Point it at what it already has instead of running it again.
        fs_key = f"{key}#{run.fs_epoch}"
        if fs_key in run.seen:
            return ToolResult(False, "Same call as before and nothing was written or run since, so the result is the same "
                                     "as above. Use the exact paths that result showed (they are from the working "
                                     "folder), or do the next step (write, run, start) now.")
        run.seen.add(fs_key)
    elif name in ("write_file", "edit_file", "delete_file", "run", "start", "stop", "mcp", "google", "make_doc",
                  "edit_video", "fetch_url"):  # fetch_url / google can save a download
        run.fs_epoch += 1
    if name == "need_tools":  # opens tool groups for the next turns (no trace step: it is bookkeeping)
        raw_groups = args.get("groups") or body or ""
        try:
            wanted = json.loads(raw_groups) if str(raw_groups).strip().startswith("[") else str(raw_groups).split(",")
        except json.JSONDecodeError:
            wanted = str(raw_groups).split(",")
        ok = {str(g).strip().lower() for g in wanted} & set(GROUP_TOOLS)
        if run.soft_gate and ({str(g).strip().lower() for g in wanted} & {"files", "work", "all", "code", "run"} or ok):
            # The model decided this "question" is real work: every tool comes back from the next turn on.
            run.soft_gate, run.gate_lifted = False, True
            run.unlocked |= ok
            return ToolResult(True, "All work tools (write_file, edit_file, run, start, ...) are available from your next "
                                    "step" + (f", plus {', '.join(sorted(ok))}" if ok else "") + ". Go on with the work.")
        if not ok:
            return ToolResult(False, f"Unknown group. Choose from: {', '.join(GROUP_TOOLS)}.")
        run.unlocked |= ok
        names = sorted(set().union(*(GROUP_TOOLS[g] for g in ok)))
        return ToolResult(True, f"Opened {', '.join(sorted(ok))}: {', '.join(names)} can be called from now on.")
    if name == "todo":  # shown as the live task list, not as a trace step
        spec = dict(args)
        if isinstance(body, str) and body.strip().startswith("{"):
            try:
                spec.update(json.loads(body))
            except ValueError:
                pass
        elif isinstance(body, str) and re.match(r"^\s*(?:advance|done|start|add)\s*[=:]", body, re.I):
            # <tool name="todo">advance=true</tool>: the short update written as the body
            spec.update({k.lower(): v.strip().strip("\"'") for k, v in
                         re.findall(r"(advance|done|start|add)\s*[=:]\s*(\[[^\]]*\]|\"[^\"]*\"|'[^']*'|[^\s,;]+)", body, re.I)})
            if isinstance(spec.get("add"), str) and spec["add"].startswith("["):
                try:
                    spec["add"] = json.loads(spec["add"])
                except ValueError:
                    spec["add"] = [spec["add"].strip("[]")]
            body = ""
        if run.todo_closed:
            # The model kept calling todo without changing anything: the list is the app's from here on.
            return ToolResult(True, "The to-do list is closed for this task (it is updated by the app now). Do not call "
                              "todo again: do the next real step with the other tools, or write the final answer.")
        before = json.dumps(run.todos, ensure_ascii=False)
        body = todo_intent(spec, body, run.todos)
        # Native calls send every field, empty ones too (advance=false, done=[], start=0, add=[] beside a new list):
        # those keys used to make the call a "short update", so the new list was dropped and an item called "[]"
        # appeared (nemotron: "the todo list seems to be getting reset"). Only fields that say something count.
        for k in ("advance", "done", "start", "add"):
            v = str(spec.get(k, "")).strip().lower()
            if k in spec and (v in ("", "[]", "none", "null", "false", "0", "no")
                              or (k == "start" and not re.search(r"[1-9]", v))):
                spec.pop(k)
        from ..tools.agent_tools import loose_json
        try:
            listed = loose_json(body) if isinstance(body, str) and body.strip() else None
        except ValueError:
            listed = None
        if isinstance(listed, dict):
            listed = listed.get("items") or listed.get("todos")
        if listed:  # a whole list: a new plan, never patched by the other fields of the same call
            for k in ("advance", "done", "start", "add"):
                spec.pop(k, None)
        elif isinstance(body, str) and re.fullmatch(r"\s*(?:\[\s*\]|null|none)?\s*", body, re.I):
            body = ""
        if run.todos and not body.strip() and not ({"advance", "done", "start", "add"} & spec.keys()):
            # Nothing to change: the list as it is, instead of "The list is empty" (the model then believed its
            # list was gone and retyped it again and again).
            from .continuity import todo_board
            return todo_noop(run, f"No change. The to-do list as the app keeps it: {todo_board(run)}. Tick an "
                             "item with done=[its number] or advance=true; do not retype the list.")
        if run.auto_ticked and str(spec.get("advance", "")).lower() in ("true", "1", "yes"):
            # The app already ticked the item the model just finished (a command / file named it): its "advance"
            # means that one, so it must not finish the next item too (step 2 showed done before it started).
            spec.pop("advance")
            if not ({"done", "start", "add"} & spec.keys()):
                spec["add"] = []  # still a short update: the list stays as the app moved it
        run.auto_ticked = 0
        if (not run.todos and {"advance", "done", "start"} & spec.keys() and not spec.get("items")
                and not (isinstance(body, str) and body.strip())):
            # ticking a list that does not exist: "The list is empty" made a model resend done=[1,2] turn after turn
            return ToolResult(True, "There is no to-do list in this task, so there is nothing to tick. Do not call "
                              "todo again: give the final answer now.")
        if (patched := todo_patch(run.todos, spec)) is not None:  # advance / done / start / add: no retyped list
            body = json.dumps(patched, ensure_ascii=False)
        res = await TOOLS[name].fn(ctx, args, body)
        if res.ok:
            todos = [dict(t) for t in res.data["todos"]]
            # A model that ticks a later item has finished the earlier one it left "in progress".
            last = max((i for i, t in enumerate(todos) if t.get("status") == "completed"), default=-1)
            for t in todos[:last]:
                if t.get("status") == "in_progress":
                    t["status"] = "completed"
            # Never backwards: a stale list (two todo calls in one parallel turn, or a model resending an old copy)
            # must not reopen an item already finished.
            done_before = {t["content"].strip().lower() for t in run.todos if t.get("status") == "completed"}
            for t in todos:
                if t["content"].strip().lower() in done_before:
                    t["status"] = "completed"
            # A new list in the middle of a task (the next phase) used to replace the old one: its items vanished and
            # the total was unclear. Items of the earlier list the new one does not repeat stay at the top (in
            # progress ones count as done: the model moved on), the new items follow.
            import difflib
            if run.todos_auto:
                # The app's stand-in list (from the request / the written plan) gives way to the model's own list:
                # merging the two showed the same steps twice in two languages.
                run.todos_auto = False
            elif run.todos:
                norm =lambda c: re.sub(r"\W+", " ", c.lower()).strip()  # noqa: E731
                new_keys = [norm(t["content"]) for t in todos]

                def repeated(c: str) -> bool:  # the same item, perhaps reworded a little
                    k = norm(c)
                    kw = set(k.split())
                    return any(k == n or k in n or n in k or difflib.SequenceMatcher(None, k, n).ratio() >= 0.8
                               or (kw and len(kw & set(n.split())) / len(kw | set(n.split())) >= 0.5)
                               for n in new_keys)
                # Only finished work of the earlier list stays (in progress counts as finished: the model moved on).
                # Its still-open items are the model's old plan, which the new list replaces: kept, they showed the
                # same steps twice in other words (4 items became 7) and the open copies sent the model round again
                # and again ("Next: draw the flowchart. Keep going." after the answer was given three times).
                kept = [{**t, "status": "completed"} for t in run.todos
                        if t["status"] in ("completed", "in_progress") and not repeated(t["content"])]
                if kept:
                    todos = (kept + todos)[:40]
            # A big request planned as one or two items ("Create project structure", marked done at once while most
            # of the job was still ahead): the request's own parts that the list does not cover are added after it,
            # pending, so the list shows the whole job and its real progress.
            if len(todos) < 3 and len(parts := request_parts(ctx.goal or "")) >= 3:
                have =[re.sub(r"\W+", " ", t["content"].lower()).strip() for t in todos]
                for p in parts:
                    k = re.sub(r"\W+", " ", p.lower()).strip()
                    if not any(k in h or h in k or difflib.SequenceMatcher(None, k, h).ratio() >= 0.7 for h in have):
                        todos.append({"content": p, "status": "pending"})
            # One item in progress at a time, the first open one the model marked; the others wait.
            first = next((i for i, t in enumerate(todos) if t["status"] == "in_progress"), None)
            for i, t in enumerate(todos):
                if t["status"] == "in_progress" and i != first:
                    t["status"] = "pending"
            if first is None and any(t["status"] == "completed" for t in todos):
                nxt = next((t for t in todos if t["status"] == "pending"), None)
                if nxt:
                    nxt["status"] = "in_progress"
            # What this call claims finished, and how much real work was done by then: if the file that should
            # deliver it is cut off before anything else finishes, the claim is taken back (see _salvage).
            was_done = {t["content"] for t in run.todos if t.get("status") == "completed"}
            run.todo_claims = {"items": [t["content"] for t in todos if t["status"] == "completed"
                                         and t["content"] not in was_done], "work": work_done(run)}
            run.todos = todos
            _emit(run, "todos", todos=run.todos)
            if json.dumps(run.todos, ensure_ascii=False) == before:
                return todo_noop(run, res.output)
            run.todo_noops = 0
        return res
    # a label is plain text: "Bilgisayar Donanım Raporu</h1>" was shown as the step's title
    first_line = next((t for t in (re.sub(r"<[^>]*>?", " ", ln).strip() for ln in body.strip().splitlines()[:8]) if t),
                      "")[:120] if body.strip() else ""
    argv = args.get("argv") if isinstance(args.get("argv"), list) else None
    label = args.get("path") or args.get("url") or args.get("id") or first_line or (" ".join(map(str, argv))[:120] if argv else name)
    if name == "team":  # never the raw JSON of the members
        from .team import parse_members
        label = " · ".join(str(m.get("title") or "?")[:40] for m in parse_members(body.strip() or args.get("members"))
                           if isinstance(m, dict))[:160] or name
    elif name == "mcp":
        label = f"{args.get('server', '?')}/{args.get('tool', '?')}"
    elif name == "google":  # "GET gmail/v1/users/me/messages" - the API and path, not the whole long URL
        u = re.sub(r"^https://(?:www\.)?", "", str(args.get("url") or "")).replace(".googleapis.com", "")
        label = f"{str(args.get('method') or 'GET').upper()} {u.split('?')[0][:110]}"
    elif name == "save_catalog":
        label = f"{args.get('kind', 'skills')}/{args.get('name') or ''}".rstrip("/")
    elif name == "web_screenshot":
        label = args.get("url") or first_line or name
        if label.lower().startswith("file:"):  # a local page: its name, not the user's full folder path
            label = re.sub(r"^.*[\\/]", "", label.split("?")[0]) or label
    elif name in BROWSER_TOOLS:
        label = _browser_label(name, args, body)
    kind = TOOL_TITLES.get(name, name)
    sid = _step(run, kind, label, "running", data={"tool": name, "args": {} if name == "team" else args})
    ctx.step_id = sid
    try:
        res = await TOOLS[name].fn(ctx, args, body)
    except PermissionError as e:
        res = ToolResult(False, f"DENIED: {e}")
    except KeyError as e:
        # a missing argument, or a value of another shape than the tool expects (an object where a list goes:
        # "Missing required argument: 0" alone sent a model guessing)
        res = ToolResult(False, f"Missing required argument {e}, or a value has the wrong shape (e.g. an object "
                                f"where a list is expected). Check the tool's description of each field.")
    except Exception as e:  # tool bugs are reported back to the model
        res = ToolResult(False, f"{type(e).__name__}: {e}")
    res.output = redact(res.output)  # stored API keys never reach the model or the trace
    if name in ("run", "start") and (url := OPENS_URL.search(f"{body}\n{args.get('argv') or ''}")):
        # Exit code 0 here only means a browser window opened: the model used to report this as "downloaded and
        # installed". Say plainly what really happened.
        res.output += (f"\n[App note: this only opened {url.group(1)} in the user's own web browser. Nothing was "
                       "downloaded, installed or checked by it. Download with Invoke-WebRequest -OutFile / curl.exe -o "
                       "or install with a package manager, and never claim otherwise.]")
    if name == "ask_model" and res.data.get("model"):
        label = res.data["model"]
    if name == "remember" and res.data.get("scope"):
        label = res.data["scope"]
    detail = (body or res.output) if name == "write_file" and res.ok else res.output if name == "write_file" else res.data.get("diff") or res.output if name == "edit_file" else res.output
    _step(run, kind, label, "done" if res.ok else "error", detail,
          data={"tool": name, "args": {} if name == "team" else args, **res.data, "output": res.output[:4000],
                **({"command": redact(body)[:6000]} if name in ("run", "start") and body else {})}, step_id=sid)
    return res


# The user asks for something to be run or measured (not only written): printed code is not an answer.
# A run that only looks (status, list, logs, version, existence checks, reading a file) changes nothing.
READ_RUN = re.compile(r"^\s*(?:start-sleep[^;]*;\s*|sleep\s+\d+\s*[;&]+\s*)?(?:get-content|gc|type|cat|more|less|head|tail|"
                      r"ls|dir|gci|get-childitem|get-item|test-path|resolve-path|select-string|sls|grep|rg|findstr|echo|"
                      r"write-output|start-sleep|sleep|timeout(?:\.exe)?\s+/t|get-command|gcm|where(?:\.exe)?|which|get-process|get-service|tasklist|netstat|"
                      r"git\s+(?:status|log|diff|show|branch)|[\w.@/-]+(?:\s+[\w-]+)?\s+(?:status|list|ls|show|info|"
                      r"--version|-v|-V|--help|-h|help|logs?|get|doctor)\b(?!\s*\S*\s*(?:--fix|--set)))", re.I)
STATE_TOOLS = {"write_file", "edit_file", "delete_file", "move_file", "start", "stop", "make_doc", "mcp_add",
               "browser_click", "browser_type", "browser_fill", "google"}


from .ledger import error_sig  # noqa: E402 - the same signature the chat ledger stores for earlier tasks


def recurring_error(run: Run, name: str, args: dict, body: str, res: ToolResult) -> ToolResult:
    """The same error coming back after changes ("fixed" three times, the same error each time) is a fix that does not
    reach the cause. Nothing is stopped or switched off for it (the user's rule: every error is shown and worked on,
    no circuit breaker); the model is told plainly that its fixes miss, what it already tried, and how to find the
    cause - from the 3rd time on, and again every 3 more. An error an earlier task of the chat also hit is named too."""
    sig = error_sig(res.output)
    if len(sig) < 8:
        return res
    e = run.err_sigs.setdefault(sig, {"n": 0, "tries": []})
    e["n"] += 1
    e["tries"].append(f"{name} {(body or json.dumps(args, ensure_ascii=False, default=str))[:90]}".strip())
    e["tries"] = e["tries"][-6:]
    notes = []
    if e["n"] == 1 and sig in run.prior_errs:
        notes.append(f"This same error also stopped task {run.prior_errs[sig]} of this chat: what was done then did not "
                     "remove it. Look for its cause first instead of repeating that fix.")
    if e["n"] >= 3 and e["n"] % 3 == 0:
        tried = "\n".join(f"  - {t}" for t in e["tries"][:-1])
        notes.append(f"This error has come back {e['n']} times in this task, after your changes. Your fixes are not "
                     f"reaching its cause. Already tried:\n{tried}\nBefore the next change: read the whole error and "
                     "the exact file and line it names; say the root cause in one sentence; change THAT. If the cause is "
                     "unclear, search the exact error message (web_search) or add a check that prints the failing value. "
                     "Keep working on it - just not the same way.")
        if hint := error_playbook(res.output):
            notes.append(hint)
    if not notes:
        return res
    return ToolResult(False, res.output + "\n\n[App note] " + "\n".join(notes), res.data)


def changes_state(name: str, args: dict | None, body: str) -> bool:
    if name in STATE_TOOLS:
        return name != "google" or str((args or {}).get("method") or "GET").upper() != "GET"
    if name == "run":
        cmd = (body or str((args or {}).get("command") or "") or " ".join(map(str, (args or {}).get("argv") or []))).strip()
        return bool(cmd) and not all(READ_RUN.match(part) for part in re.split(r"\s*(?:;|&&|\|\|)\s*", cmd) if part.strip())
    return False


RUN_ASK = re.compile(r"[çc]al[ıi][şs]t[ıi]r|\brun\b|execute|test\s*e[td]|dene\b|[öo]l[çc]|measure|benchmark|sonucu?\s*s[öo]yle",
                     re.I)


RUN_ASK = _extend(RUN_ASK, "run")


# "as Markdown / an .md file": the answer goes into a .md file, which opens in the editor (Monaco).
MD_WORDS = re.compile(r"markdown|\.md\b|\bmd\s*(dosya|olarak|format|file|çıktı)|\bmd\b\s*$", re.I)


OPENS_URL = re.compile(r"(?:Start-Process|\bstart\b|explorer(?:\.exe)?|\bopen\b|xdg-open|rundll32\s+url\.dll\S*)"
                       r"[\s\"',\[]+(?:-FilePath\s+)?[\"']?(https?://[^\s\"']+)", re.I)


async def _close_visible_browser(run: Run) -> None:
    """A visible browser window this task used is closed when the task ends (it used to stay open on the desktop).
    The profile keeps sign-ins; another task still using the window keeps it open. A hidden one is left to idle out."""
    from ..tools.browser import AGENT
    used = any((s.get("data") or {}).get("tool") in BROWSER_TOOLS or s.get("kind") == "team" for s in run.steps)
    others = any(r is not run and any((s.get("data") or {}).get("tool") in BROWSER_TOOLS for s in r.steps)
                 for r in RUNS.values())
    if used and AGENT.running() and not AGENT.headless and not others and not AGENT.lock.locked():
        try:
            await AGENT.close()
        except Exception:
            pass


def _readable(data: dict) -> str:
    """A tool's side note (policy decision, approval, background process, model error) as plain lines for the
    trace; the structured data stays in the step's data field, never shown as raw JSON."""
    op = data.get("op") or {}
    what = " ".join(str(x) for x in (op.get("tool"), op.get("path") or op.get("command") or op.get("url")) if x)
    lines = [
        what,
        data.get("command") and f"{data.get('shell') or ''} $ {data['command']}".strip(),
        data.get("category") and f"({data['category']})",
        data.get("action") and str(data["action"]).upper(),
        "; ".join(map(str, data.get("reasons") or [])),
        data.get("model") and f"{data['model']}: {data.get('error') or ''}".rstrip(": "),
    ]
    return "\n".join(l for l in lines if l)
