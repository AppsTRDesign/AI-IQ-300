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

import httpx

from .config import get_secret, load_settings

PROTOCOL = "2025-06-18"
START_TIMEOUT = 20
CALL_TIMEOUT = 120
CLIENT = {"name": "AI IQ 300", "version": "1.0"}
ID_RE = re.compile(r"^[a-z0-9_-]{1,32}$")


class MCPError(Exception):
    pass


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
        cmd = (self.cfg.get("command") or "").strip()
        if not cmd:
            raise MCPError("no command")
        exe = shutil.which(cmd) or cmd  # npx -> npx.cmd on Windows
        args = [str(a) for a in self.cfg.get("args") or []]
        if sys.platform == "win32" and exe.lower().endswith((".cmd", ".bat")):
            args, exe = ["/c", exe, *args], os.environ.get("COMSPEC", "cmd.exe")
        env = {**os.environ, **{str(k): str(v) for k, v in (self.cfg.get("env") or {}).items()}}
        self.proc = await asyncio.create_subprocess_exec(
            exe, *args, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            env=env, cwd=self.cfg.get("cwd") or None, limit=16 * 1024 * 1024,
            creationflags=0x08000000 if sys.platform == "win32" else 0)  # CREATE_NO_WINDOW
        self._reader = asyncio.create_task(self._read_stdout())
        asyncio.create_task(self._read_stderr())

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
        assert self.proc and self.proc.stdout
        try:
            while line := await self.proc.stdout.readline():
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
        if not (self.proc and self.proc.stderr):
            return
        while line := await self.proc.stderr.readline():
            self.stderr = (self.stderr + [line.decode(errors="replace").strip()])[-20:]

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
        async with pooled(timeout=CALL_TIMEOUT) as c, c.stream("POST", self.cfg["url"], json=msg, headers=headers) as r:
            if r.status_code >= 400:
                body = (await r.aread()).decode(errors="replace")[:300]
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
        out[k] = {"enabled": cfg.get("enabled", True), "running": bool(s and s.alive), "error": s.error if s else None,
                  "tools": [{"name": t["name"], "description": (t.get("description") or "")[:300],
                             "read_only": bool((t.get("annotations") or {}).get("readOnlyHint"))} for t in (s.tools if s else [])]}
    return out


def available_tools() -> list[tuple[str, dict]]:
    return [(k, t) for k, s in _servers.items() if s.alive for t in s.tools]


def _schema_hint(schema: dict) -> str:
    props = (schema or {}).get("properties") or {}
    req = set((schema or {}).get("required") or [])
    bits = [f"{n}{'' if n in req else '?'}:{(p or {}).get('type', 'any')}" for n, p in list(props.items())[:12]]
    return "{" + ", ".join(bits) + "}"


def prompt_section() -> str:
    tools = available_tools()
    if not tools:
        return ""
    lines = [f"- {k}/{t['name']}: {(t.get('description') or '').strip().splitlines()[0][:200] if t.get('description') else ''} "
             f"args {_schema_hint(t.get('inputSchema') or {})}" for k, t in tools[:80]]
    return ("# MCP tools (external servers the user connected)\nCall them with the mcp tool: server, tool and the "
            "arguments as a JSON object. Prefer them over improvised scripts when they fit the task.\n" + "\n".join(lines))


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
