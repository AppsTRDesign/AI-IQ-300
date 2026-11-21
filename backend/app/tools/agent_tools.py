"""Tools about the agent itself: code map (symbols, impact), MCP, team and ask_model, memory, skills and agents, need_tools, the to-do list.

Split out of registry.py (round 2026-11-20). registry imports this module at its end and re-exports every name, so registry.X keeps working; import tools from registry, not from here."""
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

from . import registry
from .registry import S, ToolResult, _lang_name, _network_gate, _path, _rel, _text_of, change_preview, clip, gate, tool  # noqa: F401


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
       # A JSON string, not a nested object: an object with no fixed properties came back empty from several models
       # (the lean tool definitions drop its details), so the MCP server got {} and refused. Every model fills a string.
       "arguments": S("The MCP tool's own arguments as a JSON object, every required one, e.g. "
                      "{\"repoName\": \"facebook/react\", \"question\": \"What is it for?\"}")},
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
    # The whole call written as the body ({"arguments": {...}}, {"server": .., "tool": .., "arguments": {...}}) or
    # "arguments" sent as a JSON string inside it: unwrapped (nemotron sent {"arguments": {"query": ...}} three times,
    # the server got {} and refused each time)
    for _ in range(2):
        if isinstance(arguments.get("arguments"), str):
            try:
                arguments["arguments"] = json.loads(arguments["arguments"])
            except ValueError:
                pass
        if isinstance(arguments.get("arguments"), dict) and set(arguments) <= {"arguments", "server", "tool"}:
            server = server or str(arguments.get("server") or "")
            name = name or str(arguments.get("tool") or "")
            arguments = arguments["arguments"]
    if "/" in name and not server:  # tool="server/tool"
        server, name = name.split("/", 1)
    # Weak models put the tool's own arguments next to server/tool (question="...", repoName="...") instead of inside
    # "arguments": the server then got {} and refused ("Missing required argument"). They are taken from there too.
    extra = {k: v for k, v in args.items() if k not in ("server", "tool", "arguments", "_raw")}
    arguments = {**extra, **arguments}
    spec = mcp_client.find_tool(server, name)
    if not spec:
        have = ", ".join(f"{s}/{t['name']}" for s, t in mcp_client.available_tools()[:40]) or "none"
        return ToolResult(False, f"No MCP tool {server}/{name}. Available: {have}")
    schema = spec.get("inputSchema") or {}
    props = schema.get("properties") or {}
    if missing := [r for r in schema.get("required") or [] if r not in arguments]:
        example = {k: f"<{(props.get(k) or {}).get('type', 'value')}>" for k in (schema.get("required") or list(props)[:3])}
        got = json.dumps({k: v for k, v in args.items() if k not in ("server", "tool")}, ensure_ascii=False)[:200]
        return ToolResult(False, f"MCP {server}/{name} needs {', '.join(missing)} (received: {got}, body: "
                                 f"{body.strip()[:120]!r}). Call again "
                                 f"with arguments as a JSON object: {json.dumps(example, ensure_ascii=False)}. "
                                 "Parameters: " + "; ".join(f"{k} ({(v or {}).get('type', '?')}): "
                                                            f"{str((v or {}).get('description', ''))[:80]}"
                                                            for k, v in list(props.items())[:8]))
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
      "find the right package first (or call mcp_search). Typing the whole command line into command works too "
      "(npx gets -y). remove=true disconnects a server.",
      {"id": S("Short id: lowercase letters, digits, - or _"), "command": S("stdio: program (npx, uvx, node, python...)"),
       "args": {"type": "array", "items": {"type": "string"}, "description": "stdio: arguments"},
       "url": S("http transport: server URL"), "env": S("Environment variables / tokens as a JSON object, e.g. {\"API_KEY\": \"...\"}"),
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
    if not st.get("running") and not st.get("needs_auth"):
        return ToolResult(False, f"MCP server '{sid}' was saved but did not start: {st.get('error') or 'unknown error'}. "
                          "Check the package name / command (run it once with run to see its output), then call "
                          "mcp_add again with the same id.")
    tools = ", ".join(t["name"] for t in st.get("tools", [])[:40]) or "none"
    del srv
    if st.get("needs_auth"):
        return ToolResult(False, f"MCP server '{sid}' is saved, but it needs the user's own sign-in (OAuth) - you cannot "
                                 "sign in for them. Tell the user: open Settings > MCP and click 'Sign in' next to "
                                 f"'{sid}'; its tools are usable right after that. Continue with what you can do now.",
                          {"server": sid, "needs_auth": True})
    return ToolResult(True, f"MCP server '{sid}' connected ({shown}). Tools: {tools}. Call them with the mcp tool.",
                      {"server": sid})


@tool("mcp_search", '<tool name="mcp_search">postgres database</tool>',
      "Find MCP servers for a need (a service, database, app, file type...): searches the official MCP registry, npm "
      "and GitHub and returns ranked candidates with READY mcp_add arguments (npm -> npx -y <package>, PyPI -> uvx "
      "<package>, docker, or a hosted url), the environment variables / tokens they need and whether the user must "
      "sign in. The vendor's own and reference servers come first. Then connect the best one with mcp_add and use "
      "its tools through the mcp tool.",
      {"query": S("What the server should do, in English: postgres, notion, slack, figma, pdf, browser...")},
      main="query", required=("query",))
async def mcp_search(ctx, args, body):
    from .. import mcp_client
    q = (args.get("query") or body or "").strip()
    if not q:
        return ToolResult(False, "Say what the MCP server should do.")
    if msg := await registry._network_gate(ctx, {"tool": "mcp_search", "query": q}):
        return ToolResult(False, msg)
    try:
        rows = await mcp_client.search_servers(q, 10)
    except Exception as e:  # noqa: BLE001  the registries are down / offline
        return ToolResult(False, f"MCP search failed: {str(e)[:200]}. Try web_search '{q} MCP server'.")
    if not rows:
        return ToolResult(False, f"No MCP server found for {q!r}. Try other words, or web_search '{q} MCP server'.")
    lines = []
    for i, r in enumerate(rows, 1):
        if r.get("command"):
            how = f"mcp_add id=<short-id> command={r['command']} args={json.dumps(r['args'])}"
        elif r.get("url"):
            how = f"mcp_add id=<short-id> url={r['url']}"
        else:
            how = f"read its README ({r.get('homepage')}) for the command"
        need = f"; needs env: {', '.join(r['env'])}" if r.get("env") else ""
        auth = f"; auth: {r['auth']}" if r.get("auth") else ""
        stars = f" stars {r['stars']}" if r.get("stars") else ""
        home = f"; home: {r['homepage']}" if r.get("homepage") else ""
        lines.append(f"{i}. [{r['source']}{stars}] {r['name']} - {r.get('description') or ''} -> {how}{need}{auth}{home}")
    tail = ("Connect one with mcp_add (put tokens into the body as JSON env). A server that needs a sign-in shows a "
            "'Sign in' button to the user in Settings > MCP.")
    return ToolResult(True, f"MCP servers for {q!r} (best first):\n" + "\n".join(lines) + "\n" + tail, {"results": rows})


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
                             "stage": {"type": "integer", "description": "Order: 1 first; parts of one stage run in parallel"},
                             "role": S("Optional specialist agent for this part (an @agent name from the Agents list)")},
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
STATUS_ALIASES = {"done": "completed", "complete": "completed", "finished": "completed", "checked": "completed",
                  "ok": "completed", "x": "completed", "true": "completed", "tamam": "completed", "bitti": "completed",
                  "tamamlandı": "completed", "yapıldı": "completed", "active": "in_progress", "doing": "in_progress",
                  "running": "in_progress", "current": "in_progress", "started": "in_progress", "inprogress": "in_progress",
                  "todo": "pending", "open": "pending", "not_started": "pending", "waiting": "pending"}


NEED_GROUPS = ["web", "media", "design", "browser", "places", "docs", "memory", "project", "team", "mcp", "mcp_setup",
               "system", "mobile"]


@tool("need_tools", '<tool name="need_tools" groups="web,docs"></tool>',
      "Only the tools this request needs are loaded. To get more, open groups: web (search, research, fetch_url, "
      "web_screenshot), media (inspect_media: see/hear images, videos, audio), design (stock_photo: real photos for "
      "pages; web_screenshot), browser (act in a real browser window), places (maps, nearby venues, the user's location), "
      "docs (make/read PDF, Word, Excel, PowerPoint), memory (remember rules, save skills/agents), project (symbols, "
      "impact), team (agent team, ask another model), mcp (connected MCP servers), mcp_setup (mcp_search: find an "
      "MCP server for any service on the registry / npm / GitHub; mcp_add: connect it), system (system_info: this computer's hardware and OS), mobile (mobile_env: Android emulator / iOS simulator, "
      "Maestro UI tests for mobile apps).",
      {"groups": S("Comma separated group names: " + ", ".join(NEED_GROUPS))}, main="groups", required=("groups",))
async def need_tools(ctx, args, body):  # handled by the orchestrator (it owns the task's tool offer)
    return ToolResult(False, "need_tools is handled by the agent loop.")


def todo_patch(current: list[dict], spec: dict) -> list[dict] | None:
    """A short update of the list the run already has, so a model never retypes the whole plan to tick one item
    (gemma spent 1-2 minutes writing a 1.4K-character list 26 times in one task):
    {"advance": true} finishes the item in progress and starts the next; {"done": [2, 3]} / {"start": 4} by 1-based
    number; {"add": ["Fix the bundler error"]} appends items. None when spec holds none of these."""
    if not current or not isinstance(spec, dict) or not ({"advance", "done", "start", "add"} & spec.keys()):
        return None
    items = [dict(t) for t in current]

    def nums(v) -> list[int]:
        # [4, 5], "4,5,6", "4-8", "[4, 5]", "4 5": weak models send every shape (round 6 sent "4,5,6,7,8" and the
        # items stayed open while the model believed them done)
        out = []
        for x in (v if isinstance(v, list) else [v]):
            for lo, hi, one in re.findall(r"(\d+)\s*(?:-|\.\.|–)\s*(\d+)|(\d+)", str(x)):
                a, b = (int(lo), int(hi)) if lo else (int(one), int(one))
                out.extend(range(a, min(b, a + 100) + 1))
        return [n for n in dict.fromkeys(out) if 1 <= n <= len(items)]
    if str(spec.get("advance", "")).lower() in ("true", "1", "yes"):
        for t in items:
            if t["status"] == "in_progress":
                t["status"] = "completed"
        if nxt := next((t for t in items if t["status"] == "pending"), None):
            nxt["status"] = "in_progress"
    for n in nums(spec.get("done", [])):
        items[n - 1]["status"] = "completed"
    for n in nums(spec.get("start", []))[:1]:
        for t in items:
            if t["status"] == "in_progress":
                t["status"] = "pending"
        items[n - 1]["status"] = "in_progress"
    add = spec.get("add") or []
    for c in (add if isinstance(add, list) else [add]):
        if str(c).strip():
            items.append({"content": str(c).strip()[:200], "status": "pending"})
    return items


def loose_json(text: str):
    """JSON as weak models write it: in a fence, with trailing commas, single quotes / Python literals, or as plain
    lines ('1. item', '- [x] item'). Returns the parsed value or raises ValueError. (A valid-looking list with one
    trailing comma failed again and again with 'items must be a JSON array', and the model gave up its plan.)"""
    s = str(text or "").strip()
    s = re.sub(r"^```[\w-]*\s*\n?|\n?```\s*$", "", s).strip()
    s = re.sub(r"^(?:items|todos)\s*[=:]\s*", "", s)
    for cand in (s, s[s.find("["):s.rfind("]") + 1] if "[" in s and "]" in s else ""):
        if not cand:
            continue
        for fix in (lambda x: x, lambda x: re.sub(r",\s*([\]}])", r"\1", x)):
            try:
                return json.loads(fix(cand))
            except ValueError:
                pass
        try:
            import ast
            val = ast.literal_eval(re.sub(r"\btrue\b", "True", re.sub(r"\bfalse\b", "False", cand)))
            if isinstance(val, (list, dict)):
                return val
        except (ValueError, SyntaxError):
            pass
    lines = [ln for ln in s.split("\n") if ln.strip()]
    if any(re.match(r"^\s*(?:advance|done|start|add|items|status|content)\s*[=:]", ln, re.I) for ln in lines):
        raise ValueError("arguments, not a list")  # advance=true written as the body is not a new plan
    items = []
    for ln in lines:
        m = re.match(r"^\s*(?:[-*•]|\d+[.)])?\s*(\[[ xX>~-]\])?\s*(.+?)\s*$", ln)
        if not m or len(m.group(2)) < 2 or m.group(2)[:1] in "[{":
            raise ValueError("not a list")
        mark = (m.group(1) or "").lower()
        items.append({"content": m.group(2), "status": "completed" if "x" in mark else
                      "in_progress" if ">" in mark or "~" in mark else "pending"})
    if not items:
        raise ValueError("empty")
    return items


@tool("todo", '<tool name="todo">[{"content": "Create the database schema", "status": "in_progress"}, ...]</tool>',
      "Task list shown live to the user. For any task with 3 or more steps, send it with the whole plan in the "
      "same reply as the first actions (not a reply of its own) (short imperative items in the user's language). "
      "Afterwards update it SHORT, never by retyping the list: advance=true (the item in progress is done, the next "
      "starts), done=[numbers] / start=number (1-based), add=[\"new item\"] for work found on the way (a bug fix). "
      "Exactly one item in progress. Finish every item before the final answer.",
      {"items": {"type": "array", "description": "The whole list, in order (first call / a new plan only)",
                 "items": {"type": "object", "properties": {"content": S("Short imperative item"),
                                                            "status": S("Item state", enum=list(TODO_STATES))},
                           "required": ["content", "status"]}},
       "advance": {"type": "boolean", "description": "Finish the item in progress and start the next"},
       "done": {"type": "array", "items": {"type": "integer"}, "description": "Item numbers (1-based) now finished"},
       "start": {"type": "integer", "description": "Item number (1-based) to work on now"},
       "add": {"type": "array", "items": {"type": "string"}, "description": "New items to append"}},
      main="items", required=())
async def todo(ctx, args, body):
    try:
        raw = (loose_json(body) if body.strip() else []) if isinstance(body, str) else body
    except ValueError:
        return ToolResult(False, 'items must be a JSON array like [{"content": "...", "status": "pending"}]')
    if isinstance(raw, dict):
        raw = raw.get("items") or raw.get("todos") or []
    items = []
    for it in raw if isinstance(raw, list) else []:
        if isinstance(it, str):
            it = {"content": it, "status": "pending"}
        if isinstance(it, dict) and str(it.get("content") or "").strip():
            st = str(it.get("status") or "").strip().lower().replace("-", "_").replace(" ", "_")
            # "done" / "complete" / "in-progress" as models write them (nemotron sent "done": the list stayed 0/2
            # completed and it retried for seven turns)
            st = STATUS_ALIASES.get(st, st)
            st = st if st in TODO_STATES else "pending"
            items.append({"content": str(it["content"]).strip()[:200], "status": st})
    if not items:
        return ToolResult(False, "The list is empty. Send all items with content and status.")
    done = sum(i["status"] == "completed" for i in items)
    left = [i["content"] for i in items if i["status"] != "completed"]
    note = f"Next: {left[0]}. Keep going." if left else "All items are completed: give the final answer."
    from ..agents.checks import wrong_language
    if ctx.lang in ("tr", "en") and wrong_language(" ".join(i["content"] for i in items), ctx.lang):
        # The user reads this list: a weak model wrote it in English for a Turkish user
        note += (" [App note: the user's language is " + ("Turkish" if ctx.lang == "tr" else "English")
                 + ": with your next todo call write every item in that language.]")
    return ToolResult(True, f"To-do list updated ({done}/{len(items)} completed). {note}", {"todos": items[:30]})
