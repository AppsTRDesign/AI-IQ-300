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
from collections import deque
from dataclasses import dataclass, field

from .. import approvals, db, sessions, tokens, workspace
from ..config import load_settings
from ..events import bus
from ..llm import router
from ..llm.providers import ProviderError
from ..tools.symbols import project_map
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
- To change an existing file use edit_file with a short exact snippet (SEARCH/REPLACE); rewrite a whole file with
  write_file only when most of it changes. Find code with search_code, then read_file with lines="a-b" for that part
  instead of reading whole files.
- A folder the user names ("in the onur folder", "web-app klasöründe") is a sub-folder of the working directory:
  use relative paths like onur/index.html. Never invent absolute paths (Desktop, user home, drive letters); but when
  the user gives an exact absolute path, use exactly that path (writing outside the working directory asks the user)
  and never report a different location than the one really written. write_file creates missing folders itself, so
  no mkdir is needed.
- Commands: use the shells and tool versions listed under "This computer". Programs with plain arguments: run with
  argv=["git", "status"] (no shell, fastest). Multi-line scripts: the whole source with shell=python/node/powershell/
  bash (it runs as a script file). File contents: write_file, never echo/heredoc. Heredocs (<<EOF) are bash only.
- Every command runs in a new process with no terminal input: set the folder with the cwd argument (a lone
  "cd DIR" sets it for the following commands), and use non-interactive flags (npx --yes, create-* --yes,
  npm init -y). Scaffold new projects into a new sub-folder (npx create-next-app@latest shop --yes), never into
  ".". Never delete files you did not create to make room for something; pick another folder instead.
- When the user states a lasting rule or preference ("always ...", "bundan sonra ...", "remember ...", "bunu
  hatırla"), save it with the remember tool (one short rule per call), then continue with the request.
- Python runs in the app's environment, which already has Pillow (images, logos), python-docx, openpyxl,
  reportlab and python-pptx. If a module is still missing, install it with pip and run the script again.
- Images and web pages you create are shown to the user automatically (image viewer, in-app browser): just
  mention the file path, never paste image data or ask the user to open files themselves.
- web_screenshot shows a page to the user as an image in the chat. Take one on your own when it helps: after you
  build or change a web page (to check how it looks, also device="mobile" for layout), when the user asks how a site
  looks or wants to compare designs, or when a page's look matters more than its text. Do not take screenshots for
  plain facts (use research/fetch_url) or for every step; one per page/state is enough.
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


FILE_NAME = re.compile(r"(?<![\w/\\.-])([\w./\\-]+\.(?:txt|md|csv|json|ya?ml|xml|html?|css|js|jsx|ts|tsx|py|php|java|go|rs|"
                       r"c|cpp|h|cs|rb|sh|ps1|bat|ini|cfg|toml|log|sql))\b", re.I)


def _unread_files(text: str, root: Path, messages: list[dict]) -> list[str]:
    """Existing files the user names in this request whose content is not in the conversation yet."""
    seen = "\n".join(m.get("content") or "" for m in messages if isinstance(m.get("content"), str))
    out = []
    for name in dict.fromkeys(FILE_NAME.findall(text)):
        try:
            f = (root / name).resolve()
            if f.is_file() and root.resolve() in f.parents and f"[Attached file: {name}" not in seen:
                out.append(name)
        except OSError:
            continue
    return out[:3]


# Questions whose answer changes over time or that ask for sources: answering them from memory invents facts.
CURRENT_INFO = re.compile(r"güncel|bugün|şu an(ki)?|son (durum|haber|fiyat)|fiyat|kaç (tl|lira|dolar|euro)|döviz|"
                          r"hava durumu|haber|kaynak|\b(link|202[5-9])\b|\b(current|latest|today|price|prices|cost|"
                          r"news|weather|source|sources|cite)\b", re.I)


def needs_research(text: str) -> bool:
    return bool(CURRENT_INFO.search(text or ""))


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
                        r"(dosyaya yazdım|diske kaydettim)|\b(i('ve| have)? (created|saved|written|wrote)|"
                        r"(has|have) been (created|saved|written))\b.{0,40}\b(file|document|folder)", re.I)


# The note _history adds to earlier answers; a model that copies it into its reply is pretending to have acted.
ACTION_ECHO = re.compile(r"\s*\[Tool actions in this turn[^:\]]*:[^\]]*\]\s*")
# "I updated / ran it" in a turn where no tool ran, although the user asked for a change: a hallucinated action.
CHANGE_REQUEST = re.compile(r"düzenle|güncelle|değiştir|düzelt|ekle|kaldır|çalıştır|oluştur|yaz\b|\b(edit|update|change|fix|"
                            r"modify|add|remove|run|create|write)\b", re.I)
CHANGE_CLAIM = re.compile(r"\b\w*(güncelle|düzenle|değiştir|düzelt|ekle|kaydet|oluştur|çalıştır)\w*(dim|dım|dum|düm|tim|tım|tum|tüm)\b|"
                          r"\b\w*(güncellen|düzenlen|değiştiril|düzeltil|eklen|kaydedil|oluşturul|çalıştırıl|yazıl)\w*(di|dı|du|dü)\b|"
                          r"\bi('ve| have)? (updated|edited|modified|changed|fixed|ran|executed|created|saved)\b|"
                          r"\b(has|have) been (updated|edited|modified|changed|fixed|created|saved)\b|"
                          r"\b(is|was|were) (now )?(updated|edited|modified|changed|fixed|created|saved)\b", re.I)


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


_LANG_FILES: dict[str, tuple[float, dict]] = {}


def ui_text(code: str, key: str, fallback: str = "", **values) -> str:
    """Text the app itself writes into the chat (notes, reminders, team summaries), in the active language: from
    languages/<code>.json (keys ai_*), so every installed language, also one translated later, has its own; else
    the English file, else the fallback."""
    from ..config import LANG_DIR
    for c in (code, "en"):
        f = LANG_DIR / f"{c}.json"
        try:
            mtime = f.stat().st_mtime
            hit = _LANG_FILES.get(c)
            if not hit or hit[0] != mtime:
                _LANG_FILES[c] = hit = (mtime, json.loads(f.read_text(encoding="utf-8")))
            if text := hit[1].get(key):
                return text.format(**values) if values else text
        except (OSError, ValueError, KeyError, IndexError):
            continue
    return fallback.format(**values) if values else fallback


def think_reply_reminder(code: str) -> str:
    """The short note on the latest turn: think and reply in the active language, written in that language."""
    own = ui_text(code, "ai_think_reply") if code != "en" else ""
    if own and (code == "tr" or own != ui_text("en", "ai_think_reply")):
        return own
    return f"(Think and reply in {LANG_NAMES.get(code, code)}.)"


def language_rule(code: str) -> str:
    name = LANG_NAMES.get(code, code)
    return (f"# Reply language\nReply ONLY in {name}. Every sentence, explanation, narration and summary must be in "
            f"{name}; do not mix in words from other languages. Code, file names and identifiers stay as they are.\n"
            f"The user sees your thinking too: think and reason in {name}, and write plans, to-do items and the short "
            f"notes before tool calls in {name} as well{'' if code == 'en' else ', not in English'}.\n"
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
    repeats: int = 0  # repeated read-only calls answered from memory; at 3 the web tools close for the task
    # A rewrite was requested: the shown answer stays on screen until the new text starts (no blank flicker).
    hold: bool = False
    noted: bool = False  # this turn's narration already moved into the trace (tool call started)
    thinking_blocks: list | None = None  # Anthropic: this turn's signed thinking blocks, returned with its tool calls
    prompt_est: int = 0  # unscaled estimate of the prompt of the running model turn
    summarized_at: int = 0  # message count right after the last in-task summary (summaries need new steps first)
    done_calls: list = field(default_factory=list)  # tool calls folded into in-task summaries so far
    failures: dict = field(default_factory=dict)  # "tool:error" -> count (loop guard, see _exec)
    blocked: set = field(default_factory=set)  # tools switched off for this task after 3 identical failures
    t0: float = field(default_factory=time.monotonic)
    folder_snap: asyncio.Task | None = None  # the working folder as it was when the task started (see changes.py)
    # Where the time went: model turns (wait for the first token, total), tool calls, side calls (summaries, fixes).
    perf: dict = field(default_factory=lambda: {"turns": [], "tools": [], "side_ms": 0.0, "first_ms": None, "prep_ms": None})

    def snapshot(self) -> dict:
        return {"run_id": self.id, "session_id": self.session["id"], "text": self.text, "steps": self.steps,
                "role": self.role, "todos": self.todos}


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
_BACKGROUND: set[asyncio.Task] = set()


def _emit(run: Run, type_: str, **payload) -> None:
    if type_ == "delta":
        run.text += payload["text"]
    elif type_ == "reset_text":
        run.text = ""
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


TOOL_TITLES = {"write_file": "file", "read_file": "read", "read_document": "read", "my_location": "places", "list_dir": "list", "run": "command", "start": "process",
               "stop": "stop", "web_search": "search", "research": "search", "fetch_url": "fetch", "browser_check": "visual",
               "make_doc": "document", "delete_file": "delete", "use_skill": "skill", "edit_file": "edit",
               "search_code": "grep", "symbols": "grep", "ask_model": "delegate", "remember": "memory",
               "impact": "grep", "mcp": "mcp", "team": "team", "web_screenshot": "screenshot", "save_catalog": "catalog",
               "places": "places"}
REPEAT_GUARD = {"fetch_url", "web_search", "research", "use_skill"}
# Step kinds that are actions worth remembering in later turns (see _history).
ACTION_KINDS = {"file", "edit", "delegate", "memory", "mcp", "team", "command", "process", "document", "delete", "skill", "search", "fetch", "visual", "screenshot", "catalog"}


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


def _action(s: dict) -> str:
    failed = " (failed)" if s.get("status") == "error" else ""
    data = s.get("data") or {}
    if s.get("kind") == "delegate":  # another model of the pool answered a sub-task
        return f"ask_model: another model ({s.get('title') or 'none'}) answered a sub-task{failed}"
    if s.get("kind") == "team" and data.get("members"):  # real team: every member's agent and model
        return "team of agents: " + ", ".join(
            f"{c.get('title')} (stage {c.get('stage', 1)}, model {c.get('model') or 'none'}, {c.get('state')})"
            for c in data["members"]) + failed
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
the conversation's language. Do not invent anything."""


async def compress(session_id: str, model: str, cancel: asyncio.Event | None = None,
                   keep_recent: int | None = None, before_id: int | None = None, target: float | None = None) -> dict:
    """Summarize older messages. The `keep_recent` latest stay verbatim, fewer when they alone are larger than
    `target` tokens (a few very long messages must still shrink). Messages from `before_id` on (the request being
    answered) are never summarized."""
    keep = load_settings()["context"].get("keep_recent", 6) if keep_recent is None else keep_recent
    sess = db.query("SELECT summary, summary_upto FROM sessions WHERE id=?", (session_id,))[0]
    rows = db.query("SELECT id, role, content FROM messages WHERE session_id=? AND id>? "
                    "AND role IN ('user','assistant') ORDER BY id", (session_id, sess["summary_upto"] or 0))
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


TEAM_GUIDE = (
    "# Multi-model teamwork\n"
    "Other cloud models of the pool can work for you: {models}.\n"
    "- When the user asks for a team, group, several agents or several models (takım, ekip, grup, çoklu ajan, "
    "çoklu model...), use the team tool: every member is a real agent on its own model with file, command and "
    "document tools. Parts that need an earlier part's result get a later stage (stage 2, 3...); they receive the "
    "earlier reports and file names. Put the whole pipeline in ONE team call.\n"
    "- ask_model is only for a text answer from one other model (a review, an analysis, a second opinion).\n"
    "- Never do the members' parts yourself and call it teamwork. When you report, say which model did which "
    "part exactly as the tool results (and the [Tool actions ...] notes of earlier turns) list them.")


def _system_prompt(role: str, root, session_id: str, project: dict | None, skill_names: list[str],
                   plan: str | None, native: bool, model: str = "", lang: str = "tr",
                   tools: set[str] | None = None) -> tuple[str, dict]:
    """tools: names offered this turn (None = all, empty = none)."""
    agents = catalog.agents()
    sizes: dict[str, int] = {}
    parts = [SYSTEM_CORE.format(root=root, date=time.strftime("%Y-%m-%d"), model=model, os_name=OS_NAME, shells=SHELLS,
                                project=f"\nProject: {project['name']}" if project else "")]
    if tools is None or tools & {"run", "start"}:  # the real OS build, shells and tool versions
        from .. import hostinfo
        parts.append(hostinfo.prompt_section())
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
    if tools is None or "mcp" in tools:
        from .. import mcp_client
        if section := mcp_client.prompt_section():
            parts.append(section)
            sizes["tools"] = sizes.get("tools", 0) + len(section)
    if tools is None or "team" in tools:
        pool = [e["model"] for e in router.pool() if e["model"].partition(":")[2] != model][:12]
        if pool:
            parts.append(TEAM_GUIDE.format(models=", ".join(pool)))
            sizes["tools"] = sizes.get("tools", 0) + len(parts[-1])
    # Skill discovery: the model sees every skill's purpose and loads a matching one with use_skill.
    available = {k: v for k, v in catalog.skills().items() if k not in skill_names}
    if available and (tools is None or "use_skill" in tools):
        parts.append("# Available skills\nWhen the request matches one of these, call use_skill with its name first "
                     "and follow the loaded instructions:\n" + "\n".join(
                         f"- {k}: {v.get('description_en') or v.get('description') or v['title']}"
                         for k, v in available.items()))
        sizes["skills"] = len(parts[-1])
    # The user's lasting rules: global ones (Settings) and the project's AIIQ.md. Read once per task (stable prompt).
    # Headings inside the rule texts are flattened, so they cannot break the prompt's own sections.
    flat = lambda text: re.sub(r"(?m)^#+[ \t]*", "", text).strip()  # noqa: E731
    global_rules = flat(load_settings().get("rules") or "")
    project_rules = flat(workspace.read_rules(project))
    if global_rules or project_rules:
        parts.append("# Rules from the user (always follow them; they override the defaults above)"
                     + (f"\n## For every chat\n{global_rules[:workspace.RULES_MAX]}" if global_rules else "")
                     + (f"\n## For this project ({workspace.RULES_FILE})\n{project_rules}" if project_rules else ""))
        sizes["project" if project_rules else "system"] = sizes.get("project" if project_rules else "system", 0) + len(parts[-1])
    if project:
        parts.append("# Project files\n" + workspace.summarize_tree(root, 60))
        code_map = project_map(root)
        if code_map:  # where things are defined: search_code / symbols / read_file lines=... go straight there
            parts[-1] += "\n\n# Code map (definitions per file)\n" + code_map
        sizes["project"] = sizes.get("project", 0) + len(parts[-1])
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
    toks = {k: v / 3 for k, v in chars.items() if v}
    est = sum(toks.values()) or 1
    scale = actual_input / est if actual_input else 1
    return {k: int(v * scale) for k, v in sorted(toks.items(), key=lambda kv: -kv[1])}


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
    t_req = time.monotonic()
    if run.perf["prep_ms"] is None:
        run.perf["prep_ms"] = (t_req - run.t0) * 1000
    turn = {"model": model, "wait_ms": None, "total_ms": 0.0}
    # Live context: the prompt estimate plus what the model has written so far (thinking, text, tool
    # arguments), so the meter moves during long thinking or a long file instead of jumping at the end.
    base = run.session.get("context_used") or 0
    out = {"native_think": [], "tool": 0, "at": 0.0, "real": False}

    def grow() -> None:
        now = time.monotonic()
        if out["real"] or now - out["at"] < 0.5:
            return
        out["at"] = now
        written = tokens.count("".join(raw)) + tokens.count("".join(out["native_think"])) + out["tool"] // 3
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
            if run.hold:
                run.hold = False
                _emit(run, "reset_text")
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
            if not got_output and t in ("thinking", "text", "tool_call", "tool_call_start"):
                now = time.monotonic()
                turn["wait_ms"] = (now - t_req) * 1000
                if run.perf["first_ms"] is None:
                    run.perf["first_ms"] = (now - run.t0) * 1000
            got_output = got_output or t in ("thinking", "text", "tool_call", "tool_call_start")
            if t == "thinking_blocks":
                run.thinking_blocks = evt["blocks"]
            elif t == "thinking":
                out["native_think"].append(evt["text"])
                handle("thinking", evt["text"])
                grow()
            elif t == "tool_call":
                calls.append(evt)
            elif t in ("tool_call_start", "tool_call_progress"):
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
                    run.session["usage_input"] = base = evt["input"]
                    # Tokenizers differ by about +-40%; a much smaller count is a cached prompt (only new tokens
                    # evaluated, e.g. Ollama), which says nothing about the size: keep the ratio then.
                    if run.prompt_est > 500 and 0.55 <= (r := evt["input"] / run.prompt_est) <= 1.6:
                        CTX_RATIO[model] = r
                if evt.get("output"):  # final count: no more estimates for this turn
                    out["real"] = True
                output = evt.get("output") or 0
                if evt.get("reasoning"):  # hidden reasoning (never streamed, not carried to the next turn) is left out
                    output -= max(0, evt["reasoning"] - tokens.count("".join(out["native_think"])))
                used = (run.session.get("usage_input") or 0) + max(0, output)
                run.session["context_used"] = used
                _emit(run, "context", used=used)
            elif t == "text":
                raw.append(evt["text"])
                grow()
                for kind, text in splitter.feed(evt["text"]):
                    handle(kind, text)
                if splitter.open and splitter.open[0] != "<think>":
                    m = PREP_NAME.search(splitter.buf)
                    prepare(next((g for g in m.groups() if g), None) if m else None, len(splitter.buf))
        for kind, text in splitter.flush():
            handle(kind, text)
    finally:  # never leave a spinning step behind, also when the turn fails or is cancelled
        turn["total_ms"] = (time.monotonic() - t_req) * 1000
        if turn["wait_ms"] is None:
            turn["wait_ms"] = turn["total_ms"]
        run.perf["turns"].append(turn)
        if prep_id:  # the real tool steps replace the placeholder
            run.steps = [s for s in run.steps if s["id"] != prep_id]
            _emit(run, "step_remove", step_id=prep_id)
        end_thinking()
    return "".join(raw), tags, calls


# A busy or briefly failing provider (HTTP 503/429/5xx, timeouts) is retried with growing waits instead of
# ending a long task; quota/auth errors are not transient and end the run at once.
TRANSIENT = {"overloaded", "rate_limit", "server", "bad_gateway", "timeout", "network", "unavailable"}
RETRY_WAITS = (5, 15, 30, 60, 90)

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
    # Keep provider message rules valid: the kept tail must not start with an orphan tool result.
    tail = messages[len(messages) - keep:]
    while tail and tail[0]["role"] == "tool":
        tail = tail[1:]
    messages[first:] = [{"role": "user", "content": f"{PROGRESS_TAG}\n{summary}\n\nContinue the task."}] + (
        [{"role": "assistant", "content": "OK."}] if tail and tail[0]["role"] == "user" else []) + tail
    after = estimate_tokens([system] + messages)
    _step(run, "compress", "context", "done", json.dumps({"before": est, "after": after, "mode": "summary"}), step_id=sid)
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
    if name == "todo":  # shown as the live task list, not as a trace step
        res = await TOOLS[name].fn(ctx, args, body)
        if res.ok:
            run.todos = res.data["todos"]
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
    if name == "ask_model" and res.data.get("model"):
        label = res.data["model"]
    if name == "remember" and res.data.get("scope"):
        label = res.data["scope"]
    detail = body if name == "write_file" else res.data.get("diff") or res.output if name == "edit_file" else res.output
    _step(run, kind, label, "done" if res.ok else "error", detail,
          data={"tool": name, "args": {} if name == "team" else args, **res.data, "output": res.output[:4000]}, step_id=sid)
    return res


def _budget(info: dict) -> float:
    """Tokens a task may fill before trimming: the threshold share of the window, minus room for the reply
    (a whole file)."""
    n = info["current"]
    return n * (info["threshold"] if 0 < info["threshold"] < 100 else 90) / 100 - min(8192, n // 5)


async def execute(run: Run, user_text: str, opts: dict) -> None:
    failed: dict = {}
    settings = load_settings()
    limits = settings["agent"]
    session = run.session
    project = workspace.get_project(session.get("project_id"))
    root = workspace.session_root(session)
    sdir = sessions.path(session["id"])
    model = opts.get("model") or settings["active_model"]
    mode = opts.get("permission_mode") or settings["permission_mode"]
    forced_role, skill_names, clean_text = _parse_mentions(user_text)
    ctx = ToolContext(run.id, root, mode, run.cancel, session_dir=sdir, owner=f"{session['id']}:{run.id}", project=project,
                      step=lambda kind, data: _step(run, kind, kind, "done", json.dumps(data, ensure_ascii=False)),
                      live=lambda kind, title, status, data, step_id=None: _step(run, kind, title, status, "", data, step_id))
    visible: list[str] = []
    before = workspace.output_files(root)  # images/pages that exist already are not this task's outputs
    # The whole folder as it is now, taken in a worker thread while the model writes its first reply: at the end
    # every change shows in the review card, also those made by commands, scripts and formatters.
    from .. import changes as changes_mod
    run.folder_snap = asyncio.create_task(asyncio.to_thread(changes_mod.take, root))
    changed: dict | None = None
    best = ""  # the last real answer: kept if a later rewrite or continuation comes back empty
    status = "ok"
    _emit(run, "started", model=model, mode=mode)
    try:
        ctx_info = await router.context_info(model)
        base_opts = {"num_ctx": ctx_info["current"]} if ctx_info["local"] else {}
        history = _history(session["id"], run.user_msg_id)
        limit = ctx_info["current"] * ctx_info["threshold"] / 100
        if 0 < ctx_info["threshold"] < 100 and estimate_tokens(history) + 2500 > limit:
            sid = _step(run, "compress", "context", "running")
            with _side(run):
                res = await compress(session["id"], model, run.cancel, before_id=run.user_msg_id, target=limit * 0.4)
            _step(run, "compress", "context", "done", json.dumps(res), step_id=sid)
            history = _history(session["id"], run.user_msg_id)

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
              and not sessions.state_file(session["id"]).exists()):
            allowed = set(READ_ONLY)
        # An agent or skill with a 'tools:' list gets only those tools (fewer tool definitions, fewer tokens).
        chosen = ([catalog.agents().get(forced_role)] if forced_role else []) + [catalog.skills().get(s) for s in skill_names]
        if limit := {t for item in chosen if item for t in item.get("tools") or [] if t in TOOLS}:
            allowed = (set(TOOLS) if allowed is None else allowed | limit) & (limit | {"todo", "use_skill"})
        lang = reply_language(clean_text, opts.get("ui_lang"))
        ctx.lang = lang
        ctx.goal = clean_text[:2000]
        # A short reminder on the latest turn keeps small local models from drifting into English (not stored).
        reminder = think_reply_reminder(lang)
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
        budget = _budget(ctx_info)
        debug_attempts, last_failure, leak_retries, lang_retry, nudges, used_tools = 0, None, 0, False, 0, False
        claim_retry = read_retry = research_retry = False

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
        offer = allowed

        async def model_info(m: str) -> tuple[dict, bool]:
            if m not in infos:
                i = await router.context_info(m)
                infos[m] = (i, router.native_tools(m, i))
            return infos[m]

        if multi.get("enabled") and multi.get("auto_switch", True) and not router.availability(model)[0]:
            # The chosen model is known to be out of quota: start on the most available pool model.
            alt, _ = await router.pick(None, estimate_tokens(messages), {model}, tools=True)
            if alt:
                _step(run, "fallback", alt, detail=f"{model}: {router.availability(model)[1]}",
                      data={"from": model, "to": alt, "reason": "quota"})
                model = alt
                ctx_info, native = await model_info(model)
                base_opts, budget = {}, _budget(ctx_info)
        for iteration in range(limits["max_iterations"]):
            if run.cancel.is_set():
                raise asyncio.CancelledError
            run.role = role
            _emit(run, "agent", role=role, iteration=iteration)
            visible.clear()
            run.noted = False
            run.thinking_blocks = None
            turn_model = model if role in agent_off else router.agent_model(role, model)
            t_info, t_native = (ctx_info, native) if turn_model == model else await model_info(turn_model)
            if turn_model != model and estimate_tokens(messages) > t_info["max"] * 0.8:
                turn_model, t_info, t_native = model, ctx_info, native  # the task no longer fits that model
            ctx.model = turn_model
            pool_others = [e for e in router.pool() if e["model"] != turn_model] if multi.get("enabled") else []
            if allowed is None:  # ask_model / team only when other cloud models can take work; mcp when connected
                drop = set() if pool_others and multi.get("delegate", True) else {"ask_model", "team"}
                if not has_mcp:
                    drop.add("mcp")
                offer = set(TOOLS) - drop if drop else None
            if run.repeats >= 3:  # looping over the same searches/pages: answer with what was found
                if not search_closed:
                    search_closed = True
                    messages.append({"role": "user", "content": "You repeated the same searches or page reads several "
                                     "times. Searching is closed for this task: write the answer now from what you "
                                     "already found, and say what could not be verified."})
                offer = (set(TOOLS) if offer is None else set(offer)) - REPEAT_GUARD
            # Built once per role and task: an unchanged prompt prefix lets local servers (Ollama, llama.cpp,
            # LM Studio) and cloud prompt caches reuse it, instead of re-reading everything after each file write.
            key = (role, t_native, turn_model, frozenset(offer) if offer is not None else None)
            if key not in prompts:
                prompts[key] = _system_prompt(role, root, session["id"], project, skill_names, plan,
                                              t_native, turn_model.partition(":")[2], lang, offer)
            sys_text, sys_sizes = prompts[key]
            system = {"role": "system", "content": sys_text}
            # Live context accounting before every model turn; relieve it inside long tasks. Native tool definitions
            # are part of the prompt the provider counts, so they are counted here too.
            schemas = tool_schemas(offer) if t_native and offer != set() else None
            tool_tok = tokens.count(json.dumps(schemas, ensure_ascii=False)) if schemas else 0
            est = estimate_tokens([system] + messages) + tool_tok
            if est > budget and shrink_messages(messages, keep_last=4):
                est2 = estimate_tokens([system] + messages) + tool_tok
                _step(run, "compress", "context", "done", json.dumps({"before": est, "after": est2, "mode": "trim"}))
                est = est2
            # A summary again only after 8 new messages: when the system prompt alone is near the budget, summarizing
            # every turn would double the model calls without making room.
            if est > budget and len(messages) - max(first_run_msg, run.summarized_at) > 8:
                est = await _summarize_progress(run, model, messages, first_run_msg, base_opts, system, est) + tool_tok
            run.prompt_est = est
            run.session["context_used"] = shown = int(est * CTX_RATIO.get(turn_model, 1.0))
            _emit(run, "context", used=shown)
            t_opts = {"num_ctx": t_info["current"]} if t_info["local"] else {}
            turn_opts = {**t_opts, "tools": schemas} if schemas else t_opts
            try:
                run.session["usage_input"] = None
                raw, tag_blocks, calls = await _stream_turn(run, turn_model, [system] + messages, visible, turn_opts)
                sizes = {**sys_sizes, "tools": sys_sizes.get("tools", 0)
                         + (len(json.dumps(schemas, ensure_ascii=False)) if schemas else 0)}
                run.stats = context_breakdown(sizes, messages + ([{"role": "assistant", "content": raw}] if raw else []),
                                              run.session.get("usage_input"))
            except ProviderError as e:
                if t_native and e.code in ("no_tools", "bad_request") and not "".join(visible):
                    # The model/server rejected function calling: remember it and use the tag protocol.
                    router.disable_native_tools(turn_model)
                    infos[turn_model] = (t_info, False)
                    if turn_model == model:
                        native = False
                    _step(run, "note", "tools", "done", ui_text(lang, "ai_note_no_native", NOTES["no_native"]["en"], e=e))
                    continue
                if e.code in ("context_length", "too_large") and ctx_relief < 2 and not "".join(visible):
                    # The model's real window is smaller than reported (or the request too big): trim the task's
                    # older tool traffic, then summarize it, and send again instead of ending the task.
                    ctx_relief += 1
                    est = estimate_tokens([system] + messages)
                    budget = min(budget, int(est * 0.6))
                    shrink_messages(messages, keep_last=2)
                    est2 = estimate_tokens([system] + messages)
                    if est2 > budget and len(messages) - first_run_msg > 4:
                        est2 = await _summarize_progress(run, model, messages, first_run_msg, base_opts, system, est2)
                    if est2 < est:
                        _step(run, "compress", "context", "done", json.dumps({"before": est, "after": est2, "mode": "trim"}))
                        continue
                # A provider that cannot be reached at all (connection refused, DNS) is not busy: two short retries,
                # and switching only to models of another provider (the same server is down for all its models).
                unreachable = e.code == "unavailable" and "unreachable" in str(e)
                max_retries = 2 if unreachable else len(RETRY_WAITS)
                out_of_quota = e.code in ("quota", "payment", "auth", "plan_required") or (e.code in TRANSIENT and retries >= 2)
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
                    alt, why = await router.pick(None, estimate_tokens([system] + messages), {model} | down, tools=True)
                    if alt:
                        # Quota/credits ran out (or the provider keeps failing): continue on the most available
                        # pool model with the same conversation, instead of ending the task.
                        switches += 1
                        retries = 0
                        run.hold = bool("".join(visible))
                        _step(run, "fallback", alt, detail=f"{model}: {e}",
                              data={"from": model, "to": alt, "reason": e.code})
                        model = alt
                        ctx_info, native = await model_info(model)
                        base_opts, budget = {}, _budget(ctx_info)
                        prompts.clear()
                        continue
                if e.code in TRANSIENT and retries < max_retries:
                    wait = RETRY_WAITS[retries]
                    if e.retry_at:  # the provider said when: wait that long (at most 2 minutes), not less
                        wait = int(min(120, max(wait, e.retry_at - time.time() + 1)))
                    retries += 1
                    run.hold = bool("".join(visible))  # a half-written reply is replaced by the retried one
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
            if chat_only:  # small talk: never execute tools, even if the model writes them
                tag_blocks, calls = [], []
            parsed = [parse_tool(b) for b in tag_blocks]
            if not tag_blocks and not calls:
                # Last chance for formats only detectable on the full text (Mistral, fenced JSON)...
                inline, cleaned = extract_inline_calls("".join(visible), set(TOOLS))
                text_now = "".join(visible).strip()
                open_todos = [t for t in run.todos if t["status"] != "completed"]
                if text_now and not is_announcement(text_now):
                    best = text_now
                if inline:
                    parsed, visible[:] = inline, [cleaned]
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
                elif used_tools and len(text_now) >= 200 and not is_announcement(text_now) and open_todos:
                    # A real final answer with the list left unticked: finish instead of making the model
                    # write the answer twice; the step it was on is done.
                    run.todos = [{**t, "status": "completed"} if t["status"] == "in_progress" else t for t in run.todos]
                    _emit(run, "todos", todos=run.todos)
                    await fix_language(text_now)
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
                else:
                    await fix_language(text_now)
                    break
            used_tools = True
            run.hold = False
            _emit(run, "reset_text")  # interim narration is kept in the trace, not in the final answer
            narration = "".join(visible).strip()
            if narration and not run.noted:
                _step(run, "note", role, "done", narration)
            failure = None
            if calls:
                messages.append({"role": "assistant", "content": narration,
                                 **({"thinking_blocks": run.thinking_blocks} if run.thinking_blocks else {}),
                                 "tool_calls": [{"id": c["id"], "name": c["name"], "arguments": c["arguments"]} for c in calls]})
                calls = _merge_team_calls(calls)
                for c in calls:
                    if c.get("merged"):
                        messages.append({"role": "tool", "tool_call_id": c["id"], "name": c["name"],
                                         "content": "Merged into the first team call of this turn (one team runs all parts)."})
                        continue
                    args, body = split_args(c["name"], c["arguments"]) if c["name"] in TOOLS else (c["arguments"], "")
                    res = await _exec(run, ctx, c["name"], args, body, offer)
                    messages.append({"role": "tool", "tool_call_id": c["id"], "name": c["name"], "content": res.output})
                    if not res.ok and c["name"] == "run":
                        failure = res.output
            else:
                results = []
                for call in parsed:
                    if call and call.arguments is not None and call.name in TOOLS:
                        call.args, call.body = split_args(call.name, call.arguments)
                    res = await _exec(run, ctx, call.name, call.args, call.body, offer) if call \
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
        approvals.cancel_all_for(run.id)
        # A finished run never keeps spinning steps (closed chat, error, cancel...).
        for s in run.steps:
            if s["status"] == "running":
                s["status"] = "done" if status == "ok" else "error"
                _emit(run, "step", step=s)
        answer = ACTION_ECHO.sub("\n", "".join(visible)).strip() or (best if status in ("ok", "budget", "cancelled") else "")
        # Images and web pages the task produced (also by scripts) are shown under the answer.
        outputs = workspace.new_outputs(before, root) if ctx.files_changed or ctx.commands else []
        # The error is stored with the message, so it is still explained after a reload (not an empty reply).
        if (ctx.files_changed or ctx.commands) and run.folder_snap and run.folder_snap.done() and not run.folder_snap.exception():
            try:
                after = await asyncio.to_thread(changes_mod.take, root)
                changed = changes_mod.compare(run.folder_snap.result(), after, set(ctx.files_changed))
                if not changed["files"]:
                    changed = None
            except Exception:
                changed = None
        timing = _timing(run)
        PERF.append({**timing, "status": status, "model": model, "at": time.time()})
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
        used = int((estimate_tokens(_history(session["id"])) + sum(
            v for k, v in (run.stats or {}).items() if k in ("system", "tools", "skills", "project", "state"))) * CTX_RATIO.get(model, 1.0))
        db.execute("UPDATE sessions SET context_used=?, context_stats=? WHERE id=?",
                   (used, json.dumps(run.stats) if run.stats else None, session["id"]))
        _emit(run, "done", status=status, text=answer, steps=run.steps, context_used=used, todos=run.todos,
              outputs=outputs, timing=timing, changes=changed)
        RUNS.pop(run.id, None)
        if project and (ctx.files_changed or ctx.commands):
            # The time-machine snapshot runs after the answer is shown, so the user never waits for git.
            task = asyncio.create_task(_snapshot(root, f"aiiq: {clean_text[:80]}"))
            _BACKGROUND.add(task)  # keep a reference until it finishes
            task.add_done_callback(_BACKGROUND.discard)


async def _snapshot(root, message: str) -> None:
    try:
        await workspace.git_snapshot(root, message)
    except Exception:  # a failed snapshot never affects the chat
        pass


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
