"""Agent run loop. The default role is a natural assistant; @agent mentions and /skill mentions shape it.
Tools are called with the provider's native function calling when the model supports it, otherwise with a
text tag protocol. Failed commands switch the next turn to the debugger role. Progress is published as run
events so the chat shows a collapsible activity trace."""
from __future__ import annotations

import asyncio
import base64
import itertools
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
from ..tools.registry import READ_ONLY, TOOLS, ToolContext, ToolResult, clip, split_args, tool_schemas, tools_prompt
from ..tools.browser_tools import BROWSER_TOOLS, label as _browser_label
from . import catalog
from .stream_parser import LEAK, THINK_OPENERS, StreamSplitter, ToolCall, extract_inline_calls, parse_tool

# Prompt texts and the intent/check rules live in their own modules; their names are re-exported here.
from .prompts import *  # noqa: F401,F403
from .checks import *  # noqa: F401,F403
from .prompts import HISTORY_MESSAGES, LOCAL_HISTORY, OS_NAME, SHELLS, SUMMARY_TAG, DEFAULT_ROLE, SYSTEM_CORE, CAP_HEAD, CAPABILITIES, WORK_TOOLS, WORK_RULES_LEAN, CAP_HEAD_LEAN, CAPABILITIES_LEAN, CHAT_NOTE, ABILITY_ASK, RULE_TOPICS_LEAN, BROWSER_GUIDE_LEAN, WEB_TOOLS, WORK_RULES, RULE_TOPICS, SCREENSHOT_RULE, ENV_SECTION, rule_topics, WEB_RULES, TAG_PROTOCOL  # noqa: F401
from .checks import NOT_FOUND, LANG_NAMES, SCRIPTS, TR_CHARS, TR_WORDS, EN_WORDS, _CJK, _load_intents, INTENTS, intent_alt, _extend, _lang_rx, LANG_WORD_RX, _lang_counts, reply_language, SMALL_TALK, ACTION, WORK, QUESTION, CORE_TOOLS, WEB_WORDS, GROUP_TOOLS, GROUPED, GROUP_WORDS, tool_groups, STRONG_BROWSER, BROWSER_WORDS, CODE_NOT_RUN, HOWTO, SHELL_FENCES, FENCE, CMD_START, fenced_commands, is_small_talk, FILE_NAME, _unread_files, CURRENT_INFO, needs_research, is_knowledge_question, ANNOUNCE, PROMISE, VISUAL_ASK, is_promise, is_announcement, FILE_CLAIM, ACTION_ECHO, CHANGE_REQUEST, CHANGE_CLAIM, FILE_EDIT_ASK, FILE_REF, DELIVER_VERB, DELIVERABLES, CLAIMED_FILE, _shown_files, tool_hint, missing_deliverables, FOREIGN_SCRIPT, TRANSLATE_HINT, LATIN_LANGS, CONTINUE_WORDS, wrong_language, _LANG_FILES, ui_text, think_reply_reminder, language_rule  # noqa: F401



@dataclass
class Run:
    id: str
    session: dict
    cancel: asyncio.Event = field(default_factory=asyncio.Event)
    task: asyncio.Task | None = None
    steps: list[dict] = field(default_factory=list)
    text: str = ""  # live visible answer, for snapshots when a client re-opens the chat
    role: str = DEFAULT_ROLE
    user_msg_id: int = 0
    stats: dict = field(default_factory=dict)  # context breakdown of the last model turn
    todos: list[dict] = field(default_factory=list)  # live task list kept by the model (todo tool)
    seen: set = field(default_factory=set)  # read-only calls already made in this task (see REPEAT_GUARD)
    repeats: int = 0  # repeated read-only calls answered from memory; at 3 the web tools close for the task
    # A rewrite was requested: the shown answer stays on screen until the new text starts (no blank flicker).
    hold: bool = False
    noted: bool = False  # this turn's narration already moved into the trace (tool call started)
    thinking_blocks: list | None = None  # Anthropic: this turn's signed thinking blocks, returned with its tool calls
    prompt_est: int = 0  # unscaled estimate of the prompt of the running model turn
    unlocked: set = field(default_factory=set)  # tool groups the model opened with need_tools
    model: str = ""  # the model of the running turn (can change mid-task: quota switch); its window is the meter's cap
    summarized_at: int = 0  # message count right after the last in-task summary (summaries need new steps first)
    done_calls: list = field(default_factory=list)  # tool calls folded into in-task summaries so far
    failures: dict = field(default_factory=dict)  # "tool:error" -> count (loop guard, see _exec)
    blocked: set = field(default_factory=set)  # tools switched off for this task after 3 identical failures
    t0: float = field(default_factory=time.monotonic)
    folder_snap: asyncio.Task | None = None  # the working folder as it was when the task started (see changes.py)
    partial: dict | None = None  # the tool call being written when a turn failed (name, chars): stall hints
    truncated: dict | None = None  # a tool call the provider cut off (output limit / early end)
    split_hint: bool = False  # the model was already told to write large files in parts
    carried_calls: list = field(default_factory=list)  # steps of an interrupted earlier task this task resumes
    carried_results: list = field(default_factory=list)  # and what those steps found (so nothing is fetched twice)
    carried_team: list = field(default_factory=list)  # team parts of that task (finished ones are not run again)
    started: float = field(default_factory=time.time)  # wall clock, for the live "1 min 30 s" in the chat
    steer: list = field(default_factory=list)  # messages the user sent while the task runs (guidance, not a new task)
    kept_answers: list = field(default_factory=list)  # complete answers written before a follow-up message arrived
    partial_args: dict = field(default_factory=dict)  # native tool calls streaming in: index -> {name, args[]}
    partial_tag: str = ""  # a tag-protocol tool call streaming in
    stalls: int = 0  # times the provider stopped mid-answer in this task (2: the task moves to another model)
    restricted: bool = False  # a chat-only / read-only task: tools outside its set are never opened on demand
    partial_saved_at: float = 0.0  # last time the streaming call was written to disk (power-cut safety)
    silent_writer: bool = False  # the provider sends tool calls only at the end (no live progress)
    whole_calls: bool = False  # a big native tool call arrived in one piece at the end (no streamed arguments)
    # (model, our estimate, the provider's real prompt count) of the last request that reported its real size: the
    # next request's size is that real count plus the change since, so the meter follows the provider's numbers.
    anchor: tuple | None = None
    # Where the time went: model turns (wait for the first token, total), tool calls, side calls (summaries, fixes).
    perf: dict = field(default_factory=lambda: {"turns": [], "tools": [], "side_ms": 0.0, "first_ms": None, "prep_ms": None})

    chat: bool = False  # a conversation reply: streamed into the chat as the answer (see reply_mode)
    finishing: bool = False  # the task is storing its result: a second stop must not interrupt that
    memory_relief: int = 0  # times this task's local window was made smaller because RAM ran low

    def snapshot(self) -> dict:
        return {"run_id": self.id, "session_id": self.session["id"], "text": self.text, "steps": self.steps,
                "role": self.role, "todos": self.todos, "started": self.started, "chat": self.chat,
                "approvals": approvals.pending_for(self.id), "seq": bus.last_seq}


# The timing of recent tasks, for /api/perf (percentiles of first answer, model waits, tools, overhead).
PERF: deque = deque(maxlen=300)


def _timing(run: "Run") -> dict:
    """One task's time split: first answer, preparation, model (waiting for the first token / streaming), tools by
    name, the team, side calls; what is left is the app's own overhead."""
    p = run.perf
    total = (time.monotonic() - run.t0) * 1000
    model = sum(t["total_ms"] for t in p["turns"])
    tools: dict[str, dict] = {}
    for t in p["tools"]:
        x = tools.setdefault(t["name"], {"n": 0, "ms": 0.0, "max_ms": 0.0, "failed": 0})
        x["n"] += 1
        x["ms"] += t["ms"]
        x["max_ms"] = max(x["max_ms"], t["ms"])
        x["failed"] += 0 if t["ok"] else 1
    tools_ms = sum(t["ms"] for t in p["tools"])
    r = lambda v: int(round(v)) if v is not None else None  # noqa: E731
    return {"total_ms": r(total), "first_ms": r(p["first_ms"]), "prep_ms": r(p["prep_ms"]), "model_ms": r(model),
            "model_wait_ms": r(sum(t["wait_ms"] for t in p["turns"])), "turns": len(p["turns"]),
            "slowest_wait_ms": r(max((t["wait_ms"] for t in p["turns"]), default=0)),
            "tools_ms": r(tools_ms), "tools": {k: {**v, "ms": r(v["ms"]), "max_ms": r(v["max_ms"])} for k, v in tools.items()},
            "team_ms": r(tools.get("team", {}).get("ms", 0.0)), "side_ms": r(p["side_ms"]),
            "retry_ms": r(p.get("retry_ms", 0.0)),  # waiting after provider errors (rate limits, overload)
            "overhead_ms": r(max(0.0, total - model - tools_ms - p["side_ms"] - p.get("retry_ms", 0.0)))}


RUNS: dict[str, Run] = {}
# Per model: its tokenizer's count / ours, learned from the provider-reported prompt size, so the meter shows that
# model's real numbers from the first turn on and does not jump when the real count arrives.
CTX_RATIO: dict[str, float] = {}
LAST_REAL: dict[str, tuple[str, int]] = {}  # chat id -> (model, the provider's prompt count of its last request)
_RATIO_FILE = None  # data/ctx_ratio.json: the learned ratios survive a restart (first turn uses real data too)


def _ratio_file():
    global _RATIO_FILE
    if _RATIO_FILE is None:
        from ..config import DATA_DIR
        _RATIO_FILE = DATA_DIR / "ctx_ratio.json"
        try:
            CTX_RATIO.update({k: float(v) for k, v in json.loads(_RATIO_FILE.read_text(encoding="utf-8")).items()})
        except (OSError, ValueError):
            pass
    return _RATIO_FILE


def _learn_ratio(model: str, r: float) -> None:
    """Store a ratio from the provider's real prompt count; written only when it changed noticeably."""
    f = _ratio_file()
    old = CTX_RATIO.get(model)
    CTX_RATIO[model] = round(r, 4)
    if old is None or abs(old - r) > 0.02:
        try:
            f.write_text(json.dumps(CTX_RATIO, indent=1), encoding="utf-8")
        except OSError:
            pass
_BACKGROUND: set[asyncio.Task] = set()

# How fast each model reads a prompt: milliseconds until the first token per 1000 prompt tokens (a moving average,
# kept in data/model_speed.json). A model that needs seconds per thousand tokens gets the lean prompt in "auto" mode.
SPEED: dict[str, list] = {}  # model -> [ms per 1K prompt tokens, samples]
SLOW_MS_PER_1K = 2500
_SPEED_FILE = None


def _speed_file():
    global _SPEED_FILE
    if _SPEED_FILE is None:
        from ..config import DATA_DIR
        _SPEED_FILE = DATA_DIR / "model_speed.json"
        try:
            SPEED.update({k: [float(v[0]), int(v[1])] for k, v in json.loads(_SPEED_FILE.read_text(encoding="utf-8")).items()})
        except (OSError, ValueError, TypeError, IndexError):
            pass
    return _SPEED_FILE


def _learn_speed(model: str, wait_ms: float, prompt_tokens: int) -> None:
    if prompt_tokens < 1500 or wait_ms <= 0:
        return  # a short prompt says little about reading speed (connection time dominates)
    per_k = wait_ms / prompt_tokens * 1000
    old = SPEED.get(model)
    new = [round(per_k if not old else old[0] * 0.7 + per_k * 0.3, 1), (old[1] if old else 0) + 1]
    SPEED[model] = new
    if not old or abs(old[0] - new[0]) > old[0] * 0.15 or new[1] in (2, 5):
        try:
            from ..config import atomic_write
            atomic_write(_speed_file(), json.dumps(SPEED, indent=1))
        except OSError:
            pass


def is_slow(model: str) -> bool:
    _speed_file()
    v = SPEED.get(model)
    return bool(v and v[1] >= 2 and v[0] >= SLOW_MS_PER_1K)


def lean_for(model: str, info: dict, mode: str = "auto") -> bool:
    """Whether this model gets the lean prompt: forced by Settings > Agent, else for local models, small windows
    and models measured as slow readers."""
    if mode in ("lean", "full"):
        return mode == "lean"
    return bool(info.get("local")) or (info.get("current") or 0) <= 32768 or is_slow(model)


# What a chat has opened and used so far (tool groups, skills), kept in its record: the next task of the same chat
# starts with them, so the model does not spend a round trip opening the same group or loading the same skill again.
ABILITIES = "abilities.json"
ABILITY_TASKS = 6  # a group not used for this many tasks closes again (its definitions cost tokens every turn)


def _abilities_load(session_id: str) -> dict:
    try:
        d = json.loads((sessions.path(session_id, create=False) / ABILITIES).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _abilities_open(mem: dict) -> dict:
    """{"groups": [...], "skills": [...]} still fresh for the next task."""
    n = int(mem.get("task") or 0)
    groups = [g for g, at in (mem.get("groups") or {}).items() if g in GROUP_TOOLS and n - int(at) < ABILITY_TASKS]
    return {"groups": groups, "skills": [k for k in (mem.get("skills") or [])][-6:]}


def _abilities_save(run: "Run") -> None:
    try:
        mem = _abilities_load(run.session["id"])
        n = int(mem.get("task") or 0) + 1
        used = {(s.get("data") or {}).get("tool") for s in run.steps if s.get("status") == "done"}
        groups = dict(mem.get("groups") or {})
        for g, names in GROUP_TOOLS.items():
            if g in ("project", "mcp"):
                continue  # always on when available
            if names & used:  # really used (opened but never called does not stay open)
                groups[g] = n
        skills = [k for k in (mem.get("skills") or [])]
        for st in run.steps:
            if st.get("kind") == "skill" and st.get("status") == "done" and st.get("title") and st["title"] not in skills:
                skills.append(str(st["title"])[:60])
        from ..config import atomic_write
        atomic_write(sessions.path(run.session["id"]) / ABILITIES,
                     json.dumps({"task": n, "groups": {g: at for g, at in groups.items() if n - int(at) < ABILITY_TASKS},
                                 "skills": skills[-12:]}, ensure_ascii=False))
    except (OSError, ValueError, TypeError):
        pass


def _shown_tokens(n: int, model: str) -> int:
    """A raw estimate_tokens() count, scaled like the context panel (run.session['context_used']) so a number
    shown next to a compression step always matches what the panel shows for the same model."""
    return int(n * CTX_RATIO.get(model, 1.0))


def _emit(run: Run, type_: str, **payload) -> None:
    if type_ == "delta":
        run.text += payload["text"]
    elif type_ == "reset_text":
        run.text = ""
    elif type_ == "reply_mode":
        run.chat = bool(payload.get("chat"))
    elif type_ == "context" and run.model:
        payload.setdefault("model", run.model)  # the meter compares against this model's window
    bus.publish("run", type_, {"run_id": run.id, "session_id": run.session["id"], **payload})


def _step(run: Run, kind: str, title: str, status: str = "done", detail: str = "", data: dict | None = None,
          step_id: str | None = None) -> str:
    if kind == "note" and not step_id and detail and any(
            x["kind"] == "note" and x["detail"] == detail[:8000] for x in run.steps):
        return next(x["id"] for x in run.steps if x["kind"] == "note" and x["detail"] == detail[:8000])
    sid = step_id or uuid.uuid4().hex[:8]
    step = {"id": sid, "kind": kind, "title": title, "status": status, "detail": detail[:8000],
            "data": data or {}, "ts": time.time()}
    existing = next((s for s in run.steps if s["id"] == sid), None)
    if existing:
        existing.update(step)
    else:
        run.steps.append(step)
    _emit(run, "step", step=step)
    return sid


TOOL_TITLES = {"write_file": "file", "read_file": "read", "read_document": "read", "my_location": "places", "system_info": "system", "list_dir": "list", "run": "command", "start": "process",
               "stop": "stop", "web_search": "search", "research": "search", "fetch_url": "fetch", "browser_check": "visual",
               "make_doc": "document", "delete_file": "delete", "use_skill": "skill", "edit_file": "edit",
               "search_code": "grep", "symbols": "grep", "ask_model": "delegate", "remember": "memory",
               "impact": "grep", "mcp": "mcp", "mcp_add": "mcp", "team": "team", "web_screenshot": "screenshot", "stock_photo": "photo", "generate_image": "photo", "inspect_media": "visual", "speech_to_text": "file", "text_to_speech": "file","save_catalog": "catalog",
               "places": "places", **{n: "browser" for n in BROWSER_TOOLS}}
REPEAT_GUARD = {"fetch_url", "web_search", "research", "use_skill"}
# Step kinds that are actions worth remembering in later turns (see _history).
ACTION_KINDS = {"photo", "file","edit", "delegate", "memory", "mcp", "team", "command", "process", "document", "delete", "skill", "search", "fetch", "visual", "screenshot", "catalog", "browser"}


def _parse_mentions(text: str) -> tuple[str | None, list[str], str]:
    """'@tester' selects an agent role, '/webapp' loads a skill. Unknown names are left in the text. Several agents
    ("@coder write it, @debugger check it"): the first is the role, the others' instructions join in (see
    _extra_agents)."""
    agents, skills = catalog.agents(), catalog.skills()
    found = list(dict.fromkeys(m for m in re.findall(r"(?<!\S)@([\w-]+)", text) if m in agents))
    role = found[0] if found else None
    used = list(dict.fromkeys(m for m in re.findall(r"(?<!\S)/([\w-]+)", text) if m in skills))
    names = [*found, *used]
    clean = re.sub(r"(?<!\S)[@/](%s)(?![\w-])" % "|".join(map(re.escape, names)), "", text) if names else text
    return role, used, clean.strip() or text


def _history(session_id: str, before_id: int | None = None, limit: int = HISTORY_MESSAGES) -> list[dict]:
    """Messages after the last compression point, preceded by the stored summary."""
    sess = db.query("SELECT summary, summary_upto FROM sessions WHERE id=?", (session_id,))
    summary, upto = (sess[0]["summary"], sess[0]["summary_upto"] or 0) if sess else (None, 0)
    rows = db.query("SELECT id, role, content, meta FROM messages WHERE session_id=? AND id>? AND id<? "
                    "AND role IN ('user','assistant') ORDER BY id DESC LIMIT ?",
                    (session_id, upto, before_id or 1 << 62, limit))
    msgs = []
    for r in reversed(rows):
        content = r["content"] or ""
        if r["role"] == "assistant":
            content += _action_log(r["meta"])
        if content.strip():
            msgs.append({"role": r["role"], "content": content})
    if rows and len(rows) >= limit:
        # Messages older than the window that no summary covers yet were simply left out: the model forgot them
        # without a trace (after 12 messages on a local model, 30 on a cloud one). They stay as a short digest until
        # the next summary takes them in (see _fold_overflow).
        older = db.query("SELECT role, content FROM messages WHERE session_id=? AND id>? AND id<? "
                         "AND role IN ('user','assistant') ORDER BY id DESC LIMIT ?",
                         (session_id, upto, rows[-1]["id"], OVERFLOW_DIGEST))
        lines, used = [], 0
        for r in older:  # newest first, within a budget
            text = re.sub(r"\s+", " ", r["content"] or "").strip()
            if not text:
                continue
            line = f"{r['role'].upper()}: {text[:320]}{'…' if len(text) > 320 else ''}"
            if used + len(line) > 7000:
                break
            lines.append(line)
            used += len(line)
        if lines:
            msgs = [{"role": "user", "content": f"{DIGEST_TAG}\n" + "\n".join(reversed(lines))},
                    {"role": "assistant", "content": "OK."}] + msgs
    if summary:
        msgs = [{"role": "user", "content": f"{SUMMARY_TAG}\n{summary}"},
                {"role": "assistant", "content": "OK."}] + msgs
    return msgs


OVERFLOW_DIGEST = 40  # older messages kept as one-line digests until a summary covers them
DIGEST_TAG = "[Earlier messages of this conversation, shortened (older than the ones below)]"


def _overflow(session_id: str, before_id: int | None, limit: int) -> int:
    """How many messages are older than the history window and not in the summary yet."""
    row = db.query("SELECT COUNT(*) AS c FROM messages WHERE session_id=? AND id<? AND role IN ('user','assistant') "
                   "AND id>(SELECT COALESCE(summary_upto, 0) FROM sessions WHERE id=?)",
                   (session_id, before_id or 1 << 62, session_id))
    return max(0, (row[0]["c"] if row else 0) - limit)


def _action(s: dict) -> str:
    failed =" (failed)" if s.get("status") == "error" else ""
    data = s.get("data") or {}
    if s.get("kind") == "delegate":  # another model of the pool answered a sub-task
        return f"ask_model: another model ({s.get('title') or 'none'}) answered a sub-task{failed}"
    if s.get("kind") == "team" and data.get("members"):  # real team: every member's agent and model
        return "team of agents: " + ", ".join(
            f"{c.get('title')} (stage {c.get('stage', 1)}, model {c.get('model') or 'none'}, {c.get('state')})"
            for c in data["members"]) + failed
    if s.get("kind") == "document" and data.get("source"):  # where its editable text is, and what it really holds
        return (f"document {s['title']}{failed} (source text: {data['source']}; images inside: {data.get('images', 0)})")
    return f"{s['kind']} {s['title']}{failed}"


def _action_log(meta: str | None) -> str:
    """Compact record of what an earlier turn did with tools, so 'continue' resumes exactly where it stopped
    (the visible answer alone may be empty when a run was interrupted)."""
    try:
        m = json.loads(meta or "{}")
    except json.JSONDecodeError:
        return ""
    acts = [_action(s) for s in m.get("steps") or [] if s.get("kind") in ACTION_KINDS]
    if not acts:
        return ""
    status = m.get("status") or "ok"
    unfinished = "" if status == "ok" else f"; run ended early: {status}, the task may be unfinished"
    by = f" (main model {m['model']})" if m.get("model") else ""
    return f"\n\n[Tool actions in this turn{by}: {'; '.join(acts[-40:])}{unfinished}]"


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


def _partial_call(run: "Run") -> tuple[str, dict, bool] | None:
    """The file-writing call that was streaming when a turn broke off: (tool, {path, content}, append)."""
    if run.partial_tag:
        m = re.match(r'<(?:tool|tools)\b[^>]*?name="(write_file|make_doc)"([^>]*)>(.*)', run.partial_tag, re.S) or \
            re.match(r"<(write_file|make_doc)\b([^>]*)>(.*)", run.partial_tag, re.S)
        if m:
            attrs = dict(re.findall(r'(\w+)\s*=\s*"([^"]*)"', m.group(2)))
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


def _persist_partial(run: "Run") -> None:
    """Every few seconds the call being written goes to disk too: after a power cut it is recovered."""
    now = time.time()
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
    content = args.get("content") or ""
    if "\n" in content:
        content = content[:content.rfind("\n") + 1]  # never keep half a line
    if len(content) < 200 or not args.get("path"):
        return None
    try:
        target = (Path(root) / args["path"]).resolve()
        if Path(root).resolve() not in target.parents:
            return None
        if tool == "make_doc":
            target = target.parent / ".doc-sources" / f"{target.name}.partial.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        if append and target.exists():
            with open(target, "a", encoding="utf-8", newline="") as fh:
                fh.write(content)
        else:
            target.write_text(content, encoding="utf-8", newline="")
        return target.relative_to(Path(root).resolve()).as_posix(), len(content)
    except (OSError, ValueError):
        return None


def _salvage(run: "Run", ctx, messages: list[dict]) -> tuple[str, int] | None:
    """A turn broke off while a file was being written: keep what was written and tell the model to go on from
    there (append), instead of losing it and writing it all again."""
    got = _partial_call(run)
    run.partial_args, run.partial_tag = {}, ""
    if not got:
        return None
    saved = save_partial(ctx.root, *got)
    if not saved:
        return None
    path, n = saved
    ctx.files_changed.append(path)
    tail = got[1]["content"][:n][-400:]
    how = (f"continue writing it with write_file path=\"{path}\" append=true" if got[0] == "write_file" else
           f"continue the document's source with write_file path=\"{path}\" append=true, then make_doc "
           f"source=\"{path}\" path=\"{got[1]['path']}\"")
    messages.append({"role": "user", "content": f"[App note] The connection dropped while you were writing "
                     f"{got[1]['path']}. The {n} characters you had written are SAVED in {path} - do not write them "
                     f"again. It ends with:\n...{tail}\n\nNow {how}, with ALL the rest in this ONE call (start right "
                     "after that end, finish the file). Do not split it into several calls and do not read the file "
                     "first: every extra call is another full round trip."})
    _drop_partial_file(run.session["id"])
    return saved


def _drop_partial_file(session_id: str) -> None:
    try:
        (sessions.path(session_id, create=False) / PARTIAL).unlink(missing_ok=True)
    except (OSError, ValueError):
        pass


RECORD_TAG = "[App record of this task so far - kept by the app, exact]"
CONTINUE_TAG = "[App note: connection dropped]"
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


def _tag_call(c: dict) -> str:
    """A native tool call written in the tag protocol (for a model that uses tags)."""
    spec = TOOLS.get(c.get("name") or "")
    args = c.get("arguments") if isinstance(c.get("arguments"), dict) else {}
    main = spec.main if spec else None
    body = args.get(main, "") if main else ""
    attrs = "".join(f' {k}="{v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)}"'.replace("\n", " ")
                    for k, v in args.items() if k != main and v is not None)
    return f'<tool name="{c.get("name")}"{attrs}>{body if isinstance(body, str) else json.dumps(body, ensure_ascii=False)}</tool>'


def _for_model(messages: list[dict], model: str, native: bool) -> list[dict]:
    """The conversation as this model can read it. A task can change model or protocol on the way (a busy provider, a
    quota, a provider that rejects function calling): earlier native tool calls are then shown in the tag protocol
    (many servers reject tool messages when no tools are declared), and parts only their own model understands
    (signed thinking blocks, thought signatures) are left out for the others. The stored conversation is untouched."""
    if native:
        out = []
        for m in messages:
            if m.get("tool_calls") and m.get("by") and m["by"] != model and (m.get("thinking_blocks") or any(
                    c.get("extra") for c in m["tool_calls"])):
                m = {k: v for k, v in m.items() if k != "thinking_blocks"}
                m["tool_calls"] = [{k: v for k, v in c.items() if k != "extra"} for c in m["tool_calls"]]
            out.append(m)
        return out
    if not any(m.get("tool_calls") or m["role"] == "tool" for m in messages):
        return messages
    out, results = [], []

    def flush() -> None:
        if results:
            out.append({"role": "user", "content": "Tool results:\n" + "\n".join(results)})
            results.clear()
    for m in messages:
        if m["role"] == "tool":
            results.append(f'<result tool="{m.get("name") or "tool"}" ok="true">\n{m.get("content") or ""}\n</result>')
            continue
        flush()
        if m.get("tool_calls"):
            text = ((m.get("content") or "").strip() + "\n" if (m.get("content") or "").strip() else "") + "\n".join(
                _tag_call(c) for c in m["tool_calls"])
            out.append({"role": "assistant", "content": text})
        else:
            out.append(m)
    flush()
    return out


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
    todos = "; ".join(f"[{'x' if t.get('status') == 'completed' else ' '}] {t.get('content')}" for t in state.get("todos") or [])
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


def estimate_tokens(messages: list[dict]) -> int:
    """Tokens of a message list (real tokenizer), counting tool-call arguments (whole files) too."""
    return sum(tokens.count(m.get("content") if isinstance(m.get("content"), str) else "")
               + (tokens.count(json.dumps(m["tool_calls"], ensure_ascii=False)) if m.get("tool_calls") else 0)
               + 4 + 1000 * len(m.get("images") or []) for m in messages)


SHRUNK = "[{n} characters omitted to save context; read_file shows the current file]"


def shrink_messages(messages: list[dict], keep_last: int) -> bool:
    """Context relief inside a long task: file bodies sent with earlier tool calls and long earlier tool results
    are replaced by short notes (the files are on disk). The last `keep_last` messages stay intact."""
    changed = False
    for i, m in enumerate(messages[:max(0, len(messages) - keep_last)]):
        if m.get("tool_calls"):
            calls = []
            for c in m["tool_calls"]:
                args = dict(c["arguments"])
                for k in ("content", "body"):
                    if isinstance(args.get(k), str) and len(args[k]) > 600:
                        args[k] = SHRUNK.format(n=len(args[k]))
                        changed = True
                calls.append({**c, "arguments": args})
            messages[i] = {**m, "tool_calls": calls}
        content = m.get("content") or ""
        if m["role"] == "tool" or content.startswith("Tool results:"):
            if len(content) > 1500:
                messages[i] = {**messages[i], "content": clip(content, 1200)}
                changed = True
        elif m["role"] == "assistant" and "<tool" in content and len(content) > 1500:
            new = re.sub(r'(<tool name="write_file"[^>]*>)(.{600,}?)(</tool>)',
                         lambda g: g.group(1) + SHRUNK.format(n=len(g.group(2))) + g.group(3), content, flags=re.S)
            if new != content:
                messages[i] = {**messages[i], "content": new}
                changed = True
    return changed


COMPRESS_PROMPT = """Summarize the conversation below for your own future reference. It replaces the original messages.
Keep EVERYTHING needed to continue without hallucinating: user goals and constraints, decisions, file paths created or
changed, commands run and their results, errors and fixes, open tasks, and exact names/values. Use concise bullets in
the conversation's language. Do not invent anything: only facts written below. The bracketed "[Tool actions ...]" lines
are the app's exact record of what ran; keep those actions as plain bullet points (do not copy the bracketed lines
themselves), and never list an action, file or result that is not there.
Mark unfinished or failed work as such. Output only the summary (no reasoning, no preamble)."""


async def compress(session_id: str, model: str, cancel: asyncio.Event | None = None,
                   keep_recent: int | None = None, before_id: int | None = None, target: float | None = None) -> dict:
    """Summarize older messages. The `keep_recent` latest stay verbatim, fewer when they alone are larger than
    `target` tokens (a few very long messages must still shrink). Messages from `before_id` on (the request being
    answered) are never summarized."""
    keep = load_settings()["context"].get("keep_recent", 6) if keep_recent is None else keep_recent
    sess = db.query("SELECT summary, summary_upto FROM sessions WHERE id=?", (session_id,))[0]
    rows = db.query("SELECT id, role, content, meta FROM messages WHERE session_id=? AND id>? "
                    "AND role IN ('user','assistant') ORDER BY id", (session_id, sess["summary_upto"] or 0))
    # The summary must know what really ran (files written, commands, searches), not only what was said: the
    # answers alone leave the actions out and the model would later re-do or invent them.
    rows = [{**r, "content": (r["content"] or "") + (_action_log(r["meta"]) if r["role"] == "assistant" else "")}
            for r in rows]
    if before_id:
        rows = [r for r in rows if r["id"] < before_id]
    if target:
        while keep and sum(tokens.count(r["content"] or "") for r in rows[-keep:]) > target:
            keep -= 1
    old = rows[:-keep] if keep else rows
    if not old:
        return {"compressed": 0}
    before = estimate_tokens(_history(session_id))
    info = await router.context_info(model)
    # Long messages keep their start and end; the whole transcript fits well inside the summarizing model's window.
    per = max(2000, int(info["current"] * 1.6 / max(1, len(old))))
    transcript = (f"Previous summary:\n{sess['summary']}\n\n" if sess["summary"] else "") + "\n\n".join(
        f"{r['role'].upper()}: {clip(r['content'] or '', per)}" for r in old)
    opts = {"num_ctx": info["current"]} if info["local"] else {}
    last_user = next((r["content"] for r in reversed(rows) if r["role"] == "user"), "")
    lang = reply_language(last_user, load_settings().get("language"))
    summary = (await router.complete(model, [
        {"role": "system", "content": COMPRESS_PROMPT + f"\nWrite the summary in {LANG_NAMES.get(lang, lang)}."},
        {"role": "user", "content": transcript}], opts, cancel)).strip()
    if not summary:
        raise ProviderError("empty", "The model returned an empty summary")
    db.execute("UPDATE sessions SET summary=?, summary_upto=? WHERE id=?", (summary, old[-1]["id"], session_id))
    after = estimate_tokens(_history(session_id))
    # The meter counts what the next turn sends: the history plus the fixed part (system prompt, tool definitions,
    # skills) from the last turn's breakdown; the history alone made it drop to a fraction and jump back later.
    st = db.query("SELECT context_stats FROM sessions WHERE id=?", (session_id,))
    stats = json.loads(st[0]["context_stats"]) if st and st[0]["context_stats"] else {}
    static = sum(v for k, v in stats.items() if k in ("system", "tools", "skills", "project", "state"))
    shown_after = _shown_tokens(after, model) + static
    res = {"compressed": len(old), "before": _shown_tokens(before, model) + static, "after": shown_after, "mode": "summary"}
    sessions.append_summary(session_id, summary, res)
    db.execute("UPDATE sessions SET context_used=? WHERE id=?", (shown_after, session_id))
    return res


BROWSER_GUIDE = (
    "# Browser agent\n"
    "browser_* tools open a real, visible browser window (its own profile keeps the user's sign-ins between tasks) "
    "to act on a website like a person: browser_navigate opens a page and returns it as a tree of elements with "
    "refs ([e12]); browser_click/browser_type/browser_key/browser_form act on a ref; browser_snapshot/browser_find "
    "read the page again (always re-read after an action that changes the page, never assume it worked); "
    "browser_batch runs several predictable steps at once. Use them to test a site or local app as a real user "
    "would (fill a form, click through, check the result), or to work inside an app the user is signed into. Never "
    "try to solve a CAPTCHA or bot check: call browser_handoff - the user solves it in the window and the task "
    "continues by itself as soon as it is done. Never type a card number on a real site. Passwords and risky buttons "
    "(send/delete/publish/sign up): on the site the user's request names in Full access mode (e.g. 'sign me up on "
    "mysite.com with password X') do it directly with the details the user gave; elsewhere call browser_handoff "
    "and let the user do that part, then continue. Pop-ups and cookie banners are closed automatically (the page "
    "says '[Closed automatically: ...]'); if one still blocks the page, close it yourself with its close/X button "
    "or browser_key Escape (cookie banners: always the reject / necessary-only choice) and go on. For plain information (facts, prices, a page's text) prefer "
    "research/fetch_url/web_search; use browser_* only when the task needs real interaction with a page.")


TEAM_GUIDE = (
    "# Multi-model teamwork\n"
    "Other cloud models of the pool can work for you: {models}.\n"
    "- When the user asks for a team, group, several agents or several models (takım, ekip, grup, çoklu ajan, "
    "çoklu model...), use the team tool: every member is a real agent on its own model with file, command and "
    "document tools. Parts that need an earlier part's result get a later stage (stage 2, 3...); they receive the "
    "earlier reports and file names. Put the whole pipeline in ONE team call.\n"
    "- ask_model is only for a text answer from one other model (a review, an analysis, a second opinion).\n"
    "- Call other models only when the user asks for it (a team, several agents or models, parallel work, another "
    "model's opinion); otherwise do the task yourself. When a team is done YOU check its results (read the files, "
    "run the tests), merge or compare them and write the final answer.\n"
    "- Never do the members' parts yourself and call it teamwork. When you report, say which model did which "
    "part exactly as the tool results (and the [Tool actions ...] notes of earlier turns) list them.")


def _system_prompt(role: str, root, session_id: str, project: dict | None, skill_names: list[str],
                   plan: str | None, native: bool, model: str = "", lang: str = "tr",
                   tools: set[str] | None = None, compact: bool = False,
                   extra_agents: list[str] | tuple = (), topics: frozenset = frozenset(), lean: bool = False,
                   request: str = "", chat_memory: dict | None = None) -> tuple[str, dict]:
    """tools: names offered this turn (None = all, empty = none). compact: short tool texts (small windows).
    lean: the short prompt for slow models (see WORK_RULES_LEAN). The order is: what never changes in a chat first
    (identity, rules, the capability index, the core tools), then what can change (tools of opened groups, the
    environment, state), so a local server re-reads only the tail when a group opens."""
    agents = catalog.agents()
    sizes: dict[str, int] = {}
    from .. import hostinfo
    # Static part first (the same for every chat on this model): identity, rules, capability map.
    parts = [SYSTEM_CORE.format(model=model, os_name=OS_NAME)]
    if tools is None or tools & WORK_TOOLS:
        parts.append(WORK_RULES_LEAN if lean else WORK_RULES)
        split = int((load_settings().get("agent") or {}).get("split_write_chars") or 0)
        if split > 0:  # Settings > Agent: the user wants very large files written in parts
            parts.append(f"- Files longer than ~{split:,} characters: write the first part with write_file, then each "
                         "next part with write_file append=true (continue exactly where the previous part ended).")
        parts += [(RULE_TOPICS_LEAN.get(k) if lean else None) or RULE_TOPICS[k][1] for k in sorted(topics) if k in RULE_TOPICS]
    if tools is None or tools & WEB_TOOLS:
        parts.append(WEB_RULES)
    if (tools is None or "web_screenshot" in tools) and not lean:
        parts.append(SCREENSHOT_RULE)
    asks_abilities = bool(ABILITY_ASK.search(request or ""))
    if tools is None or "need_tools" in tools:
        parts.append(CAPABILITIES_LEAN if lean else CAPABILITIES)
    elif not tools and lean and not asks_abilities:
        parts.append(CHAT_NOTE)  # a greeting does not need the whole map; "what can you do?" gets it (below)
    elif not tools:
        # A conversation turn has no tools, but the model must know everything it can do (and say so when asked:
        # "neler yapabilirsin?" got a generic answer, and later requests were refused as impossible).
        parts.append(CAPABILITIES.replace(CAP_HEAD, "# What you can do (no tools in this reply; when the user asks "
                                          "for any of this, it is done with tools in the next request)"))
    # The specialist agents (roles): the user calls them with @name; team members can take these roles.
    roles = {k: v for k, v in agents.items() if k != DEFAULT_ROLE}
    if roles and (tools is None or not tools or "need_tools" in tools) and (not lean or asks_abilities
                                                                           or re.search(r"ajan|agent|@", request or "", re.I)):
        parts.append("# Agents (the user calls one with @name; it then does the work as that specialist): "
                     + "; ".join(f"@{k} ({v.get('title_en') or v['title']})" for k, v in roles.items()))
    role_prompt = agents.get(role, agents.get(DEFAULT_ROLE, {})).get("prompt")
    if role_prompt:
        parts.append("# Instructions\n" + role_prompt)
    sizes["system"] = sum(map(tokens.count, parts))
    if tools is not None and not tools:
        sizes["tools"] = 0
    elif not native:
        # The core tools here (the same in every turn of a chat); tools of opened groups go to the end of the prompt.
        core = None if tools is None else (tools & CORE_TOOLS) or tools
        extra_tools = set() if tools is None else tools - core
        parts.append(TAG_PROTOCOL.format(tools=tools_prompt(core, compact or lean, lean)))
        sizes["tools"] = tokens.count(parts[-1])
    else:
        sizes["tools"] = 0  # native tool definitions travel beside the prompt: counted once per turn
    if tools is None or "mcp" in tools:
        from .. import mcp_client
        if section := mcp_client.prompt_section():
            parts.append(section)
            sizes["tools"] = sizes.get("tools", 0) + tokens.count(section)
    if tools is None or "team" in tools:
        pool = [e["model"] for e in router.pool() if e["model"].partition(":")[2] != model][:12]
        if pool:
            parts.append(TEAM_GUIDE.format(models=", ".join(pool)))
            sizes["tools"] = sizes.get("tools", 0) + tokens.count(parts[-1])
    tail: list[str] = []  # what can change while a chat goes on: after everything static
    if not native and tools and extra_tools:
        tail.append("# More tools (opened for this request)\n" + tools_prompt(extra_tools, compact or lean, lean))
        sizes["tools"] = sizes.get("tools", 0) + tokens.count(tail[-1])
    if tools is None or tools & BROWSER_TOOLS:  # only when at least one browser_* tool is actually offered
        tail.append(BROWSER_GUIDE_LEAN if lean else BROWSER_GUIDE)
        sizes["tools"] = sizes.get("tools", 0) + tokens.count(tail[-1])
    # Skill discovery: the model sees every skill's purpose and loads a matching one with use_skill.
    available = {k: v for k, v in catalog.skills().items() if k not in skill_names}
    if available and lean and (tools is None or "use_skill" in tools):
        # Names only (they say what they are for); the instructions arrive with use_skill.
        parts.append("# Skills (use_skill NAME when the request matches one): " + ", ".join(available))
        sizes["skills"] = tokens.count(parts[-1])
    elif available and not lean and (tools is None or "use_skill" in tools or not tools):
        # Name and title (the full instructions arrive with use_skill).
        parts.append("# Skills (when the request matches one, call use_skill with its name first and follow the loaded "
                     "instructions): " + "; ".join(f"{k} ({v.get('title_en') or v['title']})" for k, v in available.items()))
        sizes["skills"] = tokens.count(parts[-1])
    parts += tail
    mem = chat_memory or {}
    if mem.get("groups") or mem.get("skills"):
        # What this chat already opened and used: the model does not ask for it again (no need_tools round trip).
        parts.append("# Already open in this chat\n"
                     + (f"Tool groups: {', '.join(sorted(mem['groups']))} (their tools are callable now). " if mem.get("groups") else "")
                     + (f"Skills used earlier: {', '.join(mem['skills'])} (load one again only if you need its text)."
                        if mem.get("skills") else ""))
        sizes["system"] += tokens.count(parts[-1])
    # Per chat / per day from here on.
    parts.append(ENV_SECTION.format(os_line=hostinfo.os_line(), root=root, date=time.strftime("%Y-%m-%d"),
                                    project=f"\nProject: {project['name']}" if project else ""))
    if tools is None or tools & {"run", "start"}:  # the real OS build, shells and tool versions
        parts.append(hostinfo.prompt_section(short=lean))
    sizes["system"] += sum(map(tokens.count, parts[-2:])) if tools is None or tools & {"run", "start"} else tokens.count(parts[-1])
    # The user's lasting rules: global ones (Settings) and the project's AIIQ.md. Read once per task (stable prompt).
    # Headings inside the rule texts are flattened, so they cannot break the prompt's own sections.
    flat = lambda text: re.sub(r"(?m)^#+[ \t]*", "", text).strip()  # noqa: E731
    global_rules = flat(load_settings().get("rules") or "")
    project_rules = flat(workspace.read_rules(project))
    if global_rules or project_rules:
        parts.append("# Rules from the user (always follow them; they override the defaults above)"
                     + (f"\n## For every chat\n{global_rules[:workspace.RULES_MAX]}" if global_rules else "")
                     + (f"\n## For this project ({workspace.RULES_FILE})\n{project_rules}" if project_rules else ""))
        sizes["project" if project_rules else "system"] = sizes.get("project" if project_rules else "system", 0) + tokens.count(parts[-1])
    if project:
        parts.append("# Project files\n" + workspace.summarize_tree(root, 30 if lean else 60))
        code_map = "" if lean else project_map(root)  # lean: the symbols / search_code tools answer the same on demand
        if code_map:  # where things are defined: search_code / symbols / read_file lines=... go straight there
            parts[-1] += "\n\n# Code map (definitions per file)\n" + code_map
        sizes["project"] = sizes.get("project", 0) + tokens.count(parts[-1])
    state = sessions.state_file(session_id)
    if state.exists():
        parts.append("# Session state\n" + state.read_text(encoding="utf-8", errors="replace")[:900 if lean else 2000])
        sizes["state"] = tokens.count(parts[-1])
    skills = catalog.skills()
    skill_parts = [f"# Active skill /{s}: {skills[s]['title']} (the user invoked it for the latest request; "
                   f"apply these instructions to that request)\n{skills[s]['prompt']}" for s in skill_names if s in skills]
    skill_parts += [f"# Also invoked agents\n## @{a}: {agents[a]['title']} (do its part of the latest request)\n"
                    f"{agents[a]['prompt']}" for a in extra_agents if a in agents]
    parts += skill_parts
    sizes["skills"] = sizes.get("skills", 0) + sum(map(tokens.count, skill_parts))
    if plan:
        parts.append("# Plan to follow\n" + plan)
        sizes["plan"] = tokens.count(parts[-1])
    parts.append(language_rule(lang, lean))  # last, so it carries the most weight
    sizes["system"] += tokens.count(parts[-1])
    return "\n\n".join(parts), sizes


def context_breakdown(sizes: dict, messages: list[dict], actual_input: int | None) -> dict:
    """Tokens per category of what is sent to the model (real tokenizer); scaled to the provider-reported input
    when known, so the parts add up to the provider's own count."""
    toks = dict(sizes)  # system prompt parts, already in tokens
    for m in messages:
        content = m.get("content") or ""
        if m["role"] == "tool" or m.get("tool_calls") or content.startswith("Tool results:"):
            key = "tool_io"
            content += json.dumps(m.get("tool_calls") or "", ensure_ascii=False)
        elif content.startswith(SUMMARY_TAG):
            key = "summary"
        elif "[Attached file:" in content:
            head, _, att = content.partition("[Attached file:")
            toks["messages"] = toks.get("messages", 0) + tokens.count(head)
            key, content = "attachments", att
        else:
            key = "messages"
        toks[key] = toks.get(key, 0) + tokens.count(content) + 4
        if m.get("images"):
            toks["attachments"] = toks.get("attachments", 0) + 1000 * len(m["images"])
    toks = {k: v for k, v in toks.items() if v}
    est = sum(toks.values()) or 1
    scale = actual_input / est if actual_input else 1
    return {k: int(v * scale) for k, v in sorted(toks.items(), key=lambda kv: -kv[1])}


_UNIT = re.compile(r"[^\n.!?]{25,}[.!?]?")


def _loop_cut(text: str) -> str | None:
    """The text up to where a repetition loop starts, or None. A loop: one sentence (25+ characters) that appears 4+
    times within the last 4000 characters (code is left alone: repeated lines are normal there)."""
    if len(text) < 400 or text.count("```") % 2:
        return None
    tail = text[-4000:]
    counts: dict[str, int] = {}
    for m in _UNIT.finditer(tail):
        s = m.group(0).strip()
        if len(s) >= 25 and not s.lstrip().startswith(("|", "-", "*", "<", "{", "#")):
            counts[s] = counts.get(s, 0) + 1
    rep = max(counts.items(), key=lambda kv: kv[1], default=(None, 0))
    if rep[1] < 4:
        return None
    first = text.find(rep[0])
    second = text.find(rep[0], first + len(rep[0]))
    return text[:second].rstrip() if second > 0 else None


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
    t_req = time.monotonic()
    if run.perf["prep_ms"] is None:
        run.perf["prep_ms"] = (t_req - run.t0) * 1000
    turn = {"model": model, "wait_ms": None, "total_ms": 0.0}
    # Live context: the prompt plus what the model has written so far that the next request will carry (text, tool
    # arguments), so the meter moves during a long file instead of jumping at the end. Reasoning is left out: it is
    # not sent again, so counting it made the meter fall back (6K -> 5K) when the next request's real size arrived.
    base = run.session.get("context_used") or 0
    out = {"native_think": [], "tool": 0, "at": 0.0, "real": False, "n": 0, "done": [0, 0]}

    def grow() -> None:
        now = time.monotonic()
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
            run.session["context_used"] = used
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
                 ("tool_silent" if opts.get("tools") else "stalled") if name == "tool" else "writing")
        if phase == "tool_silent" and seconds >= 45 and not _call_open(run):
            run.silent_writer = True
        # The user must always see what is going on: the file being written and its size so far, or for a provider
        # that sends the call only at the end, how long nothing has come and when the app switches to streaming.
        target = _partial_target(run)
        switch_in = (max(0, SILENT_TOOL_LIMIT - seconds) if phase == "tool_silent" and opts.get("tools")
                     and not router.is_local(model) and not _call_open(run) else None)
        # An overloaded provider can pause for minutes and still finish: it is not cut early (that only made it think
        # again from the start); the step says how long nothing came and when the stream timeout would retry.
        stall_in = (max(0, int(router.silence_limits(False)[1]) - seconds)
                    if phase == "stalled" and not router.is_local(model) else None)
        prep_id = _step(run, "prepare", name or "tool", "running",
                        data={"tool": name, "chars": chars, "seconds": int(now - t_req), "idle": seconds, "phase": phase,
                              "prompt_tokens": _shown_tokens(run.prompt_est, model), "model": model,
                              "thought": sum(len(x) for x in thinking), "target": target, "switch_in": switch_in, "stall_in": stall_in,
                              "local": router.is_local(model)}, step_id=prep_id)

    def end_thinking() -> None:
        nonlocal thinking_live
        if think_id and thinking_live:
            thinking_live = False
            _step(run, "thinking", "thinking", "done", "".join(thinking)[-6000:], step_id=think_id)

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
            # At most 4 updates a second: joining the whole reasoning and sending 6 KB on every token made long
            # thinking (deepseek: thousands of tokens) slower and slower, on the server and in the browser.
            now = time.monotonic()
            if think_id is None or now - think_at[0] >= 0.25:
                think_at[0] = now
                think_id = _step(run, "thinking", "thinking", "running", "".join(thinking)[-6000:], step_id=think_id)
        elif kind in ("tool", "tool_incomplete"):
            tags.append(text)
        elif kind == "retract":  # what was shown was reasoning (a lone </think> arrived): take it back
            visible.clear()
            _emit(run, "reset_text")

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
                # Silence: either the prompt is still being processed, or the model is writing a tool call
                # (local servers stream nothing for those). Show it live instead of a frozen "thinking".
                if evt["seconds"] >= 4:
                    end_thinking()
                    prepare("tool" if got_output else "model", seconds=evt["seconds"], force=True)
                if (got_output and evt["seconds"] >= SILENT_TOOL_LIMIT and opts.get("tools") and not _call_open(run)
                        and not router.is_local(model)):
                    # A cloud provider that sends a tool call only when it is complete: minutes of nothing, no way to
                    # tell progress from a hang, and everything is lost on a drop. Stop waiting and redo this turn
                    # with the text protocol, which streams the file as it is written (and can be continued).
                    run.silent_writer = True
                    raise ProviderError("timeout", f"no tool-call data for {int(evt['seconds'])} s (the provider "
                                                   "sends tool calls only at the end); switching to streamed text calls")
                if (got_output and evt["seconds"] >= MIDCALL_STALL and (_call_open(run) or run.partial_tag)
                        and not router.is_local(model)):
                    # The file was streaming and the provider stopped in the middle of it (evren/deepseek waited
                    # 300 s for the general timeout). What was written is kept and the model continues from there.
                    run.stalls += 1
                    if opts.get("tools"):
                        # Native tool arguments that arrive in bursts with long pauses (evren/deepseek): the text
                        # protocol streams the same file as plain tokens, steadily; this model uses it from now on.
                        run.silent_writer = True
                    raise ProviderError("stalled", f"the provider stopped for {int(evt['seconds'])} s in the middle "
                                                   "of a file; the written part is kept and continued")
                continue
            if not got_output and t in ("thinking", "text", "tool_call", "tool_call_start"):
                now = time.monotonic()
                turn["wait_ms"] = (now - t_req) * 1000
                if run.perf["first_ms"] is None:
                    run.perf["first_ms"] = (now - run.t0) * 1000
            got_output = got_output or t in ("thinking", "text", "tool_call", "tool_call_start")
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
                    slot = run.partial_args.setdefault(evt.get("index", 0), {"name": evt.get("name"), "args": []})
                    slot["name"] = evt.get("name") or slot["name"]
                    slot["args"].append(evt["delta"])
                    _persist_partial(run)
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
                output = evt.get("output") or 0
                # Reasoning is not sent again, so it is not part of the next request: left out (reported by the
                # provider, else the streamed thinking in this model's units).
                think_tok = evt.get("reasoning") or int(tokens.count("".join(out["native_think"]) + "".join(thinking))
                                                        * CTX_RATIO.get(model, 1.0))
                if output:
                    output -= think_tok
                used = (run.session.get("usage_input") or 0) + max(0, output)
                run.session["context_used"] = used
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
                        _step(run, "note", "loop", "done", ui_text(
                            opts.get("lang") or load_settings().get("language") or "en", "ai_note_loop",
                            "The model began repeating the same text; the repeats were removed and its answer was "
                            "ended there."))
                        break  # ends the stream (the request is closed)
                if splitter.open and splitter.open[0] not in THINK_OPENERS:
                    m = PREP_NAME.search(splitter.buf[:600])  # the tool name is at the start: not the whole file every chunk
                    prepare(next((g for g in m.groups() if g), None) if m else None, len(splitter.buf))
                    run.partial_tag = splitter.buf  # a tag call being written (text protocol): kept for a drop
                    _persist_partial(run)
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
        if not tags and not calls and out["native_think"] and not "".join(visible).strip():
            # Some models (GLM on Cloudflare) write the tool call into the reasoning channel and send nothing
            # else: take the call from there instead of ending the turn with an empty reply.
            inner = StreamSplitter(TOOL_NAMES)
            found = [x for k, x in inner.feed("".join(out["native_think"])) + inner.flush() if k == "tool"]
            tags.extend(b for b in found if parse_tool(b, TOOL_NAMES))
            if found and think_id:  # the shown reasoning keeps its words, not the raw call syntax
                shown = "".join(thinking)
                for b in found:
                    shown = shown.replace(b, "")
                _step(run, "thinking", "thinking", "done", shown.strip()[-6000:], step_id=think_id)
    finally:  # never leave a spinning step behind, also when the turn fails or is cancelled
        try:
            await stream.aclose()  # a stream left early (loop guard) closes its request and frees its slot now
        except Exception:
            pass
        turn["total_ms"] = (time.monotonic() - t_req) * 1000
        if turn["wait_ms"] is None:
            turn["wait_ms"] = turn["total_ms"]
        elif got_output:
            _learn_speed(model, turn["wait_ms"], int(run.prompt_est * CTX_RATIO.get(model, 1.0)))
        run.perf["turns"].append(turn)
        if prep_id:  # the real tool steps replace the placeholder
            run.steps = [s for s in run.steps if s["id"] != prep_id]
            _emit(run, "step_remove", step_id=prep_id)
        end_thinking()
    return "".join(raw), tags, calls


# A busy or briefly failing provider (HTTP 503/429/5xx, timeouts) is retried with growing waits instead of
# ending a long task; quota/auth errors are not transient and end the run at once.
TRANSIENT = {"overloaded", "rate_limit", "server", "bad_gateway", "timeout", "network", "unavailable", "stalled"}
# Seconds a cloud provider may stay silent while it writes a native tool call before the turn is redone with the
# streamed text protocol (Settings > Agent > stream timeout still applies to everything else).
SILENT_TOOL_LIMIT = 75
MIDCALL_STALL = 75  # a file that was streaming and stopped this long mid-way: salvaged and continued


PATH_IN_ARGS = re.compile(r'"(?:path|file|filename|output)"\s*:\s*"([^"]{1,200})"|\b(?:path|file)="([^"]{1,200})"')


def _partial_target(run: "Run") -> str:
    """The file a tool call being written is about (from its streamed arguments or tag), for the live step."""
    src = run.partial_tag or ("".join(run.partial_args[max(run.partial_args)]["args"]) if run.partial_args else "")
    m = PATH_IN_ARGS.search(src[:2000])
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
RETRY_WAITS = (5, 15, 30, 60, 90, 120)
SPLIT_HINT = ("[App note: your previous tool call was cut off or the connection dropped while you were writing it, so "
              "it did NOT run. Everything before it did run and is kept above - do not redo those steps. Write the "
              "remaining content in at most two parts now: write_file with the first half (up to ~25,000 characters), "
              "then write_file with append=true for each following part. For documents, make_doc from a file you "
              "wrote this way (source=...).]")

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
    if run.done_calls:  # the exact record of what already ran, whatever the summary says: never redo or invent steps
        summary += "\n\nTool calls already made in this task (do not repeat them):\n" + "\n".join(
            f"- {d}" for d in run.done_calls[-80:])
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


async def _fix_language(run: Run, model: str, text: str, lang: str) -> str | None:
    """A finished reply with words in another language or script: one short call that sees only the reply (not
    the conversation) and rewrites it without thinking, instead of a second full turn (no second thinking, nothing
    added to the context, the answer not written twice). None when it fails or still drifts."""
    sid = _step(run, "note", "language", "running", ui_text(lang, "ai_note_lang", "Fixing the reply language."))
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
    _step(run, "note", "language", "done", ui_text(lang, "ai_note_lang_done" if good else "ai_note_lang_kept",
                                                   "Words in another language were translated." if good else
                                                   "The reply language could not be fixed; the reply is kept."),
          step_id=sid)
    return out if good else None


# Tools that only read or look things up: several of them in one turn can run at the same time.
PARALLEL_SAFE = {"research", "web_search", "fetch_url", "read_file", "list_dir", "search_code", "symbols", "impact",
                 "read_document", "web_screenshot", "places", "my_location", "ask_model", "use_skill", "mcp",
                 "stock_photo", "inspect_media"}


EVIDENCE_TOOLS = {"research", "web_search", "fetch_url", "read_file", "read_document", "run", "places", "mcp",
                  "ask_model", "search_code"}


TODO_DOC = {"pdf": ("pdf",), "docx": ("word", "docx"), "pptx": ("sunum", "powerpoint", "pptx", "slayt", "slide", "presentation"),
            "xlsx": ("excel", "xlsx", "tablo", "spreadsheet"), "html": ("html", "web"),
            "any": ("rapor", "report", "belge", "document", "doküman")}


TODO_RUN = re.compile(r"[çc]al[ıi][şs]t[ıi]r|test|dene|do[ğg]rula|kontrol|run|execute|verify|check|demo", re.I)


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
        hit = next((t for t in open_items if base and base in t["content"].lower()), None)
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
        hit = next((t for t in open_items if t["status"] == "in_progress" and TODO_RUN.search(t["content"])), None) \
            or next((t for t in open_items if TODO_RUN.search(t["content"])), None)
    if not hit:
        return
    hit["status"] = "completed"
    if not any(t["status"] == "in_progress" for t in run.todos):
        nxt = next((t for t in run.todos if t["status"] == "pending"), None)
        if nxt:
            nxt["status"] = "in_progress"
    run.todos = [dict(t) for t in run.todos]
    _emit(run, "todos", todos=run.todos)


def todo_line(run: "Run") -> str:
    """The list's current state, added to tool results so every model (single or in a team) works along it."""
    if not run.todos or all(t["status"] == "completed" for t in run.todos):
        return ""
    cur = next((t["content"] for t in run.todos if t["status"] == "in_progress"), None) or \
        next((t["content"] for t in run.todos if t["status"] != "completed"), "")
    done = sum(t["status"] == "completed" for t in run.todos)
    return (f"\n[To-do {done}/{len(run.todos)} done; now: {cur}. When this item is finished, call todo with the "
            "whole list updated.]")


# Calls that write a file: several in one turn run at the same time when each writes a different file.
PARALLEL_WRITE = {"write_file", "edit_file", "make_doc"}


def _job_path(job) -> str:
    a = job[1] if isinstance(job[1], dict) else {}
    return str(a.get("path") or "").replace("\\", "/").lower()


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
            paths = {_job_path(job)} - {""}
            wrote = job[0] in PARALLEL_WRITE
            while len(group) < 8 and group[-1] + 1 < len(jobs) and jobs[group[-1] + 1]:
                nxt = jobs[group[-1] + 1]
                # A look at something written earlier in the same reply (write a page, then screenshot it) waits for
                # the write: run together, the screenshot found no file yet.
                if nxt[0] in PARALLEL_SAFE and wrote and nxt[0] in ("web_screenshot", "read_file", "list_dir",
                                                                     "search_code", "read_document"):
                    break
                if nxt[0] in PARALLEL_SAFE and not (nxt[0] == "read_file" and _job_path(nxt) in paths):
                    group.append(group[-1] + 1)
                elif nxt[0] in PARALLEL_WRITE and _job_path(nxt) and _job_path(nxt) not in paths:
                    paths.add(_job_path(nxt))  # a different file: written at the same time
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
    if run.folder_snap and not run.folder_snap.done() and name not in READ_ONLY:
        try:  # the "before" picture must be complete before anything can change a file
            await asyncio.shield(run.folder_snap)
        except Exception:
            pass
    t = time.monotonic()
    res = await _run_tool(run, ctx, name, args, body, allowed)
    run.perf["tools"].append({"name": name, "ms": (time.monotonic() - t) * 1000, "ok": res.ok})
    if not res.ok and name not in ("run", "start"):  # failing commands have their own debug loop
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


async def _run_tool(run: Run, ctx: ToolContext, name: str, args: dict, body: str,
                    allowed: set[str] | None = None) -> ToolResult:
    if name not in TOOLS:
        return ToolResult(False, f"Unknown tool '{name}'. Available: {', '.join(TOOLS)}")
    if allowed is not None and name not in allowed and name in GROUPED and not run.restricted:
        # The model knows the tool from the capability map and called it before opening its group: open the group
        # and run the call, instead of an error that made it give up ("I have no text-to-speech tool").
        run.unlocked |= {g for g, names in GROUP_TOOLS.items() if name in names}
        allowed = None
    if allowed is not None and name not in allowed:
        return ToolResult(False, f"Tool '{name}' is not available for this request (the user asked a question; "
                                 "answer in chat, and only change files when asked).")
    if "_raw" in args:
        return ToolResult(False, "Invalid JSON arguments for this tool call. Send a valid JSON object.")
    # The same read-only call twice in one task (a model looping over the same page) is answered from memory.
    key = f"{name}:{json.dumps(args, sort_keys=True, ensure_ascii=False)}:{body.strip()}"
    if name in REPEAT_GUARD and key in run.seen:
        run.repeats += 1
        return ToolResult(True, "You already ran this exact call in this task; its result is above. Do not repeat it: "
                                "use what you have, try a different source, or give the answer now.")
    if name in REPEAT_GUARD:
        run.seen.add(key)
    if name == "need_tools":  # opens tool groups for the next turns (no trace step: it is bookkeeping)
        raw_groups = args.get("groups") or body or ""
        try:
            wanted = json.loads(raw_groups) if str(raw_groups).strip().startswith("[") else str(raw_groups).split(",")
        except json.JSONDecodeError:
            wanted = str(raw_groups).split(",")
        ok = {str(g).strip().lower() for g in wanted} & set(GROUP_TOOLS)
        if not ok:
            return ToolResult(False, f"Unknown group. Choose from: {', '.join(GROUP_TOOLS)}.")
        run.unlocked |= ok
        names = sorted(set().union(*(GROUP_TOOLS[g] for g in ok)))
        return ToolResult(True, f"Opened {', '.join(sorted(ok))}: {', '.join(names)} can be called from now on.")
    if name == "todo":  # shown as the live task list, not as a trace step
        res = await TOOLS[name].fn(ctx, args, body)
        if res.ok:
            todos = [dict(t) for t in res.data["todos"]]
            # A model that ticks a later item has finished the earlier one it left "in progress".
            last = max((i for i, t in enumerate(todos) if t.get("status") == "completed"), default=-1)
            for t in todos[:last]:
                if t.get("status") == "in_progress":
                    t["status"] = "completed"
            run.todos = todos
            _emit(run, "todos", todos=run.todos)
        return res
    first_line = body.strip().splitlines()[0][:120] if body.strip() else ""
    argv = args.get("argv") if isinstance(args.get("argv"), list) else None
    label = args.get("path") or args.get("url") or args.get("id") or first_line or (" ".join(map(str, argv))[:120] if argv else name)
    if name == "team":  # never the raw JSON of the members
        from .team import parse_members
        label = " · ".join(str(m.get("title") or "?")[:40] for m in parse_members(body.strip() or args.get("members"))
                           if isinstance(m, dict))[:160] or name
    elif name == "mcp":
        label = f"{args.get('server', '?')}/{args.get('tool', '?')}"
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
        res = ToolResult(False, f"Missing required argument: {e}")
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
    detail = body if name == "write_file" else res.data.get("diff") or res.output if name == "edit_file" else res.output
    _step(run, kind, label, "done" if res.ok else "error", detail,
          data={"tool": name, "args": {} if name == "team" else args, **res.data, "output": res.output[:4000],
                **({"command": redact(body)[:6000]} if name in ("run", "start") and body else {})}, step_id=sid)
    return res


# The user asks for something to be run or measured (not only written): printed code is not an answer.
RUN_ASK = re.compile(r"[çc]al[ıi][şs]t[ıi]r|\brun\b|execute|test\s*et|dene\b|[öo]l[çc]|measure|benchmark|sonucu?\s*s[öo]yle",
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
        if ctx_info["local"] and (ram := ctx_info.get("ram") or {}).get("short"):
            # The weights alone do not fit in the free RAM: loading would swap the computer to a halt (or crash
            # it). Stop before anything is sent, and say what to do.
            raise ProviderError("no_memory", ui_text(
                lang, "ai_err_no_ram", "{model} needs about {need} GB of RAM for its weights alone, but only {free} GB "
                "is free (of {total} GB, with a safety reserve). It was not loaded, to protect the computer. Close "
                "other programs, pick a smaller local model or a cloud model, and set Ollama's parallel requests "
                "(now {parallel}) to 1 in Settings > Providers > Ollama.", model=model, need=ram["weights_gb"],
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
        chat_only = is_small_talk(clean_text) and not skill_names and not forced_role
        # Plain knowledge questions in a chat without earlier work get read-only tools (no unrequested files).
        allowed = None
        if chat_only:
            allowed = set()
        elif (not skill_names and not forced_role and not project and is_knowledge_question(clean_text)
              and not MD_WORDS.search(clean_text) and not GROUP_WORDS["media"].search(clean_text)
              and not sessions.state_file(session["id"]).exists()):
            # (browser_* only when the question is about acting on a site: ~1K tokens of definitions otherwise)
            allowed = set(READ_ONLY) - (set() if BROWSER_WORDS.search(clean_text) else BROWSER_TOOLS)
        # A conversation reply (small talk, a plain question): the UI streams it straight into the chat as the answer
        # instead of the work-note slot under the steps (it showed there first, then jumped into the chat).
        _emit(run, "reply_mode", chat=chat_only or (allowed is not None and not allowed - set(READ_ONLY)))
        # An agent or skill with a 'tools:' list gets only those tools (fewer tool definitions, fewer tokens).
        chosen = ([catalog.agents().get(forced_role)] if forced_role else []) + [catalog.skills().get(s) for s in skill_names] \
            + [catalog.agents().get(a) for a in extra_agents]
        if limit := {t for item in chosen if item for t in item.get("tools") or [] if t in TOOLS}:
            allowed = (set(TOOLS) if allowed is None else allowed | limit) & (limit | {"todo", "use_skill"})
        lang = reply_language(clean_text, opts.get("ui_lang"))
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
                _step(run, "note", "resume", "done", ui_text(lang, "ai_note_resume",
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
        empty_retries = 0
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
        missing_files: list[str] = []

        def flag_unresolved() -> None:
            """The answer ends the task while the last command still fails (or the promised file still does not
            exist): the user sees that first."""
            if deliver_retries >= 2 and missing_files and "".join(visible).strip():
                still = missing_deliverables(clean_text, "".join(visible), root, run.started)
                if still:
                    warning = ui_text(lang, "ai_note_not_delivered_final", NOTES["not_delivered_final"]["en"],
                                      files=_shown_files(still))
                    _step(run, "note", "tools", "done", warning)
                    visible[:] = [f"> {warning}\n\n" + "".join(visible).strip()]
                    _emit(run, "reset_text")
                    _emit(run, "delta", text=visible[0])
                    return
            if unresolved and unresolved_asked and used_tools and "".join(visible).strip():
                warning = ui_text(lang, "ai_note_unresolved_final", NOTES["unresolved_final"]["en"])
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
                if fixed := await _fix_language(run, ctx.model, text, lang):
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
        run.restricted = allowed is not None  # a read-only / chat-only task: tools outside it stay closed
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
            while run.steer:
                # The user wrote while the task runs: it is guidance for this same task. Nothing is stopped or
                # forgotten; the model reads it with everything done so far and carries on.
                hint = run.steer.pop(0)
                messages.append({"role": "user", "content": "[Message from the user while you are working. Take it into "
                                 "account and keep going with the same task from where you are; do not start over and "
                                 "do not repeat finished steps. Answers you already wrote are shown to the user as they "
                                 "are: build on them (e.g. save that same text to a file) instead of writing them "
                                 "again in the chat.]\n" + hint})
                _step(run, "note", "steer", "done", hint)
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
            if allowed is None:
                # Tools follow the conversation: the core set, plus each group the request (or the recent
                # conversation, or this task's own steps) is about. The model can open another group itself with
                # need_tools. Sending every definition with every turn crowded small models and filled the context.
                used_now = {s.get("data", {}).get("tool") for s in run.steps}
                avail = {"team": bool(pool_others and multi.get("delegate", True)), "mcp": has_mcp or bool(mcp_client.available_tools()), "project": bool(project)}
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
            # Built once per role and task: an unchanged prompt prefix lets local servers (Ollama, llama.cpp,
            # LM Studio) and cloud prompt caches reuse it, instead of re-reading everything after each file write.
            # Small windows (local models, 16-32K): tool definitions go out in their short form. They ride along with
            # every turn, and the full ones alone took 6-7K tokens.
            # A greeting or thanks never needs the long prompt, on any model.
            lean = chat_only or lean_for(turn_model, t_info, prompt_mode)
            compact = lean or t_info["current"] <= 32768 or force_compact
            key = (role, t_native, turn_model, frozenset(offer) if offer is not None else None, topics, lean)
            if key not in prompts:
                # Built in a worker thread: the project tree, code map and token counts of a large project would
                # otherwise hold up every other chat's stream for that time.
                prompts[key] = await asyncio.to_thread(_system_prompt, role, root, session["id"], project, skill_names,
                                                       plan, t_native, turn_model.partition(":")[2], lang, offer, compact,
                                                       extra_agents, topics, lean, clean_text, chat_memory)
            sys_text, sys_sizes = prompts[key]
            system = {"role": "system", "content": sys_text}
            # Live context accounting before every model turn; relieve it inside long tasks. Native tool definitions
            # are part of the prompt the provider counts, so they are counted here too.
            schemas = tool_schemas(offer, compact, lean) if t_native and offer != set() else None
            tool_tok = tokens.count(json.dumps(schemas, ensure_ascii=False)) if schemas else 0
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
            run.session["context_used"] = shown = real_of(est)
            _emit(run, "context", used=shown)
            t_opts = {"num_ctx": t_info["current"]} if t_info["local"] else {}
            if t_info["local"]:
                # A local server that reaches the end of its window while writing drops the oldest half of the
                # prompt (the instructions and the request with it) and keeps writing nonsense. The reply is limited
                # to the room that is really left; a cut answer or file is then continued (see 'truncated').
                room = max(2048, t_info["current"] - shown - 256)
                prof = router.profile(turn_model).get("max_tokens")
                t_opts["max_tokens"] = min(int(prof), room) if prof else room
            if degenerate:  # the model looped on one token: the next tries punish repeats and sample cooler
                t_opts.update(repeat_penalty=1.18, repeat_last_n=256, temperature=0.4)
            turn_opts = {**t_opts, "tools": schemas} if schemas else t_opts
            try:
                run.session["usage_input"] = None
                raw, tag_blocks, calls = await _stream_turn(run, turn_model, [system] + _for_model(messages, turn_model, t_native),
                                                            visible, turn_opts)
                resume_text = ""  # the turn came through: the answer is whole again
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
                    _step(run, "note", "tools", "done", ui_text(lang, "ai_note_stream_tags",
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
                        _step(run, "note", "tools", "done", ui_text(lang, "ai_note_degenerate",
                              "The model's output turned into a repeated character; trying once more with a repeat penalty."))
                        continue
                    raise ProviderError("degenerate", ui_text(lang, "err_degenerate_detail",
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
                    _step(run, "note", "tools", "done", ui_text(lang, "ai_note_no_native", NOTES["no_native"]["en"], e=e))
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
                        _step(run, "note", "salvage", "done", ui_text(lang, "ai_note_salvaged",
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
                        _step(run, "note", "tools", "done", ui_text(lang, "ai_note_stream_tags",
                              "This provider sends a tool call only when it is complete; switched to the text "
                              "protocol so files stream and nothing is lost if the connection drops."))
                if e.code in ("timeout", "unavailable", "server", "bad_gateway") and big_call and not run.split_hint:
                    # The connection dropped while the model was writing a long tool call (a whole file or document):
                    # the same giant call would stall again. Ask for the content in parts this time; the steps done
                    # so far stay in the conversation, so nothing is redone.
                    run.split_hint = True
                    messages.append({"role": "user", "content": SPLIT_HINT})
                out_of_quota = e.code in ("quota", "payment", "auth", "plan_required") or (e.code in TRANSIENT and retries >= 2)
                # A rate limit that needs a long wait (a per-minute token cap): with the pool on, a free model
                # continues at once instead of the task sitting out the window again and again.
                if e.code == "rate_limit" and multi.get("enabled") and multi.get("auto_switch", True)                         and (e.retry_at or 0) - time.time() > 8:
                    out_of_quota = True
                if out_of_quota and turn_model != model:
                    # The agent's own model is out: this role continues on the main model.
                    agent_off.add(role)
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
                        ctx_info, native = await model_info(model)
                        base_opts, budget = {}, _budget(ctx_info)
                        prompts.clear()
                        continue
                if (e.code in BUSY_CODES and not unreachable and switches < 3 and not router.is_local(turn_model)
                        and turn_model == model and (retries >= 1 or run.stalls >= 2 or (e.retry_at or 0) - time.time() > 10)):
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
                        ctx_info, native = await model_info(model)
                        base_opts, budget = {}, _budget(ctx_info)
                        prompts.clear()
                        continue
                if e.code in TRANSIENT and retries < max_retries:
                    wait = RETRY_WAITS[min(retries, len(RETRY_WAITS) - 1)]
                    if e.code in BUSY_CODES and retries == 0:
                        wait = min(wait, 5)  # one short retry first: a momentary 503 often passes in seconds
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
                    _step(run, "note", "salvage", "done", ui_text(lang, "ai_note_truncated_kept",
                          "The model's output limit cut {path} at {n} characters; that part was saved and the model "
                          "continues the file from there.", path=saved[0], n=saved[1]),
                          data={"tool": "write_file", "path": saved[0], "created": True, "added": 0, "removed": 0})
                    continue
                _step(run, "note", "tools", "done", ui_text(lang, "ai_note_truncated",
                      "The model's output was cut off while writing {name}; asking it to write it in parts.",
                      name=tr.get("name") or "-"))
                messages += [{"role": "assistant", "content": "".join(visible).strip() or "(tool call cut off)"},
                             {"role": "user", "content": SPLIT_HINT}]
                run.split_hint = True
                continue
            if chat_only:  # small talk: never execute tools, even if the model writes them
                tag_blocks, calls = [], []
            parsed = [parse_tool(b, TOOL_NAMES) for b in tag_blocks]
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
                if text_now and not is_announcement(text_now):
                    best = text_now
                if inline:
                    parsed, visible[:] = inline, [cleaned]
                    _step(run, "note", "tools", "done", ui_text(lang, "ai_note_cli_calls",
                          "The model wrote a tool call as plain text ({names}); it was recognized and is being run for real.",
                          names=", ".join(dict.fromkeys(c.name for c in inline))))
                elif (not used_tools and allowed is None and not chat_only and code_runs < 3 and "run" in TOOLS
                      and (offer is None or "run" in offer) and (WORK.search(clean_text) or RUN_ASK.search(clean_text))
                      and not HOWTO.search(clean_text) and (cmds := fenced_commands(text_now, RUN_ASK.search(clean_text)))):
                    # The user asked for an action and the model answered with the command in a code block instead
                    # of calling run ("I'll create it with ffmpeg: ```bash ffmpeg ...```"): run exactly that command
                    # now (with the usual approvals) instead of asking again and again - the result goes back to it.
                    code_runs += 1
                    parsed = [ToolCall("run", {"shell": sh}, body) for sh, body in cmds]
                    visible[:] = [text_now.split("```", 1)[0].strip()]
                    _step(run, "note", "tools", "done", ui_text(lang, "ai_note_code_run", NOTES["code_run"]["en"]))
                elif LEAK.search(text_now) and leak_retries < 2:
                    # ...and never show unparsed tool syntax: ask the model to redo the call properly.
                    leak_retries += 1
                    _emit(run, "reset_text")
                    _step(run, "note", "tools", "done", ui_text(lang, "ai_note_leak", NOTES["leak"]["en"]))
                    messages += [{"role": "assistant", "content": raw},
                                 {"role": "user", "content": "Your last reply contained raw tool-call syntax that was NOT "
                                  "executed. Call the tool correctly using the available tools, or answer in plain text "
                                  "without any tool syntax. Do not claim actions that did not run."}]
                    continue
                elif not used_tools and allowed is None and not printed_retry and "```" in text_now and (
                        RUN_ASK.search(clean_text) or FILE_NAME.search(clean_text)):
                    # The user asked to run it (or for a named file) and the reply only prints code: do it for real.
                    printed_retry = True
                    run.hold = True
                    _step(run, "note", "tools", "done", ui_text(lang, "ai_note_code_not_run", NOTES["code_not_run"]["en"]))
                    messages += [{"role": "assistant", "content": raw},
                                 {"role": "user", "content": "You only printed the code. The user asked you to create "
                                  "and run it: write the file with write_file now, run it with the run tool, and answer "
                                  "with the REAL output. Do not paste the whole code again in the answer."}]
                    continue
                elif not used_tools and allowed is None and code_nudges < 2 and WORK.search(clean_text) \
                        and CODE_NOT_RUN.search(text_now):
                    # A command/script was printed as text instead of actually run with a tool: redo it for real
                    # (twice at most; after that the reply stands, with the "nothing ran" note of the checks below).
                    code_nudges += 1
                    run.hold = True
                    _step(run, "note", "tools", "done", ui_text(lang, "ai_note_code_not_run", NOTES["code_not_run"]["en"]))
                    messages += [{"role": "assistant", "content": raw},
                                 {"role": "user", "content": "You wrote a command/script instead of actually running "
                                  "it. Call the matching tool directly now (my_location for the user's location, "
                                  "places for nearby venues/maps, research/web_search/fetch_url for web facts, run "
                                  "for a real command) - do not install packages or write ad-hoc code for something "
                                  "a tool already does."}]
                    continue
                elif not used_tools and allowed is None and fake_claims >= 2 and (
                        ACTION_ECHO.search(text_now) or (CHANGE_REQUEST.search(clean_text) and CHANGE_CLAIM.search(text_now))):
                    # Still only claims after two reminders: keep the answer, but say plainly that nothing ran.
                    warning = ui_text(lang, "ai_note_no_action", "Nothing was executed in this turn.")
                    _step(run, "note", "tools", "done", warning)
                    visible[:] = [f"> {warning}\n\n{ACTION_ECHO.sub(chr(10), text_now).strip()}"]
                    _emit(run, "reset_text")
                    _emit(run, "delta", text=visible[0])
                    break
                elif not used_tools and allowed is None and (
                        ACTION_ECHO.search(text_now) or (CHANGE_REQUEST.search(clean_text) and CHANGE_CLAIM.search(text_now))):
                    # Claims (or copies the app's action note) without running a single tool: do it for real.
                    fake_claims += 1
                    run.hold = True
                    messages += [{"role": "assistant", "content": ACTION_ECHO.sub(" ", raw).strip()},
                                 {"role": "user", "content": "Nothing was executed in this turn: no tool ran, so no file "
                                  "was changed and no command was run. The bracketed '[Tool actions in this turn ...]' "
                                  "notes are written by the app about earlier turns; never write them yourself. Do the "
                                  "requested work now with the tools, then report what really happened."}]
                    continue
                elif (not used_tools and allowed is None and not chat_only and "".join(visible).strip()
                      and (is_promise(text_now) or is_announcement(text_now))):
                    # The reply promises work ("I'll create the chart now", "it is being generated...") but no tool
                    # was called: nothing is happening. Make it act; after two more empty promises say so plainly.
                    promise_retries += 1
                    if promise_retries > 2:
                        warning = ui_text(lang, "ai_note_no_action", "Nothing was executed in this turn.")
                        _step(run, "note", "tools", "done", warning)
                        visible[:] = [f"> {warning}"]
                        _emit(run, "reset_text")
                        _emit(run, "delta", text=visible[0])
                        best = ""
                        break
                    run.hold = True
                    _step(run, "note", "tools", "done", ui_text(lang, "ai_note_promise",
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
                elif (used_tools and not visual_retry and allowed is None and VISUAL_ASK.search(clean_text)
                      and (docs := [s for s in run.steps if s.get("status") == "done" and (s.get("data") or {}).get("tool") == "make_doc"
                                    and not str((s.get("data") or {}).get("path", "")).lower().endswith((".xlsx", ".csv"))])
                      and not any((s.get("data") or {}).get("images") for s in docs)):
                    # A chart/image was asked for and the document that was made has none: saying "with a chart"
                    # would be false. Create it for real and rebuild the document (once).
                    visual_retry = True
                    run.hold = True
                    _step(run, "note", "tools", "done", ui_text(lang, "ai_note_no_visual",
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
                elif (used_tools and not edit_retry and allowed is None and not ctx.files_changed and text_now
                      and FILE_EDIT_ASK.search(clean_text) and FILE_REF.search(clean_text)):
                    # "Add this to the same file and run it again": a weak model ran a one-off command that printed
                    # the wanted output and reported success, while the file on disk was never touched. Once.
                    edit_retry = True
                    run.hold = True
                    _step(run, "note", "tools", "done", ui_text(lang, "ai_note_no_edit",
                          "The request was to change a file, but no file was changed; the model is asked to edit it."))
                    messages += [{"role": "assistant", "content": raw or text_now},
                                 {"role": "user", "content": "[App note] The user asked to change a file, but no file was "
                                  "written or edited in this task (only commands ran), so the file on disk is unchanged. "
                                  "Make the change in the file itself now with edit_file (read_file first if you do not "
                                  "have its content), run it again if asked, and answer with the real output. If no "
                                  "change is needed at all, say so plainly."}]
                    continue
                elif (deliver_retries < 2 and allowed is None and not chat_only and text_now
                      and (missing := await asyncio.to_thread(missing_deliverables, clean_text, text_now, root, run.started))):
                    # The answer presents a file (the PDF asked for, "open report.pdf") that is not on disk: a weak
                    # model printed a script and said "created". Make it produce the file for real (twice at most).
                    deliver_retries += 1
                    missing_files = missing
                    run.hold = True
                    _emit(run, "reset_text")
                    _step(run, "note", "tools", "done", ui_text(lang, "ai_note_not_delivered", NOTES["not_delivered"]["en"],
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
                                  "say plainly that it was not created."}]
                    continue
                elif used_tools and unresolved and not unresolved_asked and text_now and allowed is None:
                    # The last command failed and nothing fixed it, yet the model is writing its final answer
                    # (often "done, the video has subtitles"): make it fix the step or say plainly that it failed.
                    unresolved_asked = True
                    run.hold = True
                    _step(run, "note", "tools", "done", ui_text(lang, "ai_note_unresolved", NOTES["unresolved"]["en"]))
                    messages += [{"role": "assistant", "content": raw},
                                 {"role": "user", "content": "[App note] The last command FAILED and no later command "
                                  "fixed it:\n" + unresolved + "\nIts output file does not exist or is broken. Fix it "
                                  "now (different options/codec/format, overwrite with -y), check the result, and only "
                                  "then answer. If it really cannot be done, say plainly in the answer what failed "
                                  "and why - never present it as done."}]
                    continue
                elif used_tools and len(text_now) >= 200 and not is_announcement(text_now) and open_todos:
                    # A real final answer with the list left unticked: finish instead of making the model
                    # write the answer twice; the step it was on is done.
                    run.todos = [{**t, "status": "completed"} if t["status"] == "in_progress" else t for t in run.todos]
                    _emit(run, "todos", todos=run.todos)
                    await fix_language(text_now)
                    flag_unresolved()
                    break
                elif used_tools and nudges < (6 if opts.get("goal_mode") else 3) and allowed is None and (
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
                    await fix_language(text_now)
                    flag_unresolved()
                    break
            used_tools = True
            run.hold = False
            _emit(run, "reset_text")  # interim narration is kept in the trace, not in the final answer
            narration = "".join(visible).strip()
            if narration and not run.noted:
                _step(run, "note", role, "done", narration)
            failure = None
            if calls:
                messages.append({"role": "assistant", "content": narration, "by": turn_model,
                                 **({"thinking_blocks": run.thinking_blocks} if run.thinking_blocks else {}),
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
                        unresolved = "" if res.ok else res.output[-700:]
                    if not res.ok and c["name"] == "run":
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
                        unresolved = "" if res.ok else res.output[-700:]
                    if not res.ok and name == "run":
                        failure = res.output
                messages += [{"role": "assistant", "content": raw},
                             {"role": "user", "content": "Tool results:\n" + "\n".join(results)}]
                _checkpoint(run, messages, first_run_msg, clean_text)
            if failure:
                debug_attempts += 1
                signature = re.sub(r"\d+", "#", failure[-400:])
                if (not limits.get("unlimited_debug") and debug_attempts > limits["max_debug_attempts"]) or signature == last_failure:
                    messages.append({"role": "user", "content": "The same failure repeats without progress. Stop calling "
                                     "tools; explain the diagnosis and what the user should do."})
                elif (allowed is None and NOT_FOUND.search(failure)
                      and (absent := [n for n in dict.fromkeys(FILE_NAME.findall(failure[-1500:]))
                                      if not (root / n).exists() and n not in ctx.files_changed][:2])):
                    # A weak model ran a script it never wrote ("can't open file 'hesap.py'") and then searched
                    # the web for the error: the cause is plain - the file does not exist yet.
                    hint = (f"\n\n[App note: {', '.join(absent)} does NOT exist - no tool wrote it in this task. Create "
                            "it first with write_file (the complete content), then run it. No web search needed.]")
                    messages[-1] = {**messages[-1], "content": (messages[-1].get("content") or "") + hint}
                elif allowed is None and not search_closed:
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
                note = ui_text(lang, "ai_budget_note", BUDGET_NOTE["en"], n=limits["max_iterations"])
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
            # Servers the agent started and did not stop: stopped automatically a while after the task (safety net).
            ttl = float(limits.get("server_ttl_minutes", 10) or 0)
            if ttl > 0 and (left := proc_manager.expire(f"{session['id']}:", ttl * 60)):
                _step(run, "note", "process", "done", ui_text(lang, "ai_note_server_ttl",
                      "{n} server(s) started in this task are still running; they stop automatically in {m} min "
                      "(or stop them now under Context > Background tasks).", n=len(left), m=int(ttl)))
            # A finished run never keeps spinning steps (closed chat, error, cancel...).
            for s in run.steps:
                if s["status"] == "running":
                    s["status"] = "done" if status == "ok" else "error"
                    _emit(run, "step", step=s)
            answer = ACTION_ECHO.sub("\n", "".join(visible)).strip() or (best if status in ("ok", "budget", "cancelled") else "")
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
            if status == "ok" and answer and not answer.rstrip().endswith("?") and any(
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
            db.add_message(session["id"], "assistant", answer,
                           {"steps": run.steps, "status": status, "model": model, "todos": run.todos, "outputs": outputs,
                            "timing": timing, **({"changes": changed} if changed else {}),
                            **(failed if status == "error" else {})})
            try:
                if ctx.files_changed or ctx.commands:
                    name = project["name"] if project else (session.get("title") or "Sohbet")
                    workspace.write_state(sessions.state_file(session["id"]), root, name, clean_text[:200],
                                          ctx.files_changed, ctx.commands, status)
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
            db.execute("UPDATE sessions SET context_used=?, context_stats=? WHERE id=?",
                       (used, json.dumps(run.stats) if run.stats else None, session["id"]))
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
        if not row or not row[0]["title_auto"]:
            return
        if router.is_local(model):
            # A local server runs one request at a time: a title call there (20-40 s on a CPU) would delay the
            # user's next message and push the chat out of the server's prompt cache. A cloud model the user set up
            # writes it instead; without one, the request's own first words are the title (no model call).
            model = router.side_model()
            if not model:
                return
        raw = await asyncio.wait_for(router.complete(model, [
            {"role": "system", "content": TITLE_PROMPT.format(language=LANG_NAMES.get(lang, lang))},
            {"role": "user", "content": f"USER: {user_text[:600]}\n\nASSISTANT: {answer[:600]}"}],
            {"max_tokens": 200, "think": False, "lane": "side"}), 120)
        title = clean_title(raw.strip().splitlines()[0] if raw.strip() else "")
        row = db.query("SELECT title_auto FROM sessions WHERE id=?", (session_id,))
        if 2 <= len(title) <= 70 and row and row[0]["title_auto"]:
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
                                         {"attachments": opts.get("attachments", [])})
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
