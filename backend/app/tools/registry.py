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
    if m := FENCED.match(text):
        text = m.group(1)
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


@tool("write_file", '<tool name="write_file" path="REL/PATH">full file content</tool>',
      "Create or overwrite a file (parent folders are created). Always write the COMPLETE file content in ONE call, "
      "however large (a whole web page, a full script): every extra call is a full model round trip. append=true adds "
      "to the end of an existing file (only to continue a file that was cut off).",
      {"path": S("File path relative to the working directory"), "content": S("Complete file content (or the next part with append)"),
       "append": {"type": "boolean", "description": "Add content to the end of the existing file (large files in parts)"}},
      main="content", required=("path", "content"))
async def write_file(ctx, args, body):
    target = _path(ctx, args["path"])
    from .verify import is_binary_name, text_into_binary
    if is_binary_name(target):  # an .mp4/.png/.pdf/.docx made of text is a fake file with the right name
        return ToolResult(False, text_into_binary(target))
    op = {"tool": "write_file", "path": str(target), "sha": hashlib.sha256(body.encode()).hexdigest()[:16]}
    content = with_charset(target, clean_file_content(body))
    existed = target.exists()
    if str(args.get("append", "")).lower() in ("true", "1", "yes") and existed:
        if msg := await gate(ctx, {**op, "tool": "write_file"}, policy.decide_file_write(target, ctx.root, ctx.mode)):
            return ToolResult(False, msg)
        old = target.read_bytes().decode("utf-8", errors="replace")
        joined = old + ("" if not old or old.endswith("\n") or content.startswith("\n") else "\n") + content
        target.write_text(joined, encoding="utf-8", newline="")
        rel = _rel(ctx, target)
        ctx.files_changed.append(rel)
        added = content.count("\n") + (0 if content.endswith("\n") else 1)
        diff = "@@ appended @@\n" + "\n".join("+" + line for line in content.splitlines()[:4000])
        return ToolResult(True, f"appended {len(content)} chars to {rel} (now {len(joined)} chars)",
                          {"path": rel, "language": target.suffix.lstrip("."), "created": False,
                           "added": added, "removed": 0, "diff": diff[:PREVIEW_LIMIT]})
    preview = lambda: change_preview("overwrite" if existed else "new", _text_of(target) if existed else None,  # noqa: E731
                                     content, _rel(ctx, target))
    rel = _rel(ctx, target)
    if existed and _text_of(target) == content:
        # The same file again with the same content (a model re-creating what it already wrote): nothing to do.
        return ToolResult(True, f"{rel} already has exactly this content; nothing was written. Do not write it again: "
                                "continue with the next step.", {"path": rel})
    again = existed and rel in ctx.files_changed
    if msg := await gate(ctx, op, policy.decide_file_write(target, ctx.root, ctx.mode), preview):
        return ToolResult(False, msg)
    # This write's own line changes (like an edit's), so the review card can add up every operation of the task.
    try:
        change = await asyncio.to_thread(change_preview, "overwrite" if existed else "new",
                                         _text_of(target) if existed else None, content, rel)
    except Exception:
        change = {}
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8", newline="")
    ctx.files_changed.append(rel)
    note = (" Note: this file was already written earlier in this task - for further changes use edit_file with the "
            "changed part only; never recreate a finished file.") if again else ""
    if js := await js_check(target):
        note += "\n" + js
    return ToolResult(True, f"{'updated' if existed else 'created'} {rel} ({len(content)} chars).{note}",
                      {"path": rel, "language": target.suffix.lstrip("."), "created": not existed,
                       **({"diff": change["diff"], "added": change["added"], "removed": change["removed"]}
                          if change.get("diff") is not None and "added" in change else {})})


@tool("edit_file", '<tool name="edit_file" path="REL/PATH">\n<<<<<<< SEARCH\nexact lines from the file\n=======\nnew lines\n'
      '>>>>>>> REPLACE\n</tool>',
      "Change part of an existing file: replace an exact snippet (copied from the file, a few lines that occur once) "
      "with new text. Much faster than rewriting the whole file; several SEARCH/REPLACE blocks may follow each other. "
      "Use write_file only for new files or complete rewrites.",
      {"path": S("File path relative to the working directory"),
       "old": S("Exact text to replace, copied from the file (a few lines that occur once)"),
       "new": S("Replacement text (empty to delete the snippet)"),
       "replace_all": {"type": "boolean", "description": "Replace every occurrence instead of exactly one"},
       "edits": S("Alternative: one or more <<<<<<< SEARCH / ======= / >>>>>>> REPLACE blocks")},
      main="edits", required=("path",))
async def edit_file(ctx, args, body):
    from .editing import EditError, apply_edit, diff, parse_blocks
    target = _path(ctx, args["path"])
    if not target.is_file():
        return ToolResult(False, f"not found: {args['path']}. Use write_file to create a new file.")
    pairs = [(args["old"], args.get("new", ""))] if args.get("old") else parse_blocks(body)
    if not pairs:
        return ToolResult(False, "No edit given: pass old/new, or SEARCH/REPLACE blocks in the body.")
    before = target.read_bytes().decode("utf-8", errors="replace")  # bytes: keep the file's own line endings
    crlf = "\r\n" in before
    text = before.replace("\r\n", "\n")
    replace_all = str(args.get("replace_all", "")).lower() in ("true", "1", "yes")
    done = 0
    for i, (old, new) in enumerate(pairs, 1):
        try:
            text, n = apply_edit(text, old.replace("\r\n", "\n"), new.replace("\r\n", "\n"), replace_all)
        except EditError as e:
            prefix = f"Edit {i} of {len(pairs)} failed (nothing was saved): " if len(pairs) > 1 else ""
            return ToolResult(False, prefix + str(e))
        done += n
    after = text.replace("\n", "\r\n") if crlf else text
    if after == before:
        return ToolResult(True, f"{args['path']}: no change (the new text equals the old one)", {"path": args["path"]})
    op = {"tool": "edit_file", "path": str(target), "sha": hashlib.sha256(after.encode()).hexdigest()[:16]}
    preview = lambda: change_preview("edit", before.replace("\r\n", "\n"), text, _rel(ctx, target))  # noqa: E731
    if msg := await gate(ctx, op, policy.decide_file_write(target, ctx.root, ctx.mode), preview):
        return ToolResult(False, msg)
    target.write_text(after, encoding="utf-8", newline="")
    rel = _rel(ctx, target)
    ctx.files_changed.append(rel)
    patch = diff(before.replace("\r\n", "\n"), text, rel)
    added = sum(1 for l in patch.splitlines() if l.startswith("+") and not l.startswith("+++"))
    removed = sum(1 for l in patch.splitlines() if l.startswith("-") and not l.startswith("---"))
    js = await js_check(target)
    return ToolResult(True, f"edited {rel}: {done} replacement(s), +{added} -{removed} lines" + (f"\n{js}" if js else ""),
                      {"path": rel, "language": target.suffix.lstrip("."), "diff": patch,
                       "added": added, "removed": removed})


@tool("search_code", '<tool name="search_code" path="." glob="*.js,*.css" regex="false">text to find</tool>',
      "Search the project's files for text or a regular expression; returns path:line: matching line. Use it to find "
      "where something is defined or used instead of reading files one by one.",
      {"query": S("Text or regular expression to find"), "path": S("Folder or file to search, default '.'"),
       "glob": S("Only files matching these patterns, comma separated (e.g. *.py,*.js)"),
       "regex": {"type": "boolean", "description": "Treat the query as a regular expression"},
       "case_sensitive": {"type": "boolean", "description": "Match upper/lower case exactly"}},
      main="query", required=("query",))
async def search_code(ctx, args, body):
    from .editing import EditError, search
    query = body.strip() or args.get("query", "")
    if not query:
        return ToolResult(False, "Empty query.")
    base = _path(ctx, args.get("path") or ".")
    if not base.exists():
        return ToolResult(False, f"not found: {args.get('path')}")
    flag = lambda k: str(args.get(k, "")).lower() in ("true", "1", "yes")  # noqa: E731
    try:
        lines, scanned, total = await asyncio.to_thread(
            search, ctx.root.resolve(), base, query, flag("regex"), args.get("glob", ""), flag("case_sensitive"))
    except EditError as e:
        return ToolResult(False, str(e))
    if not lines:
        return ToolResult(True, f"No matches for {query!r} in {scanned} files.", {"matches": 0})
    more = f"\n... {total - len(lines)} more matches (narrow the search with path or glob)" if total > len(lines) else ""
    return ToolResult(True, f"{total} matches in {scanned} files:\n" + "\n".join(lines) + more, {"matches": total})


@tool("read_file", '<tool name="read_file" path="REL/PATH" lines="40-120"></tool>',
      "Read a text file. For big files read only the lines you need (lines=\"start-end\", e.g. from search_code).",
      {"path": S("File path"), "lines": S("Optional line range, e.g. 40-120")}, required=("path",))
async def read_file(ctx, args, body):
    target = _path(ctx, args["path"])
    if not target.is_file():
        return ToolResult(False, f"not found: {args['path']}")
    from .docread import DOC_EXTS
    if target.suffix.lower() in DOC_EXTS - {".txt", ".md", ".json", ".xml", ".html", ".htm", ".log", ".csv", ".tsv"}:
        return await read_document(ctx, {"path": args["path"]}, "")  # PDF/Office/image: pages, OCR
    text = target.read_text(encoding="utf-8", errors="replace")
    # Inline images (data:...;base64) are megabytes of noise for a model: shown as a short placeholder.
    text = re.sub(r"(data:[\w/+.-]+;base64,)[A-Za-z0-9+/=\s]{300,}",
                  lambda m: f"{m.group(1)}[{len(m.group(0)) * 3 // 4096} KB image data omitted]", text)
    st = target.stat()
    key = str(target.resolve())
    if not args.get("lines") and ctx.read_seen.get(key) == (st.st_mtime_ns, st.st_size):
        # The same unchanged file again: its content is already in this conversation.
        return ToolResult(True, f"{args['path']} is unchanged since you read it earlier in this task ({len(text)} "
                                "characters); its content is above. Continue with the next step (read_file lines=a-b "
                                "only if you need one part again).", {"path": args["path"]})
    if not args.get("lines"):
        ctx.read_seen[key] = (st.st_mtime_ns, st.st_size)
    if m := re.fullmatch(r"\s*(\d+)\s*(?:-\s*(\d+))?\s*", args.get("lines") or ""):
        all_lines = text.split("\n")
        start = max(1, int(m.group(1)))
        end = min(len(all_lines), int(m.group(2) or start + 199))
        part = "\n".join(all_lines[start - 1:end])
        return ToolResult(True, f"[{args['path']} lines {start}-{end} of {len(all_lines)}]\n" + clip(part),
                          {"path": args["path"]})
    return ToolResult(True, clip(text), {"path": args["path"]})


@tool("read_document", '<tool name="read_document" path="docs/report.pdf" pages="3-7">optional question to find passages</tool>',
      "Read a document with page numbers: PDF (scanned pages are OCR'd), Word, Excel, PowerPoint, OpenDocument "
      "(odt/ods/odp), CSV, text, or an image (OCR). Every part is labelled (p. 3, slide 2, sheet rows, paragraphs) "
      "so answers can cite where each fact is. Long documents: give a question to get the best passages, or "
      "pages=\"a-b\". Web documents: use fetch_url with the document's URL.",
      {"path": S("Document path"), "pages": S("Optional page range, e.g. 3-7 (PDF pages)"),
       "query": S("Optional: what to look for; returns the best passages with their page numbers")},
      main="query", required=("path",))
async def read_document(ctx, args, body):
    from . import docread
    target = _path(ctx, args["path"])
    if not target.is_file():
        return ToolResult(False, f"not found: {args['path']}")
    pages = docread.parse_pages(args.get("pages"))
    try:
        doc = await asyncio.to_thread(docread.load, target, "tr" if ctx.lang == "tr" else "en", pages)
    except ValueError as e:
        return ToolResult(False, str(e))
    except Exception as e:  # a damaged or password-protected file
        return ToolResult(False, f"could not read {args['path']}: {type(e).__name__}: {str(e)[:200]}")
    text = docread.render(doc, (body.strip() or args.get("query") or "").strip())
    return ToolResult(True, clip(text, 16000), {"path": args["path"], "parts": len(doc.parts),
                                                "ocr": sum(p.ocr for p in doc.parts)})


@tool("list_dir", '<tool name="list_dir" path="."></tool>', "List a directory tree (ignores node_modules/.git).",
      {"path": S("Directory path, default '.'")})
async def list_dir(ctx, args, body):
    from ..workspace import summarize_tree
    return ToolResult(True, summarize_tree(_path(ctx, args.get("path", ".")), 300))


@tool("delete_file", '<tool name="delete_file" path="REL/PATH"></tool>', "Delete a file (always asks the user).",
      {"path": S("File path")}, required=("path",))
async def delete_file(ctx, args, body):
    target = _path(ctx, args["path"])
    op = {"tool": "delete_file", "path": str(target)}
    preview = lambda: change_preview("delete", _text_of(target), None, _rel(ctx, target)) if target.is_file() else None  # noqa: E731
    if ".session" in target.parts:
        return ToolResult(False, "The chat's .session folder is the app's own record; it cannot be deleted.")
    try:  # a file this task itself made (a failed output, a temp file) in the working folder: its own to remove
        own = target.is_file() and target.stat().st_mtime >= ctx.started - 1 and target.resolve().is_relative_to(ctx.root.resolve())
    except OSError:
        own = False
    # 'full' (Tam erişim): never asked; 'auto': only files this task made; 'ask': always asked.
    decision = policy.Decision("allow", "write") if ctx.mode == "full" or (own and ctx.mode == "auto") else \
        policy.Decision("ask", "dangerous", ["file deletion"])
    if msg := await gate(ctx, op, decision, preview):
        return ToolResult(False, msg)
    if target.is_file():
        target.unlink()
        ctx.files_changed.append(args["path"])
        return ToolResult(True, f"deleted {args['path']}")
    return ToolResult(False, "not a file")


DEFAULT_SHELL = "powershell" if sys.platform == "win32" else "bash"
POWERSHELLS = ("powershell", "powershell5", "pwsh")
# Python scripts run with the app's own interpreter (its packages: Pillow, python-docx, openpyxl, reportlab...).
PYTHON = sys.executable or "python"
SCRIPT_SHELLS = {"powershell": ".ps1", "powershell5": ".ps1", "pwsh": ".ps1", "python": ".py", "node": ".js", "php": ".php",
                 "bash": ".sh"}

# A bash heredoc (cat > f <<'EOF' ... EOF, python - <<EOF ...) is bash syntax: PowerShell and cmd fail on it.
HEREDOC = re.compile(r"<<-?[ \t]*(['\"]?)([A-Za-z_][\w-]*)\1[^\n]*\n(?:.*\n)*?[ \t]*\2[ \t]*(?:\n|$)")
# PowerShell here-strings must close at the start of a line ('@ / "@); models often indent the closing mark.
HERE_CLOSE = re.compile(r"(?m)^[ \t]+(['\"]@)")


def route_heredoc(shell: str, command: str) -> tuple[str, str]:
    """A bash heredoc sent to PowerShell/cmd runs in bash (Git Bash on Windows), where it means what the model wrote.
    Without bash, a simple 'cat > file <<EOF' becomes a PowerShell file write and other heredocs are piped as input."""
    if shell not in POWERSHELLS + ("cmd",) or not HEREDOC.search(command):
        return shell, command
    from ..hostinfo import git_bash
    if git_bash():
        return "bash", command
    lines, out, i = command.split("\n"), [], 0
    while i < len(lines):
        m = re.search(r"^(.*?)<<-?[ \t]*(['\"]?)([A-Za-z_][\w-]*)\2(.*)$", lines[i])
        end = next((k for k in range(i + 1, len(lines)) if lines[k].strip() == (m.group(3) if m else None)), None)
        if not m or end is None:
            out.append(lines[i])
            i += 1
            continue
        body = "\n".join(lines[i + 1:end]) + "\n"
        head, tail = m.group(1).strip(), m.group(4).strip()
        literal = "@'\n" + body.replace("\n'@", "\n '@") + "'@"
        redirect = re.search(r"(>>?)\s*(\S+)", head + " " + tail)
        if head in ("cat", "tee") or (head.startswith(("cat", "tee")) and redirect):
            path = redirect.group(2) if redirect else ""
            verb = "Add-Content" if redirect and redirect.group(1) == ">>" else "Set-Content"
            out.append(f"{verb} -LiteralPath '{path}' -Encoding utf8 -Value {literal}" if path else f"Write-Output {literal}")
        else:
            out.append(f"{literal} | {head} {tail}".strip())
        i = end + 1
    return "powershell" if shell == "cmd" else shell, "\n".join(out)


def _powershell(shell: str) -> tuple[str, bool]:
    """(executable, is PowerShell 7+): powershell = pwsh when installed, powershell5 = Windows PowerShell 5.1."""
    pwsh = shutil.which("pwsh")
    if shell == "pwsh" or (shell == "powershell" and pwsh):
        if pwsh:
            return pwsh, True
    return shutil.which("powershell") or "powershell", False


# Windows PowerShell 5.1 (the built-in one) has no && / || and its aliases reject the Unix/cmd habits models write
# (rm -rf, del /s /q, rmdir /s /q, mkdir -p a b, ls -la, touch). The shims below step in ONLY for such arguments;
# native use (Remove-Item -Recurse, ls -Filter *.txt, dir | Where-Object ...) goes to the real cmdlet unchanged.
# One deliberate exception: mkdir of a folder that already exists succeeds (like mkdir -p), so chains such as
# 'mkdir app && cd app && ...' work the second time too.
PS_SHIM = r"""$ErrorActionPreference = 'Continue'
foreach ($__a in 'rm','rmdir','rd','del','erase','mkdir','md','ls','dir','touch') { Remove-Item "Alias:$__a" -Force -ErrorAction SilentlyContinue }
$global:__aiiq_failed = $false; $global:__aiiq_err = $false
function global:__aiiq_isflag($x) { "$x" -cmatch '^(--?[A-Za-z][A-Za-z0-9-]*|/[a-zA-Z])$' }
# Native use: every flag is a real parameter of the cmdlet, and either a flag is given or there is at most one path.
function global:__aiiq_native($a, $known) { $n = 0; foreach ($x in $a) { if (__aiiq_isflag $x) { if ("$x" -notmatch $known) { return $false }; $n++ } }; return ($n -gt 0 -or @(__aiiq_paths $a).Count -le 1) }
function global:__aiiq_paths($a) { @($a | Where-Object { -not (__aiiq_isflag $_) }) }
function global:__aiiq_rm($a) { $f = @($a | Where-Object { __aiiq_isflag $_ }) -join ' '; $quiet = $f -match '(^|\s)(-\w*f\w*|--force|/[qQ])'; foreach ($x in (__aiiq_paths $a)) { if (Test-Path -Path $x) { Remove-Item -Path $x -Recurse -Force } elseif (-not $quiet) { Write-Error "rm: not found: $x"; $global:__aiiq_err = $true } } }
$global:__aiiq_rmnative = '^-(Path|LiteralPath|Filter|Include|Exclude|Recurse|Force|Confirm|WhatIf|ErrorAction|Stream|Credential|r|R|f)$'
function rm { if (__aiiq_native $args $__aiiq_rmnative) { Microsoft.PowerShell.Management\Remove-Item @args; if (-not $?) { $global:__aiiq_err = $true } } else { __aiiq_rm $args } }
function rmdir { rm @args }
function rd { rm @args }
function del { rm @args }
function erase { rm @args }
function mkdir { $p = @(__aiiq_paths $args); if (-not ($args | Where-Object { __aiiq_isflag $_ }) -and $p.Count -eq 1 -and (Test-Path -LiteralPath $p[0] -PathType Container)) { return }; if (__aiiq_native $args '^-(Path|Name|Force|Value|Confirm|WhatIf|ErrorAction)$') { New-Item -ItemType Directory @args; if (-not $?) { $global:__aiiq_err = $true } } else { foreach ($x in $p) { New-Item -ItemType Directory -Force -Path $x | Out-Null } } }
function md { mkdir @args }
function touch { foreach ($x in (__aiiq_paths $args)) { if (Test-Path -LiteralPath $x) { (Get-Item -LiteralPath $x).LastWriteTime = Get-Date } else { New-Item -ItemType File -Path $x -Force | Out-Null } } }
function ls { if (__aiiq_native $args '^-(Path|LiteralPath|Filter|Include|Exclude|Recurse|Depth|Force|Name|File|Directory|Hidden|ReadOnly|System|Attributes|ErrorAction)$') { Microsoft.PowerShell.Management\Get-ChildItem @args; if (-not $?) { $global:__aiiq_err = $true } } else { $f = @($args | Where-Object { __aiiq_isflag $_ }) -join ' '; $p = __aiiq_paths $args; $a = @{}; if ($f -match '(^|\s)(-\w*a\w*|/a)') { $a.Force = $true }; if ($f -cmatch '(^|\s)(-\w*R\w*|/s)') { $a.Recurse = $true }; if ($p.Count) { Microsoft.PowerShell.Management\Get-ChildItem -Path $p @a } else { Microsoft.PowerShell.Management\Get-ChildItem @a } } }
function dir { ls @args }
"""
# The script's exit code: Windows PowerShell exits 0 even when the last native command failed.
PS_TRAILER = r"""
$__ok = $?
if ($global:__aiiq_failed -or $global:__aiiq_err -or -not $__ok) { if ($LASTEXITCODE) { exit $LASTEXITCODE } else { exit 1 } }
"""


def _split_chain(line: str) -> list[str] | None:
    """Split a line at top-level && / || (outside quotes): [cmd, op, cmd, op, cmd...] or None."""
    parts, buf, quote, i = [], "", "", 0
    while i < len(line):
        ch = line[i]
        if quote:
            quote = "" if ch == quote else quote
        elif ch in "'\"":
            quote = ch
        elif line[i:i + 2] in ("&&", "||"):
            parts += [buf.strip(), line[i:i + 2]]
            buf, i = "", i + 2
            continue
        buf += ch
        i += 1
    if len(parts) < 2 or not buf.strip() or any(not x for x in parts[::2]):
        return None
    return parts + [buf.strip()]


def ps_chain(line: str) -> str:
    """'a && b || c' -> PowerShell 5.1 statements with the shell's left-to-right short-circuit meaning."""
    parts = _split_chain(line)
    if not parts:
        return line
    ok = "$__s = $? -and -not $global:__aiiq_err"  # the shims above report their own failures
    out = f"{parts[0]}; {ok}"
    for op, seg in zip(parts[1::2], parts[2::2]):
        out += f"; if ({'' if op == '&&' else '-not '}$__s) {{ $global:__aiiq_err = $false; {seg}; {ok} }}"
    return out + "; $global:__aiiq_failed = -not $__s"


def ps_script(command: str, pwsh: bool) -> str:
    """Script text for PowerShell: compatibility shims, && / || chains (5.1 only) and a real exit code."""
    if not pwsh and "@'" not in command and '@"' not in command:  # here-strings stay as written
        command = "\n".join(ps_chain(l) if ("&&" in l or "||" in l) and not l.rstrip().endswith("`") else l
                            for l in command.split("\n"))
    return PS_SHIM + command + PS_TRAILER


# One command line for a program (not source code of the language): "python --version", "node -v", "pip install x".
CLI_LINE = re.compile(r"\s*(python3?|py|pip3?|node|npm|npx|php|composer|git|winget|choco|scoop|dotnet|java|go|cargo|"
                      r"deno|bun|yarn|pnpm|where|which)(\.exe)?(\s+-{1,2}[\w-]+|\s+[\w./:\\-]+)*\s*$", re.I)
CD_ONLY = re.compile(r"\s*(?:cd|chdir|Set-Location|sl|pushd)(?:\s+/d)?\s+(?:-Path\s+)?(['\"]?)([^'\";&|<>]+?)\1\s*;?\s*")


PY_START = re.compile(r"(?:import [A-Za-z_][\w.]*(?:\s*,\s*[\w.]+)*(?: as \w+)?|from [A-Za-z_.][\w.]* import .+"
                      r"|def \w+\(.*\):|class \w+.*:|async def \w+\(.*\):)\s*$")
PS_HINT = re.compile(r"(?m)^\s*(?:\$\w+\s*=|[A-Z][a-z]+-[A-Z]\w+\b|param\s*\()")


FFMPEG_NO_Y = re.compile(r"(?m)(?:^|(?<=[;&|(]))\s*(?:&\s*)?[\"']?(?:[\w:\\/. -]*[\\/])?ffmpeg(?:\.exe)?[\"']?(?=\s)(?![^\n;&|]*\s-[yn]\b)")


def looks_python(command: str) -> bool:
    """Multi-line Python source (it starts with an import/def/class line and has no PowerShell syntax)."""
    lines = [ln for ln in command.strip().splitlines() if ln.strip() and not ln.lstrip().startswith("#")]
    return len(lines) > 1 and bool(PY_START.match(lines[0].strip())) and not PS_HINT.search(command)         and "<<" not in command


def build_argv(ctx: ToolContext, shell: str, command: str) -> list[str]:
    """Turn a shell + command into an argv vector. Script shells use an explicit script file."""
    shell = (shell or DEFAULT_SHELL).lower()
    if shell != "python" and "ffmpeg" in command:
        # ffmpeg asks "File exists. Overwrite? [y/N]" and, with no input, gives up: models then delete files or
        # report a video that was never made. -y overwrites (a command that says -n keeps its choice).
        command = FFMPEG_NO_Y.sub(lambda m: m.group(0) + " -y", command)
    if shell == "python" and "\n" not in command.strip():
        # Models often send a shell line to the python "shell" ("python app.py", "app.py arg", "pip install x"),
        # which would run as Python source and fail: run it as the command it is.
        line = command.strip()
        if m := re.fullmatch(r"(?:(?:python3?|py)(?:\.exe)?\s+)?([\w./\\:-]+\.py)((?:\s+.*)?)", line, re.I):
            return [PYTHON, m.group(1), *shlex.split(m.group(2) or "", posix=sys.platform != "win32")]
        if m := re.fullmatch(r"(?:python3?|py)(?:\.exe)?\s+(-m\s+.+|-c\s+.+)", line, re.I):
            return [PYTHON, *shlex.split(m.group(1))]  # posix: quotes around -c code are removed
        if m := re.fullmatch(r"pip3?\s+(.+)", line, re.I):
            return [PYTHON, "-m", "pip", *shlex.split(m.group(1), posix=sys.platform != "win32")]
    if shell in POWERSHELLS + ("cmd", "bash") and looks_python(command):
        shell = "python"  # Python source sent without shell="python" (it failed as PowerShell before)
    if sys.platform != "win32" and shell in POWERSHELLS + ("cmd",) and not shutil.which("pwsh"):
        shell = "bash"  # Linux/macOS without PowerShell: run the command in bash
    shell, command = route_heredoc(shell, command)
    if shell in POWERSHELLS:
        command = HERE_CLOSE.sub(r"\1", command)
    if shell == "bash":
        from ..hostinfo import git_bash
        bash = git_bash() or "bash"
        if "\n" not in command.strip():
            return [bash, "-c", command]  # no login shell: profile scripts make every command slower
    if shell in SCRIPT_SHELLS:
        scripts = (ctx.session_dir or ctx.root / ".aiiq") / "scripts"
        scripts.mkdir(parents=True, exist_ok=True)
        f = scripts / f"{hashlib.sha256(f'{shell}:{command}'.encode()).hexdigest()[:12]}{SCRIPT_SHELLS[shell]}"
        if shell in POWERSHELLS:
            exe, seven = _powershell(shell)
            f.write_text(ps_script(command, seven), encoding="utf-8-sig")
            return [exe, "-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(f)]
        f.write_text(command if shell != "bash" else command.replace("\r\n", "\n"), encoding="utf-8", newline="\n")
        if shell == "bash":
            return [bash, str(f)]
        return [PYTHON if shell == "python" else shell, str(f)]
    if shell == "cmd":
        return ["cmd", "/d", "/s", "/c", command]
    argv = shlex.split(command, posix=sys.platform != "win32")  # "exec": direct argv
    if argv and argv[0].lower() in ("python", "python3", "py"):
        argv[0] = PYTHON
    elif argv and argv[0].lower() in ("pip", "pip3"):
        argv[:1] = [PYTHON, "-m", "pip"]
    return argv


async def _spawn(ctx: ToolContext, args: dict, body: str, background: bool):
    command = body.strip()
    shell = args.get("shell") or DEFAULT_SHELL
    direct = args.get("argv")
    if isinstance(direct, str) and direct.strip().startswith("["):
        try:
            direct = json.loads(direct)
        except ValueError:
            direct = None
    if isinstance(direct, list) and direct and all(isinstance(x, (str, int, float)) for x in direct):
        # A program with its arguments, started directly: no shell parsing, no quoting problems, fastest start.
        direct = [str(x) for x in direct]
        shell, command = "exec", " ".join(shlex.quote(x) if " " in x else x for x in direct)
    if not command:
        return None, ToolResult(False, "Give the command (or argv=[program, args...]).")
    if shell in ("python", "node", "php") and CLI_LINE.match(command) and "\n" not in command.strip():
        # A command line ("python --version", "pip install x") sent with shell=python would run as Python source
        # (NameError): it belongs to the system shell.
        shell = DEFAULT_SHELL
    cwd = _path(ctx, args.get("cwd") or ctx.shell_cwd or ".")
    if shell in ("powershell", "cmd", "bash") and (m := CD_ONLY.fullmatch(command)):
        # Each command runs in its own process, so a lone "cd" would change nothing: remember it instead,
        # like a terminal does, and run the following commands there.
        target = _path(ctx, str(cwd / m.group(2).strip()))
        if not target.is_dir():
            return None, ToolResult(False, f"cd: no such folder: {m.group(2).strip()}")
        ctx.shell_cwd = str(target)
        return None, ToolResult(True, f"working folder for the next commands: {_rel(ctx, target)}")
    op = {"tool": "start" if background else "run", "shell": shell, "cwd": str(cwd), "command": command}
    if msg := await gate(ctx, op, policy.decide_command(command, ctx.mode)):
        return None, ToolResult(False, msg)
    env = policy.minimal_env()  # the PATH as it is now (a program installed a moment ago is found)
    if isinstance(direct, list) and direct and shell == "exec":
        argv = list(direct)
        exe = shutil.which(argv[0], path=env.get("PATH"))
        if argv[0].lower() in ("python", "python3", "py"):
            argv[0] = PYTHON
        elif exe:
            argv[0] = exe  # resolves npm -> npm.cmd on Windows
    else:
        argv = build_argv(ctx, shell, command)
    ctx.commands.append(command)
    timeout = None if background else float(args.get("timeout") or load_settings()["agent"]["command_timeout"])
    info = await manager.start(argv, str(cwd), env, owner=ctx.owner or ctx.run_id, timeout=timeout,
                               background=background)
    if background:
        ctx.step("process", {"process_id": info.id, "command": command, "shell": shell})
    return info, None


@tool("run", '<tool name="run" shell="powershell|powershell5|pwsh|cmd|bash|python|node|php|exec" cwd="." timeout="300">command or script</tool>',
      "Run a command or a whole script and wait for it; returns the exit code and the output tail. Builds, tests, "
      "installs, git, CLI scaffolding. Multi-line scripts: send the source with shell=python/node/powershell/bash (it "
      "runs as a script file, no quoting or heredoc needed). argv=[\"git\", \"log\", \"-1\"] starts a program directly "
      "without a shell (fastest, exact arguments). Heredocs (<<EOF) only with shell=bash; file contents go through "
      "write_file. Use the shell syntax of the versions listed under 'This computer'.",
      {"command": S("Command line or script source"), "shell": S("Interpreter", enum=SHELLS),
       "argv": {"type": "array", "items": {"type": "string"}, "description": "Program and arguments, run without a shell"},
       "cwd": S("Working directory, default '.'"), "timeout": {"type": "integer", "description": "Seconds"}},
      main="command", required=())
async def run(ctx, args, body):
    if SERVER_CMD.search(body or "") or SERVER_CMD.search(" ".join(map(str, args.get("argv") or []))):
        # A server never "finishes": with run the task would wait for the command timeout (minutes). It is started
        # in the background instead and returns once it is up (it is stopped later with stop, or automatically).
        res = await start(ctx, args, body)
        return ToolResult(res.ok, "[This is a server, so it was started in the background with start.]\n" + res.output,
                          res.data)
    t0 = time.time()
    info, denied = await _spawn(ctx, args, body, background=False)
    if denied:
        return denied
    waiter = asyncio.create_task(info.done.wait())
    canceller = asyncio.create_task(ctx.cancel.wait())
    try:
        await asyncio.wait({waiter, canceller}, return_when=asyncio.FIRST_COMPLETED)
    except asyncio.CancelledError:  # the task was stopped while the command ran: never leave it running
        await asyncio.shield(manager.stop(info.id))
        raise
    finally:
        canceller.cancel()
    if ctx.cancel.is_set():
        await manager.stop(info.id)
    out = "\n".join(info.tail)
    # Files the command wrote are checked by type (a 1 KB "video", an empty PDF, a .docx that is no zip...):
    # exit code 0 alone does not mean the output is real.
    from .verify import check_outputs
    broken = "" if ctx.cancel.is_set() else await check_outputs(ctx.root, t0)
    return ToolResult(info.state == "exited" and not broken,
                      f"exit_code={info.exit_code} state={info.state}\n{clip(out)}{broken}",
                      {"process_id": info.id, "exit_code": info.exit_code})


# Commands that start a server or a watcher (they run until stopped).
SERVER_CMD = re.compile(
    r"http\.server|\bphp\s+(-\w+\s+)*-S\s|\bnpm\s+(run\s+)?(dev|start|serve|watch)\b|\b(yarn|pnpm|bun)\s+(run\s+)?(dev|start|serve)\b|"
    r"\bnpx\s+(--yes\s+)?(serve|http-server|vite|live-server|nodemon)\b|\bvite(\s|$)|\bnext\s+(dev|start)\b|"
    r"\buvicorn\b|\bflask\s+run\b|manage\.py\s+runserver|\brails\s+s(erver)?\b|\bhugo\s+server|\bjekyll\s+serve|"
    r"\bnodemon\b|\bhttp-server\b|\blive-server\b|webpack\s+serve|ng\s+serve|\bdotnet\s+(run|watch)\b.*--urls", re.I)
# A dev server says it is up ("Local: http://localhost:5173", "listening on 3000", "ready in 412 ms").
READY = re.compile(r"https?://(localhost|127\.0\.0\.1|0\.0\.0\.0|\[::\]?1?\]?)(:\d+)?|listening|ready in|ready on|"
                   r"started (server|on)|server (is )?running|compiled successfully|webpack compiled|"
                   r"application startup complete|press ctrl\+c|serving (http|on)", re.I)


async def wait_ready(info, limit: float = 15.0) -> str:
    """Return as soon as a background process shows it is up (a ready line), exits, or goes quiet after printing
    something; never longer than limit. Returns why it returned."""
    t0 = time.monotonic()
    while True:
        if info.done.is_set():
            return "exited"
        tail = list(info.tail)[-40:]
        if any(READY.search(line) for line in tail):
            await asyncio.sleep(0.15)  # the rest of the banner
            return "ready"
        quiet = time.monotonic() - (info.last_output or info.started_mono)
        elapsed = time.monotonic() - t0
        if info.last_output and quiet > 1.2 and elapsed > 1.5:
            return "quiet"
        if not info.last_output and elapsed > 4:
            return "no output yet"
        if elapsed > limit:
            return "still starting"
        await asyncio.sleep(0.1)


@tool("start", '<tool name="start" shell="powershell" cwd=".">npm run dev</tool>',
      "Start a long-running background process (dev servers, watchers). Returns as soon as it reports it is ready "
      "(or exits), with its process id and first output; it keeps running after this call.",
      {"command": S("Command line"), "shell": S("Interpreter", enum=SHELLS), "cwd": S("Working directory"),
       "argv": {"type": "array", "items": {"type": "string"}, "description": "Program and arguments, run without a shell"}},
      main="command", required=())
async def start(ctx, args, body):
    info, denied = await _spawn(ctx, args, body, background=True)
    if denied:
        return denied
    why = await wait_ready(info)
    note = ("\nStop it with stop id=" + info.id + " when your check is done; if left running it is stopped "
            "automatically a few minutes after this task.") if info.state == "running" else ""
    return ToolResult(info.state in ("running", "exited"),
                      f"process_id={info.id} state={info.state} ({why})\n{clip(chr(10).join(info.tail), 3000)}{note}",
                      {"process_id": info.id, "ready": why})


@tool("stop", '<tool name="stop" id="PROCESS_ID"></tool>', "Stop a background process and its children.",
      {"id": S("Process id returned by start")}, required=("id",))
async def stop(ctx, args, body):
    return ToolResult(await manager.stop(args["id"]), f"stop {args['id']}")


async def _network_gate(ctx: ToolContext, op: dict) -> str | None:
    return await gate(ctx, op, policy.Decision("ask" if ctx.mode == "ask" else "allow", "network"))


@tool("web_search", '<tool name="web_search">query</tool>',
      "Search the web (several engines merged). Returns titles, URLs and snippets. Use research for reading sources.",
      {"query": S("Search query")}, main="query", required=("query",))
async def web_search(ctx, args, body):
    from . import web
    q = body.strip()
    if msg := await _network_gate(ctx, {"tool": "web_search", "query": q}):
        return ToolResult(False, msg)
    results, engines = await web.search(q)
    text = "\n".join(f"- {x['title']} <{x['url']}>\n  {x['snippet']}" for x in results)
    return ToolResult(bool(results), text or "no results (all engines failed or returned nothing)",
                      {"results": results, "engines": engines})


@tool("fetch_url", '<tool name="fetch_url" url="https://..." query="optional: what to look for"></tool>',
      "Read a web page as plain text (real-browser fallback for JS pages; an archived copy when the page cannot be read). "
      "Also reads online documents with page numbers: PDF (scanned pages OCR'd), Word, Excel, PowerPoint, OpenDocument, "
      "CSV. For a long document give query to get the matching passages. If the result says BLOCKED, do not retry it.",
      {"url": S("https:// URL"), "query": S("Optional: what to look for in a long document")}, required=("url",))
async def fetch_url(ctx, args, body):
    from . import web
    url = args.get("url") or body.strip()
    if msg := await _network_gate(ctx, {"tool": "fetch_url", "url": url}):
        return ToolResult(False, msg)
    r = await web.fetch(url, 8000, str(args.get("query") or "") if args.get("url") else "")
    if not r.get("ok"):
        return ToolResult(False, r.get("error", "failed"), {"blocked": r.get("blocked", False)})
    return ToolResult(True, f"# {r.get('title') or url}\n(source: {url}, via {r['via']})\n\n{r['text']}")


@tool("research", '<tool name="research">question or topic</tool>',
      "Web research: searches several engines and reads the best sources in parallel. Returns excerpts with URLs. "
      "Prefer this for factual or current questions; cite the URLs in your answer.",
      {"query": S("What to research")}, main="query", required=("query",))
async def research(ctx, args, body):
    from . import web
    q = body.strip()
    if msg := await _network_gate(ctx, {"tool": "research", "query": q}):
        return ToolResult(False, msg)
    r = await web.research(q)
    parts = [f"Engines: {', '.join(r['engines']) or 'none'}"]
    parts += [f"## {p['title']}\nURL: {p['url']}\n{p['excerpt']}" for p in r["pages"]]
    if r["blocked"]:
        parts.append("Blocked by site protection (not readable): " + ", ".join(r["blocked"]))
    if len(r["pages"]) < 2 and r["results"]:  # few readable sources: the other results' snippets help too
        read = {p["url"] for p in r["pages"]}
        parts.append(("No source could be read. " if not r["pages"] else "") + "Search snippets:\n" +
                     "\n".join(f"- {x['title']} <{x['url']}>: {x['snippet']}" for x in r["results"] if x["url"] not in read))
    return ToolResult(bool(r["pages"] or r["results"]), clip("\n\n".join(parts), 14000),
                      {"sources": [p["url"] for p in r["pages"]]})


@tool("my_location", '<tool name="my_location"></tool>',
      "The user's current location (this device's Wi-Fi/GPS through the app, else approximate from the internet "
      "address) with its street address and accuracy. Use it when the user says near me / here / around me / "
      "yakınımda / buralarda, then search places around it (places near=\"me\" does this by itself).",
      {"fresh": {"type": "boolean", "description": "Ask again instead of the location of the last minutes"}})
async def my_location(ctx, args, body):
    from .. import location
    if msg := await _network_gate(ctx, {"tool": "my_location"}):
        return ToolResult(False, msg)
    loc = await location.current("tr" if ctx.lang == "tr" else "en", str(args.get("fresh", "")).lower() in ("true", "1"))
    return ToolResult("error" not in loc, location.describe(loc), {k: loc.get(k) for k in ("lat", "lon", "accuracy_m", "source")})


@tool("system_info", '<tool name="system_info"></tool>',
      "This computer's hardware and OS in one call: CPU, cores, RAM modules, GPU and VRAM, motherboard, BIOS, disks "
      "and free space, network adapters, monitors, OS version. Use it for any 'my PC specs / donanım / sistem "
      "özellikleri' request instead of systeminfo/wmic/findstr commands (those break on non-English systems).", {})
async def system_info(ctx, args, body):
    from . import sysinfo
    try:
        text = await asyncio.to_thread(sysinfo.report)
    except Exception as e:  # noqa: BLE001 - a missing source must not break the task
        return ToolResult(False, f"system_info failed: {e}")
    return ToolResult(True, text)


@tool("places", '<tool name="places" near="Kadıköy, İstanbul" radius="1500" map="true">kahve dükkanı</tool>',
      "Find places on a map (venues, shops, restaurants, hotels, pharmacies, competitors...) near a district, address "
      "or 'lat,lon': name, category, address, distance, phone, website, opening hours, and rating/review count when "
      "Google or Yandex Places is set up (else OpenStreetMap, free). map=true also writes an interactive map page "
      "(maps/<name>.html) the user can open. For comparing places or market research call it per place/area, then "
      "use research for reviews and details.",
      {"query": S("What to find (a kind of place or a name)"), "near": S("District, address, city or 'lat,lon'"),
       "radius": {"type": "integer", "description": "Search radius in metres (100-30000, default 1500)"},
       "limit": {"type": "integer", "description": "Max results (default 10)"},
       "map": {"type": "boolean", "description": "Also write an interactive map page"},
       "provider": S("Optional: google, yandex or osm", enum=["google", "yandex", "osm"])},
      main="query", required=("query",))
async def places(ctx, args, body):
    from . import maps
    q = (body.strip() or args.get("query", "")).strip()
    if not q:
        return ToolResult(False, "Say what to find (query) and where (near).")
    near = str(args.get("near") or "")
    if msg := await _network_gate(ctx, {"tool": "places", "query": q, "near": near}):
        return ToolResult(False, msg)
    from .. import location
    here = None
    if location.means_here(near):  # "near me": the user's real location (device, else approximate)
        here = await location.current("tr" if ctx.lang == "tr" else "en")
        if "error" in here:
            return ToolResult(False, location.describe(here))
        near = f"{here['lat']:.6f},{here['lon']:.6f}"
    try:
        res = await maps.find_places(q, near, int(args.get("radius") or 1500), int(args.get("limit") or 10),
                                     "tr" if ctx.lang == "tr" else "en", str(args.get("provider") or ""))
        if here and res.get("center"):
            res["center"].update(name=here.get("address") or res["center"]["name"], you=True,
                                 accuracy_m=here.get("accuracy_m"), source=here.get("source"))
    except Exception as e:  # network or provider failure: say it, the model can still use research
        return ToolResult(False, f"Map search failed: {type(e).__name__}: {str(e)[:300]}")
    text = (location.describe(here) + "\n" if here else "") + maps.format_places(res, ctx.lang)
    data = {"provider": res["provider"], "count": len(res["results"])}
    if str(args.get("map", "")).lower() in ("true", "1", "yes") and res["results"]:
        slug = re.sub(r"[^\w-]+", "-", f"{q}-{'here' if here else near}".lower(), flags=re.U).strip("-")[:60] or "map"
        target = _path(ctx, f"maps/{slug}.html")
        if msg := await gate(ctx, {"tool": "write_file", "path": str(target)}, policy.decide_file_write(target, ctx.root, ctx.mode)):
            return ToolResult(True, text + f"\n\n(Map page not written: {msg})", data)
        maps.write_map(target, f"{q} · {near}".strip(" ·"), res, ctx.lang)
        rel = _rel(ctx, target)
        ctx.files_changed.append(rel)
        text += f"\n\nInteractive map written: {rel} (the user can open it)."
        data["path"] = rel
    return ToolResult(bool(res["results"]), clip(text, 9000), data)


@tool("browser_check", '<tool name="browser_check" url="http://localhost:5173">what to verify</tool>',
      "Visual Tester: open the page headless (Playwright), screenshot it, and have the vision model review it.",
      {"url": S("Page URL"), "criteria": S("What to verify")}, main="criteria", required=("url",))
async def browser_check(ctx, args, body):
    from .visual import capture_and_review
    shot, review, console = await capture_and_review(args["url"], body.strip(), ctx.session_dir or ctx.root)
    return ToolResult(True, f"screenshot: {shot}\nconsole errors: {console or 'none'}\nvisual review:\n{review}",
                      {"screenshot": shot})


@tool("web_screenshot", '<tool name="web_screenshot" url="https://example.com" device="desktop|laptop|tablet|mobile" full_page="true"></tool>',
      "Take a screenshot of a web page (or an .html file in the working folder) with a real browser; the image shows "
      "in the chat. Options: device, width/height, full_page (default true), selector (one element), dark, "
      "wait_ms, hide (CSS selectors to hide, e.g. cookie banners), path (.png, .jpg or .pdf).",
      {"url": S("https:// URL or a .html path in the working folder"),
       "device": S("Viewport preset", enum=["desktop", "laptop", "tablet", "mobile"]),
       "width": S("Viewport width in px (optional)"), "height": S("Viewport height in px (optional)"),
       "full_page": S("true: whole page, false: first screen", enum=["true", "false"]),
       "selector": S("CSS selector of one element to capture (optional)"),
       "dark": S("true: prefers-color-scheme dark", enum=["true", "false"]),
       "wait_ms": S("Extra wait before capture, ms (optional)"),
       "hide": S("CSS selectors to hide before capture (optional)"),
       "path": S("Output path, default screenshots/<site>-<time>.png")}, main="url", required=("url",))
async def web_screenshot(ctx, args, body):
    from . import shot
    url = (args.get("url") or body).strip()
    if url.lower().startswith("file:"):  # file:///C:/... of a page in the working folder: check it as a path
        from urllib.parse import urlsplit
        from urllib.request import url2pathname
        url = url2pathname(urlsplit(url).path)
    if not re.match(r"https?://", url):
        local = _path(ctx, url)
        if not local.is_file():
            return ToolResult(False, f"Not a http(s) URL or a file in the working folder: {url}")
        url = local.resolve().as_uri()
    elif msg := await _network_gate(ctx, {"tool": "web_screenshot", "url": url}):
        return ToolResult(False, msg)
    rel = (args.get("path") or "").strip() or shot.default_name(url, "png")
    if Path(rel).suffix.lower() not in (".png", ".jpg", ".jpeg", ".pdf"):
        rel += ".png"
    target = _path(ctx, rel)
    if msg := await gate(ctx, {"tool": "web_screenshot", "path": str(target)}, policy.decide_file_write(target, ctx.root, ctx.mode)):
        return ToolResult(False, msg)
    flag = lambda k, d=False: str(args.get(k, d)).lower() in ("true", "1", "yes")  # noqa: E731
    num = lambda k: int(re.sub(r"\D", "", str(args.get(k) or "")) or 0) or None  # noqa: E731
    try:
        info = await shot.capture(url, target, device=args.get("device") or "desktop", width=num("width"),
                                  height=num("height"), full_page=flag("full_page", True), selector=args.get("selector") or "",
                                  dark=flag("dark"), wait_ms=num("wait_ms") or 0, hide=args.get("hide") or "", lang=ctx.lang)
    except ImportError:
        return ToolResult(False, "Playwright is not installed (run install.bat / install.sh).")
    except Exception as e:  # navigation errors, missing browser, bad selector
        msg = str(e).splitlines()[0][:300]
        if "Executable doesn't exist" in str(e):
            msg = "Chromium for Playwright is missing: run `python -m playwright install chromium`."
        return ToolResult(False, f"screenshot failed: {msg}")
    out = _rel(ctx, target)
    ctx.files_changed.append(out)
    from .visual import describe_for
    seen = await describe_for(ctx.model, target, ctx.goal) if target.suffix.lower() != ".pdf" else None
    look = (f"The vision model {seen[0]} looked at the screenshot:\n{seen[1]}\n\n" if seen else
            "If you describe the page, use ONLY the page content below (you may not be able to see the image); never "
            "guess colors, layout or elements that are not listed.\n")
    return ToolResult(True, f"saved {out} ({info['width']}x{info['height']}px) - {info['title'] or info['final_url']}\n"
                            "The image is already shown to the user in the chat. " + look +
                            f"Headings: {' | '.join(info.get('headings') or []) or '-'}\n"
                            f"Buttons/links: {' | '.join(info.get('buttons') or []) or '-'}\n"
                            f"Images on the page: {info.get('images', 0)}; page background: {info.get('background', '?')}\n"
                            + (("Problems found while the page ran (fix them, then take the screenshot again):\n- "
                                + "\n- ".join(info["problems"]) + "\n") if info.get("problems")
                               else "The page's JavaScript ran without errors; every image loaded.\n") +
                            f"Visible text:\n{info.get('text') or '(none)'}",
                      {"path": out, "screenshot": out, "url": info["final_url"], "title": info["title"],
                       "size": [info["width"], info["height"]]})


@tool("stock_photo", '<tool name="stock_photo" folder="images" count="3" wide="true">coffee shop interior</tool>',
      "Find real free photos (Openverse / Wikimedia Commons, commercial-use licenses) and download them into the "
      "working folder, web-sized. Get ALL the photos a page needs in ONE call: list the subjects separated by commas "
      "(\"latte art cup, iced coffee, croissant, coffee shop interior\"); they are searched in parallel, one photo "
      "each (count = total). Short concrete English subjects work best. Use the returned relative paths (never hotlink "
      "a photo URL). Returns each file with its author and license for a credit line.",
      {"query": S("Subjects in English, comma separated: one call for every photo the page needs"), "folder": S("Folder in the working directory (default images)"),
       "count": {"type": "integer", "description": "How many photos (1-8, default 3)"},
       "wide": {"type": "boolean", "description": "Landscape photos only (hero/banner); default true"}},
      main="query", required=("query",))
async def stock_photo(ctx, args, body):
    from . import stock
    query = (args.get("query") or body).strip()
    if not query:
        return ToolResult(False, "Say what the photo should show.")
    if msg := await _network_gate(ctx, {"tool": "stock_photo", "url": "https://api.openverse.org"}):
        return ToolResult(False, msg)
    folder = _path(ctx, (args.get("folder") or "images").strip() or "images")
    if msg := await gate(ctx, {"tool": "stock_photo", "path": str(folder)}, policy.decide_file_write(folder / "x.jpg", ctx.root, ctx.mode)):
        return ToolResult(False, msg)
    wide = str(args.get("wide", True)).lower() not in ("false", "0", "no")
    try:
        got = await stock.find(query, folder, int(re.sub(r"\D", "", str(args.get("count") or "")) or 3), wide)
    except Exception as e:  # network down, Pillow missing...
        return ToolResult(False, f"photo search failed: {str(e)[:200]}")
    if not got:
        return ToolResult(False, f"No usable photo found for {query!r}: try other, simpler English words, or use "
                                 "CSS/SVG art instead.")
    lines = []
    for g in got:
        rel = _rel(ctx, g["path"])
        ctx.files_changed.append(rel)
        lines.append(f"- {rel} ({g['width']}x{g['height']}) \"{g['title'][:70]}\" by {g['author']} · {g['license']} · {g['source']}")
    return ToolResult(True, f"Downloaded {len(got)} photo(s); use these relative paths in the page (src=\"{_rel(ctx, got[0]['path'])}\") "
                            "and add a small credit line (author, license) in the footer:\n" + "\n".join(lines),
                      {"files": [_rel(ctx, g["path"]) for g in got]})


@tool("inspect_media", '<tool name="inspect_media" path="photo.jpg" transcript="true">what to look for</tool>',
      "See and hear any image, video or audio file, even if you cannot see images yourself: returns its facts (size, "
      "duration, codecs, EXIF, dominant colours, brightness, sharpness, faces), the text in it (OCR, also on video "
      "frames), a description by a vision model (a video as numbered key frames at scene changes; the frame sheet "
      "is saved and shown to the user) and the speech as text (offline transcription). Use it before you describe, "
      "edit or judge a media file.",
      {"path": S("Image, video or audio file in the working folder"),
       "question": S("Optional: what to look for"),
       "transcript": {"type": "boolean", "description": "Transcribe speech in video/audio (default true)"},
       "minutes": {"type": "integer", "description": "Transcribe at most this many minutes (default 10)"}},
      main="question", required=("path",))
async def inspect_media(ctx, args, body):
    from . import media_inspect
    target = _path(ctx, (args.get("path") or "").strip())
    if not target.is_file():
        return ToolResult(False, f"No such file in the working folder: {args.get('path')}")
    try:
        res = await media_inspect.inspect(
            target, ctx.root, ctx.model, (args.get("question") or body or ctx.goal or "")[:400], ctx.lang or "tr",
            transcript=str(args.get("transcript", True)).lower() not in ("false", "0", "no"),
            minutes=float(re.sub(r"[^\d.]", "", str(args.get("minutes") or "")) or 10))
    except ValueError as e:
        return ToolResult(False, str(e))
    except Exception as e:  # a broken file, ffmpeg missing...
        return ToolResult(False, f"inspection failed: {type(e).__name__}: {str(e)[:200]}")
    data: dict = {"path": _rel(ctx, target)}
    if res.get("sheet"):
        data["screenshot"] = _rel(ctx, res["sheet"])  # the key-frame sheet appears under the step like a screenshot
        ctx.files_changed.append(data["screenshot"])
    return ToolResult(True, clip(media_inspect.report(res), 16000), data)


@tool("generate_image", '<tool name="generate_image" path="images/hero.jpg" width="1280" height="768">detailed English prompt</tool>',
      "Create a new picture from a description (free FLUX image model via Pollinations, no key, a few seconds): "
      "photo-realistic scenes, product shots, illustrations, 3D renders, logos ideas, a picture 'like this one' (first "
      "describe the original with inspect_media, then write that description as the prompt). Write a detailed English "
      "prompt: subject, setting, lighting, camera/style (e.g. 'food photography, top view, soft daylight'). For exact "
      "diagrams or text-heavy graphics draw with code (skia/drawsvg) instead.",
      {"prompt": S("Detailed English description of the picture"), "path": S("Output file (default images/generated.jpg)"),
       "width": {"type": "integer", "description": "Width in px (256-2048, default 1024)"},
       "height": {"type": "integer", "description": "Height in px (256-2048, default 1024)"},
       "seed": {"type": "integer", "description": "Optional seed: the same seed and prompt give the same picture"}},
      main="prompt", required=("prompt",))
async def generate_image(ctx, args, body):
    prompt = (args.get("prompt") or body or "").strip()
    if not prompt:
        return ToolResult(False, "Describe the picture to create.")
    if msg := await _network_gate(ctx, {"tool": "generate_image", "url": "https://image.pollinations.ai"}):
        return ToolResult(False, msg)
    rel = (args.get("path") or "images/generated.jpg").strip()
    target = _path(ctx, rel if Path(rel).suffix.lower() in (".jpg", ".jpeg", ".png", ".webp") else rel + ".jpg")
    if msg := await gate(ctx, {"tool": "generate_image", "path": str(target)}, policy.decide_file_write(target, ctx.root, ctx.mode)):
        return ToolResult(False, msg)
    from . import imagegen
    num = lambda k, d: max(256, min(2048, int(re.sub(r"\D", "", str(args.get(k) or "")) or d)))  # noqa: E731
    seed = int(args["seed"]) if str(args.get("seed") or "").strip().isdigit() else None
    try:
        data, clean = await imagegen.generate(prompt, num("width", 1024), num("height", 1024), seed)
    except RuntimeError as e:
        return ToolResult(False, f"image generation failed ({e}); try again or draw it with code.")
    w, h = await asyncio.to_thread(imagegen.save, data, target)
    out = _rel(ctx, target)
    ctx.files_changed.append(out)
    note = ("" if clean else " (the free service puts its small pollinations.ai logo in a corner; a free Pollinations "
            "token in Settings > Web research removes it)")
    return ToolResult(True, f"created {out} ({w}x{h}px){note}. It is shown to the user; look at it with inspect_media "
                            "if you need to check.", {"path": out, "files": [out]})


@tool("speech_to_text", '<tool name="speech_to_text" path="interview.mp4" language="tr" model="base"></tool>',
      "Turn the speech in an audio or video file into text, offline (faster-whisper on the CPU): returns the "
      "transcript with timestamps and writes <name>.srt (subtitles) and <name>.txt into the working folder. "
      "language: optional (auto-detected); model: tiny (fastest), base (default), small or medium (more accurate, "
      "slower); minutes: only the first N minutes.",
      {"path": S("Audio or video file in the working folder"), "language": S("Optional language code: tr, en..."),
       "model": S("tiny | base | small | medium"),
       "minutes": {"type": "integer", "description": "Only the first N minutes (default: all)"}},
      required=("path",))
async def speech_to_text(ctx, args, body):
    from . import speech
    target = _path(ctx, (args.get("path") or body or "").strip())
    if not target.is_file():
        return ToolResult(False, f"No such file in the working folder: {args.get('path') or body}")
    from .media_inspect import AUDIO, VIDEO
    if target.suffix.lower() not in AUDIO | VIDEO:
        return ToolResult(False, f"{target.name} is not an audio or video file. For a picture use inspect_media "
                                 "(it reads the text in it with OCR).")
    out_dir = target.parent
    if msg := await gate(ctx, {"tool": "speech_to_text", "path": str(out_dir / (target.stem + ".srt"))},
                         policy.decide_file_write(out_dir / (target.stem + ".srt"), ctx.root, ctx.mode)):
        return ToolResult(False, msg)
    try:
        res = await speech.speech_to_text(target, out_dir, (args.get("language") or "").strip() or None,
                                          (args.get("model") or "base").strip(),
                                          float(re.sub(r"[^\d.]", "", str(args.get("minutes") or "")) or 0))
    except ImportError:
        return ToolResult(False, "faster-whisper is not installed (run install.bat / install.sh).")
    except Exception as e:
        return ToolResult(False, f"speech to text failed: {type(e).__name__}: {str(e)[:200]}")
    srt, txt = _rel(ctx, res["srt"]), _rel(ctx, res["txt"])
    ctx.files_changed += [srt, txt]
    if not res["segments"]:
        return ToolResult(True, f"No speech was found in {target.name} (silence or music only).", {"path": txt})
    return ToolResult(True, clip(
        f"Transcribed {res['segments']} segments, {int(res['duration'])} s of speech, language {res['language']}; "
        f"saved {srt} (subtitles) and {txt} (plain text).\nShow the transcript to the user as this table (translate "
        f"the header to the user's language, keep the times), then name the two files:\n\n{res['text']}", 16000),
        {"path": txt, "files": [srt, txt]})


@tool("text_to_speech", '<tool name="text_to_speech" path="audio/intro.mp3" language="tr" gender="female">text to read</tool>',
      "Turn text into natural speech (Microsoft neural voices, free): writes an .mp3 into the working folder, any "
      "length. language picks a matching voice (gender female/male), or give voice like tr-TR-AhmetNeural; rate "
      "0.5-2.0. Use it for voice-overs, audio versions of texts, video narration (then merge with ffmpeg).",
      {"text": S("The text to read"), "path": S("Output .mp3 path (default speech.mp3)"),
       "language": S("Language code: tr, en, de..."), "gender": S("female | male"),
       "voice": S("Optional exact voice id, e.g. tr-TR-EmelNeural"),
       "rate": {"type": "number", "description": "Speed 0.5-2.0 (default 1.0)"}},
      main="text", required=("text",))
async def text_to_speech(ctx, args, body):
    from . import speech
    text = (args.get("text") or body or "").strip()
    if not text:
        return ToolResult(False, "Give the text to read.")
    rel = (args.get("path") or "speech.mp3").strip()
    target = _path(ctx, rel if rel.lower().endswith(".mp3") else rel + ".mp3")
    if msg := await gate(ctx, {"tool": "text_to_speech", "path": str(target)},
                         policy.decide_file_write(target, ctx.root, ctx.mode)):
        return ToolResult(False, msg)
    try:
        res = await speech.text_to_speech(text, target, (args.get("language") or ctx.lang or "tr").strip().lower()[:3],
                                          (args.get("voice") or "").strip(), (args.get("gender") or "").strip(),
                                          float(args.get("rate") or 1.0))
    except Exception as e:  # offline, unknown voice...
        return ToolResult(False, f"text to speech failed: {str(e)[:200]}")
    out = _rel(ctx, target)
    ctx.files_changed.append(out)
    lang = res["voice"].split("-")[0]
    return ToolResult(True, f"saved {out} ({res['bytes'] // 1024} KB, voice {res['voice']}, {res['chars']} characters). "
                            "The user plays it in the chat and can pick another voice there (with previews).",
                      {"path": out, "tts": {"text": text[:20000], "voice": res["voice"], "lang": lang,
                                            "rate": float(args.get("rate") or 1.0)}})


@tool("make_doc", '<tool name="make_doc" type="pdf|docx|pptx|xlsx|html" path="docs/report.pdf" theme="corporate">'
      'markdown, HTML or JSON content</tool>',
      "Generate a professional document (designed layout, every language and script, clickable links, LaTeX math). "
      "pdf/docx/pptx/html take full Markdown (headings, **bold**, lists, tables, links, images, code, > quotes, "
      "$inline$ and $$display$$ LaTeX) or HTML; in pptx every # / ## heading (or ---) starts a slide, the first # "
      "alone is the title slide. xlsx takes JSON rows, {\"sheets\": {\"Name\": rows}} or Markdown tables (one sheet "
      "each; numbers become real numbers). For the most professional reports write HTML (a fragment, the designed "
      "template styles it): <h1>, <h2>, <p>, <table>, plus ready components: KPI cards <div class=\"kpis\"><div "
      "class=\"kpi\"><span>USD/TRY</span><b>50,36</b><em class=\"up\">+0,22%</em></div>...</div>, a bar chart <div "
      "class=\"bars\"><div style=\"--v:76%\"><span>USD</span><i></i><b>50,36</b></div>...</div> (--v = bar length in "
      "% of the largest value), <div class=\"callout\">note</div>, <span class=\"badge\">tag</span>, <div "
      "class=\"cols\">two columns</div>, inline <svg> charts. They need no image file and also work in docx/pptx. "
      "Large content: write it to a .md/.html file first (write_file, append "
      "parts) and pass source=that file instead of content. Write real data and real source URLs, never placeholders.",
      {"type": S("Document type", enum=["pdf", "docx", "pptx", "xlsx", "html"]), "path": S("Output path"),
       "content": S("Markdown / HTML, or JSON rows for xlsx"),
       "source": S("Optional: a .md/.html/.json file in the working folder to convert instead of content"),
       "theme": S("Color theme", enum=["corporate", "blue", "green", "red", "purple", "orange", "teal", "gray", "dark"]),
       "landscape": {"type": "boolean", "description": "PDF in landscape (wide tables)"}},
      main="content", required=("path",))
async def make_doc(ctx, args, body):
    from .docs_gen import generate
    target = _path(ctx, args["path"])
    content = body
    base_dir = ctx.root
    if args.get("source"):
        src = _path(ctx, args["source"])
        if not src.is_file():
            return ToolResult(False, f"source not found: {args['source']}")
        content = src.read_text(encoding="utf-8", errors="replace")
        base_dir = src.parent
    if not (content or "").strip():
        return ToolResult(False, "No content: pass Markdown/HTML/JSON as content, or source=<file>.")
    if msg := await gate(ctx, {"tool": "make_doc", "path": str(target)}, policy.decide_file_write(target, ctx.root, ctx.mode)):
        return ToolResult(False, msg)
    try:
        info = await generate(args.get("type") or target.suffix.lstrip("."), content, target, base_dir=base_dir,
                              theme=args.get("theme"), lang=getattr(ctx, "lang", None) or "en",
                              landscape=str(args.get("landscape", "")).lower() in ("true", "1", "yes"))
    except ValueError as e:
        return ToolResult(False, str(e))
    rel = _rel(ctx, target)
    ctx.files_changed.append(rel)
    # The document's source stays next to it: a later "add a chart / change the table" edits this text and
    # converts again, instead of rebuilding the document from memory (a PDF itself cannot be edited).
    src_rel = args.get("source") or ""
    if not src_rel:
        try:
            keep = target.parent / ".doc-sources" / f"{target.name}.md"
            keep.parent.mkdir(parents=True, exist_ok=True)
            keep.write_text(content, encoding="utf-8")
            src_rel = _rel(ctx, keep)
        except OSError:
            src_rel = ""
    extra = ", ".join(f"{k}: {v}" for k, v in info.items() if k in ("slides", "sheets", "formulas", "images", "engine") and v)
    if kind_of(args, target) != "xlsx":
        extra += f". The document contains {info.get('images', 0)} image(s)/chart(s)"
    if miss := info.get("missing_images"):
        # The document was written without them: the model must know, so it never tells the user they are there.
        extra += (f". WARNING: {len(miss)} image(s) were NOT included because the file does not exist or is not an "
                  f"image: {', '.join(miss)}. The document has NO such picture. If a chart/image is wanted, create it "
                  "for real first (run with shell=python and matplotlib: plt.savefig('chart.png')), check it exists, "
                  "then call make_doc again with ![caption](chart.png). Never claim an image that was not included")
    if bad := unverified_figures(ctx, content):
        extra += (f". WARNING: {len(bad)} figures in this document appear in NO source read in this task: "
                  f"{', '.join(bad[:12])}. Numbers must come from the sources: read them again (research / fetch_url) "
                  "and correct the document, or state clearly which values are your own calculation. Do not present "
                  "unverified numbers as facts")
    if src_rel:
        extra += (f". Source text: {src_rel} (to change this document later: edit_file that source, then make_doc "
                  f"source={src_rel} with the same path)")
    return ToolResult(True, f"generated {rel} ({info.get('bytes', 0) // 1024} KB{', ' + extra if extra else ''})",
                      {"path": rel, "source": src_rel, "images": info.get("images", 0),
                       **{k: v for k, v in info.items() if k in ("slides", "sheets", "engine")}})


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
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                page = await browser.new_page()
                page.on("pageerror", lambda e: problems.append(f"Uncaught {str(e)[:300]}"))
                page.on("console", lambda m: problems.append(f"console.{m.type}: {m.text[:300]}") if m.type == "error" else None)
                page.on("requestfailed", lambda r: problems.append(f"failed to load {r.url[-120:]}")
                        if r.url.startswith("file:") else None)
                await page.goto(target.resolve().as_uri(), wait_until="load", timeout=15000)
                await page.evaluate(JS_CHECK)
            finally:
                await browser.close()
    except Exception as e:  # noqa: BLE001 - no browser: no check, never a failed write
        return f"(JavaScript check skipped: {type(e).__name__})"
    if not problems:
        return "JavaScript check: the page loaded without errors."
    return "JavaScript ERRORS when the page loads (fix them, then the check runs again):\n- " + "\n- ".join(
        dict.fromkeys(problems[:12]))


def b64_file(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode()


@tool("symbols", '<tool name="symbols" path="src"></tool>',
      "List the functions, classes, methods and other definitions of a file or folder with line numbers "
      "(then read_file lines=... to read one). Faster than reading files to find where something is defined.",
      {"path": S("File or folder, default '.'")})
async def symbols(ctx, args, body):
    from .symbols import detail
    base = _path(ctx, args.get("path") or body.strip() or ".")
    if not base.exists():
        return ToolResult(False, f"not found: {args.get('path')}")
    return ToolResult(True, clip(await asyncio.to_thread(detail, ctx.root.resolve(), base)), {"path": args.get("path", ".")})


@tool("impact", '<tool name="impact">src/utils.js | functionName</tool>',
      "Before changing a file or a function/class, see what the change affects: from the syntax tree, the files that "
      "use what a file defines, or every place a symbol is defined and used (code only, not comments or strings).",
      {"target": S("A file path, or a function/class/variable name")}, main="target", required=("target",))
async def impact(ctx, args, body):
    from .syntax import available, impact as analyse
    target = (body.strip() or args.get("target", "")).strip()
    if not target:
        return ToolResult(False, "Give a file path or a symbol name.")
    if not available():
        return ToolResult(False, "Syntax trees are not installed (tree-sitter-language-pack); use search_code.")
    f = _path(ctx, target) if ("/" in target or "." in target) else None
    rel = _rel(ctx, f) if f is not None and f.is_file() else target
    return ToolResult(True, clip(await asyncio.to_thread(analyse, ctx.root.resolve(), rel)), {"target": target})


@tool("mcp", '<tool name="mcp" server="SERVER" tool="TOOL">{"arg": "value"}</tool>',
      "Call a tool of a connected MCP server (see 'MCP tools'): server id, tool name and the arguments as a JSON object.",
      {"server": S("MCP server id"), "tool": S("Tool name on that server"),
       "arguments": {"type": "object", "description": "Arguments for the tool"}},
      main="arguments", required=("server", "tool"))
async def mcp(ctx, args, body):
    from .. import mcp_client
    server, name = args.get("server", ""), args.get("tool", "")
    raw = body.strip() or args.get("arguments") or "{}"
    try:
        arguments = json.loads(raw) if isinstance(raw, str) else raw
        if not isinstance(arguments, dict):
            raise ValueError
    except ValueError:
        return ToolResult(False, "arguments must be a JSON object.")
    spec = mcp_client.find_tool(server, name)
    if not spec:
        have = ", ".join(f"{s}/{t['name']}" for s, t in mcp_client.available_tools()[:40]) or "none"
        return ToolResult(False, f"No MCP tool {server}/{name}. Available: {have}")
    read_only = bool((spec.get("annotations") or {}).get("readOnlyHint"))
    op = {"tool": "mcp", "server": server, "name": name, "arguments": arguments}
    decision = policy.Decision("allow" if read_only or ctx.mode == "full" else "ask", "mcp", [f"{server}/{name}"])
    if msg := await gate(ctx, op, decision):
        return ToolResult(False, msg)
    try:
        ok, out = await mcp_client.call(server, name, arguments)
    except Exception as e:
        return ToolResult(False, f"MCP {server}/{name} failed: {e}")
    return ToolResult(ok, clip(out), {"server": server, "name": name})


@tool("mcp_add", '<tool name="mcp_add" id="github" command="npx" args=\'["-y", "@modelcontextprotocol/server-github"]\'>{"GITHUB_PERSONAL_ACCESS_TOKEN": "..."}</tool>',
      "Connect a new MCP server so its tools become usable (stdio: command + args, e.g. npx -y <npm package>, "
      "uvx <pypi package>, or node/python with a script cloned from GitHub; http: url). Body: environment variables "
      "as a JSON object (tokens stay in the secret store). Returns the server's tools. Use the skill mcp-servers to "
      "find the right package first. remove=true disconnects a server.",
      {"id": S("Short id: lowercase letters, digits, - or _"), "command": S("stdio: program (npx, uvx, node, python...)"),
       "args": {"type": "array", "items": {"type": "string"}, "description": "stdio: arguments"},
       "url": S("http transport: server URL"), "env": {"type": "object", "description": "Environment variables / tokens"},
       "remove": {"type": "boolean", "description": "Disconnect and delete this server"}},
      main="env", required=("id",))
async def mcp_add(ctx, args, body):
    import re as _re
    from .. import mcp_client
    from ..config import load_settings, save_settings, set_secret
    sid = str(args.get("id") or "").strip().lower()
    if not _re.fullmatch(r"[a-z0-9_-]{1,32}", sid):
        return ToolResult(False, "id must be 1-32 lowercase letters, digits, - or _.")
    if args.get("remove") in (True, "true", "1"):
        if sid not in (load_settings().get("mcp_servers") or {}):
            return ToolResult(False, f"No MCP server '{sid}'.")
        if msg := await gate(ctx, {"tool": "mcp_add", "remove": sid}, policy.Decision("allow" if ctx.mode == "full" else "ask", "mcp", [sid])):
            return ToolResult(False, msg)
        save_settings({"mcp_servers": {sid: None}})
        set_secret(f"mcp_{sid}", None)
        await mcp_client.ensure()
        return ToolResult(True, f"MCP server '{sid}' removed.")
    raw_env = body.strip() or args.get("env") or {}
    try:
        env = json.loads(raw_env) if isinstance(raw_env, str) else raw_env
        if not isinstance(env, dict):
            raise ValueError
    except ValueError:
        return ToolResult(False, "env must be a JSON object of NAME: value.")
    argv = args.get("args") or []
    if isinstance(argv, str):
        try:
            argv = json.loads(argv)
        except ValueError:
            argv = argv.split()
    url, command = str(args.get("url") or "").strip(), str(args.get("command") or "").strip()
    if not (command or url):
        return ToolResult(False, "Give command (+ args) for a stdio server or url for an http server.")
    cfg = {"name": sid, "transport": "http" if url and not command else "stdio", "command": command,
           "args": [str(a) for a in argv], "url": url, "cwd": str(ctx.root), "enabled": True}
    shown = " ".join([command, *cfg["args"]]) if command else url
    op = {"tool": "mcp_add", "id": sid, "command": shown, "env": sorted(env)}
    if msg := await gate(ctx, op, policy.Decision("allow" if ctx.mode == "full" else "ask", "mcp", [shown])):
        return ToolResult(False, msg)
    save_settings({"mcp_servers": {sid: None}})
    save_settings({"mcp_servers": {sid: cfg}})
    key = "headers" if cfg["transport"] == "http" else "env"
    set_secret(f"mcp_{sid}", json.dumps({key: {str(k): str(v) for k, v in env.items()}}) if env else None)
    srv = await mcp_client.restart(sid)
    st = mcp_client.status().get(sid) or {}
    if not st.get("running"):
        return ToolResult(False, f"MCP server '{sid}' was saved but did not start: {st.get('error') or 'unknown error'}. "
                          "Check the package name / command (run it once with run to see its output), then call "
                          "mcp_add again with the same id.")
    tools = ", ".join(t["name"] for t in st.get("tools", [])[:40]) or "none"
    del srv
    return ToolResult(True, f"MCP server '{sid}' connected ({shown}). Tools: {tools}. Call them with the mcp tool.",
                      {"server": sid})


@tool("team", '<tool name="team">[{"title": "Backend API", "task": "complete sub-task", "need": "code", "stage": 1}, ...]</tool>',
      "Real multi-agent teamwork: 1-6 parts of a task, each done by its own agent on a different cloud model of the "
      "pool (they read/write files, run commands and make documents in the same folder, and can message each other). "
      "Parts with the same stage run at the same time and must touch different files; a part that needs another "
      "part's result MUST get a later stage (2, 3...): it then starts after it and receives the earlier stages' "
      "reports and file names (without a stage it would run at the same time and see nothing). Give each "
      "a complete, self-contained task with the exact file paths and names from the user's request. You get every "
      "report back with the model that did it.",
      {"members": {"type": "array", "description": "1-6 parts",
                   "items": {"type": "object", "properties": {"title": S("Short name"), "task": S("Complete sub-task"),
                             "need": S("Capability", enum=["code", "reasoning", "fast", "writing"]),
                             "stage": {"type": "integer", "description": "Order: 1 first; parts of one stage run in parallel"}},
                             "required": ["title", "task"]}}},
      main="members", required=("members",))
async def team(ctx, args, body):
    from ..agents.team import parse_members, run_team
    members = parse_members(body.strip() or args.get("members"))
    if not members and args.get("task"):  # one part sent flat ({"title", "task"}) instead of a members list
        members = [{k: args[k] for k in ("title", "task", "need") if args.get(k)}]
    return await run_team(ctx, members)


@tool("ask_model", '<tool name="ask_model" need="code|reasoning|fast|vision|long_context|writing">self-contained sub-task '
      'with all the context it needs</tool>',
      "Hand a self-contained sub-task (a review, a draft, an analysis, a second opinion, a long text) to another model "
      "of the multi-model pool. The most available model for the capability is chosen (quota, rate limit, context). "
      "It answers with text only (no tools), so include everything it needs in the task.",
      {"task": S("The complete sub-task, with the code/text it needs"),
       "need": S("Capability that matters most", enum=["code", "reasoning", "fast", "vision", "long_context", "writing"])},
      main="task", required=("task",))
async def ask_model(ctx, args, body):
    from ..llm import router
    from ..llm.providers import ProviderError
    task = body.strip() or args.get("task", "")
    if not task:
        return ToolResult(False, "Empty task.")
    need = args.get("need") or None
    tried: set[str] = {ctx.model}
    for _ in range(3):  # the first choice may turn out busy or out of quota: try the next one
        mid, why = await router.pick(need, len(task) // 3 + 2000, exclude=tried)
        if not mid:
            return ToolResult(False, f"No other model is available right now ({why}). Do this part yourself.",
                              {"model": ""})
        tried.add(mid)
        try:
            text = await router.complete(mid, [
                {"role": "system", "content": "You are a helper model called by another AI agent. Do exactly the task, "
                 "completely and concisely. Think and answer in " + _lang_name(ctx.lang) + ". No tool calls; answer "
                 "with the result only."},
                {"role": "user", "content": task}], {}, ctx.cancel)
        except ProviderError as e:
            ctx.step("note", {"model": mid, "error": str(e)[:300]})
            continue
        if text.strip():
            return ToolResult(True, clip(f"[{mid}]\n{text.strip()}"), {"model": mid, "need": need})
    return ToolResult(False, "The other models failed or returned nothing. Do this part yourself.", {"model": ""})


@tool("remember", '<tool name="remember" scope="project|global">a lasting rule or preference</tool>',
      "Save a lasting rule the user gave (\"always use Tailwind\", \"bundan sonra yorumları Türkçe yaz\", \"remember that ...\") "
      "so every later chat follows it. scope=project (default in a project: the project's AIIQ.md) or global (all chats). "
      "One short rule per call; not for one-off task details.",
      {"rule": S("The rule, short and self-contained"), "scope": S("project or global", enum=["project", "global"])},
      main="rule", required=("rule",))
async def remember(ctx, args, body):
    from .. import workspace
    from ..config import load_settings, save_settings
    rule = (body.strip() or args.get("rule", "")).strip()
    if not rule or len(rule) > 500:
        return ToolResult(False, "Give one short rule (at most 500 characters).")
    scope = args.get("scope") or ("project" if ctx.project else "global")
    if scope == "project" and ctx.project:
        before = workspace.read_rules(ctx.project)
        heading = workspace.RULES_HEADING.get(ctx.lang, workspace.RULES_HEADING["en"])
        after = workspace.add_rule(before, rule, heading)
        if after == before:
            return ToolResult(True, "This rule is already saved.", {"scope": "project"})
        if len(after) > workspace.RULES_MAX:
            return ToolResult(False, "The project rules file is full; ask the user to tidy it in the project's Rules.")
        workspace.write_rules(ctx.project, after)
        return ToolResult(True, f"Saved to {workspace.RULES_FILE}: {rule}", {"scope": "project", "rule": rule})
    before = load_settings().get("rules") or ""
    after = workspace.add_rule(before, rule)
    if after != before:
        save_settings({"rules": after[:workspace.RULES_MAX]})
    return ToolResult(True, f"Saved as a global rule: {rule}", {"scope": "global", "rule": rule})


@tool("use_skill", '<tool name="use_skill">skill-name</tool>',
      "Load the full instructions of a skill listed under 'Available skills' when the request matches it; then follow them.",
      {"name": S("Skill name")}, main="name", required=("name",))
async def use_skill(ctx, args, body):
    from ..agents import catalog
    name = (body or args.get("name", "")).strip().lstrip("/")
    skills = catalog.skills()
    if name not in skills:
        return ToolResult(False, f"Unknown skill '{name}'. Available: {', '.join(skills) or 'none'}")
    return ToolResult(True, f"# Skill: {skills[name]['title']}\n{skills[name]['prompt']}", {"skill": name})


@tool("save_catalog", '<tool name="save_catalog" kind="skills|agents" name="my-skill">---\nname: ...\n---\ninstructions</tool>',
      "Save a new or improved skill (kind=skills, used with /name) or agent role (kind=agents, used with @name) into "
      "the app's own folders. Content: frontmatter (name, title, title_tr, title_en, description, description_tr, "
      "description_en, optional tools: comma list) then the instructions. The user approves the write.",
      {"kind": S("skills or agents", enum=["skills", "agents"]), "name": S("lowercase-name"),
       "content": S("The whole .md file")}, main="content", required=("kind", "content"))
async def save_catalog(ctx, args, body):
    from ..agents import catalog
    from ..errors import AppError
    kind = args.get("kind") or "skills"
    content = (body or args.get("content") or "").strip() + "\n"
    try:
        meta = catalog.validate(kind, content)
    except AppError as e:
        return ToolResult(False, f"not saved: {e}")
    name = args.get("name") or meta["name"]
    if name != meta["name"]:
        return ToolResult(False, f"not saved: name '{name}' differs from the frontmatter name '{meta['name']}'")
    target = catalog.DIRS[kind] / f"{name}.md"
    exists = target.is_file()
    decision = policy.Decision("allow" if ctx.mode == "full" else "ask", "catalog")
    preview = lambda: change_preview("overwrite" if exists else "new", _text_of(target) if exists else None,  # noqa: E731
                                     content, f"{kind}/{name}.md")
    if msg := await gate(ctx, {"tool": "save_catalog", "path": f"{kind}/{name}.md"}, decision, preview):
        return ToolResult(False, msg)
    catalog.write(kind, name, content)
    langs = [p.stem for p in LANG_DIR.glob("*.json")]
    try:  # fill missing title_/description_ translations for the installed languages (best effort)
        await asyncio.wait_for(asyncio.to_thread(catalog.localize, langs, [target]), 30)
    except Exception:
        pass
    use = f"/{name}" if kind == "skills" else f"@{name}"
    return ToolResult(True, f"saved {kind}/{name}.md ({'updated' if exists else 'new'}); the user can use it as {use}",
                      {"path": f"{kind}/{name}.md", "kind": kind, "name": name, "catalog": True})


TODO_STATES = ("pending", "in_progress", "completed")


NEED_GROUPS = ["web", "media", "design", "browser", "places", "docs", "memory", "project", "team", "mcp", "mcp_setup",
               "system"]


@tool("need_tools", '<tool name="need_tools" groups="web,docs"></tool>',
      "Only the tools this request needs are loaded. To get more, open groups: web (search, research, fetch_url, "
      "web_screenshot), media (inspect_media: see/hear images, videos, audio), design (stock_photo: real photos for "
      "pages; web_screenshot), browser (act in a real browser window), places (maps, nearby venues, the user's location), "
      "docs (make/read PDF, Word, Excel, PowerPoint), memory (remember rules, save skills/agents), project (symbols, "
      "impact), team (agent team, ask another model), mcp (connected MCP servers), mcp_setup (mcp_add: connect a "
      "new MCP server), system (system_info: this computer's hardware and OS).",
      {"groups": S("Comma separated group names: " + ", ".join(NEED_GROUPS))}, main="groups", required=("groups",))
async def need_tools(ctx, args, body):  # handled by the orchestrator (it owns the task's tool offer)
    return ToolResult(False, "need_tools is handled by the agent loop.")


@tool("todo", '<tool name="todo">[{"content": "Create the database schema", "status": "in_progress"}, ...]</tool>',
      "Task list shown live to the user. For any task with 3 or more steps, send it with the whole plan in the "
      "same reply as the first actions (not a reply of its own) "
      "(short imperative items), then call it again with the WHOLE updated list whenever an item starts "
      "(in_progress, exactly one at a time) or is finished (completed). Finish every item before the final answer.",
      {"items": {"type": "array", "description": "The whole list, in order",
                 "items": {"type": "object", "properties": {"content": S("Short imperative item"),
                                                            "status": S("Item state", enum=list(TODO_STATES))},
                           "required": ["content", "status"]}}},
      main="items", required=("items",))
async def todo(ctx, args, body):
    try:
        raw = json.loads(body) if isinstance(body, str) else body
    except json.JSONDecodeError:
        return ToolResult(False, 'items must be a JSON array like [{"content": "...", "status": "pending"}]')
    if isinstance(raw, dict):
        raw = raw.get("items") or raw.get("todos") or []
    items = []
    for it in raw if isinstance(raw, list) else []:
        if isinstance(it, str):
            it = {"content": it, "status": "pending"}
        if isinstance(it, dict) and str(it.get("content") or "").strip():
            st = it.get("status") if it.get("status") in TODO_STATES else "pending"
            items.append({"content": str(it["content"]).strip()[:200], "status": st})
    if not items:
        return ToolResult(False, "The list is empty. Send all items with content and status.")
    done = sum(i["status"] == "completed" for i in items)
    left = [i["content"] for i in items if i["status"] != "completed"]
    note = f"Next: {left[0]}. Keep going." if left else "All items are completed: give the final answer."
    return ToolResult(True, f"To-do list updated ({done}/{len(items)} completed). {note}", {"todos": items[:30]})


# browser_* tools live in their own module (separate concern, long file); importing it here runs their
# @tool(...) decorators so they register into TOOLS, same as every function above.
from . import browser_tools  # noqa: E402,F401
