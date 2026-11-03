"""Agent run loop. The default role is a natural assistant; @agent mentions and /skill mentions shape it.
Tools are called with the provider's native function calling when the model supports it, otherwise with a
text tag protocol. Failed commands switch the next turn to the debugger role. Progress is published as run
events so the chat shows a collapsible activity trace."""
from __future__ import annotations

import asyncio
import json
import re
import sys
import time
import uuid
from dataclasses import dataclass, field

from .. import approvals, db, sessions, workspace
from ..config import load_settings
from ..events import bus
from ..llm import router
from ..llm.providers import ProviderError
from ..tools.registry import READ_ONLY, TOOLS, ToolContext, ToolResult, clip, split_args, tool_schemas, tools_prompt
from . import catalog
from .stream_parser import LEAK, StreamSplitter, extract_inline_calls, parse_tool

HISTORY_MESSAGES = 30
OS_NAME = {"win32": "Windows", "darwin": "macOS"}.get(sys.platform, "Linux")
SHELLS = ("powershell (default), cmd, python, node, php, bash" if sys.platform == "win32"
          else "bash (default), python, node, php")
# Language-neutral marker for the injected summary (no wording that could pull the reply language).
SUMMARY_TAG = "[Summary of the earlier conversation (context compressed)]"
DEFAULT_ROLE = "assistant"

SYSTEM_CORE = """# Identity
Your name is AI IQ 300. You are an autonomous AI assistant running locally on the user's own {os_name} computer
(underlying model: "{model}") and you can act on the computer with tools. When you greet or introduce yourself, say
you are AI IQ 300. Never claim to be another assistant or product (not ChatGPT, Claude, Qwen, etc.).

# Environment
Working directory: {root}{project}
Date: {date}

# How to behave
- Talk naturally, like a capable assistant, in the user's language and tone. Never introduce yourself with an internal
  role or agent name (planner, coder, debugger, tester, assistant); just help.
- Small talk, greetings, questions about you ("who are you?", "how are you?"), explanations and anything you can
  answer from knowledge: reply in text only. NEVER call tools for these (no listing folders, no reading files).
  Only use tools when the user asks for an action on the computer or for current information from the web.
- When the user does ask for an action (create or edit files/projects, run code or commands, install packages, test,
  search the web, make documents): actually DO it with tools instead of describing it. Work step by step, run and
  verify, fix errors, and continue until it works.
- Write complete files, never placeholders. Paths are relative to the working directory.
- A folder the user names ("in the onur folder", "web-app klasöründe") is a sub-folder of the working directory:
  use relative paths like onur/index.html. Never invent absolute paths (Desktop, user home, drive letters). write_file
  creates missing folders itself, so no mkdir is needed.
- Shells: {shells}; shell "exec" runs a program directly (git, npm, pip...).
- Questions, advice and explanations are answered in chat. Create or change files only when the user asks for a
  file, document, folder, project or app.
- Multi-step tasks: keep working with tools until the WHOLE task is finished. Never end a reply by announcing the next
  step ("now I'll create X"): call the tool for it in the same reply. Only stop when everything works or you need
  the user's decision.
- The latest user message is the task. Earlier messages are background; do not redo or continue an earlier task
  unless the latest message asks for it.
- When done, briefly say what you did and how to run/use it. Never claim success a tool result did not show.
- For facts that may be current or that you are unsure about, use research/web_search and cite source URLs.
  Search queries use the user's own topic words; do not add years, dates or other terms the user did not ask for.
  If a site is BLOCKED, say so and use other sources; never present a block page or guesses as content.
- Code shown to the user goes in fenced blocks with a language.
- File contents passed to write_file are the raw file only: no markdown fences, no "EOF"/"end of file" markers.
- Narration before a tool call is one short sentence; never repeat the final answer twice."""

# Language names for the reply-language rule.
LANG_NAMES = {"tr": "Turkish (Türkçe)", "en": "English", "de": "German (Deutsch)", "fr": "French (Français)",
              "es": "Spanish (Español)", "it": "Italian (Italiano)", "pt": "Portuguese (Português)",
              "nl": "Dutch (Nederlands)", "ar": "Arabic (العربية)", "fa": "Persian (فارسی)", "ru": "Russian (Русский)",
              "uk": "Ukrainian (Українська)", "zh": "Chinese (中文)", "ja": "Japanese (日本語)", "ko": "Korean (한국어)",
              "el": "Greek (Ελληνικά)", "he": "Hebrew (עברית)", "hi": "Hindi (हिन्दी)", "th": "Thai (ไทย)"}
# Writing systems that identify a language on their own (checked before the Latin-script heuristics).
SCRIPTS = [("ja", r"[\u3040-\u30ff]"), ("ko", r"[\uac00-\ud7af]"), ("zh", r"[\u4e00-\u9fff]"),
           ("ar", r"[\u0600-\u06ff]"), ("ru", r"[\u0400-\u04ff]"), ("el", r"[\u0370-\u03ff]"),
           ("he", r"[\u0590-\u05ff]"), ("th", r"[\u0e00-\u0e7f]"), ("hi", r"[\u0900-\u097f]")]
# Case-sensitive on purpose: with re.I, "İ" would match every "i"/"I" and English would look Turkish.
TR_CHARS = re.compile(r"[çğıöşüÇĞİÖŞÜ]")
TR_WORDS = re.compile(r"\b(merhaba|selam|nasıl|nasılsın|bana|bir|ve|ile|için|mısın|misin|musun|yap|yaz|oluştur|kur|"
                      r"neden|nedir|lütfen|teşekkür|evet|hayır|şunu|bunu|dosya|klasör|araştır|ben|sen|bu|şu|ne|var|"
                      r"yok|gibi|daha|çok|olarak|olan|sana|size|kodu|kod)\b", re.I)
EN_WORDS = re.compile(r"\b(the|and|you|your|with|this|that|there|here|is|are|was|be|to|of|in|on|for|please|what|how|"
                      r"why|who|create|write|make|build|can|could|would|should|thanks|hello|hi|i|i'm|am|it|my|me)\b", re.I)


def _lang_counts(text: str) -> tuple[int, int]:
    sample = re.sub(r"```.*?```|`[^`]*`|https?://\S+|[\w./\\-]+\.\w{1,5}\b", " ", text or "", flags=re.S)
    tr = len(TR_CHARS.findall(sample)) + 2 * len(TR_WORDS.findall(sample))
    return tr, len(EN_WORDS.findall(sample))


def reply_language(text: str, ui_lang: str | None) -> str:
    """The language of the user's latest message (fallback: the UI language)."""
    sample = re.sub(r"```.*?```|`[^`]*`", " ", text or "", flags=re.S)
    letters = max(1, len(re.findall(r"\w", sample)))
    for code, pattern in SCRIPTS:
        if len(re.findall(pattern, sample)) / letters > 0.3:
            if code == "ru" and ui_lang == "uk":
                return "uk"
            if code == "ar" and ui_lang == "fa":
                return "fa"
            return code
    tr, en = _lang_counts(text)
    if tr > en:
        return "tr"
    if en > tr:
        return "en"
    return ui_lang or "tr"


SMALL_TALK = re.compile(
    r"^\W*(merhaba|selam(lar)?|günaydın|iyi (akşamlar|geceler|günler)|nasılsın(ız)?|naber|ne haber|kimsin|"
    r"sen kimsin|kendini tanıt\w*|bana kendini tanıt\w*( mısın)?|teşekkür(ler| ederim)?|sağ ?ol|eyvallah|"
    r"hello|hi|hey|good (morning|evening|night)|how are you|who are you|what are you|introduce yourself|"
    r"thanks|thank you)\b[\w\s,.!?']{0,60}$", re.I)
ACTION = re.compile(r"\b(oluştur|yaz|kur|çalıştır|araştır|ara|sil|düzenle|create|write|build|run|search|delete|"
                    r"edit|install|make|fix|list)\b", re.I)
# Words that ask for work on the computer or the web (stems: Turkish suffixes vary).
WORK = re.compile(r"\b(oluştur|yaz|kur|çalıştır|araştır|ara|bul|sil|düzenle|yap|hazırla|ekle|kaydet|indir|güncelle|"
                  r"düzelt|test|başlat|derle|dosya|klasör|proje|uygulama|site|belge|excel|word|pdf|tablo|kod|script|"
                  r"web|internet|güncel|create|write|build|run|search|delete|edit|install|make|fix|list|generate|add|"
                  r"save|update|setup|deploy|start|file|folder|project|app|code|document|look up|find|latest|current)",
                  re.I)
QUESTION = re.compile(r"\?\s*$|\b(nasıl|neden|nedir|ne demek|hangi|kaç|mı|mi|mu|mü|how|why|what|which|when|who)\b", re.I)


def is_small_talk(text: str) -> bool:
    """Greetings / identity / thanks: answered in text without offering tools, so eager models cannot run commands."""
    t = text.strip()
    return len(t) <= 80 and bool(SMALL_TALK.match(t)) and not ACTION.search(t)


def is_knowledge_question(text: str) -> bool:
    """A plain question that asks for no work: only read-only tools are offered, so small models cannot write
    unrequested files ("How should I start learning PHP?")."""
    t = text.strip()
    return len(t) <= 400 and bool(QUESTION.search(t)) and not WORK.search(t)


# A reply that only announces the next step ("Now I'll create the routes.") means the model stopped mid-task.
ANNOUNCE = re.compile(r"(şimdi|ardından|sonra|sıradaki|devam|now|next|then|let me|i'?ll|i will|i'm going to)\b.{0,160}"
                      r"(\w+(uyorum|üyorum|ıyorum|iyorum|ayım|eyim|acağım|eceğim)\b|let me|i'?ll|i will|going to)|"
                      r"(oluştur|yaz|ekl|kur|başl|geç|düzenl|devam ed)\w*(uyorum|üyorum|ıyorum|iyorum|ayım|eyim|acağım|"
                      r"eceğim)\W*$|:\s*$|(^|[.!]\s+)(now,? |next,? )?(let me|i'?ll|i will|i'm going to)\b[^.!?]*[.!]?\s*$",
                      re.I | re.S)


def is_announcement(text: str) -> bool:
    t = text.strip()
    return 0 < len(t) <= 500 and "```" not in t and bool(ANNOUNCE.search(t))


# "I saved it to a file" although no file tool ran in this task: a hallucinated action.
FILE_CLAIM = re.compile(r"(dosya\w*|belge\w*|klasör\w*)\s+(\w+\s+){0,3}(oluştur|kaydet|yaz|hazırla)\w*(dım|dim|dum|düm|ldı|ldi)|"
                        r"(dosya|belge)\w*\s+(oluştur|kaydet|yaz|hazırla)\w*(arak|ıp|ip|up)\s+(\w+\s+){0,3}\w+(dım|dim|dum|düm|tım|tim)\b|"
                        r"(oluşturdum|kaydettim|dosyaya yazdım)|\b(i('ve| have)? (created|saved|written|wrote)|"
                        r"(has|have) been (created|saved|written))\b.{0,40}\b(file|document|folder)", re.I)


FOREIGN_SCRIPT = re.compile(r"[\u0370-\u03ff\u0400-\u04ff\u0590-\u06ff\u0900-\u097f\u0e00-\u0e7f"
                            r"\u3040-\u30ff\u4e00-\u9fff\uac00-\ud7af]")
TRANSLATE_HINT = re.compile(r"çevir|tercüme|translat|übersetz|tradu|翻译|翻訳|перевед", re.I)
LATIN_LANGS = {"tr", "en", "de", "fr", "es", "it", "pt", "nl"}


def wrong_language(text: str, lang: str, user_text: str = "") -> bool:
    """True when a reply drifted away from the reply language (code, paths and URLs ignored):
    mostly the other of TR/EN, or foreign-script words inside a Latin-script answer (e.g. a stray Chinese word)."""
    body = re.sub(r"```.*?```|`[^`]*`|https?://\S+", " ", text or "", flags=re.S)
    if lang in LATIN_LANGS and FOREIGN_SCRIPT.search(body):
        if not FOREIGN_SCRIPT.search(user_text) and not TRANSLATE_HINT.search(user_text):
            return True
    if lang not in ("tr", "en"):
        return False
    tr, en = _lang_counts(text)
    return (en >= 5 and en > 2 * tr) if lang == "tr" else (tr >= 8 and tr > 2 * en)


def language_rule(code: str) -> str:
    name = LANG_NAMES.get(code, code)
    return (f"# Reply language\nReply ONLY in {name}. Every sentence, explanation, narration and summary must be in "
            f"{name}; do not mix in words from other languages. Code, file names and identifiers stay as they are.\n"
            f"The agent, skill and instruction texts above may be written in other languages (English, Chinese, ...); "
            f"follow what they say, but they never change the reply language: always answer in {name}.")

TAG_PROTOCOL = """# Tool protocol
Call tools by writing tags; their results arrive in the next message. Tags are hidden from the user.
{tools}"""


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

    def snapshot(self) -> dict:
        return {"run_id": self.id, "session_id": self.session["id"], "text": self.text, "steps": self.steps,
                "role": self.role, "todos": self.todos}


RUNS: dict[str, Run] = {}


def _emit(run: Run, type_: str, **payload) -> None:
    if type_ == "delta":
        run.text += payload["text"]
    elif type_ == "reset_text":
        run.text = ""
    bus.publish("run", type_, {"run_id": run.id, "session_id": run.session["id"], **payload})


def _step(run: Run, kind: str, title: str, status: str = "done", detail: str = "", data: dict | None = None,
          step_id: str | None = None) -> str:
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


TOOL_TITLES = {"write_file": "file", "read_file": "read", "list_dir": "list", "run": "command", "start": "process",
               "stop": "stop", "web_search": "search", "research": "search", "fetch_url": "fetch", "browser_check": "visual",
               "make_doc": "document", "delete_file": "delete", "use_skill": "skill"}
REPEAT_GUARD = {"fetch_url", "web_search", "research", "use_skill"}
# Step kinds that are actions worth remembering in later turns (see _history).
ACTION_KINDS = {"file", "command", "process", "document", "delete", "skill", "search", "fetch", "visual"}


def _parse_mentions(text: str) -> tuple[str | None, list[str], str]:
    """'@tester' selects an agent role, '/webapp' loads a skill. Unknown names are left in the text."""
    agents, skills = catalog.agents(), catalog.skills()
    role = next((m for m in re.findall(r"(?<!\S)@([\w-]+)", text) if m in agents), None)
    used = list(dict.fromkeys(m for m in re.findall(r"(?<!\S)/([\w-]+)", text) if m in skills))
    names = [*([role] if role else []), *used]
    clean = re.sub(r"(?<!\S)[@/](%s)(?![\w-])" % "|".join(map(re.escape, names)), "", text) if names else text
    return role, used, clean.strip() or text


def _history(session_id: str, before_id: int | None = None) -> list[dict]:
    """Messages after the last compression point, preceded by the stored summary."""
    sess = db.query("SELECT summary, summary_upto FROM sessions WHERE id=?", (session_id,))
    summary, upto = (sess[0]["summary"], sess[0]["summary_upto"] or 0) if sess else (None, 0)
    rows = db.query("SELECT id, role, content, meta FROM messages WHERE session_id=? AND id>? AND id<? "
                    "AND role IN ('user','assistant') ORDER BY id DESC LIMIT ?",
                    (session_id, upto, before_id or 1 << 62, HISTORY_MESSAGES))
    msgs = []
    for r in reversed(rows):
        content = r["content"] or ""
        if r["role"] == "assistant":
            content += _action_log(r["meta"])
        if content.strip():
            msgs.append({"role": r["role"], "content": content})
    if summary:
        msgs = [{"role": "user", "content": f"{SUMMARY_TAG}\n{summary}"},
                {"role": "assistant", "content": "OK."}] + msgs
    return msgs


def _action_log(meta: str | None) -> str:
    """Compact record of what an earlier turn did with tools, so 'continue' resumes exactly where it stopped
    (the visible answer alone may be empty when a run was interrupted)."""
    try:
        m = json.loads(meta or "{}")
    except json.JSONDecodeError:
        return ""
    acts = [f"{s['kind']} {s['title']}{' (failed)' if s.get('status') == 'error' else ''}"
            for s in m.get("steps") or [] if s.get("kind") in ACTION_KINDS]
    if not acts:
        return ""
    status = m.get("status") or "ok"
    unfinished = "" if status == "ok" else f"; run ended early: {status}, the task may be unfinished"
    return f"\n\n[Tool actions in this turn: {'; '.join(acts[-40:])}{unfinished}]"


def estimate_tokens(messages: list[dict]) -> int:
    """~3 characters per token, counting tool-call arguments (whole files) too."""
    chars = sum(len(m.get("content") or "") + (len(json.dumps(m["tool_calls"], ensure_ascii=False))
                                               if m.get("tool_calls") else 0) for m in messages)
    return chars // 3 + 4 * len(messages) + 1000 * sum(len(m.get("images") or []) for m in messages)


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
the conversation's language. Do not invent anything."""


async def compress(session_id: str, model: str, cancel: asyncio.Event | None = None,
                   keep_recent: int | None = None) -> dict:
    keep = load_settings()["context"].get("keep_recent", 6) if keep_recent is None else keep_recent
    sess = db.query("SELECT summary, summary_upto FROM sessions WHERE id=?", (session_id,))[0]
    rows = db.query("SELECT id, role, content FROM messages WHERE session_id=? AND id>? "
                    "AND role IN ('user','assistant') ORDER BY id", (session_id, sess["summary_upto"] or 0))
    old = rows[:-keep] if keep else rows
    if not old:
        return {"compressed": 0}
    before = estimate_tokens(_history(session_id))
    transcript = (f"Previous summary:\n{sess['summary']}\n\n" if sess["summary"] else "") + "\n\n".join(
        f"{r['role'].upper()}: {r['content'][:6000]}" for r in old)
    info = await router.context_info(model)
    opts = {"num_ctx": info["current"]} if info["local"] else {}
    summary = (await router.complete(model, [{"role": "system", "content": COMPRESS_PROMPT},
                                             {"role": "user", "content": transcript}], opts, cancel)).strip()
    if not summary:
        raise ProviderError("empty", "The model returned an empty summary")
    db.execute("UPDATE sessions SET summary=?, summary_upto=? WHERE id=?", (summary, old[-1]["id"], session_id))
    after = estimate_tokens(_history(session_id))
    res = {"compressed": len(old), "before": before, "after": after}
    sessions.append_summary(session_id, summary, res)
    db.execute("UPDATE sessions SET context_used=? WHERE id=?", (after, session_id))
    return res


def _system_prompt(role: str, root, session_id: str, project: dict | None, skill_names: list[str],
                   plan: str | None, native: bool, model: str = "", lang: str = "tr",
                   tools: set[str] | None = None) -> tuple[str, dict]:
    """tools: names offered this turn (None = all, empty = none)."""
    agents = catalog.agents()
    sizes: dict[str, int] = {}
    parts = [SYSTEM_CORE.format(root=root, date=time.strftime("%Y-%m-%d"), model=model, os_name=OS_NAME, shells=SHELLS,
                                project=f"\nProject: {project['name']}" if project else "")]
    role_prompt = agents.get(role, agents.get(DEFAULT_ROLE, {})).get("prompt")
    if role_prompt:
        parts.append("# Instructions\n" + role_prompt)
    sizes["system"] = sum(map(len, parts))
    if tools is not None and not tools:
        sizes["tools"] = 0
    elif not native:
        parts.append(TAG_PROTOCOL.format(tools=tools_prompt(tools)))
        sizes["tools"] = len(parts[-1])
    else:
        sizes["tools"] = len(json.dumps(tool_schemas(tools), ensure_ascii=False))
    # Skill discovery: the model sees every skill's purpose and loads a matching one with use_skill.
    available = {k: v for k, v in catalog.skills().items() if k not in skill_names}
    if available and (tools is None or "use_skill" in tools):
        parts.append("# Available skills\nWhen the request matches one of these, call use_skill with its name first "
                     "and follow the loaded instructions:\n" + "\n".join(
                         f"- {k}: {v.get('description_en') or v.get('description') or v['title']}"
                         for k, v in available.items()))
        sizes["skills"] = len(parts[-1])
    if project:
        parts.append("# Project files\n" + workspace.summarize_tree(root, 60))
        sizes["project"] = len(parts[-1])
    state = sessions.state_file(session_id)
    if state.exists():
        parts.append("# Session state\n" + state.read_text(encoding="utf-8", errors="replace")[:2000])
        sizes["state"] = len(parts[-1])
    skills = catalog.skills()
    skill_parts = [f"# Active skill /{s}: {skills[s]['title']} (the user invoked it for the latest request; "
                   f"apply these instructions to that request)\n{skills[s]['prompt']}" for s in skill_names if s in skills]
    parts += skill_parts
    sizes["skills"] = sizes.get("skills", 0) + sum(map(len, skill_parts))
    if plan:
        parts.append("# Plan to follow\n" + plan)
        sizes["plan"] = len(parts[-1])
    parts.append(language_rule(lang))  # last, so it carries the most weight
    sizes["system"] += len(parts[-1])
    return "\n\n".join(parts), sizes


def context_breakdown(sizes: dict, messages: list[dict], actual_input: int | None) -> dict:
    """Token estimate per category of what is sent to the model; scaled to the provider-reported input when known."""
    chars = dict(sizes)
    for m in messages:
        content = m.get("content") or ""
        if m["role"] == "tool" or m.get("tool_calls") or content.startswith("Tool results:"):
            key = "tool_io"
            content += json.dumps(m.get("tool_calls") or "", ensure_ascii=False)
        elif content.startswith(SUMMARY_TAG):
            key = "summary"
        elif "[Attached file:" in content:
            head, _, att = content.partition("[Attached file:")
            chars["messages"] = chars.get("messages", 0) + len(head)
            key, content = "attachments", att
        else:
            key = "messages"
        chars[key] = chars.get(key, 0) + len(content) + 16
        if m.get("images"):
            chars["attachments"] = chars.get("attachments", 0) + 3000 * len(m["images"])
    tokens = {k: v / 3 for k, v in chars.items() if v}
    est = sum(tokens.values()) or 1
    scale = actual_input / est if actual_input else 1
    return {k: int(v * scale) for k, v in sorted(tokens.items(), key=lambda kv: -kv[1])}


PREP_NAME = re.compile(r'<function=([\w.-]+)|<tool\s+name="([\w.-]+)"|"name"\s*:\s*"([\w.-]+)"')


async def _stream_turn(run: Run, model: str, messages: list[dict], visible: list[str],
                       opts: dict) -> tuple[str, list[str], list[dict]]:
    """Stream one model turn. Returns (raw_text, tag_tool_blocks, native_tool_calls)."""
    splitter, raw, tags, calls = StreamSplitter(), [], [], []
    think_id = None
    thinking: list[str] = []
    prep_id, prep_at = None, 0.0

    got_output = False  # anything received yet (else silence = prompt processing / model loading)
    thinking_live = False

    def prepare(name: str | None, chars: int = 0, seconds: int = 0, force: bool = False) -> None:
        """Live 'preparing <tool>' step while the model is still writing a tool call (throttled)."""
        nonlocal prep_id, prep_at
        now = time.monotonic()
        if prep_id and not force and now - prep_at < 0.35:
            return
        prep_at = now
        prep_id = _step(run, "prepare", name or "tool", "running",
                        data={"tool": name, "chars": chars, "seconds": seconds}, step_id=prep_id)

    def end_thinking() -> None:
        nonlocal thinking_live
        if think_id and thinking_live:
            thinking_live = False
            _step(run, "thinking", "thinking", "done", "".join(thinking)[-6000:], step_id=think_id)

    def handle(kind: str, text: str) -> None:
        nonlocal think_id, thinking_live
        if kind == "visible":
            end_thinking()
            visible.append(text)
            _emit(run, "delta", text=text)
        elif kind == "thinking":
            thinking.append(text)
            thinking_live = True
            think_id = _step(run, "thinking", "thinking", "running", "".join(thinking)[-6000:], step_id=think_id)
        elif kind in ("tool", "tool_incomplete"):
            tags.append(text)

    try:
        async for evt in router.stream_chat(model, messages, opts, cancel=run.cancel,
                                            on_fallback=lambda m: _step(run, "fallback", m, detail="cloud fallback")):
            t = evt["type"]
            if t == "idle":
                # Silence: either the prompt is still being processed, or the model is writing a tool call
                # (local servers stream nothing for those). Show it live instead of a frozen "thinking".
                if evt["seconds"] >= 4:
                    end_thinking()
                    prepare("tool" if got_output else "model", seconds=evt["seconds"], force=True)
                continue
            got_output = got_output or t in ("thinking", "text", "tool_call", "tool_call_start")
            if t == "thinking":
                handle("thinking", evt["text"])
            elif t == "tool_call":
                calls.append(evt)
            elif t in ("tool_call_start", "tool_call_progress"):
                end_thinking()
                prepare(evt.get("name"), evt.get("chars", 0))
            elif t == "usage" and (evt.get("input") or evt.get("output")):
                if evt.get("input"):
                    run.session["usage_input"] = evt["input"]
                used = (run.session.get("usage_input") or 0) + (evt.get("output") or 0)
                run.session["context_used"] = used
                _emit(run, "context", used=used)
            elif t == "text":
                raw.append(evt["text"])
                for kind, text in splitter.feed(evt["text"]):
                    handle(kind, text)
                if splitter.open and splitter.open[0] != "<think>":
                    m = PREP_NAME.search(splitter.buf)
                    prepare(next((g for g in m.groups() if g), None) if m else None, len(splitter.buf))
        for kind, text in splitter.flush():
            handle(kind, text)
    finally:  # never leave a spinning step behind, also when the turn fails or is cancelled
        if prep_id:  # the real tool steps replace the placeholder
            run.steps = [s for s in run.steps if s["id"] != prep_id]
            _emit(run, "step_remove", step_id=prep_id)
        end_thinking()
    return "".join(raw), tags, calls


BUDGET_NOTE = {"tr": "Adım sınırına ulaşıldı ({n} adım) ve görev henüz bitmedi. Kaldığı yerden sürdürmek için "
                     "\"devam et\" yazın; sınırı Ayarlar > Ajan bölümünden artırabilirsiniz.",
               "en": "The step limit was reached ({n} steps) before the task finished. Type \"continue\" to resume "
                     "where it stopped; the limit can be raised in Settings > Agent."}
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
    lines = []
    for m in old:
        calls = "; ".join(f"{c['name']}({', '.join(f'{k}={str(v)[:80]}' for k, v in c['arguments'].items())})"
                          for c in m.get("tool_calls") or [])
        lines.append(f"{m['role'].upper()}: {(m.get('content') or '')[:1500]}" + (f"\nCALLS: {calls}" if calls else ""))
    try:
        summary = (await router.complete(model, [
            {"role": "system", "content": COMPRESS_PROMPT},
            {"role": "user", "content": "\n\n".join(lines)}], opts, run.cancel)).strip()
    except ProviderError:
        summary = ""
    if not summary:  # fall back to a mechanical log of the steps
        summary = "\n".join(l[:300] for l in lines)
    # Keep provider message rules valid: the kept tail must not start with an orphan tool result.
    tail = messages[len(messages) - keep:]
    while tail and tail[0]["role"] == "tool":
        tail = tail[1:]
    messages[first:] = [{"role": "user", "content": f"{PROGRESS_TAG}\n{summary}\n\nContinue the task."}] + (
        [{"role": "assistant", "content": "OK."}] if tail and tail[0]["role"] == "user" else []) + tail
    after = estimate_tokens([system] + messages)
    _step(run, "compress", "context", "done", json.dumps({"before": est, "after": after, "mode": "summary"}), step_id=sid)
    return after


async def _exec(run: Run, ctx: ToolContext, name: str, args: dict, body: str,
                allowed: set[str] | None = None) -> ToolResult:
    if name not in TOOLS:
        return ToolResult(False, f"Unknown tool '{name}'. Available: {', '.join(TOOLS)}")
    if allowed is not None and name not in allowed:
        return ToolResult(False, f"Tool '{name}' is not available for this request (the user asked a question; "
                                 "answer in chat, and only change files when asked).")
    if "_raw" in args:
        return ToolResult(False, "Invalid JSON arguments for this tool call. Send a valid JSON object.")
    # The same read-only call twice in one task (a model looping over the same page) is answered from memory.
    key = f"{name}:{json.dumps(args, sort_keys=True, ensure_ascii=False)}:{body.strip()}"
    if name in REPEAT_GUARD and key in run.seen:
        return ToolResult(True, "You already ran this exact call in this task; its result is above. Do not repeat it: "
                                "use what you have, try a different source, or give the answer now.")
    if name in REPEAT_GUARD:
        run.seen.add(key)
    if name == "todo":  # shown as the live task list, not as a trace step
        res = await TOOLS[name].fn(ctx, args, body)
        if res.ok:
            run.todos = res.data["todos"]
            _emit(run, "todos", todos=run.todos)
        return res
    first_line = body.strip().splitlines()[0][:120] if body.strip() else ""
    label = args.get("path") or args.get("url") or args.get("id") or first_line or name
    kind = TOOL_TITLES.get(name, name)
    sid = _step(run, kind, label, "running", data={"tool": name, "args": args})
    try:
        res = await TOOLS[name].fn(ctx, args, body)
    except PermissionError as e:
        res = ToolResult(False, f"DENIED: {e}")
    except KeyError as e:
        res = ToolResult(False, f"Missing required argument: {e}")
    except Exception as e:  # tool bugs are reported back to the model
        res = ToolResult(False, f"{type(e).__name__}: {e}")
    detail = body if name == "write_file" else res.output
    _step(run, kind, label, "done" if res.ok else "error", detail,
          data={"tool": name, "args": args, **res.data, "output": res.output[:4000]}, step_id=sid)
    return res


async def execute(run: Run, user_text: str, opts: dict) -> None:
    settings = load_settings()
    limits = settings["agent"]
    session = run.session
    project = workspace.get_project(session.get("project_id"))
    root = workspace.session_root(session)
    sdir = sessions.path(session["id"])
    model = opts.get("model") or settings["active_model"]
    mode = opts.get("permission_mode") or settings["permission_mode"]
    forced_role, skill_names, clean_text = _parse_mentions(user_text)
    ctx = ToolContext(run.id, root, mode, run.cancel, session_dir=sdir, owner=f"{session['id']}:{run.id}",
                      step=lambda kind, data: _step(run, kind, kind, "done", json.dumps(data, ensure_ascii=False)))
    visible: list[str] = []
    status = "ok"
    _emit(run, "started", model=model, mode=mode)
    try:
        ctx_info = await router.context_info(model)
        base_opts = {"num_ctx": ctx_info["current"]} if ctx_info["local"] else {}
        history = _history(session["id"], run.user_msg_id)
        limit = ctx_info["current"] * ctx_info["threshold"] / 100
        if 0 < ctx_info["threshold"] < 100 and estimate_tokens(history) + 2500 > limit:
            sid = _step(run, "compress", "context", "running")
            res = await compress(session["id"], model, run.cancel)
            _step(run, "compress", "context", "done", json.dumps(res), step_id=sid)
            history = _history(session["id"], run.user_msg_id)

        plan = None
        if forced_role == "planner" or opts.get("plan_mode"):
            sid = _step(run, "plan", "planner", "running")
            plan = (await router.complete(model, [
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
              and not sessions.state_file(session["id"]).exists()):
            allowed = set(READ_ONLY)
        lang = reply_language(clean_text, opts.get("ui_lang"))
        # A short reminder on the latest turn keeps small local models from drifting into English (not stored).
        reminder = {"tr": "(Türkçe yanıt ver.)", "en": "(Reply in English.)"}.get(lang, f"(Reply in {LANG_NAMES.get(lang, lang)}.)")
        skill_note = "".join(f"\n[Skill /{s} invoked: do this request with that skill's instructions.]"
                             for s in skill_names)
        if opts.get("goal_mode"):
            skill_note += ("\n[Goal mode: this is a goal to reach autonomously. Keep a to-do list, work through every "
                           "item, verify the result yourself and finish only when the goal is fully achieved.]")
        user_msg = {"role": "user", "content": f"{clean_text}{skill_note}\n\n{reminder}"}
        if opts.get("images"):
            user_msg["images"] = opts["images"]
        messages = history + [user_msg]
        first_run_msg = len(messages)  # messages after this index belong to the current task
        num_ctx = ctx_info["current"]
        # Leave room for the reply (a whole file) inside the window the threshold allows.
        budget = num_ctx * (ctx_info["threshold"] if 0 < ctx_info["threshold"] < 100 else 90) / 100 \
            - min(8192, num_ctx // 5)
        debug_attempts, last_failure, leak_retries, lang_retry, nudges, used_tools = 0, None, 0, False, 0, False
        claim_retry = False
        for iteration in range(limits["max_iterations"]):
            if run.cancel.is_set():
                raise asyncio.CancelledError
            run.role = role
            _emit(run, "agent", role=role, iteration=iteration)
            visible.clear()
            sys_text, sys_sizes = _system_prompt(role, root, session["id"], project, skill_names, plan,
                                                 native, model.partition(":")[2], lang, allowed)
            system = {"role": "system", "content": sys_text}
            # Live context accounting before every model turn; relieve it inside long tasks.
            est = estimate_tokens([system] + messages)
            if est > budget and shrink_messages(messages, keep_last=4):
                est2 = estimate_tokens([system] + messages)
                _step(run, "compress", "context", "done", json.dumps({"before": est, "after": est2, "mode": "trim"}))
                est = est2
            if est > budget and len(messages) - first_run_msg > 6:
                est = await _summarize_progress(run, model, messages, first_run_msg, base_opts, system, est)
            run.session["context_used"] = est
            _emit(run, "context", used=est)
            offered = None if allowed is None else allowed
            turn_opts = {**base_opts, "tools": tool_schemas(offered)} if native and offered != set() else base_opts
            try:
                run.session["usage_input"] = None
                raw, tag_blocks, calls = await _stream_turn(run, model, [system] + messages, visible, turn_opts)
                run.stats = context_breakdown(sys_sizes, messages + ([{"role": "assistant", "content": raw}] if raw else []),
                                              run.session.get("usage_input"))
            except ProviderError as e:
                if native and e.code in ("no_tools", "bad_request") and not "".join(visible):
                    # The model/server rejected function calling: remember it and use the tag protocol.
                    router.disable_native_tools(model)
                    native = False
                    _step(run, "note", "tools", "done", f"Native tool calling not supported; switched to the text protocol: {e}")
                    continue
                raise
            if chat_only:  # small talk: never execute tools, even if the model writes them
                tag_blocks, calls = [], []
            parsed = [parse_tool(b) for b in tag_blocks]
            if not tag_blocks and not calls:
                # Last chance for formats only detectable on the full text (Mistral, fenced JSON)...
                inline, cleaned = extract_inline_calls("".join(visible), set(TOOLS))
                text_now = "".join(visible).strip()
                open_todos = [t for t in run.todos if t["status"] != "completed"]
                if inline:
                    parsed, visible[:] = inline, [cleaned]
                elif not lang_retry and wrong_language(text_now, lang, clean_text):
                    # The answer drifted into another language: rewrite it once, entirely in the user's language.
                    lang_retry = True
                    _emit(run, "reset_text")
                    messages += [{"role": "assistant", "content": raw},
                                 {"role": "user", "content": "Rewrite your previous answer entirely in "
                                  f"{LANG_NAMES.get(lang, lang)}. Same content, no other language, no tool calls."}]
                    continue
                elif LEAK.search(text_now) and leak_retries < 2:
                    # ...and never show unparsed tool syntax: ask the model to redo the call properly.
                    leak_retries += 1
                    _emit(run, "reset_text")
                    _step(run, "note", "tools", "done", "Unparsed tool syntax was hidden; the model was asked to retry the call.")
                    messages += [{"role": "assistant", "content": raw},
                                 {"role": "user", "content": "Your last reply contained raw tool-call syntax that was NOT "
                                  "executed. Call the tool correctly using the available tools, or answer in plain text "
                                  "without any tool syntax. Do not claim actions that did not run."}]
                    continue
                elif (not claim_retry and used_tools and not ctx.files_changed and FILE_CLAIM.search(text_now)
                      and not sessions.state_file(session["id"]).exists()):  # no files from earlier turns either
                    # The answer claims a file that was never written: correct it once (no invented actions).
                    claim_retry = True
                    _emit(run, "reset_text")
                    messages += [{"role": "assistant", "content": raw},
                                 {"role": "user", "content": "No file was created or saved in this task (no file tool "
                                  "ran). If the user asked for a file, create it now with the tools; otherwise rewrite "
                                  "your answer without claiming a file."}]
                    continue
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
                else:
                    break
            used_tools = True
            _emit(run, "reset_text")  # interim narration is kept in the trace, not in the final answer
            narration = "".join(visible).strip()
            if narration:
                _step(run, "note", role, "done", narration)
            failure = None
            if calls:
                messages.append({"role": "assistant", "content": narration,
                                 "tool_calls": [{"id": c["id"], "name": c["name"], "arguments": c["arguments"]} for c in calls]})
                for c in calls:
                    args, body = split_args(c["name"], c["arguments"]) if c["name"] in TOOLS else (c["arguments"], "")
                    res = await _exec(run, ctx, c["name"], args, body, allowed)
                    messages.append({"role": "tool", "tool_call_id": c["id"], "name": c["name"], "content": res.output})
                    if not res.ok and c["name"] == "run":
                        failure = res.output
            else:
                results = []
                for call in parsed:
                    if call and call.arguments is not None and call.name in TOOLS:
                        call.args, call.body = split_args(call.name, call.arguments)
                    res = await _exec(run, ctx, call.name, call.args, call.body, allowed) if call \
                        else ToolResult(False, "Malformed tool call.")
                    name = call.name if call else "?"
                    results.append(f'<result tool="{name}" ok="{str(res.ok).lower()}">\n{res.output}\n</result>')
                    if not res.ok and name == "run":
                        failure = res.output
                messages += [{"role": "assistant", "content": raw},
                             {"role": "user", "content": "Tool results:\n" + "\n".join(results)}]
            if failure:
                debug_attempts += 1
                signature = re.sub(r"\d+", "#", failure[-400:])
                if debug_attempts > limits["max_debug_attempts"] or signature == last_failure:
                    messages.append({"role": "user", "content": "The same failure repeats without progress. Stop calling "
                                     "tools; explain the diagnosis and what the user should do."})
                last_failure, role = signature, "debugger"
                _step(run, "debug", f"#{debug_attempts}", "done", failure[-2000:])
            elif role == "debugger":
                role = forced_role or DEFAULT_ROLE
        else:
            status = "budget"
            _step(run, "budget", "iteration budget exhausted", "error")
            if not "".join(visible).strip():
                note = BUDGET_NOTE.get(lang, BUDGET_NOTE["en"]).format(n=limits["max_iterations"])
                visible[:] = [note]
                _emit(run, "delta", text=note)
    except asyncio.CancelledError:
        status = "cancelled"
    except ProviderError as e:
        status = "error"
        _emit(run, "error", code=e.code, message=str(e))
    except Exception as e:
        status = "error"
        _emit(run, "error", code="internal", message=f"{type(e).__name__}: {e}")
    finally:
        approvals.cancel_all_for(run.id)
        # A finished run never keeps spinning steps (closed chat, error, cancel...).
        for s in run.steps:
            if s["status"] == "running":
                s["status"] = "done" if status == "ok" else "error"
                _emit(run, "step", step=s)
        answer = "".join(visible).strip()
        db.add_message(session["id"], "assistant", answer,
                       {"steps": run.steps, "status": status, "model": model, "todos": run.todos})
        try:
            if ctx.files_changed or ctx.commands:
                name = project["name"] if project else (session.get("title") or "Sohbet")
                workspace.write_state(sessions.state_file(session["id"]), root, name, clean_text[:200],
                                      ctx.files_changed, ctx.commands, status)
                if project:
                    sha = await workspace.git_snapshot(root, f"aiiq: {clean_text[:80]}")
                    if sha:
                        _step(run, "git", sha, "done", f"snapshot {sha}")
            title = db.query("SELECT title FROM sessions WHERE id=?", (session["id"],))
            sessions.write_meta({**session, "title": title[0]["title"] if title else ""}, model=model,
                                last_status=status, context_stats=run.stats)
        except OSError:
            pass
        # What the next turn will carry: the stored history (the task's tool traffic is not resent).
        used = estimate_tokens(_history(session["id"])) + sum(
            v for k, v in (run.stats or {}).items() if k in ("system", "tools", "skills", "project", "state"))
        db.execute("UPDATE sessions SET context_used=?, context_stats=? WHERE id=?",
                   (used, json.dumps(run.stats) if run.stats else None, session["id"]))
        _emit(run, "done", status=status, text=answer, steps=run.steps, context_used=used, todos=run.todos)
        RUNS.pop(run.id, None)


def start_run(session: dict, text: str, opts: dict) -> Run:
    run = Run(uuid.uuid4().hex[:12], session)
    RUNS[run.id] = run
    run.user_msg_id = db.add_message(session["id"], "user", opts.get("display_text") or text,
                                     {"attachments": opts.get("attachments", [])})
    run.task = asyncio.create_task(execute(run, text, opts))
    return run


def active_run(session_id: str) -> dict | None:
    return next((r.snapshot() for r in RUNS.values() if r.session["id"] == session_id), None)


async def cancel_run(run_id: str) -> bool:
    run = RUNS.get(run_id)
    if not run:
        return False
    run.cancel.set()
    approvals.cancel_all_for(run_id)
    if run.task:
        run.task.cancel()
    return True


async def cancel_session(session_id: str) -> None:
    for r in [r for r in RUNS.values() if r.session["id"] == session_id]:
        await cancel_run(r.id)
