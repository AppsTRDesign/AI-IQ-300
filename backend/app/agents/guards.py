"""Output guards of a running task: repetition / babble / word-salad cuts, page errors and failure signatures.

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



PAGE_TOOLS = {"web_screenshot", "browser_navigate", "browser_snapshot", "browser_batch", "browser_check"}


PAGE_ERR = re.compile(r"Fatal error|Parse error|Uncaught (?:Exception|Error|TypeError|ReferenceError|SyntaxError|PDOException)"
                      r"|Warning</b>:|\(HTTP 5\d\d\)|\bHTTP 5\d\d\b|Internal Server Error|Traceback \(most recent call|Unable to open database"
                      # web_screenshot / browser checks: a JS error, a 404 script or stylesheet, a bundle refused,
                      # the page check the browser tools add after every page action
                      r"|JS error: |\bHTTP 404: \S+\.(?:m?js|css|bundle)\b|Refused to execute script|\[Page check: |UNSTYLED PAGE: ", re.I)


def page_state(name: str, res, unresolved: str) -> str:
    """A page the model opened shows an error (a PHP Fatal error, a 500, an uncaught exception): the task is not
    done - it is held like a failed command until a later look at the page is clean. Before, a site that showed
    "Fatal error: Unable to open database" on its menu page was reported as finished."""
    if name not in PAGE_TOOLS:
        return unresolved
    if m := PAGE_ERR.search(res.output or ""):
        start = max(0, m.start() - 80)
        return "[page error] " + (res.output or "")[start:start + 600]
    return "" if unresolved.startswith("[page error]") else unresolved


CHECK_TOOLS = {"read_file", "inspect_media", "browser_navigate", "web_screenshot", "browser_check", "browser_snapshot"}
_OUT_PATH = re.compile(r"[\w.:-]*(?:[\\/]+[\w.-]+)+\.\w{1,5}\b|[\w-]+\.(?:html?|md|json|pdf|mp4|mp3|wav|png|jpe?g|csv|txt|zip)\b")


def _norm_path(p: str, root: Path | None) -> str:
    p = re.sub(r"^file:/+", "", str(p).strip().strip("'\"`")).replace("\\\\", "/").replace("\\", "/").lower()
    r = str(root).replace("\\", "/").lower().rstrip("/") + "/" if root else ""
    if r and p.startswith(r):
        p = p[len(r):]
    return p.lstrip("./")


def failed_outputs(unresolved: str, root: Path | None, since: float) -> list[str]:
    """Files the failed command's output names that exist on disk and were written during this task (a program that
    finished its job and only reported a non-zero exit: 'done in 63.7s', "report": "out\\x\\report.html")."""
    if not unresolved or unresolved.startswith("[page error]") or ": SYNTAX ERROR -" in unresolved or not root:
        return []
    found: list[str] = []
    for m in _OUT_PATH.finditer(unresolved.replace("\\\\", "\\")):
        rel = _norm_path(m.group(0), root)
        if len(rel) < 4 or rel in found:
            continue
        p = Path(rel) if Path(rel).is_absolute() else Path(root) / rel
        try:
            if p.is_file() and p.stat().st_size > 0 and p.stat().st_mtime >= since - 5:
                found.append(rel)
        except OSError:
            continue
    return found


def output_checked(unresolved: str, name: str, args: dict | None, body: str, ok: bool, root: Path | None,
                   since: float) -> str:
    """The failed command's own output file was then opened and read without an error (read_file / inspect_media /
    the page in the browser): the step is shown to work, so it is no longer an open failure. A rea-video run reported
    exit 1 (PowerShell 2>&1), the model read report.html and opened it cleanly, and the answer still got "the last
    command still fails". Returns the new 'unresolved'."""
    if not unresolved or not ok or name not in CHECK_TOOLS:
        return unresolved
    targets = [str(v) for k, v in (args or {}).items() if k in ("path", "url", "file", "src") and v] + ([body] if body else [])
    outs = failed_outputs(unresolved, root, since)
    for t in targets:
        tn = _norm_path(t, root)
        if tn and any(tn == o or tn.endswith("/" + o) or o.endswith("/" + tn) for o in outs):
            return ""
    return unresolved


def failure_signature(failure: str) -> str:
    """A failed command's error without what changes on every attempt (temp script names, paths, hex ids, numbers),
    so the same error is recognised as the same."""
    return re.sub(r"[A-Za-z]:\\[^\s:'\"]+|/[^\s:'\"]*/[^\s:'\"]+|\b[0-9a-f]{6,}\b|\d+", "#",
                  (failure or "")[-600:]).strip()[-400:]


_UNIT = re.compile(r"[^\n.!?]{25,}[.!?]?")


def _loop_cut(text: str) -> str | None:
    """The text up to where a repetition loop starts, or None. A loop: one sentence (25+ characters) that appears 4+
    times within the last 4000 characters (code is left alone: repeated lines are normal there)."""
    if len(text) < 400 or text.count("```") % 2:
        return _babble_cut(text)
    tail = text[-4000:]
    counts: dict[str, int] = {}
    for m in _UNIT.finditer(tail):
        s = m.group(0).strip()
        if len(s) >= 25 and not s.lstrip().startswith(("|", "-", "*", "<", "{", "#")):
            counts[s] = counts.get(s, 0) + 1
    rep = max(counts.items(), key=lambda kv: kv[1], default=(None, 0))
    if rep[1] < 4:
        return _list_cut(text) or _babble_cut(text)
    first = text.find(rep[0])
    second = text.find(rep[0], first + len(rep[0]))
    return text[:second].rstrip() if second > 0 else None


def _list_cut(text: str) -> str | None:
    """A list that never ends: the same few items again and again, separated by commas ("browser_screenshot,
    browser_navigate, browser_inspect, ..." and "1215752192 bps Intel(R) Wi-Fi 6E ..., Realtek ..." for minutes, seen
    live on qwen3-vl). No sentence is long enough for the check above. In the last 3000 characters: 40+ items of
    which at most a quarter are different = a loop; cut where its second round starts."""
    if text.count("```") % 2:
        return None
    pos = max(0, len(text) - 3000)
    tail = text[pos:]
    items = [m for m in re.finditer(r"[^,;\n]{2,160}", tail)]
    if len(items) < 40:
        return None
    norm = [re.sub(r"\s+", " ", m.group(0)).strip().lower() for m in items]
    if len(set(norm)) > len(norm) * 0.25:
        return None
    loop = set(norm)
    start = max(0, len(text) - 20000)
    seen: set[str] = set()
    for m in re.finditer(r"[^,;\n]{2,160}", text[start:]):
        n = re.sub(r"\s+", " ", m.group(0)).strip().lower()
        if n in loop and n in seen:  # an item of the loop met again: its second round starts here
            cut = start + m.start()
            return text[:cut].rstrip(" ,;")
        seen.add(n)
    return None


def _babble_cut(text: str) -> str | None:
    """A model that lost the thread writes a run of tiny, all-different lines ("BOOM.", "LFG.", "tulcall.", "火.",
    "DISPARAR.") in mixed languages instead of calling its tool: none repeats, so the loop check above never fired
    and gemma babbled for minutes. 14+ lines in a row of at most 4 words each (outside code / lists) is that state:
    cut where the run starts."""
    if text.count("```") % 2:
        return None
    lines = text.split("\n")
    run_start, run_len = None, 0
    for i, ln in enumerate(lines):
        s = ln.strip().strip("-_*#>").strip()
        if not s:
            continue
        short = len(s) <= 40 and len(s.split()) <= 4 and not re.match(r"^(\d+[.)]|[|<{`$]|[\w./\\-]+\.\w{1,5}\b)", s)
        if short:
            if run_len == 0:
                run_start = sum(len(x) + 1 for x in lines[:i])
            run_len += 1
            if run_len >= 14:
                return text[:run_start].rstrip()
        else:
            run_len = 0
    return _salad_cut(text)


_SALAD_WORD = re.compile(r"[^\W\d_][\w'’-]*", re.U)


def _salad_cut(text: str) -> str | None:
    """Word salad: a model whose reasoning fell apart writes hundreds of words with no sentence in them ("exit
    withdraw retreat pull back step aside stand down ..." / "size cells connection oriented virtual circuits VC
    permanent switched signaling SS7 ...", seen live for minutes on NVIDIA and EVREN). Nothing repeats, so the loop
    check above never fired. 160+ words on one line with almost no punctuation is that state: cut where it starts."""
    if text.count("```") % 2:
        return None
    pos = max(0, len(text) - 6000)
    for ln in text[pos:].split("\n"):
        words = _SALAD_WORD.findall(ln)
        if len(words) >= 160:
            marks = len(re.findall(r"[.,;:!?()\[\]{}=<>\"`]", ln))
            if marks / len(words) < 0.03:
                at = text.find(ln, pos)
                # keep the sound start of that line (its first sentence-like words), drop the salad
                return text[:at].rstrip() if at > 0 else ""
        pos += len(ln) + 1
    return None
