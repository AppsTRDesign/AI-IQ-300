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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Awaitable, Callable


from .. import approvals, policy
from ..config import load_settings
from ..process_manager import manager

MAX_RESULT = 6000


@dataclass
class ToolContext:
    run_id: str
    root: Path
    mode: str
    cancel: asyncio.Event
    session_dir: Path | None = None  # chat/<id>-session: scripts, screenshots, state
    owner: str | None = None  # "<session_id>:<run_id>": groups background tasks per chat
    files_changed: list[str] = field(default_factory=list)
    commands: list[str] = field(default_factory=list)
    step: Callable[[str, dict], None] = lambda kind, data: None


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
SHELLS = ["powershell", "cmd", "python", "node", "php", "bash", "exec"]


def tool(name: str, usage: str, description: str, params: dict | None = None, main: str | None = None,
         required: tuple = ()):
    def deco(fn):
        TOOLS[name] = ToolSpec(name, usage, description, fn, params or {}, main, required)
        return fn
    return deco


# Tools that change nothing on the computer: offered alone for plain knowledge questions.
READ_ONLY = {"read_file", "list_dir", "web_search", "fetch_url", "research", "use_skill"}


def _pick(names: set[str] | None) -> list[ToolSpec]:
    return [t for t in TOOLS.values() if names is None or t.name in names]


def tools_prompt(names: set[str] | None = None) -> str:
    return "\n".join(f"- {t.usage}\n  {t.description}" for t in _pick(names))


def tool_schemas(names: set[str] | None = None) -> list[dict]:
    """Native function-calling definitions (provider adapters wrap them in their own format)."""
    return [{"name": t.name, "description": t.description,
             "parameters": {"type": "object", "properties": t.params, "required": list(t.required)}}
            for t in _pick(names)]


def split_args(name: str, arguments: dict) -> tuple[dict, str]:
    """Native call arguments -> (attribute args as strings, body) like the tag protocol."""
    spec = TOOLS[name]
    args = {k: (v if isinstance(v, str) else json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else str(v))
            for k, v in arguments.items() if v is not None}
    body = args.pop(spec.main, "") if spec.main else ""
    return args, body


def clip(text: str, n: int = MAX_RESULT) -> str:
    return text if len(text) <= n else text[: n // 3] + f"\n...[{len(text) - n} chars omitted]...\n" + text[-2 * n // 3:]


async def gate(ctx: ToolContext, op: dict, decision: policy.Decision) -> str | None:
    """Returns None if allowed, else a denial message for the model."""
    if decision.action == "deny":
        ctx.step("policy", {"op": op, "action": "deny", "reasons": decision.reasons})
        return f"DENIED by policy ({decision.category}). This operation is never allowed."
    if decision.action == "ask":
        ctx.step("approval", {"op": op, "category": decision.category})
        if not await approvals.request(ctx.run_id, op, decision.category, decision.reasons):
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


def _path(ctx: ToolContext, rel: str) -> Path:
    return policy.resolve_in(ctx.root, rel, allow_outside=ctx.mode == "full")


@tool("write_file", '<tool name="write_file" path="REL/PATH">full file content</tool>',
      "Create or overwrite a file (parent folders are created). Always write the COMPLETE file content.",
      {"path": S("File path relative to the working directory"), "content": S("Complete file content")},
      main="content", required=("path", "content"))
async def write_file(ctx, args, body):
    target = _path(ctx, args["path"])
    op = {"tool": "write_file", "path": str(target), "sha": hashlib.sha256(body.encode()).hexdigest()[:16]}
    if msg := await gate(ctx, op, policy.decide_file_write(target, ctx.root, ctx.mode)):
        return ToolResult(False, msg)
    target.parent.mkdir(parents=True, exist_ok=True)
    existed = target.exists()
    content = clean_file_content(body)
    target.write_text(content, encoding="utf-8", newline="")
    rel = target.relative_to(ctx.root).as_posix() if ctx.root in target.parents else str(target)
    ctx.files_changed.append(rel)
    return ToolResult(True, f"{'updated' if existed else 'created'} {rel} ({len(content)} chars)",
                      {"path": rel, "language": target.suffix.lstrip("."), "created": not existed})


@tool("read_file", '<tool name="read_file" path="REL/PATH"></tool>', "Read a text file.",
      {"path": S("File path")}, required=("path",))
async def read_file(ctx, args, body):
    target = _path(ctx, args["path"])
    if not target.is_file():
        return ToolResult(False, f"not found: {args['path']}")
    return ToolResult(True, clip(target.read_text(encoding="utf-8", errors="replace")), {"path": args["path"]})


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
    if msg := await gate(ctx, op, policy.Decision("ask", "dangerous", ["file deletion"])):
        return ToolResult(False, msg)
    if target.is_file():
        target.unlink()
        ctx.files_changed.append(args["path"])
        return ToolResult(True, f"deleted {args['path']}")
    return ToolResult(False, "not a file")


DEFAULT_SHELL = "powershell" if sys.platform == "win32" else "bash"
SCRIPT_SHELLS = {"powershell": ".ps1", "python": ".py", "node": ".js", "php": ".php"}


def build_argv(ctx: ToolContext, shell: str, command: str) -> list[str]:
    """Turn a shell + command into an argv vector. Script shells use an explicit script file."""
    shell = (shell or DEFAULT_SHELL).lower()
    if sys.platform != "win32" and shell in ("powershell", "cmd") and not shutil.which("pwsh"):
        shell = "bash"  # Linux/macOS without PowerShell: run the command in bash
    if shell in SCRIPT_SHELLS:
        scripts = (ctx.session_dir or ctx.root / ".aiiq") / "scripts"
        scripts.mkdir(parents=True, exist_ok=True)
        f = scripts / f"{hashlib.sha256(command.encode()).hexdigest()[:12]}{SCRIPT_SHELLS[shell]}"
        f.write_text(command, encoding="utf-8-sig" if shell == "powershell" else "utf-8")
        if shell == "powershell":
            exe = shutil.which("pwsh") or "powershell"
            return [exe, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(f)]
        return [shell, str(f)]
    if shell == "cmd":
        return ["cmd", "/d", "/s", "/c", command]
    if shell == "bash":
        return ["bash", "-lc", command]
    return shlex.split(command, posix=sys.platform != "win32")  # "exec": direct argv


async def _spawn(ctx: ToolContext, args: dict, body: str, background: bool):
    command = body.strip()
    shell = args.get("shell") or DEFAULT_SHELL
    cwd = _path(ctx, args.get("cwd", "."))
    op = {"tool": "start" if background else "run", "shell": shell, "cwd": str(cwd), "command": command}
    if msg := await gate(ctx, op, policy.decide_command(command, ctx.mode)):
        return None, ToolResult(False, msg)
    argv = build_argv(ctx, shell, command)
    ctx.commands.append(command)
    timeout = None if background else float(args.get("timeout") or load_settings()["agent"]["command_timeout"])
    info = await manager.start(argv, str(cwd), policy.minimal_env(), owner=ctx.owner or ctx.run_id, timeout=timeout)
    if background:
        ctx.step("process", {"process_id": info.id, "command": command, "shell": shell})
    return info, None


@tool("run", '<tool name="run" shell="powershell|cmd|python|node|php|bash|exec" cwd="." timeout="300">command or script</tool>',
      "Run a command or script and wait for it. Returns exit code and output tail. Use for builds, tests, installs, git, "
      "and for creating folders/projects with CLI tools. Shell 'exec' runs a program directly (git, npm, python args).",
      {"command": S("Command line or script source"), "shell": S("Interpreter", enum=SHELLS),
       "cwd": S("Working directory, default '.'"), "timeout": {"type": "integer", "description": "Seconds"}},
      main="command", required=("command",))
async def run(ctx, args, body):
    info, denied = await _spawn(ctx, args, body, background=False)
    if denied:
        return denied
    waiter = asyncio.create_task(info.done.wait())
    canceller = asyncio.create_task(ctx.cancel.wait())
    await asyncio.wait({waiter, canceller}, return_when=asyncio.FIRST_COMPLETED)
    if ctx.cancel.is_set():
        await manager.stop(info.id)
    canceller.cancel()
    out = "\n".join(info.tail)
    return ToolResult(info.state == "exited", f"exit_code={info.exit_code} state={info.state}\n{clip(out)}",
                      {"process_id": info.id, "exit_code": info.exit_code})


@tool("start", '<tool name="start" shell="powershell" cwd=".">npm run dev</tool>',
      "Start a long-running background process (dev servers). Returns process id and first output.",
      {"command": S("Command line"), "shell": S("Interpreter", enum=SHELLS), "cwd": S("Working directory")},
      main="command", required=("command",))
async def start(ctx, args, body):
    info, denied = await _spawn(ctx, args, body, background=True)
    if denied:
        return denied
    try:
        await asyncio.wait_for(info.done.wait(), 6)
    except asyncio.TimeoutError:
        pass
    return ToolResult(info.state in ("running", "exited"),
                      f"process_id={info.id} state={info.state}\n{clip(chr(10).join(info.tail), 3000)}",
                      {"process_id": info.id})


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


@tool("fetch_url", '<tool name="fetch_url" url="https://..."></tool>',
      "Read a web page as plain text (real-browser fallback for JS pages). If the result says BLOCKED, do not retry it.",
      {"url": S("https:// URL")}, required=("url",))
async def fetch_url(ctx, args, body):
    from . import web
    url = args.get("url") or body.strip()
    if msg := await _network_gate(ctx, {"tool": "fetch_url", "url": url}):
        return ToolResult(False, msg)
    r = await web.fetch(url)
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
    if not r["pages"]:
        parts.append("No source could be read. Search snippets:\n" +
                     "\n".join(f"- {x['title']} <{x['url']}>: {x['snippet']}" for x in r["results"]))
    return ToolResult(bool(r["pages"] or r["results"]), clip("\n\n".join(parts), 14000),
                      {"sources": [p["url"] for p in r["pages"]]})


@tool("browser_check", '<tool name="browser_check" url="http://localhost:5173">what to verify</tool>',
      "Visual Tester: open the page headless (Playwright), screenshot it, and have the vision model review it.",
      {"url": S("Page URL"), "criteria": S("What to verify")}, main="criteria", required=("url",))
async def browser_check(ctx, args, body):
    from .visual import capture_and_review
    shot, review, console = await capture_and_review(args["url"], body.strip(), ctx.session_dir or ctx.root)
    return ToolResult(True, f"screenshot: {shot}\nconsole errors: {console or 'none'}\nvisual review:\n{review}",
                      {"screenshot": shot})


@tool("make_doc", '<tool name="make_doc" type="docx|xlsx|pdf|pptx" path="docs/report.docx">markdown or JSON content</tool>',
      "Generate an office document. docx/pdf/pptx take markdown (# headings, - bullets; '---' splits slides); "
      "xlsx takes a JSON array of rows.",
      {"type": S("Document type", enum=["docx", "xlsx", "pdf", "pptx"]), "path": S("Output path"),
       "content": S("Markdown, or JSON rows for xlsx")}, main="content", required=("path", "content"))
async def make_doc(ctx, args, body):
    from .docs_gen import generate
    target = _path(ctx, args["path"])
    if msg := await gate(ctx, {"tool": "make_doc", "path": str(target)}, policy.decide_file_write(target, ctx.root, ctx.mode)):
        return ToolResult(False, msg)
    await asyncio.to_thread(generate, args.get("type") or target.suffix.lstrip("."), body, target)
    ctx.files_changed.append(args["path"])
    return ToolResult(True, f"generated {args['path']}", {"path": args["path"]})


def b64_file(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode()


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


TODO_STATES = ("pending", "in_progress", "completed")


@tool("todo", '<tool name="todo">[{"content": "Create the database schema", "status": "in_progress"}, ...]</tool>',
      "Task list shown live to the user. For any task with 3 or more steps, call it first with the whole plan "
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
