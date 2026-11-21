"""MCP client: connects the MCP servers configured in Settings > MCP and exposes their tools to the model.

Transports: stdio (a local command, newline-delimited JSON-RPC) and Streamable HTTP (POST JSON-RPC; the reply is
JSON or an SSE stream). Servers start lazily on first use and are restarted after a crash or a settings change.
The model reaches every MCP tool through the single `mcp` tool (server, tool, arguments), so the tool list and
the prompt prefix stay stable while servers come and go.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import sys
from dataclasses import dataclass, field


from .config import get_secret, load_settings

PROTOCOL = "2025-06-18"
START_TIMEOUT = 20
CALL_TIMEOUT = 120
from .config import VERSION as _APP_VERSION

CLIENT = {"name": "AI IQ 300", "version": _APP_VERSION}
ID_RE = re.compile(r"^[a-z0-9_-]{1,32}$")


class MCPError(Exception):
    pass


# Commands that install or log in and then exit (pasted from a product page as "the MCP"): not servers.
INSTALLER = re.compile(r"\b(skills\s+add|npm\s+(i|install)\b|pip\s+install|auth\s+login|claude\s+mcp\s+add)\b", re.I)


def split_command(command: str, args: list) -> tuple[str, list[str]]:
    """'npx -y pkg dir' typed into the command field becomes ('npx', ['-y', 'pkg', 'dir']) - the whole line was looked
    up as one program name before ("FileNotFoundError"). npx gets -y, so it never waits for "Ok to proceed?"."""
    import shlex
    command = (command or "").strip()
    args = [str(a) for a in args or []]
    if command and not shutil.which(command) and re.search(r"\s", command):
        try:
            parts = shlex.split(command, posix=sys.platform != "win32")
        except ValueError:
            parts = command.split()
        parts = [p.strip('"') for p in parts]
        command, args = parts[0], parts[1:] + args
    if re.fullmatch(r"npx(\.cmd)?", os.path.basename(command), re.I) and not {"-y", "--yes"} & set(args):
        args = ["-y", *args]
    return command, args


def secret_parts(sid: str) -> dict:
    """env / headers values live in secrets.json (they often hold tokens); settings keep only their names."""
    try:
        v = json.loads(get_secret(f"mcp_{sid}") or "{}")
        return v if isinstance(v, dict) else {}
    except json.JSONDecodeError:
        return {}


def servers_cfg() -> dict[str, dict]:
    out = {}
    for k, v in (load_settings().get("mcp_servers") or {}).items():
        if v:
            sec = secret_parts(k)
            out[k] = {**v, "env": sec.get("env") or {}, "headers": sec.get("headers") or {}}
    return out


def _signature(cfg: dict) -> str:
    return json.dumps({k: cfg.get(k) for k in ("transport", "command", "args", "env", "url", "headers")}, sort_keys=True)


@dataclass
class Server:
    sid: str
    cfg: dict
    tools: list[dict] = field(default_factory=list)
    error: str | None = None
    proc: asyncio.subprocess.Process | None = None
    session: str | None = None  # Streamable HTTP: Mcp-Session-Id
    _next: int = 0
    _pending: dict = field(default_factory=dict)
    _reader: asyncio.Task | None = None
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    started: bool = False
    stderr: list[str] = field(default_factory=list)

    @property
    def sig(self) -> str:
        return _signature(self.cfg)

    # ------------------------------------------------------------------ lifecycle
    async def start(self) -> None:
        self.error, self.tools = None, []
        try:
            if self.cfg.get("transport", "stdio") == "stdio":
                await self._spawn()
            init = await self.request("initialize", {"protocolVersion": PROTOCOL, "capabilities": {},
                                                     "clientInfo": CLIENT}, START_TIMEOUT)
            self.cfg["_server_info"] = init.get("serverInfo") or {}
            await self.notify("notifications/initialized")
            tools, cursor = [], None
            for _ in range(20):  # paginated tools/list
                res = await self.request("tools/list", {"cursor": cursor} if cursor else {}, START_TIMEOUT)
                tools += res.get("tools") or []
                cursor = res.get("nextCursor")
                if not cursor:
                    break
            self.tools = [t for t in tools if isinstance(t, dict) and t.get("name")]
            self.started = True
        except Exception as e:  # any failure: report it in the UI and to the model, never crash the app
            self.error = _short(e) + (f" | {' '.join(self.stderr[-3:])[:300]}" if self.stderr else "")
            await self.stop()

    async def _spawn(self) -> None:
        cmd, args = split_command(self.cfg.get("command") or "", self.cfg.get("args") or [])
        if not cmd:
            raise MCPError("no command")
        if INSTALLER.search(" ".join([cmd, *args])):
            raise MCPError(f"'{' '.join([cmd, *args])}' installs something and exits; it is not an MCP server. "
                           "An MCP server command keeps running (e.g. npx -y @modelcontextprotocol/server-filesystem "
                           "C:/folder). For a hosted service use the http transport with its MCP URL.")
        # npx -> npx.cmd on Windows; uv / uvx installed with the app live next to its Python (not always on PATH)
        exe = shutil.which(cmd) or shutil.which(cmd, path=os.path.dirname(sys.executable))
        if not exe:
            need = {"npx": "Node.js (nodejs.org)", "npm": "Node.js (nodejs.org)", "node": "Node.js (nodejs.org)",
                    "uvx": "uv (docs.astral.sh/uv)", "uv": "uv (docs.astral.sh/uv)", "docker": "Docker Desktop"}
            raise MCPError(f"'{cmd}' was not found on this computer" + (f": install {need[cmd]}" if cmd in need else "")
                           + " (or give the full path of the program).")
        # A .cmd/.bat (npx, npm, uvx shims) is started directly: Windows runs it through cmd itself and quotes a
        # path with spaces ("D:\Program Files\nodejs\npx.cmd") correctly. Wrapping it in "cmd /c" broke such paths.
        env = {**os.environ, **{str(k): str(v) for k, v in (self.cfg.get("env") or {}).items()}}
        self.proc = await asyncio.create_subprocess_exec(
            exe, *args, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            env=env, cwd=self.cfg.get("cwd") or None, limit=16 * 1024 * 1024,
            creationflags=0x08000000 if sys.platform == "win32" else 0)  # CREATE_NO_WINDOW
        self._reader = asyncio.create_task(self._read_stdout())
        self._err_reader = asyncio.create_task(self._read_stderr())

    async def stop(self) -> None:
        self.started = False
        for fut in self._pending.values():
            if not fut.done():
                fut.set_exception(MCPError("server stopped"))
        self._pending.clear()
        if self._reader:
            self._reader.cancel()
            self._reader = None
        if self.proc and self.proc.returncode is None:
            try:
                self.proc.kill()
                await asyncio.wait_for(self.proc.wait(), 5)
            except Exception:
                pass
        self.proc = None
        self.session = None

    @property
    def alive(self) -> bool:
        if self.cfg.get("transport", "stdio") == "stdio":
            return self.started and self.proc is not None and self.proc.returncode is None
        return self.started

    # ------------------------------------------------------------------ stdio
    async def _read_stdout(self) -> None:
        proc = self.proc  # (see _read_stderr: self.proc may be cleared while this waits)
        if not (proc and proc.stdout):
            return
        try:
            while line := await proc.stdout.readline():
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue  # servers sometimes print logs on stdout
                self._dispatch(msg)
        finally:
            for fut in self._pending.values():
                if not fut.done():
                    fut.set_exception(MCPError("server exited"))

    async def _read_stderr(self) -> None:
        # The process is held locally: stopping / restarting the server sets self.proc to None while this reader still
        # waits ("'NoneType' object has no attribute 'stderr'" in the log after every restart).
        proc = self.proc
        if not (proc and proc.stderr):
            return
        try:
            while line := await proc.stderr.readline():
                self.stderr = (self.stderr + [line.decode(errors="replace").strip()])[-20:]
        except (OSError, ValueError, asyncio.CancelledError):
            pass

    def _dispatch(self, msg: dict) -> None:
        if not isinstance(msg, dict):
            return
        if "id" in msg and ("result" in msg or "error" in msg):
            fut = self._pending.pop(msg["id"], None)
            if fut and not fut.done():
                if msg.get("error"):
                    fut.set_exception(MCPError(str((msg["error"] or {}).get("message") or msg["error"])))
                else:
                    fut.set_result(msg.get("result") or {})
        elif "id" in msg and msg.get("method"):  # a server->client request (ping, roots...): answer politely
            reply = {"jsonrpc": "2.0", "id": msg["id"],
                     **({"result": {}} if msg["method"] == "ping" else {"error": {"code": -32601, "message": "not supported"}})}
            if self.proc and self.proc.stdin:
                self.proc.stdin.write((json.dumps(reply) + "\n").encode())

    # ------------------------------------------------------------------ JSON-RPC
    async def request(self, method: str, params: dict, timeout: float = CALL_TIMEOUT) -> dict:
        self._next += 1
        rid = self._next
        msg = {"jsonrpc": "2.0", "id": rid, "method": method, "params": params}
        if self.cfg.get("transport", "stdio") == "http":
            return await asyncio.wait_for(self._http(msg), timeout)
        if not (self.proc and self.proc.stdin) or self.proc.returncode is not None:
            raise MCPError("server is not running")
        fut = asyncio.get_running_loop().create_future()
        self._pending[rid] = fut
        self.proc.stdin.write((json.dumps(msg, ensure_ascii=False) + "\n").encode())
        await self.proc.stdin.drain()
        try:
            return await asyncio.wait_for(fut, timeout)
        finally:
            self._pending.pop(rid, None)

    async def notify(self, method: str) -> None:
        msg = {"jsonrpc": "2.0", "method": method}
        if self.cfg.get("transport", "stdio") == "http":
            await self._http(msg, expect=False)
        elif self.proc and self.proc.stdin:
            self.proc.stdin.write((json.dumps(msg) + "\n").encode())
            await self.proc.stdin.drain()

    async def _http(self, msg: dict, expect: bool = True) -> dict:
        from .llm.providers import pooled
        headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
                   "MCP-Protocol-Version": PROTOCOL, **{str(k): str(v) for k, v in (self.cfg.get("headers") or {}).items()}}
        if self.session:
            headers["Mcp-Session-Id"] = self.session
        if not any(k.lower() == "authorization" for k in headers) and (tok := await bearer(self.sid)):
            headers["Authorization"] = f"Bearer {tok}"  # signed in with the server's own OAuth (Settings > MCP)
        async with pooled(timeout=CALL_TIMEOUT) as c, c.stream("POST", self.cfg["url"], json=msg, headers=headers) as r:
            if r.status_code >= 400:
                body = (await r.aread()).decode(errors="replace")[:300]
                if r.status_code in (401, 403) and "resource_metadata" in r.headers.get("www-authenticate", ""):
                    raise MCPError(f"SIGN_IN_REQUIRED: HTTP {r.status_code} - this server needs you to sign in: use "
                                   "the Sign in button (or add its API key as an Authorization header)")
                raise MCPError(f"HTTP {r.status_code}: {body}")
            self.session = r.headers.get("mcp-session-id") or self.session
            if not expect:
                return {}
            if "text/event-stream" in r.headers.get("content-type", ""):
                async for line in r.aiter_lines():
                    if line.startswith("data:"):
                        try:
                            d = json.loads(line[5:].strip())
                        except json.JSONDecodeError:
                            continue
                        if d.get("id") == msg["id"]:
                            if d.get("error"):
                                raise MCPError(str(d["error"].get("message") or d["error"]))
                            return d.get("result") or {}
                raise MCPError("no response in the event stream")
            d = json.loads(await r.aread() or b"{}")
            if isinstance(d, list):
                d = next((x for x in d if x.get("id") == msg["id"]), {})
            if d.get("error"):
                raise MCPError(str(d["error"].get("message") or d["error"]))
            return d.get("result") or {}

    async def call(self, tool: str, arguments: dict) -> tuple[bool, str]:
        res = await self.request("tools/call", {"name": tool, "arguments": arguments})
        parts = []
        for c in res.get("content") or []:
            if c.get("type") == "text":
                parts.append(c.get("text", ""))
            elif c.get("type") == "resource":
                r = c.get("resource") or {}
                parts.append(r.get("text") or f"[resource {r.get('uri', '')}]")
            else:
                parts.append(f"[{c.get('type')} content]")
        if res.get("structuredContent") is not None and not parts:
            parts.append(json.dumps(res["structuredContent"], ensure_ascii=False))
        return not res.get("isError"), "\n".join(parts).strip() or "(empty result)"


def _short(e: Exception) -> str:
    text = str(e) or type(e).__name__
    return f"{type(e).__name__}: {text}"[:400] if not isinstance(e, MCPError) else text[:400]


# ---------------------------------------------------------------------- manager
_servers: dict[str, Server] = {}
_start_lock = asyncio.Lock()


async def ensure(sid: str | None = None) -> None:
    """Start enabled servers (or one) that are not running; restart those whose settings changed."""
    async with _start_lock:
        cfgs = servers_cfg()
        for old in [k for k in _servers if k not in cfgs or not cfgs[k].get("enabled", True)]:
            await _servers.pop(old).stop()
        todo = []
        for k, cfg in cfgs.items():
            if (sid and k != sid) or not cfg.get("enabled", True):
                continue
            s = _servers.get(k)
            if s and s.sig == _signature(cfg) and (s.alive or s.error):
                continue  # running, or failed with these settings (retried by test / settings change)
            if s:
                await s.stop()
            s = _servers[k] = Server(k, dict(cfg))
            todo.append(s.start())
        if todo:
            await asyncio.gather(*todo)


async def restart(sid: str) -> Server | None:
    async with _start_lock:
        if s := _servers.pop(sid, None):
            await s.stop()
    await ensure(sid)
    return _servers.get(sid)


async def shutdown() -> None:
    for s in list(_servers.values()):
        await s.stop()
    _servers.clear()


def status() -> dict[str, dict]:
    out = {}
    for k, cfg in servers_cfg().items():
        s = _servers.get(k)
        err = s.error if s else None
        out[k] = {"enabled": cfg.get("enabled", True), "running": bool(s and s.alive), "error": err,
                  "needs_auth": bool(err and "SIGN_IN_REQUIRED" in err),
                  "signed_in": bool(oauth_data(k).get("access_token")),
                  "tools": [{"name": t["name"], "description": (t.get("description") or "")[:300],
                             "read_only": bool((t.get("annotations") or {}).get("readOnlyHint")),
                             "input_schema": t.get("inputSchema") or {}} for t in (s.tools if s else [])]}
    return out


def available_tools() -> list[tuple[str, dict]]:
    return [(k, t) for k, s in _servers.items() if s.alive for t in s.tools]


def _schema_hint(schema: dict) -> str:
    props = (schema or {}).get("properties") or {}
    req = set((schema or {}).get("required") or [])
    bits = [f"{n}{'' if n in req else '?'}:{(p or {}).get('type', 'any')}" for n, p in list(props.items())[:12]]
    return "{" + ", ".join(bits) + "}"


def picked_tools(request: str) -> list[tuple[str, str]]:
    """'server/tool' names in the request (the composer's MCP tool chip, or typed) whose server is configured."""
    # A #server/tool chip or the MCP mode chip's "server/tool MCP ..." names a tool even when that server is not
    # installed (then the model is told so); a bare "a/b" counts only when "a" is a configured server.
    cfg = servers_cfg()
    out = []
    for m in re.finditer(r"(#?)\b([a-z0-9_-]{1,32})/([A-Za-z0-9_.-]{1,64})\b(\s+MCP\b)?", request or ""):
        if m.group(1) or m.group(4) or m.group(2) in cfg:
            out.append((m.group(2), m.group(3)))
    return list(dict.fromkeys(out))


def prompt_section(request: str = "") -> str:
    tools = available_tools()
    picked = picked_tools(request)
    # the tool the user picked goes first (never cut by the 80-tool limit) with its whole argument list
    first = [(k, t) for k, t in tools if (k, t["name"]) in picked]
    tools = first + [x for x in tools if x not in first]
    missing = [f"{s}/{t}" for s, t in picked if not any(k == s and x["name"] == t for k, x in tools)]
    note = ""
    if missing:  # picked, but its server is off / failed / has no such tool: say it once, no guessing, no retries
        from .mcp_catalog import CATALOG
        cfg = servers_cfg()
        ready = []  # not installed but in the ready catalog: the model can connect it itself
        for s in dict.fromkeys(x.split("/")[0] for x in missing):
            c = next((e for e in CATALOG if e["id"] == s and not e.get("auth")), None)
            if c and s not in cfg:
                ready.append(f'mcp_add {{"id": "{s}", ' + (f'"url": "{c["url"]}"' if c["transport"] == "http" else
                             f'"command": "{c["command"]}", "args": {json.dumps(c["args"].split())}') + "}")
        note = ("\nNOT AVAILABLE now: " + ", ".join(missing) + " (its server is not installed / not running, or has no "
                "such tool). Do not pretend to call it and do not repeat yourself. "
                + ("It is a ready server: connect it with " + "; ".join(ready) + ", then call the tool. " if ready else
                   "Tell the user in one sentence to switch it on or add it in Settings > MCP, then answer what you "
                   "can without it."))
    if not tools:
        return ("# MCP tools" + note) if note else ""
    lines = [f"- {k}/{t['name']}: {(t.get('description') or '').strip().splitlines()[0][:200] if t.get('description') else ''} "
             f"args {_schema_hint(t.get('inputSchema') or {})}" for k, t in tools[:80]]
    s0, t0 = tools[0]
    ex = {k: "..." for k in ((t0.get("inputSchema") or {}).get("required") or [])[:3]}
    return ("# MCP tools (external servers the user connected)\nCall them with the mcp tool: server, tool and EVERY "
            "required argument (no ?) inside arguments, e.g. mcp {\"server\": \"" + s0 + "\", \"tool\": \"" + t0["name"]
            + "\", \"arguments\": " + json.dumps(ex) + "}. Prefer them over improvised scripts when they fit the "
            "task." + (" The user picked " + ", ".join(f"{k}/{t['name']}" for k, t in first) + ": call it." if first else "")
            + note + "\n" + "\n".join(lines))


def find_tool(server: str, tool: str) -> dict | None:
    s = _servers.get(server)
    return next((t for t in s.tools if t["name"] == tool), None) if s else None


async def call(server: str, tool: str, arguments: dict) -> tuple[bool, str]:
    s = _servers.get(server)
    if not s or not s.alive:
        await ensure(server)
        s = _servers.get(server)
    if not s or not s.alive:
        raise MCPError(f"MCP server '{server}' is not running" + (f": {s.error}" if s and s.error else ""))
    try:
        return await s.call(tool, arguments)
    except MCPError as e:
        if s.cfg.get("transport", "stdio") == "stdio" and not s.alive:  # crashed: one restart, one retry
            s2 = await restart(server)
            if s2 and s2.alive:
                return await s2.call(tool, arguments)
        raise e


# ---------------------------------------------------------------------- OAuth sign-in (HTTP servers)
# The MCP authorization flow: the server answers 401 with its protected-resource metadata -> its authorization
# server's metadata -> dynamic client registration -> authorization code with PKCE in the user's browser -> bearer
# token (refreshed when it expires). Krea, Poko and most hosted MCP servers sign in this way; a server that wants a
# plain API key takes it as a header (Authorization: Bearer <key>) instead.
_OAUTH_PENDING: dict[str, dict] = {}


def oauth_data(sid: str) -> dict:
    try:
        v = json.loads(get_secret(f"mcp_oauth_{sid}") or "{}")
        return v if isinstance(v, dict) else {}
    except json.JSONDecodeError:
        return {}


def _oauth_save(sid: str, data: dict | None) -> None:
    from .config import set_secret
    set_secret(f"mcp_oauth_{sid}", json.dumps(data) if data else None)


async def _get_json(c, url: str) -> dict:
    try:
        r = await c.get(url, headers={"Accept": "application/json", "MCP-Protocol-Version": PROTOCOL})
        if r.status_code == 200 and "json" in r.headers.get("content-type", ""):
            d = r.json()
            return d if isinstance(d, dict) else {}
    except Exception:
        pass
    return {}


async def oauth_start(sid: str, redirect_uri: str) -> str:
    """The browser URL that signs the user in to an HTTP MCP server (MCP authorization spec)."""
    import base64
    import hashlib
    import secrets
    import time
    from urllib.parse import urlencode, urlsplit

    import httpx
    cfg = servers_cfg().get(sid)
    if not cfg or cfg.get("transport") != "http":
        raise MCPError("sign-in is only for http servers")
    url = cfg["url"]
    u = urlsplit(url)
    origin = f"{u.scheme}://{u.netloc}"
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as c:
        r = await c.post(url, json={"jsonrpc": "2.0", "id": 1, "method": "initialize",
                                    "params": {"protocolVersion": PROTOCOL, "capabilities": {}, "clientInfo": CLIENT}},
                         headers={"Content-Type": "application/json", "Accept": "application/json, text/event-stream"})
        www = r.headers.get("www-authenticate", "")
        if r.status_code not in (401, 403):
            raise MCPError(f"this server answered HTTP {r.status_code} without asking to sign in: no sign-in is needed")
        m = re.search(r'resource_metadata="([^"]+)"', www)
        sm = re.search(r'scope="([^"]+)"', www)
        scope = sm[1] if sm else ""
        cands = ([m[1]] if m else []) + [f"{origin}/.well-known/oauth-protected-resource{u.path}",
                                          f"{origin}/.well-known/oauth-protected-resource"]
        res_meta: dict = {}
        for cu in cands:
            res_meta = await _get_json(c, cu)
            if res_meta.get("authorization_servers"):
                break
        auth_server = ((res_meta.get("authorization_servers") or [origin])[0]).rstrip("/")
        resource = res_meta.get("resource") or url
        scope = scope or " ".join(res_meta.get("scopes_supported") or [])
        a = urlsplit(auth_server)
        base, path = f"{a.scheme}://{a.netloc}", a.path.rstrip("/")
        meta: dict = {}
        for cu in (f"{base}/.well-known/oauth-authorization-server{path}", f"{base}/.well-known/openid-configuration{path}",
                   f"{auth_server}/.well-known/oauth-authorization-server", f"{auth_server}/.well-known/openid-configuration"):
            meta = await _get_json(c, cu)
            if meta.get("authorization_endpoint"):
                break
        if not meta.get("authorization_endpoint"):
            raise MCPError("this server offers no browser sign-in: add its API key as a header "
                           "(Authorization: Bearer <key>) with the edit button")
        saved = oauth_data(sid)
        client_id, client_secret = saved.get("client_id"), saved.get("client_secret")
        issuer = meta.get("issuer", base)
        if not client_id or saved.get("redirect_uri") != redirect_uri or saved.get("issuer") != issuer:
            if not meta.get("registration_endpoint"):
                raise MCPError("this server does not let apps register themselves: add its API key as a header "
                               "(Authorization: Bearer <key>) with the edit button")
            body = {"client_name": "AI IQ 300", "redirect_uris": [redirect_uri],
                    "grant_types": ["authorization_code", "refresh_token"], "response_types": ["code"],
                    "token_endpoint_auth_method": "none"}
            if scope:
                body["scope"] = scope
            rr = await c.post(meta["registration_endpoint"], json=body)
            if rr.status_code >= 400:
                raise MCPError(f"app registration failed: HTTP {rr.status_code} {rr.text[:200]}")
            reg = rr.json()
            client_id, client_secret = reg.get("client_id"), reg.get("client_secret")
            _oauth_save(sid, {"client_id": client_id, "client_secret": client_secret, "redirect_uri": redirect_uri,
                              "issuer": issuer})
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state = secrets.token_urlsafe(18)
    for k in [k for k, v in _OAUTH_PENDING.items() if time.time() - v["at"] > 900]:
        _OAUTH_PENDING.pop(k, None)
    _OAUTH_PENDING[state] = {"sid": sid, "verifier": verifier, "client_id": client_id, "client_secret": client_secret,
                             "token_endpoint": meta["token_endpoint"], "redirect_uri": redirect_uri, "resource": resource,
                             "issuer": issuer, "at": time.time()}
    params = {"response_type": "code", "client_id": client_id, "redirect_uri": redirect_uri, "state": state,
              "code_challenge": challenge, "code_challenge_method": "S256", "resource": resource}
    if scope:
        params["scope"] = scope
    sep = "&" if "?" in meta["authorization_endpoint"] else "?"
    return meta["authorization_endpoint"] + sep + urlencode(params)


async def _token(flow: dict, form: dict) -> dict:
    import time

    import httpx
    form = {**form, "client_id": flow["client_id"]}
    if flow.get("resource"):
        form["resource"] = flow["resource"]
    if flow.get("client_secret"):
        form["client_secret"] = flow["client_secret"]
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.post(flow["token_endpoint"], data=form, headers={"Accept": "application/json"})
    if r.status_code >= 400:
        raise MCPError(f"token request failed: HTTP {r.status_code} {r.text[:200]}")
    tok = r.json()
    if not tok.get("access_token"):
        raise MCPError("the server sent no access token")
    return {"access_token": tok["access_token"], "refresh_token": tok.get("refresh_token") or flow.get("refresh_token"),
            "expires_at": time.time() + float(tok["expires_in"]) if tok.get("expires_in") else 0}


async def oauth_finish(state: str, code: str) -> str:
    """The browser came back with a code: trade it for a token and keep it (secrets.json). Returns the server id."""
    flow = _OAUTH_PENDING.pop(state, None)
    if not flow:
        raise MCPError("this sign-in link expired or was already used; start the sign-in again")
    tok = await _token(flow, {"grant_type": "authorization_code", "code": code, "redirect_uri": flow["redirect_uri"],
                              "code_verifier": flow["verifier"]})
    keep = {k: flow[k] for k in ("client_id", "client_secret", "redirect_uri", "token_endpoint", "resource", "issuer")}
    _oauth_save(flow["sid"], {**keep, **tok})
    return flow["sid"]


async def bearer(sid: str) -> str | None:
    """The signed-in token of a server, refreshed shortly before it expires."""
    import time
    d = oauth_data(sid)
    if not d.get("access_token"):
        return None
    if d.get("expires_at") and time.time() > d["expires_at"] - 60 and d.get("refresh_token") and d.get("token_endpoint"):
        try:
            d.update(await _token(d, {"grant_type": "refresh_token", "refresh_token": d["refresh_token"]}))
            _oauth_save(sid, d)
        except MCPError:
            return None  # the user signs in again
    return d["access_token"]


def oauth_signout(sid: str) -> None:
    d = oauth_data(sid)
    keep = {k: d[k] for k in ("client_id", "client_secret", "redirect_uri", "issuer") if d.get(k)}
    _oauth_save(sid, keep or None)


# ---------------------------------------------------------------------- finding servers (for the agent)
REGISTRY = "https://registry.modelcontextprotocol.io/v0/servers"


def _env_list(items) -> list[str]:
    out = []
    for e in items or []:
        if isinstance(e, dict) and e.get("name"):
            flags = [f for f, on in (("required", e.get("isRequired") or e.get("is_required")),
                                     ("secret", e.get("isSecret") or e.get("is_secret"))) if on]
            out.append(e["name"] + (f" ({', '.join(flags)})" if flags else ""))
    return out


async def search_servers(query: str, limit: int = 10) -> list[dict]:
    """MCP servers for a need from the official MCP registry, npm and GitHub, each with ready mcp_add arguments.
    [{source, name, description, command, args, url, env, auth, homepage, stars}]"""
    import asyncio as _asyncio

    import httpx
    q = " ".join(str(query or "").split())[:80]
    if not q:
        return []
    out: list[dict] = []
    seen: set[str] = set()

    def add(item: dict) -> None:
        key = (item.get("args") or [None, item.get("url") or item["name"]])[-1] if item.get("command") else (item.get("url") or item["name"])
        key = str(key).lower()
        if key not in seen:
            seen.add(key)
            out.append(item)

    async with httpx.AsyncClient(timeout=15, follow_redirects=True, headers={"User-Agent": "AI-IQ-300 (mcp search)"}) as c:
        async def registry():
            r = await c.get(REGISTRY, params={"search": q, "limit": 30})
            rows = []
            for s in (r.json().get("servers") or []) if r.status_code == 200 else []:
                srv = s.get("server", s)
                desc = (srv.get("description") or "")[:200]
                home = ((srv.get("repository") or {}).get("url") or "")
                for p in srv.get("packages") or []:
                    kind = (p.get("registryType") or p.get("registry_type") or p.get("registry_name") or "").lower()
                    ident = p.get("identifier") or p.get("name") or ""
                    if not ident:
                        continue
                    if kind == "npm":
                        cmd, args = "npx", ["-y", ident]
                    elif kind == "pypi":
                        cmd, args = "uvx", [ident]
                    elif kind in ("oci", "docker"):
                        cmd, args = "docker", ["run", "-i", "--rm", ident]
                    else:
                        continue
                    rows.append({"source": "registry", "name": srv.get("name", ident), "description": desc, "command": cmd,
                                 "args": args, "env": _env_list(p.get("environmentVariables") or p.get("environment_variables")),
                                 "auth": "", "homepage": home})
                for rem in srv.get("remotes") or []:
                    if not rem.get("url"):
                        continue
                    hdrs = [h.get("name") for h in rem.get("headers") or [] if isinstance(h, dict) and h.get("name")]
                    smithery = "smithery" in rem["url"]
                    rows.append({"source": "registry (hosted)", "name": srv.get("name", rem["url"]), "description": desc,
                                 "url": rem["url"], "env": [],
                                 "auth": ("needs a Smithery API key header" if smithery else
                                          f"header {', '.join(hdrs)}" if hdrs else "sign-in (OAuth) or none"),
                                 "homepage": home})
            return rows

        async def npm():
            r = await c.get("https://registry.npmjs.org/-/v1/search", params={"text": f"mcp server {q}", "size": 8})
            rows = []
            for o in (r.json().get("objects") or []) if r.status_code == 200 else []:
                p = o.get("package") or {}
                name, desc = p.get("name", ""), (p.get("description") or "")
                if not name or not re.search(r"mcp|model.?context", name + " " + desc, re.I):
                    continue
                if re.search(r"/sdk$|^@modelcontextprotocol/server$|typegen|inspector|/types$|-types$|create-mcp", name):
                    continue  # libraries and generators, not servers
                rows.append({"source": "npm", "name": name, "description": desc[:200], "command": "npx", "args": ["-y", name],
                             "env": [], "auth": "see README", "homepage": (p.get("links") or {}).get("repository")
                             or (p.get("links") or {}).get("npm") or "",
                             "popularity": float(((o.get("score") or {}).get("detail") or {}).get("popularity") or 0)})
            return rows

        async def github():
            r = await c.get("https://api.github.com/search/repositories",
                            params={"q": f"{q} mcp server", "sort": "stars", "order": "desc", "per_page": 6},
                            headers={"Accept": "application/vnd.github+json"})
            return [{"source": "github", "name": x.get("full_name", ""), "description": (x.get("description") or "")[:200],
                     "stars": x.get("stargazers_count", 0), "homepage": x.get("html_url", ""), "env": [],
                     "auth": "read its README for the command and tokens"}
                    for x in ((r.json().get("items") or []) if r.status_code == 200 else [])]

        results = await _asyncio.gather(registry(), npm(), github(), return_exceptions=True)
    names: set[str] = set()
    for group in results:
        if isinstance(group, list):
            for item in group:
                if item["source"].startswith("registry") and item["name"] in names and item.get("command"):
                    continue  # one line per registry server (its other package versions are the same server)
                names.add(item["name"])
                add(item)
    words = [w for w in re.findall(r"[a-z0-9]{3,}", q.lower())]

    def score(x: dict) -> float:
        ident = " ".join([x["name"], *(x.get("args") or [])]).lower()
        scope = ident.split("/")[0] if ident.startswith("@") else ""
        sc = {"registry": 3.0, "npm": 3.0, "registry (hosted)": 2.0, "github": 1.0}.get(x["source"], 0)
        if OFFICIAL.search(ident) or (scope and any(w in scope for w in words)):
            sc += 4  # the vendor's own or the reference server
        if x.get("url") and "smithery" in x["url"]:
            sc -= 2  # needs another account's key
        sc += 3 * float(x.get("popularity") or 0) + min(float(x.get("stars") or 0), 20000) / 10000
        return sc

    runnable = sorted((x for x in out if x["source"] != "github"), key=score, reverse=True)
    repos = sorted((x for x in out if x["source"] == "github"), key=score, reverse=True)[:2]
    return runnable[:max(1, limit - len(repos))] + repos


OFFICIAL = re.compile(r"@modelcontextprotocol/|@microsoft/|@notionhq/|@stripe/|@supabase/|@cloudflare/|@github/|"
                      r"@azure/|@google/|@upstash/|@playwright/|@sentry/|@neondatabase/|@vercel/|@browserbasehq/|"
                      r"@anthropic-ai/|@mongodb|@redis/|@elastic/|@atlassian/|@linear/|@figma/|@shopify/|@hubspot/")
