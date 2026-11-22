"""Tool registry. The model invokes tools with a provider-agnostic tag protocol:

    <tool name="write_file" path="src/index.php">...raw file content...</tool>
    <tool name="run" shell="powershell">npm install</tool>

Attributes are arguments; the body is the main argument. Every tool goes through backend policy.
New tools: decorate an async function with @tool(...)."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import re
import shlex
import shutil
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Awaitable, Callable


from .. import approvals, policy
from ..config import LANG_DIR, load_settings
from ..process_manager import manager

MAX_RESULT = 6000


@dataclass
class ToolContext:
    run_id: str
    root: Path
    mode: str
    cancel: asyncio.Event
    session_dir: Path | None = None  # chat/<id>/.session: scripts, screenshots, state
    owner: str | None = None  # "<session_id>:<run_id>": groups background tasks per chat
    files_changed: list[str] = field(default_factory=list)
    commands: list[str] = field(default_factory=list)
    step: Callable[[str, dict], None] = lambda kind, data: None
    model: str = ""  # the model running this turn (ask_model never hands work back to it)
    project: dict | None = None  # the chat's project (remember writes its AIIQ.md)
    lang: str = "tr"  # the reply/UI language: text the app writes for the user follows it
    # live(kind, title, status, data, step_id) -> step_id: one step updated in place (team task board)
    live: Callable[..., str] | None = None
    step_id: str | None = None  # the trace step of the tool call running now (team board updates it in place)
    goal: str = ""  # the user's request of this task (team members get it, so paths and names are not lost)
    team_prior: list = field(default_factory=list)  # team parts of the interrupted task this one resumes
    shell_cwd: str = ""  # set by a standalone "cd DIR": later run/start calls without cwd run there
    # Decimal figures seen in this task's sources (tool results, the user's messages): a document is checked
    # against them, so invented numbers are flagged. sourced = a web/file source was read in this task.
    evidence: set = field(default_factory=set)
    read_seen: dict = field(default_factory=dict)  # path -> (mtime, size) of whole-file reads in this task
    started: float = field(default_factory=time.time)  # when this task began (files newer than this are its own)
    read_limit: int = 20000  # characters one read_file returns (set per turn from the model's window)
    sourced: bool = False


@dataclass
class ToolResult:
    ok: bool
    output: str
    data: dict = field(default_factory=dict)


@dataclass
class ToolSpec:
    name: str
    usage: str
    description: str
    fn: Callable[[ToolContext, dict, str], Awaitable[ToolResult]]
    params: dict = field(default_factory=dict)  # JSON schema properties
    main: str | None = None  # parameter that maps to the tag body
    required: tuple = ()


TOOLS: dict[str, ToolSpec] = {}
S = lambda desc, **kw: {"type": "string", "description": desc, **kw}  # noqa: E731
SHELLS = ["powershell", "powershell5", "pwsh", "cmd", "bash", "python", "node", "php", "exec"]


def tool(name: str, usage: str, description: str, params: dict | None = None, main: str | None = None,
         required: tuple = ()):
    def deco(fn):
        TOOLS[name] = ToolSpec(name, usage, description, fn, params or {}, main, required)
        return fn
    return deco


# Tools that change nothing on the computer: offered alone for plain knowledge questions.
READ_ONLY = {"read_file", "list_dir", "search_code", "symbols", "impact", "web_search", "fetch_url", "research", "use_skill", "web_screenshot",
             "places", "read_document", "my_location", "system_info", "browser_snapshot", "browser_find", "browser_inspect",
             "browser_screenshot", "browser_scroll", "browser_wait"}


def _pick(names: set[str] | None) -> list[ToolSpec]:
    return [t for t in TOOLS.values() if names is None or t.name in names]


def _short(text: str, limit: int) -> str:
    """The first sentence of a description (or the first `limit` characters at a word boundary)."""
    text = re.sub(r"\s+", " ", text or "").strip()
    m = re.match(r"(.{20,}?[.!?])(\s|$)", text)
    first = m.group(1) if m else text
    return first if len(first) <= limit else first[:limit].rsplit(" ", 1)[0] + "…"


def _compact_param(p: dict) -> dict:
    out = {k: v for k, v in p.items() if k not in ("description", "items", "properties")}
    if p.get("description"):
        out["description"] = _short(p["description"], 70)
    if isinstance(p.get("items"), dict):
        out["items"] = _compact_param(p["items"])
    if isinstance(p.get("properties"), dict):
        out["properties"] = {k: _compact_param(v) for k, v in p["properties"].items()}
    return out


def tools_prompt(names: set[str] | None = None, compact: bool = False, lean: bool = False) -> str:
    """lean: the usage line and one short sentence (the usage already shows the arguments)."""
    if lean:
        return "\n".join(f"- {t.usage}\n  {_short(t.description, 90)}" for t in _pick(names))
    return "\n".join(f"- {t.usage}\n  {_short(t.description, 160) if compact else t.description}" for t in _pick(names))


def _lean_param(p: dict) -> dict:
    out = {k: v for k, v in p.items() if k in ("type", "enum")}
    if p.get("description"):
        out["description"] = _short(p["description"], 40)
    if isinstance(p.get("items"), dict):
        out["items"] = {"type": p["items"].get("type", "string")}
    return out


def tool_schemas(names: set[str] | None = None, compact: bool = False, lean: bool = False) -> list[dict]:
    """Native function-calling definitions (provider adapters wrap them in their own format). compact: the first
    sentence of each description only, for small context windows (the definitions are sent with every turn)."""
    if lean:  # slow models: one short sentence per tool, a few words per argument
        return [{"name": t.name, "description": _short(t.description, 90),
                 "parameters": {"type": "object", "properties": {k: _lean_param(v) for k, v in t.params.items()},
                                "required": list(t.required)}} for t in _pick(names)]
    return [{"name": t.name, "description": _short(t.description, 160) if compact else t.description,
             "parameters": {"type": "object", "properties": {k: _compact_param(v) for k, v in t.params.items()}
                            if compact else t.params, "required": list(t.required)}}
            for t in _pick(names)]


def split_args(name: str, arguments: dict) -> tuple[dict, str]:
    """Native call arguments -> (attribute args as strings, body) like the tag protocol."""
    spec = TOOLS[name]
    args = {k: (v if isinstance(v, str) else json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else str(v))
            for k, v in arguments.items() if v is not None}
    body = args.pop(spec.main, "") if spec.main else ""
    return args, body


def _lang_name(code: str) -> str:
    from ..agents.orchestrator import LANG_NAMES
    return LANG_NAMES.get(code, code)


def clip(text: str, n: int = MAX_RESULT) -> str:
    return text if len(text) <= n else text[: n // 3] + f"\n...[{len(text) - n} chars omitted]...\n" + text[-2 * n // 3:]


async def gate(ctx: ToolContext, op: dict, decision: policy.Decision, preview=None) -> str | None:
    """Returns None if allowed, else a denial message for the model. preview: callable building the change
    preview (diff) shown on the approval card; only called when the user is actually asked."""
    if decision.action == "deny":
        ctx.step("policy", {"op": op, "action": "deny", "reasons": decision.reasons})
        if decision.category == "kills_app":
            return ("DENIED: this kills processes by name (every python / node on the computer) - that would also end this "
                    "app and your task, and the user's other programs. Nothing was run. To free a port, start your server "
                    "on another free port; stop a server you started here with its process_id (stop tool), or one other "
                    "process by its PID only.")
        if decision.category == "protected":
            return ("DENIED: secrets.json (the user's API keys) and aiiq.db (all chats) belong to the app and are never "
                    "read or changed by a task. Nothing was run. Do the work without them.")
        return f"DENIED by policy ({decision.category}). This operation is never allowed."
    if decision.action == "ask":
        ctx.step("approval", {"op": op, "category": decision.category})
        shown = None
        if preview:
            try:
                shown = preview()
            except Exception:  # a preview must never block the approval itself
                shown = None
        if not await approvals.request(ctx.run_id, op, decision.category, decision.reasons, shown):
            return "DENIED by user. Choose a different approach or ask the user."
    return None


EOF_LINE = re.compile(r"^\s*(//|#|--|;|/\*|<!--|\{\{!--)?\s*(EOF|END OF FILE|END-OF-FILE|end of file|Dosya sonu|DOSYA SONU)"
                      r"\s*\.?\s*(\*/|-->|--\}\})?\s*$", re.I)
FENCED = re.compile(r"^\s*```[\w.+-]*[ \t]*\n(.*?)\n```\s*$", re.S)


def clean_file_content(text: str) -> str:
    """Remove artifacts models add around file contents: a markdown fence wrapping the whole file and trailing
    'EOF' / 'end of file' marker lines (after `?>` those are even printed as page output)."""
    text = text[1:] if text.startswith("\n") else text
    text = APP_LINES.sub("", text)
    if m := FENCED.match(text):
        text = m.group(1)
    if (s := text.strip()).startswith("<![CDATA[") and (s.endswith("]]>") or "]]>" not in s):
        # The whole body wrapped XML style (seen live in .md sources): the wrapper is not part of the file.
        text = s[len("<![CDATA["):].removesuffix("]]>")
    lines = text.rstrip().split("\n")
    while lines and (EOF_LINE.match(lines[-1]) or not lines[-1].strip()):
        lines.pop()
    return "\n".join(lines) + "\n" if lines else ""


PREVIEW_LIMIT = 20_000  # characters of diff sent to the approval card
PREVIEW_MAX_FILE = 1_000_000


def _text_of(target: Path) -> str | None:
    """Current text of a file for the preview; None for a missing, binary or very large file."""
    try:
        if not target.is_file() or target.stat().st_size > PREVIEW_MAX_FILE:
            return None
        raw = target.read_bytes()
    except OSError:
        return None
    if b"\0" in raw[:8000]:
        return None
    return raw.decode("utf-8", errors="replace").replace("\r\n", "\n")


def change_preview(kind: str, before: str | None, after: str | None, rel: str) -> dict:
    """What a write will change, shown on the approval card before the user decides:
    kind new | overwrite | edit | delete, a unified diff and the added / removed line counts."""
    from .editing import diff
    if kind == "delete" and before is None:
        return {"kind": kind, "path": rel, "diff": "", "added": 0, "removed": 0, "binary": True}
    full = diff(before or "", after or "", rel, 10 ** 9)
    lines = full.splitlines()
    added = sum(1 for l in lines if l.startswith("+") and not l.startswith("+++"))
    removed = sum(1 for l in lines if l.startswith("-") and not l.startswith("---"))
    cut = len(full) > PREVIEW_LIMIT
    return {"kind": kind, "path": rel, "diff": full[:PREVIEW_LIMIT].rsplit("\n", 1)[0] if cut else full,
            "added": added, "removed": removed, "truncated": cut}


def _path(ctx: ToolContext, rel: str) -> Path:
    return policy.resolve_in(ctx.root, rel, allow_outside=ctx.mode == "full")


def _rel(ctx: ToolContext, target: Path) -> str:
    """Path shown to the model/UI: relative to the working folder when inside it (both sides resolved, so
    8.3 short names or symlinks on Windows do not break the comparison)."""
    try:
        return target.resolve().relative_to(ctx.root.resolve()).as_posix()
    except ValueError:
        return str(target)


APP_MARKS = re.compile(r"characters omitted to save context|\[older step shortened|characters of file content "
                       r"\(it is on disk\) left out", re.I)
# The app's own bookkeeping lines a model copied into a file ("[To-do item continues below]" ended up as line 161 of
# app.js and broke it): taken out of the content before it is written.
APP_LINES = re.compile(r"(?m)^[ \t]*\[(?:To-do (?:item|\d+/\d+)|App note|App record)[^\n]*\][ \t]*\r?\n?")
EMPTY_OK = {".gitkeep", ".keep", "__init__.py", ".nojekyll", ".gitignore", ".env", "py.typed"}
TEMP_NAME = re.compile(r"\.(?:tmp\w*|bak|orig|old)$|^(?:tmp|temp)\d*[._-]", re.I)


def garbled_path(path: str) -> str:
    """A path the model mangled while its output fell apart ('hes-ap-ma-kine-s-i / b u i l d . g r a d l e'): writing
    it creates junk folders. Refused with the reason, so the next call sends the real name."""
    p = str(path or "")
    if re.search(r"\s[/\\]|[/\\]\s", p) or re.search(r"(?:^|[\s/\\])(?:\S\s){3,}\S(?:$|[\s/\\])", p) \
            or "�" in p or re.search(r"[<>|\"?*\x00-\x1f]", p):
        return (f"Refused: the path {p!r} looks garbled (spaces around '/' or between single letters, or characters "
                "a file name cannot have). Send the real relative path, e.g. app/build.gradle.kts.")
    return ""


def broken_chars_note(text: str) -> str:
    """The provider sent broken characters (U+FFFD) instead of letters (Turkish ı/ğ split between tokens): the file
    holds them now. Said in the result with where, so the model rewrites those words."""
    n = text.count("�")
    if not n:
        return ""
    lines = [f"{i}: {ln.strip()[:120]}" for i, ln in enumerate(text.split("\n"), 1) if "�" in ln][:5]
    return (f"\nWarning: the written text has {n} broken character(s) (�) where letters were lost in transfer, "
            "e.g. lines " + " | ".join(lines) + ". Fix those words with edit_file (in code comments and strings plain "
            "ASCII is safest).")


def app_placeholder(text: str, path: str) -> str:
    """The app shortens a file the model wrote earlier in what it sends back ("[1202 characters omitted to save
    context; read_file shows the current file]"); a model that forgot the file copied that line into it as the
    content and the page showed only that line. Such text is never written."""
    if text and APP_MARKS.search(text):
        return (f"Refused: this contains the app's note for a shortened earlier step, not real file content. The "
                f"conversation only keeps a short form of files written earlier - read_file {path} to get its real "
                "content, then write or edit with the actual text.")
    return ""


async def _network_gate(ctx: ToolContext, op: dict) -> str | None:
    return await gate(ctx, op, policy.Decision("ask" if ctx.mode == "ask" else "allow", "network"))


def kind_of(args: dict, target: Path) -> str:
    return str(args.get("type") or target.suffix.lstrip(".")).lower()


FIGURE = re.compile(r"(?<![\w.,])\d{1,3}(?:[.,]\d{3})*[.,]\d{1,4}(?![\w]|[.,]\d)")


def figures(text: str) -> set[str]:
    """Decimal numbers of a text in one spelling (50,36 = 50.36), for the evidence check."""
    out = set()
    for m in FIGURE.findall(text or ""):
        digits = re.sub(r"[.,](?=\d{3}(?:\D|$))", "", m) if re.search(r"[.,]\d{3}[.,]", m) else m
        out.add(digits.replace(",", "."))
    return out


def unverified_figures(ctx: "ToolContext", content: str) -> list[str]:
    """Figures of a document that no source of this task contains (only when sources were read at all)."""
    if not ctx.sourced or not ctx.evidence:
        return []
    mine = figures(content)
    known = set(ctx.evidence)
    for e in ctx.evidence:  # a source's 50.1926 also covers 50.19 and 50.2 (rounded or cut)
        whole, _, frac = e.partition(".")
        for n in range(1, len(frac)):
            known.add(f"{whole}.{frac[:n]}")
            try:
                known.add(f"{round(float(e), n):.{n}f}")
            except ValueError:
                pass
    unknown = sorted(f for f in mine if f not in known)
    return unknown if len(unknown) >= 3 and len(unknown) > len(mine) * 0.4 else []


def with_charset(target: Path, content: str) -> str:
    """A whole HTML page without a charset declaration gets <meta charset="utf-8"> (browsers otherwise guess and
    Turkish letters break)."""
    if target.suffix.lower() not in (".html", ".htm") or re.search(r"<meta[^>]+charset", content[:4000], re.I):
        return content
    if m := re.search(r"<head[^>]*>", content[:4000], re.I):
        return content[:m.end()] + '\n<meta charset="utf-8">' + content[m.end():]
    if m := re.search(r"<html[^>]*>", content[:4000], re.I):
        return content[:m.end()] + '\n<head><meta charset="utf-8"></head>' + content[m.end():]
    return content


JS_CHECK = """() => new Promise((done) => setTimeout(done, 900))"""


def _current_file_note(text: str, rel: str) -> str:
    """A failed edit usually means the model edited from an old memory of the file (its earlier text was shortened
    in the context): a small file comes back whole, so the next SEARCH text is copied from what is really there."""
    if len(text) > 7000:
        return f"\n(The file has changed since you last saw it: read_file {rel} the part you edit before retrying.)"
    return f"\nCurrent content of {rel} (copy SEARCH text exactly from here):\n{text}"


async def _syntax_note(target: Path) -> str:
    """A written source file that does not parse ('6'li Paket' in single quotes): said at once, with the line, so the
    model fixes it before building on it (a weak model wrote it last and reported the task done)."""
    from .syntax import syntax_errors
    try:
        errs = await asyncio.to_thread(syntax_errors, target)
    except Exception:  # noqa: BLE001 - a check must never fail the write
        return ""
    if not errs:
        return ""
    return ("\nSYNTAX ERROR - this file does not parse; fix it now with edit_file before anything else:\n"
            + "\n".join(f"- line {ln}: {txt}" for ln, txt in errs))


async def js_check(target: Path) -> str:
    """Opens a written HTML page (with its scripts) in headless Chromium and reports JavaScript errors: uncaught
    exceptions, console errors and failed local scripts/styles. Empty string when the page is clean."""
    try:
        text = target.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    if not re.search(r"<script|onclick=|onload=", text, re.I):
        return ""
    from playwright.async_api import async_playwright
    problems: list[str] = []
    served = [0]  # references that only work from a server (/admin.js, fetch('/api/...')): not errors of the page
    home = target.resolve().parent.as_uri()

    def server_only(url: str, text: str = "") -> bool:
        """Opened as file://, a root path (/admin.js -> file:///C:/admin.js) or an API call cannot load: a page made to
        be served by the project's server (admin panel on :4000) got false 'JavaScript ERRORS' the model had to
        reason away twice in a live test."""
        if url.startswith("file:") and not url.startswith(home):
            return True
        return bool(re.search(r"Fetch API cannot load file:|origin 'null'|ERR_FILE_NOT_FOUND|Failed to fetch|"
                              r"NetworkError when attempting to fetch|net::ERR_", text))

    def on_console(m) -> None:
        if m.type != "error":
            return
        if server_only((m.location or {}).get("url", ""), m.text):
            served[0] += 1
        else:
            problems.append(f"console.{m.type}: {m.text[:300]}")

    def on_failed(r) -> None:
        if not r.url.startswith("file:"):
            return
        if server_only(r.url):
            served[0] += 1
        else:
            problems.append(f"failed to load {r.url[-120:]}")
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                page = await browser.new_page()
                from .browser import _page_error  # with the error's type and line (index.html:3106:21)
                page.on("pageerror", lambda e: (served.__setitem__(0, served[0] + 1) if server_only("", str(e))
                                                else problems.append(_page_error(e)["text"][:400])))
                page.on("console", on_console)
                page.on("requestfailed", on_failed)
                await page.goto(target.resolve().as_uri(), wait_until="load", timeout=15000)
                await page.evaluate(JS_CHECK)
            finally:
                await browser.close()
    except Exception as e:  # noqa: BLE001 - no browser: no check, never a failed write
        return f"(JavaScript check skipped: {type(e).__name__})"
    note = (f" ({served[0]} server-only reference(s) such as /api/... or root paths were skipped: they load only when "
            "the page is served - check it at its server URL with browser_navigate)") if served[0] else ""
    if not problems:
        return "JavaScript check: the page loaded without errors." + note
    return note.strip() + ("\n" if note else "") + "JavaScript ERRORS when the page loads (fix them, then the check runs again):\n- " + "\n- ".join(
        dict.fromkeys(problems[:12]))


def b64_file(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode()


# browser_* tools live in their own module (separate concern, long file); importing it here runs their
# @tool(...) decorators so they register into TOOLS, same as every function above.
from . import browser_tools  # noqa: E402,F401


# Tool groups in their own modules (round 2026-11-20): importing them registers their tools; every name
# stays available here (registry.X), and TOOLS keeps the order it always had (the prompt does not change).
from . import shell_tools  # noqa: E402,F401
from . import file_tools  # noqa: E402,F401
from . import web_tools  # noqa: E402,F401
from . import media_tools  # noqa: E402,F401
from . import doc_tools  # noqa: E402,F401
from . import agent_tools  # noqa: E402,F401
from .shell_tools import _did_you_mean, DEFAULT_SHELL, POWERSHELLS, PYTHON, SCRIPT_SHELLS, HEREDOC, HERE_CLOSE, route_heredoc, _powershell, PS_SHIM, PS_TRAILER, _split_chain, ps_chain, ps_script, CLI_LINE, SCRIPT_ONLY, CD_ONLY, PY_START, PS_HINT, FFMPEG_NO_Y, looks_python, PIP_CALL, venv_pip, build_argv, INSTALL_HINT, _unquote_arg, _shell_join, _spawn, ERR_AT, error_context, run, MISSING_PATH, _real_places, SERVER_CMD, READY, wait_ready, start, _script_text, _port_of, _port_busy, stop  # noqa: E402,F401
from .file_tools import write_file, _write_file, edit_file, search_code, read_file, read_document, list_dir, delete_file  # noqa: E402,F401
from .web_tools import web_search, fetch_url, DOWNLOAD_EXT, _github_repo, _download, research, my_location, system_info, places, browser_check, local_page_instead, web_screenshot  # noqa: E402,F401
from .media_tools import stock_photo, _provider_of, inspect_media, generate_image, edit_video, animate_image, generate_video, mobile_env, speech_to_text, text_to_speech  # noqa: E402,F401
from .doc_tools import PLACEHOLDER, placeholder_marks, _anchor_images, make_doc, doc_template  # noqa: E402,F401
from .agent_tools import symbols, impact, mcp, mcp_add, mcp_search, team, ask_model, remember, use_skill, save_catalog, TODO_STATES, NEED_GROUPS, need_tools, todo_patch, loose_json, todo  # noqa: E402,F401
_ORDER = ["write_file", "edit_file", "search_code", "read_file", "read_document", "list_dir", "delete_file", "run", "start", "stop", "web_search", "fetch_url", "research", "my_location", "system_info", "places", "browser_check", "web_screenshot", "stock_photo", "inspect_media", "generate_image", "edit_video", "animate_image", "generate_video", "mobile_env", "speech_to_text", "text_to_speech", "make_doc", "doc_template", "symbols", "impact", "mcp", "mcp_add", "mcp_search", "team", "ask_model", "remember", "use_skill", "save_catalog", "need_tools", "todo", "browser_navigate", "browser_snapshot", "browser_find", "browser_click", "browser_type", "browser_key", "browser_form", "browser_scroll", "browser_wait", "browser_tabs", "browser_screenshot", "browser_inspect", "browser_handoff", "browser_batch"]
_now = dict(TOOLS)
TOOLS.clear()
TOOLS.update({k: _now[k] for k in _ORDER if k in _now})
TOOLS.update({k: v for k, v in _now.items() if k not in TOOLS})
del _now

