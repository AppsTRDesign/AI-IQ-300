"""The task's conversation as models read it: older steps shortened (files read and unchanged stay whole), native calls shown in the tag protocol, token estimates, trimming and compression.

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
from .learning import _shown_tokens  # noqa: F401
from .runstate import ACTION_KINDS  # noqa: F401


OLD_STEP_MARK = "[older step shortened"


KEEP_RECENT = 6  # the latest messages of the task always go in full


def _short(text: str, head: int, tail: int, what: str) -> str:
    return f"{text[:head]}\n{OLD_STEP_MARK}: {len(text) - head - tail} characters of {what} left out to save context. " \
           f"You saw it whole when it ran and what you wrote from it then is right - run it again only for a detail " \
           f"your work so far does not have]\n{text[-tail:] if tail else ''}"


def _gone_body(text: str) -> str:
    """An old file body in the model's own earlier tool call. It used to keep its first 300 characters followed by the
    shortening note, and the model copied that shape into NEW files (real code, then the note): minutes of writing
    refused four times in one task. The whole body becomes one line that looks like no file at all, so there is no
    'content + note' pattern left to imitate (and a copied line is refused in a second)."""
    return f"{OLD_STEP_MARK}: file body ({len(text)} characters) is on disk, not repeated here - read_file it if needed]"


READ_TOOLS = {"read_file", "read_document"}


CHANGE_TOOLS = {"write_file", "edit_file", "delete_file"}


_RESULT_BLOCK = re.compile(r'(<result tool="([\w.-]+)" ok="(?:true|false)">\n)(.*?)(\n</result>)', re.S)


_READ_HEAD = re.compile(r"^\[([^\]\n]+?) (?:lines|satır) (\d+)-(\d+) of \d+")


_TAG_CALL = re.compile(r'<(?:tool\s+name="([\w.-]+)"|([a-z_]+))((?:\s+[\w.-]+\s*=\s*(?:"[^"\n]*"|\'[^\'\n]*\'))*)\s*/?>')


def _pkey(path: str) -> str:
    return str(path or "").replace("\\", "/").lstrip("./").lower()


def _kept_reads(messages: list[dict], first: int, budget: int) -> set:
    """Which read_file results stay whole when older steps are shortened: the newest read of each file (and range)
    that the task has not changed since, newest first, up to `budget` characters. Shortening every tool output after
    three turns took away the files the model had just read: it read style.css twelve times in 80 steps ("I need the
    class names again"), forgot, read again - the reading loop users saw in every long task."""
    if budget <= 0:
        return set()
    changed: dict[str, int] = {}
    calls: dict[str, tuple[str, dict]] = {}
    reads: list[tuple[tuple, str, int]] = []  # (id, file key, size)
    for i in range(first, len(messages)):
        m = messages[i]
        for c in m.get("tool_calls") or []:
            a = c.get("arguments") if isinstance(c.get("arguments"), dict) else {}
            calls[c.get("id")] = (c.get("name"), a)
            if c.get("name") in CHANGE_TOOLS and a.get("path"):
                changed[_pkey(a["path"])] = i
        content = m.get("content") if isinstance(m.get("content"), str) else ""
        if m.get("role") == "assistant" and content:
            for t in _TAG_CALL.finditer(content):
                if (t.group(1) or t.group(2)) in CHANGE_TOOLS and (p := attrs(t.group(3)).get("path")):
                    changed[_pkey(p)] = i
        if m.get("role") == "tool" and m.get("name") in READ_TOOLS:
            name, a = calls.get(m.get("tool_call_id"), ("", {}))
            rng = json.dumps({k: v for k, v in a.items() if k != "path"}, sort_keys=True, default=str)
            reads.append(((i, None), f"{_pkey(a.get('path'))}#{rng}", len(content)))
        elif content.startswith("Tool results:") and i > first:
            prev = messages[i - 1].get("content") if isinstance(messages[i - 1].get("content"), str) else ""
            asked = [attrs(t.group(3)) for t in _TAG_CALL.finditer(prev or "") if (t.group(1) or t.group(2)) in READ_TOOLS]
            n = 0
            for j, b in enumerate(_RESULT_BLOCK.finditer(content)):
                if b.group(2) not in READ_TOOLS:
                    continue
                head = _READ_HEAD.match(b.group(3))
                a = asked[n] if n < len(asked) else {}
                n += 1
                path = head.group(1) if head else a.get("path", "")
                rng = f"{head.group(2)}-{head.group(3)}" if head else json.dumps(
                    {k: v for k, v in a.items() if k != "path"}, sort_keys=True)
                reads.append(((i, j), f"{_pkey(path)}#{rng}", len(b.group(3))))
    keep, seen, used = set(), set(), 0
    for rid, key, size in reversed(reads):
        path = key.split("#", 1)[0]
        if not path or key in seen or changed.get(path, -1) > rid[0] or used + size > budget:
            continue
        seen.add(key)
        used += size
        keep.add(rid)
    return keep


def shrink_old_steps(messages: list[dict], first: int, keep_reads: int = 0) -> None:
    """Every turn sends the whole task again, so each finished step made all later turns longer: whole files the
    model wrote (in its tool calls) and long tool outputs, read again on every call (19K -> 34K tokens in one task,
    minutes before the first token, dropped connections). Older steps keep their beginning and end; the last
    KEEP_RECENT messages stay complete. Done once per message (marked), so the shortened history stays the same
    from turn to turn (prompt caches keep working). Files the model read and has not changed since stay whole up to
    keep_reads characters (see _kept_reads), so it does not have to read them again."""
    end = len(messages) - KEEP_RECENT
    kept = _kept_reads(messages, first, keep_reads)
    # How much of an old tool output stays: 1.1K characters on a small window, up to 16K on a large one (a 1M window
    # cut system_info to 1.1K; the model then thought it had "invented" the values and ran everything again).
    room = max(1100, min(16000, (keep_reads or 0) // 5))
    head, tail = int(room * 0.65), room - int(room * 0.65)
    for i, m in enumerate(messages[first:max(first, end)], first):
        content = m.get("content")
        if isinstance(content, str) and content.startswith("Tool results:") and len(content) > 1800:
            # per result: a read that stays is left whole, the other outputs of the same turn are shortened
            def one(b: re.Match, _i=i) -> str:
                j = one.n
                one.n += 1
                body = b.group(3)
                if (_i, j) in kept or len(body) <= room + 400 or OLD_STEP_MARK in body:
                    return b.group(0)
                return b.group(1) + _short(body, head, tail, "this tool output") + b.group(4)
            one.n = 0
            if _RESULT_BLOCK.search(content):
                m["content"] = _RESULT_BLOCK.sub(one, content)
            elif OLD_STEP_MARK not in content:
                m["content"] = _short(content, head, tail, "this tool output") if len(content) > room + 400 else content
            continue
        if isinstance(content, str) and len(content) > 1800 and OLD_STEP_MARK not in content:
            if m.get("role") == "tool":
                stale_read = m.get("name") in ("read_file", "read_document")  # a read not kept = the file changed since
                if (i, None) not in kept and (stale_read or len(content) > room + 400):
                    m["content"] = (_short(content, 700, 400, "this tool output") if stale_read
                                    else _short(content, head, tail, "this tool output"))
            elif m.get("role") == "assistant":
                # tag protocol: file contents inside <tool name="write_file" ...>...</tool>
                m["content"] = re.sub(
                    r'(<tool name="(?:write_file|make_doc|edit_file)"[^>]*>)(.{1500,}?)(</tool>)',
                    lambda x: x.group(1) + _gone_body(x.group(2)) + x.group(3),
                    content, flags=re.S)
        for c in m.get("tool_calls") or []:
            args = c.get("arguments")
            if c.get("name") in ("write_file", "make_doc", "edit_file", "append_file") and isinstance(args, dict):
                for k in ("content", "body", "new", "new_string", "text"):
                    v = args.get(k)
                    if isinstance(v, str) and len(v) > 1500 and OLD_STEP_MARK not in v:
                        c["arguments"] = {**args, k: _gone_body(v)}
                        args = c["arguments"]


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
