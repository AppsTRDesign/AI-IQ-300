"""Per-model numbers learned from real requests: the token ratio of each model's tokenizer, the time to the first token, which models are slow (lean prompts for them).

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


def _shown_tokens(n: int, model: str) -> int:
    """A raw estimate_tokens() count, scaled like the context panel (run.session['context_used']) so a number
    shown next to a compression step always matches what the panel shows for the same model."""
    return int(n * CTX_RATIO.get(model, 1.0))
