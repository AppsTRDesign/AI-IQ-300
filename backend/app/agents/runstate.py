"""A running task's state (Run), the live run table, timings, and how steps and events reach the chat (_emit / _step).

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
    fs_epoch: int = 0  # tools that can change the disk so far (a repeated list_dir / read_file before the next one is a loop)
    fail_streak: int = 0  # model turns whose tool calls failed in a row: every 4 the model must change the approach
    turn_idx: int = 0  # tool rounds so far (fail_streak counts one per round)
    plan_refusals: int = 0  # work calls refused because the multi-part job had no plan yet
    counted: dict = field(default_factory=dict)  # call pattern with numbers masked -> calls (counting loops)
    media_calls: dict = field(default_factory=dict)  # media tool -> calls in this task (MEDIA_CAP)
    ctx_peak: int = 0  # the largest context a turn of this task sent (the meter shows it after the task)
    tools_off: bool = False  # stuck in a loop: no tools are offered or run any more, the model must answer
    turn_counts: dict = field(default_factory=dict)  # calls in the current turn
    turn_fail_sigs: dict = field(default_factory=dict)  # (turn, tool, error kind) -> failures in that turn
    outcomes: dict = field(default_factory=dict)  # call -> (result digest, times in a row): same call, same result
    fail_turn: int = -1
    file_loops: int = 0  # files that turned into a generation loop in this task (see _file_loop_check)
    written_names: set = field(default_factory=set)  # file names written in this task (to-do items naming several)
    overthought: int = 0  # turns cut for reasoning far too long without acting (THINK_CAP)
    soft_gate: bool = False  # tools limited to read-only because the request's words looked like a question
    gate_lifted: bool = False  # the model asked for work tools (need_tools): lift that limit next turn
    todos_auto: bool = False  # the list was opened by the app (from the request / the written plan), not the model
    auto_ticked: int = 0  # items the app ticked itself since the model's last todo call (its advance means those)
    todo_claims: dict | None = None  # items the model's last todo call marked done + the work count then
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
    probe: dict | None = None  # connection check of the current silent stream: {"state": checking|alive|slow|..., "ms"}
    restricted: bool = False  # a chat-only / read-only task: tools outside its set are never opened on demand
    partial_saved_at: float = 0.0  # last time the streaming call was written to disk (power-cut safety)
    live_ctx: object = None  # the task's ToolContext: a file streaming in is written live into its real path
    live_at: float = 0.0  # last live write of the streaming file
    silent_writer: bool = False  # the provider sends tool calls only at the end (no live progress)
    tps: float | None = None  # output speed of the last model turn (tokens per second)
    whole_calls: bool = False  # a big native tool call arrived in one piece at the end (no streamed arguments)
    # The reasoning of the last model turn and how long it took: a turn that breaks off (provider pause, timeout,
    # drop) hands it to the retry, which acts on it instead of thinking the whole plan through again (minutes).
    last_thinking: str = ""
    think_secs: float = 0.0
    carry_thinking: str = ""  # reasoning carried into the next request after a break (see _carry_thinking)
    no_think: bool = False  # the next request goes without reasoning (the carried plan is already there)
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
            # output speed over the whole task: generated tokens / generation time (after each first token)
            "out_tokens": sum(t.get("out_tokens", 0) for t in p["turns"]) or None,
            "tps": (round(sum(t.get("out_tokens", 0) for t in p["turns"])
                          / max(0.001, sum(t.get("gen_ms", 0) for t in p["turns"]) / 1000), 2)
                    if sum(t.get("gen_ms", 0) for t in p["turns"]) > 300 else None),
            "tools_ms": r(tools_ms), "tools": {k: {**v, "ms": r(v["ms"]), "max_ms": r(v["max_ms"])} for k, v in tools.items()},
            "team_ms": r(tools.get("team", {}).get("ms", 0.0)), "side_ms": r(p["side_ms"]),
            "retry_ms": r(p.get("retry_ms", 0.0)),  # waiting after provider errors (rate limits, overload)
            "overhead_ms": r(max(0.0, total - model - tools_ms - p["side_ms"] - p.get("retry_ms", 0.0)))}


RUNS: dict[str, Run] = {}


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
    if kind == "note" and detail:
        # A model that copied the app's own "[Tool actions in this turn ...]" history line into its narration:
        # that line is bookkeeping for the model, never text for the user.
        detail = ACTION_ECHO.sub("\n", detail).strip()
        if not detail:
            return ""
    if kind == "note" and not step_id and detail and any(
            x["kind"] == "note" and x["detail"] == detail[:8000] for x in run.steps):
        return next(x["id"] for x in run.steps if x["kind"] == "note" and x["detail"] == detail[:8000])
    sid = step_id or uuid.uuid4().hex[:8]
    now = time.time()
    existing = next((s for s in run.steps if s["id"] == sid), None)
    step = {"id": sid, "kind": kind, "title": title, "status": status, "detail": (detail[-30000:] if kind == "thinking" else detail[:8000]),
            "data": data or {}, "ts": now}
    # how long the step took (its first update to the one that ends it): shown in the steps export with the speed
    t0 = (existing.get("t0") or existing.get("ts") or now) if existing else now
    step["t0"] = t0
    if status != "running" and existing:
        step["ms"] = round((now - t0) * 1000)
    if existing:
        existing.update(step)
    else:
        run.steps.append(step)
    _emit(run, "step", step=step)
    return sid


TOOL_TITLES = {"write_file": "file", "read_file": "read", "read_document": "read", "my_location": "places", "system_info": "system", "list_dir": "list", "run": "command", "start": "process",
               "stop": "stop", "web_search": "search", "research": "search", "fetch_url": "fetch", "browser_check": "visual",
               "make_doc": "document", "doc_template": "document", "delete_file": "delete", "use_skill": "skill", "edit_file": "edit",
               "search_code": "grep", "symbols": "grep", "ask_model": "delegate", "remember": "memory",
               "impact": "grep", "mcp": "mcp", "mcp_add": "mcp", "team": "team", "web_screenshot": "screenshot", "stock_photo": "photo", "generate_image": "image_gen", "edit_video": "video_edit", "animate_image": "video_gen", "generate_video": "video_gen", "mobile_env": "command", "mcp_search": "mcp", "inspect_media": "inspect", "speech_to_text": "transcribe", "text_to_speech": "speech","save_catalog": "catalog",
               "places": "places", **{n: "browser" for n in BROWSER_TOOLS}}


# Step kinds that are actions worth remembering in later turns (see _history).
ACTION_KINDS = {"photo", "image_gen", "video_gen", "video_edit", "inspect", "speech", "transcribe", "file", "edit", "delegate", "memory", "mcp", "team", "command", "process", "document", "delete", "skill", "search", "fetch", "visual", "screenshot", "catalog", "browser"}
