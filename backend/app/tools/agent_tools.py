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


# Names models use for an MCP argument the tool calls otherwise (Playwright: ref -> target, path -> filename,
# expression -> function). One wasted turn each in a real run; renamed only when the tool has no such argument itself.
MCP_ALIASES = {
    "target": ("ref", "element_ref", "selector", "locator"),
    "filename": ("path", "file", "file_path", "filepath", "output", "save_path"),
    "function": ("expression", "script", "code", "js", "javascript"),
    "url": ("href", "link", "address"),
    "text": ("value", "content", "input"),
    "query": ("q", "search", "keywords"),
}


def mcp_args(raw) -> dict:
    """MCP arguments as models write them: in a fence, with trailing commas, \\' inside a string (Drive queries:
    "name contains \\'fatura\\'" is not valid JSON and failed with 'arguments must be a JSON object'), or as a
    Python dict. Raises ValueError when it is not an object."""
    if isinstance(raw, dict):
        return raw
    s = re.sub(r"^```[\w-]*\s*\n?|\n?```\s*$", "", str(raw or "").strip()).strip() or "{}"
    # A long Markdown page / issue text (Notion, Linear) holds raw line breaks and tabs inside its strings, and models
    # add a sentence after the object: strict=False takes the control characters, raw_decode stops at the object's end.
    dec = json.JSONDecoder(strict=False)
    for fix in (lambda x: x, lambda x: x.replace("\\'", "'"), lambda x: re.sub(r",\s*([\]}])", r"\1", x.replace("\\'", "'"))):
        t = fix(s)
        try:
            val = dec.decode(t)
            if isinstance(val, dict):
                return val
        except ValueError:
            pass
        if (i := t.find("{")) >= 0:
            try:
                val, _ = dec.raw_decode(t, i)
                if isinstance(val, dict):
                    return val
            except ValueError:
                pass
    try:
        import ast
        val = ast.literal_eval(re.sub(r"\btrue\b", "True", re.sub(r"\bfalse\b", "False", re.sub(r"\bnull\b", "None", s))))
        if isinstance(val, dict):
            return val
    except (ValueError, SyntaxError):
        pass
    raise ValueError("not a JSON object")


# Answers of Google's Workspace MCP servers that mean "this cannot work yet" - with what is true and what to do, so
# the model stops guessing (it told the user to add OAuth scopes the token already had, and to delete token files).
MCP_KNOWN_ERRORS = (
    (re.compile(r"enrolled in the Google Workspace Developer Preview Program", re.I),
     "[App: this is not a scope or sign-in problem - the token already has the needed permissions. Google's Workspace "
     "MCP servers only work for Cloud projects enrolled in the Google Workspace Developer Preview Program "
     "(https://developers.google.com/workspace/preview). Do the same work with the built-in `google` tool instead "
     "(Google's regular REST APIs, no preview needed; skill google lists the endpoints). Never ask the user to add "
     "scopes, delete tokens or reconnect.]"),
    (re.compile(r"API has not been used in project \d+ before or it is disabled", re.I),
     "[App: the API is off in the user's Google Cloud project: the user presses 'Enable the APIs' on the Google card "
     "in Settings > Connections (or opens the link above), waits a few minutes, then asks again. Not a scope problem.]"),
)


def mcp_known_error(server: str, out: str) -> str:
    for pat, note in MCP_KNOWN_ERRORS:
        if pat.search(out or ""):
            return f"{out}\n{note}"
    if server == "github" and re.search(r"\b404\b|Not Found", out or "") and len(out or "") < 2000:
        # nemotron sent owner="AI-IQ-300" (the repository name) and concluded the repository does not exist
        return (f"{out}\n[App: owner is the GitHub login of the account that holds the repository (github/get_me "
                "gives the user's own login; search_repositories query=\"<name> user:<login>\" finds it). Retry with "
                "the right owner before saying it does not exist.]")
    if server.startswith("google-") and (out or "").strip() == "The caller does not have permission":
        return (f"{out}\n[App: the token already has this service's permissions (checked at sign-in), so this is not "
                "a scope problem: Google's Workspace MCP servers need the Developer Preview enrollment. Use the "
                "built-in `google` tool instead (regular REST APIs; skill google lists the endpoints).]")
    return out


def mcp_repair(schema: dict, arguments: dict) -> tuple[dict, list[str]]:
    """Missing required MCP arguments filled from a synonym the model sent, or from the schema's own default / single
    choice (Playwright's take_screenshot requires scale, which has a default). Returns the arguments and what changed."""
    props, fixed = schema.get("properties") or {}, []
    out = dict(arguments)
    for req in schema.get("required") or []:
        if req in out:
            continue
        for alias in MCP_ALIASES.get(req, ()):
            if alias in out and alias not in props:
                val = out.pop(alias)
                if req == "function" and isinstance(val, str) and "=>" not in val and not val.lstrip().startswith("function"):
                    val = f"() => ({val.strip().rstrip(';')})"  # an expression -> the function the tool wants
                out[req] = val
                fixed.append(f"{alias} -> {req}")
                break
        else:
            p = props.get(req) or {}
            if "default" in p:
                out[req] = p["default"]
                fixed.append(f"{req}={p['default']!r} (default)")
            elif isinstance(p.get("enum"), list) and p["enum"]:
                out[req] = p["enum"][0]
                fixed.append(f"{req}={p['enum'][0]!r} (first choice)")
    # A value outside its key's choices that is a choice of another, unset key: moved there. GitHub's
    # search_repositories got order="updated" (order takes asc/desc; "updated" belongs to sort) and was refused.
    for key, val in list(out.items()):
        choices = (props.get(key) or {}).get("enum")
        if not isinstance(choices, list) or val in choices or not isinstance(val, str):
            continue
        home = [k for k, p in props.items() if k not in out and isinstance(p.get("enum"), list) and val in p["enum"]]
        if len(home) == 1:
            out[home[0]] = out.pop(key)
            fixed.append(f"{key}={val!r} -> {home[0]}")
    return out, fixed


MCP_REL_FILE = re.compile(r"(?<![\w/\\:.])(\.?[\w.-]+(?:[\\/][\w .-]+)*[\\/][\w .-]+\.(?:png|jpe?g|webp|gif|pdf|ya?ml|log|json|txt|md|html|csv|zip|mp4|webm))\b")


def mcp_files_home(ctx, server: str, out: str) -> str:
    """Files a stdio MCP server saved under a relative path (".playwright-mcp\\page-...png") live in the server's own
    folder, not the chat's working folder: the model looked for them there, did not find them and gave up the task.
    They are copied into the working folder at the same relative path, and the result says so."""
    from .. import mcp_client
    home = mcp_client.server_dir(server)
    if not home or not out:
        return out
    root = ctx.root.resolve()
    copied = []
    for rel in dict.fromkeys(MCP_REL_FILE.findall(out)):
        src = Path(home, rel.replace("\\", "/"))
        try:
            if not src.is_file() or src.stat().st_size > 50 * 1024 * 1024:
                continue
            dst = (root / rel.replace("\\", "/")).resolve()
            if root not in dst.parents or dst == src.resolve():
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            copied.append(dst.relative_to(root).as_posix())
        except OSError:
            continue
    if copied:
        out += ("\n[App: the MCP server saved these in its own folder; copied into the working folder: "
                + ", ".join(copied[:12]) + "]")
    return out


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
    raw = unwrap_arg(body.strip() or args.get("arguments") or "{}")
    if (inner := re.match(r"<(tool|mcp)\b([^>]*)(?:>(.*?))?(?:</(?:tool|mcp)>)?\s*$", raw, re.S)):
        # Another tag written as the body (<mcp server="git" tool="git_log" arguments>{}, <tool name="run" argv=..>):
        # an mcp tag is that call itself; any other tool is a separate call that never ran.
        from ..agents.stream_parser import attrs as _attrs
        got = _attrs(inner.group(2))
        if inner.group(1) == "tool" and got.get("name", "mcp") != "mcp":
            return ToolResult(False, f"This mcp call's arguments hold a separate `{got['name']}` call, which did not run. "
                                     "Write each call as its own tag; the mcp arguments are only a JSON object.")
        server, name = got.get("server") or server, got.get("tool") or name
        raw = (inner.group(3) or "").strip() or got.get("arguments") or "{}"
    try:
        arguments = mcp_args(raw)
    except ValueError:
        if name.lower() in ("", "list", "help", "?", "tools", "list_tools"):
            arguments = {}  # listing a server's tools needs no arguments: junk in the body is ignored
        else:
            where = ""
            try:
                json.JSONDecoder(strict=False).decode(str(raw).strip())
            except ValueError as e:  # the exact spot, so the next call fixes that instead of guessing
                pos = getattr(e, "pos", None)
                if pos is not None:
                    where = (f" JSON error: {getattr(e, 'msg', e)} at line {getattr(e, 'lineno', '?')} column "
                             f"{getattr(e, 'colno', '?')}, near {str(raw)[max(0, pos - 40):pos + 40]!r}. Usually a "
                             "double quote inside a string that needs a backslash (\\\") .")
            return ToolResult(False, "arguments must be a JSON object, e.g. {\"query\": \"name contains 'invoice'\"} "
                                     f"(received: {str(raw)[:160]!r}).{where} Double quotes around keys and string "
                                     "values; single quotes inside a string need no backslash.")
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
    if server in mcp_client.hidden_servers():
        # seen in the chat history: these refuse every call without Google's Developer Preview
        return ToolResult(False, f"Do not use the {server} MCP server: use the built-in `google` tool for this (Google's "
                                 "REST APIs, same sign-in, it works; skill google lists the endpoints). E.g. Drive "
                                 "search: google url=\"https://www.googleapis.com/drive/v3/files?q=name contains "
                                 "'fatura' and trashed=false&fields=files(id,name,mimeType,webViewLink)\". The OAuth "
                                 "scopes are fine - never ask the user to change them.")
    # Weak models put the tool's own arguments next to server/tool (question="...", repoName="...") instead of inside
    # "arguments": the server then got {} and refused ("Missing required argument"). They are taken from there too.
    extra = {k: v for k, v in args.items() if k not in ("server", "tool", "arguments", "_raw")}
    arguments = {**extra, **arguments}
    all_tools = mcp_client.available_tools()
    servers = list(dict.fromkeys(s for s, _ in all_tools))
    if name.lower() in ("", "list", "help", "?", "tools", "list_tools") and not mcp_client.find_tool(server, name):
        # the server's tools with every argument: the prompt lists most tools by name only
        own = [t for s, t in all_tools if s == server]
        if not own:
            return ToolResult(False, f"No running MCP server '{server}'. Running: {', '.join(servers) or 'none'}.")
        return ToolResult(True, f"MCP server '{server}' tools ({len(own)}):\n" + "\n".join(
            f"- {t['name']}: {(t.get('description') or '').strip()[:300]}\n  arguments: "
            + json.dumps((t.get("inputSchema") or {}).get("properties") or {}, ensure_ascii=False)[:600]
            + f" required: {(t.get('inputSchema') or {}).get('required') or []}" for t in own[:120]))
    spec = mcp_client.find_tool(server, name)
    if not spec:
        same = [t["name"] for s, t in all_tools if s == server]
        have = (f"Tools of {server}: {', '.join(same)}" if same else
                "Running servers: " + ", ".join(f"{s} ({sum(1 for x, _ in all_tools if x == s)} tools)" for s in servers))
        # the nearest names first: nemotron called the missing github/get_issue three times in a row (it is issue_read)
        import difflib
        words = set(re.split(r"[_\W]+", name.lower())) - {"", "get", "list", "read", "the", "a"}
        near = list(dict.fromkeys(difflib.get_close_matches(name, same, 3, 0.5)
                                  + [t for t in same if any(a.startswith(w) or w.startswith(a)
                                                            for w in words for a in t.lower().split("_") if len(a) > 2)]
                                  ))[:6]
        hint = f"Did you mean: {', '.join(near)}? " if near else ""
        return ToolResult(False, f"No MCP tool {server}/{name}. {hint}{have or 'none'}. tool=\"list\" shows a server's tools.")
    schema = spec.get("inputSchema") or {}
    props = schema.get("properties") or {}
    arguments, repaired = mcp_repair(schema, arguments)
    if missing := [r for r in schema.get("required") or [] if r not in arguments]:
        example = {k: f"<{(props.get(k) or {}).get('type', 'value')}>" for k in (schema.get("required") or list(props)[:3])}
        got = json.dumps(arguments, ensure_ascii=False)[:200]
        return ToolResult(False, f"MCP {server}/{name} needs {', '.join(missing)} (received: {got}, body: "
                                 f"{body.strip()[:120]!r}). Call again "
                                 f"with arguments as a JSON object: {json.dumps(example, ensure_ascii=False)}. "
                                 + (f"Nothing you sent arrived - write it exactly like this: <tool name=\"mcp\" "
                                    f"server=\"{server}\" tool=\"{name}\">{json.dumps(example, ensure_ascii=False)}"
                                    "</tool> (the JSON between the tags, with real values). "
                                    if not body.strip() else "") +
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
    if server.startswith("google-"):
        from .. import connections as _conn
        _conn.google_mcp_seen(bool(_conn.MCP_PREVIEW_ERR.search(out or "")))  # hides / shows the google-* servers
    out = mcp_known_error(server, await asyncio.to_thread(mcp_files_home, ctx, server, out))
    if repaired:
        out += f"\n[App: arguments adjusted to the tool's names: {', '.join(repaired)}; use these names next time.]"
    return ToolResult(ok, clip(out), {"server": server, "name": name})


def _b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode((s or "") + "=" * (-len(s or "") % 4))


def gmail_message(m: dict) -> dict:
    """A Gmail message as a model can read it: headers, labels and the text body (base64 parts decoded, HTML
    stripped) instead of the nested MIME payload."""
    pay = m.get("payload") or {}
    hdr = {h.get("name", "").lower(): h.get("value", "") for h in pay.get("headers") or []}
    texts, html, files = [], [], []

    def walk(p):
        mt = p.get("mimeType", "")
        data = (p.get("body") or {}).get("data")
        if p.get("filename"):
            files.append({"name": p["filename"], "mimeType": mt, "attachmentId": (p.get("body") or {}).get("attachmentId"),
                          "size": (p.get("body") or {}).get("size")})
        elif data and mt == "text/plain":
            texts.append(_b64d(data).decode("utf-8", "replace"))
        elif data and mt == "text/html":
            html.append(_b64d(data).decode("utf-8", "replace"))
        for q in p.get("parts") or []:
            walk(q)
    walk(pay)
    text = "\n".join(texts)
    if not text and html:
        text = re.sub(r"[ \t]+", " ", re.sub(r"<[^>]+>", " ", re.sub(r"(?is)<(script|style).*?</\1>", "", "\n".join(html))))
        text = re.sub(r"\n\s*\n+", "\n\n", text)
    out = {"id": m.get("id"), "threadId": m.get("threadId"), "labels": m.get("labelIds"),
           **{k: hdr[k] for k in ("from", "to", "cc", "subject", "date") if k in hdr},
           "snippet": m.get("snippet")}
    if pay:
        out["text"] = text.strip()[:12000]
    if files:
        out["attachments"] = files
    return {k: v for k, v in out.items() if v not in (None, "", [])}


def gmail_raw(body: dict) -> dict:
    """{to, subject, text[, cc, bcc, html, threadId, inReplyTo]} -> the base64url RFC 822 message Gmail wants, so the
    model never builds MIME by hand. Returns the body unchanged when it already has raw/message."""
    if not isinstance(body, dict) or "raw" in body or "message" in body or not ({"to", "subject", "text", "html"} & set(body)):
        return body
    from email.message import EmailMessage
    msg = EmailMessage()
    for k, h in (("to", "To"), ("cc", "Cc"), ("bcc", "Bcc"), ("subject", "Subject")):
        if body.get(k):
            v = body[k]
            msg[h] = ", ".join(v) if isinstance(v, list) else str(v)
    if body.get("inReplyTo"):
        msg["In-Reply-To"] = msg["References"] = str(body["inReplyTo"])
    msg.set_content(str(body.get("text") or re.sub(r"<[^>]+>", "", str(body.get("html") or ""))))
    if body.get("html"):
        msg.add_alternative(str(body["html"]), subtype="html")
    raw = {"raw": base64.urlsafe_b64encode(msg.as_bytes()).decode().rstrip("=")}
    if body.get("threadId"):
        raw["threadId"] = body["threadId"]
    return raw


SELF_ADDR = {"me", "self", "myself", "kendim", "kendime", "ben", "bana"}
_ARG_WRAP = re.compile(r"^<(arguments?|parameters?|args?|input|json)\b[^>]*>(.*?)(?:</\1>)?\s*$", re.S | re.I)


def unwrap_arg(raw):
    """'<argument name="body">{...}</argument>' (nemotron, twice in a row: "body must be JSON") -> '{...}'."""
    if isinstance(raw, str) and (m := _ARG_WRAP.match(raw.strip())):
        return m.group(2).strip()
    return raw


# POST actions that take no body (trash a mail / file, stop a watch...)
GOOGLE_NO_BODY = re.compile(r"/(trash|untrash|stop)$|:(batchClear|clear|undelete)$", re.I)
GOOGLE_ALWAYS_ASK = re.compile(r"/messages/send|/drafts/send|/permissions|:batchDelete|/trash\b", re.I)


@tool("google", '<tool name="google" method="GET" url="https://gmail.googleapis.com/gmail/v1/users/me/messages?q=is:unread&maxResults=10"></tool>',
      "Call a Google REST API with the user's connected Google account: method + full url (query in the url) + the "
      "JSON body IN the body argument (POST/PUT/PATCH need it). Main URLs: Gmail https://gmail.googleapis.com/gmail/v1/"
      "users/me/messages?q=... (then messages/<id>?format=full; drafts body {to, subject, text}); Drive "
      "https://www.googleapis.com/drive/v3/files?q=name contains 'x'; Calendar https://www.googleapis.com/calendar/v3/"
      "calendars/primary/events?timeMin=...&timeMax=...&singleEvents=true&orderBy=startTime; Sheets "
      "https://sheets.googleapis.com/v4/spreadsheets (body {\"properties\": {\"title\": ...}}), values: PUT "
      "spreadsheets/<id>/values/<Sheet>!A1?valueInputOption=USER_ENTERED body {\"values\": [[...]]}; Docs "
      "https://docs.googleapis.com/v1/documents; Contacts https://people.googleapis.com/v1/people/me?personFields=names. "
      "Upload a local file to Drive: POST https://www.googleapis.com/upload/drive/v3/files file=\"report.pdf\" body "
      "{\"name\": \"report.pdf\"}. save=<path> stores a download (GET only). use_skill google has every endpoint.",
      {"method": S("GET (default), POST, PUT, PATCH or DELETE"),
       "url": S("Full URL, e.g. https://www.googleapis.com/drive/v3/files?q=name contains 'invoice'"),
       "body": S("JSON body for POST/PUT/PATCH, as a JSON object (for an upload: the file's metadata, e.g. "
                 "{\"name\": \"report.pdf\", \"parents\": [\"<folder id>\"]})"),
       "file": S("Upload: a file in the working folder to send (Drive: POST https://www.googleapis.com/upload/drive/"
                 "v3/files, or PATCH .../upload/drive/v3/files/<id> to replace a file's content)"),
       "save": S("Download (GET only): save the response - a file's content (alt=media) or an export - to this "
                 "path in the working folder")},
      main="body", required=("url",))
async def google(ctx, args, body):
    from urllib.parse import parse_qsl, urlsplit, urlunsplit
    from .. import connections as conn
    method = str(args.get("method") or "GET").upper()
    url = str(args.get("url") or "").strip()
    if method not in ("GET", "POST", "PUT", "PATCH", "DELETE"):
        return ToolResult(False, "method is GET, POST, PUT, PATCH or DELETE.")
    raw = unwrap_arg(body.strip() or args.get("body") or "")
    upload = str(args.get("file") or args.get("upload") or args.get("media") or "").strip()
    if not upload and method != "GET" and isinstance(raw, str) and raw and not raw.lstrip().startswith(("{", "[")):
        # the file's name written as the body (PATCH .../upload/drive/v3/files/<id> body "Donanim_Raporu.pdf")
        try:
            if _path(ctx, raw.strip()).is_file():
                upload, raw = raw.strip(), ""
        except Exception:  # noqa: BLE001 - not a path: the JSON check below reports it
            pass
    save = str(args.get("save") or "").strip()
    if save and method != "GET":
        if not upload and "/upload/" in url:
            # nemotron sent save="report.pdf" to the upload URL to upload that file: the app wrote Google's 128-byte
            # answer over the 71 KB PDF. save only ever stores a download.
            upload = save
        save = ""
    data = None
    if raw:
        try:
            data = mcp_args(raw) if not isinstance(raw, list) else raw
        except ValueError:
            try:
                data = json.loads(raw)
            except ValueError:
                return ToolResult(False, f"body must be JSON (received: {str(raw)[:160]!r}).")
    if upload:
        return await _google_upload(ctx, method, url, data, upload)
    if "/upload/" in url and method != "GET":
        return ToolResult(False, "An upload needs the local file: call google again with file=\"<path in the working "
                                 "folder>\" (and the metadata, e.g. {\"name\": \"report.pdf\"}, as the body).")
    if method in ("PUT", "PATCH") or (method == "POST" and not GOOGLE_NO_BODY.search(url.split("?")[0])):
        if data in (None, {}, []):
            # nemotron wrote 'body {"properties": {"title": ...}}' as its message text and sent the call without it:
            # the sheet was created untitled, the PUT wrote no cells, and the answer claimed the table was filled.
            return ToolResult(False, f"{method} needs its JSON in the body argument of this call (it was empty, so "
                                     "nothing was sent). Call google again with the same url and body={...} - "
                                     "writing the JSON in your message text does not send it.")
    if not conn.google_connected():
        return ToolResult(False, "Google is not connected. The user connects it in Settings > Connections > Google; "
                                 "never ask for a password or token in the chat.")
    parts = urlsplit(url)
    params = parse_qsl(parts.query, keep_blank_values=True)
    url = urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
    if "gmail.googleapis.com" in url and isinstance(data, dict):
        tgt = data.get("message") if isinstance(data.get("message"), dict) else data
        if str(tgt.get("to") or "").strip().lower() in SELF_ADDR:
            # "kendime taslak": nemotron wrote to="me", which Gmail keeps as a literal, undeliverable address
            try:
                st, _ct, prof = await conn.google_api("GET", "https://gmail.googleapis.com/gmail/v1/users/me/profile")
                if st == 200:
                    tgt["to"] = json.loads(prof).get("emailAddress") or tgt["to"]
            except Exception:  # noqa: BLE001 - the draft still goes out, only the address stays as written
                pass
        if url.rstrip("/").endswith("/drafts") and isinstance(data.get("message"), dict):
            data["message"] = gmail_raw(data["message"])
        else:
            data = gmail_raw(data)
            if url.rstrip("/").endswith("/drafts") and "raw" in data:
                data = {"message": data}
    if method != "GET":
        always = bool(GOOGLE_ALWAYS_ASK.search(url)) or method == "DELETE"
        op = {"tool": "google", "method": method, "url": url, "body": json.dumps(data, ensure_ascii=False)[:600] if data else ""}
        decision = policy.Decision("allow" if ctx.mode == "full" and not always else "ask", "google", [f"{method} {url}"])
        if msg := await gate(ctx, op, decision):
            return ToolResult(False, msg)
    try:
        status, ctype, content = await conn.google_api(method, url, params, data)
    except conn.ConnError as e:
        return ToolResult(False, str(e))
    except Exception as e:  # noqa: BLE001  network
        return ToolResult(False, f"Google request failed: {e}")
    if status >= 400:
        try:
            err = json.loads(content).get("error") or {}
            text = err.get("message") if isinstance(err, dict) else str(err)
        except ValueError:
            text = content[:400].decode("utf-8", "replace")
        out = f"Google answered HTTP {status}: {text}"
        if status == 404 and ("<html" in (text or "").lower() or text in ("Not Found", "")):
            out = (f"Google answered HTTP 404: this URL does not exist ({method} {url}). Check the endpoint (the tool "
                   "description lists the main ones; use_skill google has all), e.g. calendar events are "
                   "GET https://www.googleapis.com/calendar/v3/calendars/primary/events, calendars "
                   "GET .../calendar/v3/users/me/calendarList, free/busy POST .../calendar/v3/freeBusy.")
        if status == 403 and "insufficient" in (text or "").lower():
            out += ("\n[App: the sign-in does not include this permission: the user ticks this service on the Google "
                    "card in Settings > Connections and presses Reconnect.]")
        return ToolResult(False, mcp_known_error("google-", out), {"url": url, "status": status})
    if save:
        f = _path(ctx, save)
        if "json" in ctype and f.suffix.lower() != ".json":
            # Google answered with metadata, not the file (no alt=media / export): written to report.pdf it would
            # replace a real document with 128 bytes of JSON
            return ToolResult(False, "Not saved: Google sent metadata (JSON), not the file's content, so "
                                     f"{_rel(ctx, f)} was left as it is. To download a Drive file use "
                                     "GET https://www.googleapis.com/drive/v3/files/<id>?alt=media (or .../export?"
                                     "mimeType=... for Google Docs/Sheets). The answer:\n"
                                     + clip(content.decode("utf-8", "replace"), 3000), {"url": url})
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(content)
        if isinstance(getattr(ctx, "files_changed", None), list):
            ctx.files_changed.append(_rel(ctx, f))
        return ToolResult(True, f"Saved {len(content)} bytes to {_rel(ctx, f)}.", {"url": url, "path": _rel(ctx, f)})
    if "json" in ctype:
        try:
            d = json.loads(content or b"{}")
        except ValueError:
            d = None
        if isinstance(d, dict) and "gmail.googleapis.com" in url:
            if "payload" in d or ("snippet" in d and "id" in d):
                d = gmail_message(d)
            elif isinstance(d.get("messages"), list) and any("payload" in m for m in d["messages"]):
                d = {**{k: v for k, v in d.items() if k != "messages"}, "messages": [gmail_message(m) for m in d["messages"]]}
        if d is not None:
            return ToolResult(True, clip(json.dumps(d, ensure_ascii=False, indent=1)), {"url": url})
    if ctype.startswith("text/") or "csv" in ctype or "xml" in ctype:
        return ToolResult(True, clip(content.decode("utf-8", "replace")), {"url": url})
    return ToolResult(True, f"Binary response ({ctype or 'unknown type'}, {len(content)} bytes): call again with "
                            "save=\"<file path>\" to store it in the working folder.", {"url": url})


async def _google_upload(ctx, method: str, url: str, meta, upload: str) -> ToolResult:
    """A local file to Google (Drive upload / replace content). The plain Drive URL is turned into the upload one."""
    import mimetypes
    from urllib.parse import parse_qsl, urlsplit, urlunsplit
    from .. import connections as conn
    try:
        f = _path(ctx, upload)
    except Exception as e:  # noqa: BLE001 - outside the working folder
        return ToolResult(False, f"file: {e}")
    if not f.is_file():
        return ToolResult(False, f"file: {upload} was not found in the working folder (list_dir shows what is there).")
    if f.stat().st_size > 2 * 1024 ** 3:
        return ToolResult(False, "file: larger than 2 GB, too large to upload from here.")
    if method not in ("POST", "PATCH", "PUT"):
        method = "POST"
    parts = urlsplit(url)
    path = parts.path
    if "/upload/" not in path and re.match(r"/drive/v3/files(/[\w-]+)?$", path):
        path = "/upload" + path  # https://www.googleapis.com/drive/v3/files -> the upload endpoint
    if "/upload/" not in path:
        return ToolResult(False, "file= uploads need an upload URL, e.g. POST https://www.googleapis.com/upload/drive/"
                                 "v3/files (new file) or PATCH .../upload/drive/v3/files/<id> (new content).")
    if method != "PATCH" and re.search(r"/files/[\w-]+$", path):
        method = "PATCH"  # POST / PUT to /files/<id> does not exist: replacing a file's content is PATCH
    target = urlunsplit(("https", "www.googleapis.com" if "drive" in path else parts.netloc, path, "", ""))
    params = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)]
    if not any(k == "fields" for k, _ in params):
        params.append(("fields", "id,name,mimeType,size,webViewLink"))
    meta = meta if isinstance(meta, dict) else {}
    if method == "POST" and not meta.get("name"):
        meta["name"] = f.name
    mime = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
    op = {"tool": "google", "method": method, "url": target, "file": _rel(ctx, f), "body": json.dumps(meta)[:300]}
    decision = policy.Decision("allow" if ctx.mode == "full" else "ask", "google", [f"{method} {target} ({f.name})"])
    if msg := await gate(ctx, op, decision):
        return ToolResult(False, msg)
    try:
        status, ctype, content = await conn.google_upload(method, target, params, meta, f, mime)
    except conn.ConnError as e:
        return ToolResult(False, str(e))
    except Exception as e:  # noqa: BLE001  network
        return ToolResult(False, f"Google upload failed: {e}")
    text = content.decode("utf-8", "replace")
    if status >= 400:
        try:
            text = (json.loads(content).get("error") or {}).get("message") or text
        except (ValueError, AttributeError):
            pass
        return ToolResult(False, f"Google answered HTTP {status} to the upload: {text[:600]}", {"url": target})
    try:
        d = json.loads(content)
    except ValueError:
        d = {}
    size = int(d.get("size") or 0)
    if d.get("size") is not None and size != f.stat().st_size:
        return ToolResult(False, f"Uploaded, but Drive reports {size} bytes for a {f.stat().st_size}-byte file: "
                                 f"check it. {text[:400]}", {"url": target})
    return ToolResult(True, f"Uploaded {_rel(ctx, f)} ({f.stat().st_size} bytes) to Google: "
                            + json.dumps(d, ensure_ascii=False), {"url": target, "id": d.get("id"),
                                                                  "link": d.get("webViewLink")})


@tool("mcp_add",'<tool name="mcp_add" id="github" command="npx" args=\'["-y", "@modelcontextprotocol/server-github"]\'>{"GITHUB_PERSONAL_ACCESS_TOKEN": "..."}</tool>',
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


@tool("recall", '<tool name="recall" part="files|commands|failures|tasks|env|tools|open|all" query="optional word"></tool>',
      "Read this chat's ledger: what earlier tasks really did, recorded by the app (environment facts, every file made "
      "with its size, commands run, failures, one line per task, items left open, servers still running). Use it "
      "instead of guessing or re-checking when the user refers to earlier work, or before redoing something.",
      {"part": S("Which part (default all)", enum=["all", "env", "files", "commands", "failures", "tasks", "tools", "open"]),
       "query": S("Only lines that contain this text (a file name, a tool, a word)")}, main="query")
async def recall(ctx, args, body):
    from ..agents import ledger
    sid = (ctx.owner or "").split(":")[0]
    if not sid:
        return ToolResult(False, "No chat record here.")
    try:
        text = ledger.full(sid, str(args.get("part") or "all").lower(), str(args.get("query") or body or "").strip())
    except ValueError:
        return ToolResult(False, "No chat record here.")
    return ToolResult(True, clip(text, 6000))


@tool("use_skill", '<tool name="use_skill">skill-name</tool>',
      "Load the full instructions of a skill listed under 'Available skills' when the request matches it; then follow them.",
      {"name": S("Skill name")}, main="name", required=("name",))
async def use_skill(ctx, args, body):
    from ..agents import catalog
    # the name under another key (skill="docs", id=, value=) or as a bare word in the body: an empty name failed with
    # "Unknown skill ''" and the model went on without the skill's instructions
    name = str(body.strip() or args.get("name") or args.get("skill") or args.get("id") or args.get("value")
               or next((v for k, v in args.items() if isinstance(v, str) and k != "_raw" and v.strip()), "")).strip()
    name = name.lstrip("/").split()[0].lower() if name else ""
    skills = catalog.skills()
    if name not in skills and (close := [s for s in skills if name and (s.startswith(name) or name.startswith(s))]):
        name = close[0]
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
# Not a plan item: tool markup ('<tool name="run" ...>') or a raw command line ('& "C:\...\gradle.bat" assembleDebug')
JUNK_ITEM = re.compile(r"^\s*(?:</?\w[\w-]*(?:\s[^>]*)?/?>|&\s*[\"'$]|\$\w+\s*=|[\"']?[A-Za-z]:[\\/][^\s\"']*\.(?:exe|bat|cmd|ps1)\b)|<tool\b",
                       re.I)
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
      "docs (make/read PDF, Word, Excel, PowerPoint), memory (remember rules, recall earlier tasks of this chat, save skills/agents), project (symbols, "
      "impact), team (agent team, ask another model), mcp (connected MCP servers), mcp_setup (mcp_search: find an "
      "MCP server for any service on the registry / npm / GitHub; mcp_add: connect it), system (system_info overview, hardware_info, software_info, mobile_info), mobile (mobile_env: Android emulator / iOS simulator, "
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
    if isinstance(add, str) and add.strip().startswith("["):
        try:  # native calls send every field as text: add="[]" became an item called "[]"
            add = json.loads(add)
        except ValueError:
            add = [add.strip("[] ")]
    for c in (add if isinstance(add, list) else [add]):
        if str(c).strip() and not JUNK_ITEM.search(str(c)):
            items.append({"content": str(c).strip()[:200], "status": "pending"})
    return items


def loose_json(text: str):
    """JSON as weak models write it: in a fence, with trailing commas, single quotes / Python literals, or as plain
    lines ('1. item', '- [x] item'). Returns the parsed value or raises ValueError. (A valid-looking list with one
    trailing comma failed again and again with 'items must be a JSON array', and the model gave up its plan.)"""
    s = str(text or "").strip()
    # A todo call left open swallowed the next call (nemotron: the list became the two "items"
    # '<tool name="run" shell="powershell" cwd="...">' and the gradle command line): nothing from a tag on is the plan.
    if (cut := re.search(r"</?tool\b", s)) and cut.start() > 0:
        s = s[:cut.start()].strip()
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
        if isinstance(it, dict) and str(it.get("content") or "").strip() and not JUNK_ITEM.search(str(it["content"])):
            st =str(it.get("status") or "").strip().lower().replace("-", "_").replace(" ", "_")
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
