"""AI IQ 300 FastAPI backend: REST control API, event WebSocket, static frontend."""
from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import sys
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import approvals, db, i18n, policy, sessions, workspace
from .errors import fail, to_http
from .agents import catalog, orchestrator
from .config import FRONTEND_DIST, LANG_DIR, load_settings, save_settings, secret_status, set_secret
from .events import bus
from .llm import router
from .process_manager import manager


def _quiet_disconnects(loop: asyncio.AbstractEventLoop) -> None:
    """Windows (Proactor loop): when the browser drops a connection it no longer needs (the video player seeks or is
    closed mid-download of a 206 range, a tab closes), asyncio prints a ConnectionResetError [WinError 10054]
    traceback from _call_connection_lost. Nothing failed; only that one message is dropped, every other error still
    reaches the default handler."""
    default = loop.get_exception_handler()

    def handler(lp, context):
        exc = context.get("exception")
        if isinstance(exc, (ConnectionResetError, ConnectionAbortedError, BrokenPipeError)) and \
                "_call_connection_lost" in str(context.get("handle") or context.get("message") or ""):
            return
        if default:
            default(lp, context)
        else:
            lp.default_exception_handler(context)

    loop.set_exception_handler(handler)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if sys.platform == "win32":
        _quiet_disconnects(asyncio.get_running_loop())
    # Processes from a previous backend instance (dev servers the agent started, then the app was closed hard) are
    # no longer supervised: stop the ones still alive, then mark them orphaned. A dev server left on localhost:8000
    # kept running and locked its chat folder.
    # Before v0.10.3 chat files lived in workspace/: move them into chat/<id>/ once.
    await asyncio.to_thread(workspace.migrate_layout)
    _s = load_settings()  # one Cloudflare account id for chat and images (older settings kept it in one place only)
    _a, _b = (_s.get("providers", {}).get("cloudflare") or {}).get("account_id"), (_s.get("media") or {}).get("cloudflare_account")
    if bool(_a) != bool(_b) and "cloudflare" in _s.get("providers", {}):
        save_settings({"providers": {"cloudflare": {"account_id": _a or _b}}, "media": {"cloudflare_account": _a or _b}})
    await asyncio.to_thread(_stop_orphans)
    db.execute("UPDATE processes SET state='orphaned' WHERE state IN ('queued','running','cancelling')")
    # Tasks that were running when the app stopped (power cut, crash): shown as interrupted, resumable.
    await asyncio.to_thread(orchestrator.recover_interrupted)
    from .tools import syntax
    syntax.warm()  # tree-sitter grammars load in the background (first run downloads them)
    from . import hostinfo, toolchain
    toolchain.setup_paths()
    hostinfo.warm()
    # ffmpeg / composer fetched in the background when missing, then the tool list in the prompt is refreshed
    asyncio.create_task(toolchain.ensure()).add_done_callback(lambda _t: hostinfo.refresh())  # OS build, shells and tool versions for the system prompt, detected once in the background
    from . import mcp_client
    if mcp_client.servers_cfg():  # connected MCP servers start in the background (Settings shows their state)
        _bg(mcp_client.ensure())
    warm = asyncio.create_task(router.warm_info())  # model windows ready before the first task asks
    guard = asyncio.create_task(_ram_guard())  # unloads local models before low RAM freezes the computer
    health = asyncio.create_task(_health_watch())  # local servers / settings changes pushed to the UI
    from . import netwatch
    net = asyncio.create_task(netwatch.watch())  # internet drops / returns pushed to the UI; tasks wait and resume
    yield
    net.cancel()
    warm.cancel()
    guard.cancel()
    health.cancel()
    await orchestrator.shutdown()  # tasks store their checkpoint and message before the loop closes
    await manager.shutdown()
    from . import mcp_client
    await mcp_client.shutdown()
    db.checkpoint()  # the write-ahead log is folded into the database file
    from .llm import modelstats
    modelstats.flush()


def _net_snapshot() -> dict:
    from . import netwatch
    return netwatch.snapshot()


async def _ram_guard() -> None:
    """Background RAM guard for local models (llm/memguard.py): unload before low memory freezes the computer."""
    from .llm import memguard
    from .agents.orchestrator import ui_text

    def ollama() -> tuple[str, str]:
        """(provider id, base URL) of the enabled local Ollama server (any id, not only the default one)."""
        for pid, cfg in load_settings()["providers"].items():
            if cfg.get("local") and cfg.get("enabled") and cfg.get("kind", pid) == "ollama":
                return pid, (cfg.get("base_url") or "").rstrip("/")
        return "", ""

    def state() -> dict:
        s = load_settings()
        g = s.get("local_guard") or {}
        pid, base = ollama()
        active = s.get("active_model") or ""
        return {"enabled": g.get("enabled", True), "emergency_unload": bool(g.get("emergency_unload")),
                "low": g.get("low", 12), "critical": g.get("critical", 6), "base_url": base,
                "active": active.partition(":")[2] if pid and active.startswith(pid + ":") else ""}

    def busy(name: str) -> bool:
        pid, _ = ollama()
        return any((r.model or "") == f"{pid}:{name}" for r in orchestrator.RUNS.values())

    fallbacks = {
        "app": "Free {what} is low ({free} GB of {total} GB): the app released {freed} MB of its own caches.",
        "idle": "Free {what} is low ({free} GB of {total} GB): the unused model {model} was unloaded. The model in use "
                "stays loaded.",
        "shrunk": "Free {what} is critically low ({free} GB of {total} GB): the context window of {model} was reduced "
                  "from {old} to {new}. The model stays loaded and no chat memory is lost.",
        "floor": "Free {what} is critically low ({free} GB of {total} GB) and the window of {model} is already at its "
                 "smallest. Close other programs.",
        "unloaded": "Free {what} is critically low ({free} GB of {total} GB): {model} was unloaded (emergency unload is "
                    "on). The chat and the task's progress are kept; type \"continue\" to resume.",
    }

    def notify(kind: str, **info) -> None:
        lang = load_settings().get("language") or "en"
        info["what"] = "VRAM" if info.get("what") == "vram" else "RAM"
        for k in ("old", "new"):
            if isinstance(info.get(k), int):
                info[k] = f"{info[k] // 1024}K"
        text = ui_text(lang, f"ai_guard_{kind}", fallbacks.get(kind, ""), **info)
        bus.publish("model", "memory", {"model": info.get("model") or "", "message": text, "kind": kind})
        if kind in ("shrunk", "unloaded"):
            pid, _ = ollama()
            bus.publish("model", "context", {"model": f"{pid}:{info.get('model')}"})

    async def relief() -> None:
        """The app's other memory nobody is using right now: a browser window no task needs."""
        from .tools.browser import AGENT
        if AGENT.running() and not orchestrator.any_run_active() and not AGENT.lock.locked():
            await AGENT.close()
        # LM Studio: its models are unloaded only when no task uses that server and it is not the chosen one.
        s = load_settings()
        active = (s.get("active_model") or "").partition(":")[0]
        for pid, cfg in s["providers"].items():
            if cfg.get("local") and cfg.get("enabled") and cfg.get("kind", pid) != "ollama" and pid != active \
                    and not any((r.model or "").startswith(pid + ":") for r in orchestrator.RUNS.values()):
                if lms := router._lms():
                    await router._run(lms, "unload", "--all")

    lms_last = {"t": 0.0}

    async def other_local(free, total, what, now) -> None:
        """LM Studio (and other non-Ollama local servers) at critical memory: the chosen model is made smaller, never
        closed. A task streaming on it is asked to give memory back itself (stop, summarize, smaller window)."""
        if now - lms_last["t"] < 60:
            return
        s = load_settings()
        active = s.get("active_model") or ""
        pid, _, name = active.partition(":")
        cfg = s["providers"].get(pid) or {}
        if not (name and cfg.get("local") and cfg.get("enabled") and cfg.get("kind", pid) != "ollama"):
            return
        lms_last["t"] = now
        if any((r.model or "") == active for r in orchestrator.RUNS.values()):
            if not memguard.pressure(name):
                memguard._PRESSURE[name] = now
            return
        cur = (await router.context_info(active))["current"]
        new = memguard.shrink(name, cur) if cur else None
        if new and await router.reload_local(active, new):
            notify("shrunk", model=name, old=cur, new=new, free=free, total=total, what=what)
        elif not new:
            notify("floor", model=name, free=free, total=total, what=what)

    await memguard.watchdog(state, busy, notify, relief, other_local)


def _stop_orphans() -> None:
    """Kill the process trees of a previous run's still-running processes. Only when the live process with that PID
    is the same program that was started (PIDs are reused), so nothing else is ever touched."""
    import subprocess
    import sys
    for row in db.query("SELECT pid, argv FROM processes WHERE state IN ('queued','running','cancelling') AND pid"):
        try:
            exe = Path(json.loads(row["argv"])[0]).stem.lower()
            if sys.platform == "win32":
                out = subprocess.run(["tasklist", "/FI", f"PID eq {int(row['pid'])}", "/FO", "CSV", "/NH"],
                                     capture_output=True, text=True, timeout=10, creationflags=0x08000000).stdout.lower()
                if exe and f'"{exe}' in out:
                    subprocess.run(["taskkill", "/PID", str(int(row["pid"])), "/T", "/F"], capture_output=True,
                                   timeout=15, creationflags=0x08000000)
            else:
                import os
                import signal
                cmd = Path(f"/proc/{int(row['pid'])}/cmdline")
                if cmd.exists() and exe in cmd.read_bytes().decode(errors="replace").lower():
                    os.killpg(os.getpgid(int(row["pid"])), signal.SIGTERM)
        except Exception:  # noqa: BLE001 - a process that is gone or not ours is simply left alone
            continue


app = FastAPI(title="AI IQ 300", lifespan=lifespan)
_BG: set[asyncio.Task] = set()


def _bg(coro) -> asyncio.Task:
    """A background task that keeps a reference until it ends (an unreferenced task can be collected mid-flight)."""
    task = asyncio.create_task(coro)
    _BG.add(task)
    task.add_done_callback(_BG.discard)
    return task


LOOPBACK = ("127.0.0.1", "localhost", "[::1]")


def _origin_ok(origin: str | None, host: str | None = None) -> bool:
    """Allowed origins from settings, plus the app's own page on a loopback address at whatever port it runs on.
    Only loopback names count for the same-origin case, so a DNS-rebinding page cannot pass as the app."""
    if origin is None or origin in load_settings()["allowed_origins"]:
        return True
    return bool(host) and origin == f"http://{host}" and host.rsplit(":", 1)[0] in LOOPBACK


@app.middleware("http")
async def origin_guard(request: Request, call_next):
    # Blocks cross-site browser requests to the control API (backend binds to loopback by default).
    if request.url.path.startswith("/api") and not _origin_ok(request.headers.get("origin"), request.headers.get("host")):
        return JSONResponse({"detail": "origin not allowed"}, status_code=403)
    return await call_next(request)


# ---------- projects & sessions ----------
class ProjectIn(BaseModel):
    name: str
    path: str | None = None


class ProjectPatch(BaseModel):
    name: str | None = None
    pinned: bool | None = None


class SessionIn(BaseModel):
    project_id: str | None = None
    title: str | None = None


@app.get("/api/projects")
def list_projects():
    return db.query("SELECT * FROM projects ORDER BY pinned DESC, created DESC")


@app.post("/api/projects")
def create_project(body: ProjectIn):
    if not body.name.strip():
        raise fail(400, "project_name_required", "Project name is required")
    try:
        return workspace.create_project(body.name.strip(), body.path or None)
    except ValueError as e:
        raise to_http(e, 400)


@app.patch("/api/projects/{pid}")
def rename_project(pid: str, body: ProjectPatch):
    if body.name is not None and body.name.strip():
        db.execute("UPDATE projects SET name=? WHERE id=?", (body.name.strip(), pid))
    if body.pinned is not None:
        db.execute("UPDATE projects SET pinned=? WHERE id=?", (int(body.pinned), pid))
    return {"ok": True}


@app.post("/api/projects/{pid}/archive_chats")
def archive_project_chats(pid: str):
    """Archives every chat of the project (they stay on disk and can be restored)."""
    n = db.execute("UPDATE sessions SET archived=1 WHERE project_id=? AND archived=0", (pid,)).rowcount
    return {"archived": n}


@app.delete("/api/projects/{pid}")
def remove_project(pid: str):
    """Removes the project and its chats from the app. Files on disk are NOT touched."""
    for srow in db.query("SELECT id FROM sessions WHERE project_id=?", (pid,)):
        db.execute("DELETE FROM messages WHERE session_id=?", (srow["id"],))
        sessions.remove(srow["id"])
    db.execute("DELETE FROM sessions WHERE project_id=?", (pid,))
    db.execute("DELETE FROM projects WHERE id=?", (pid,))
    return {"ok": True}


class RulesIn(BaseModel):
    text: str = ""


@app.get("/api/projects/{pid}/rules")
def get_project_rules(pid: str):
    proj = workspace.get_project(pid)
    if not proj:
        raise fail(404, "project_not_found", "Project not found")
    return {"text": workspace.read_rules(proj), "path": str(workspace.rules_path(proj))}


@app.put("/api/projects/{pid}/rules")
def put_project_rules(pid: str, body: RulesIn):
    proj = workspace.get_project(pid)
    if not proj:
        raise fail(404, "project_not_found", "Project not found")
    if len(body.text) > workspace.RULES_MAX:
        raise fail(400, "rules_too_long", f"Rules are limited to {workspace.RULES_MAX} characters")
    try:
        workspace.write_rules(proj, body.text)
    except OSError as e:
        raise fail(500, "rules_write_failed", str(e))
    return {"text": workspace.read_rules(proj), "path": str(workspace.rules_path(proj))}


@app.post("/api/projects/{pid}/reveal")
def reveal_project(pid: str):
    import os
    import subprocess
    import sys
    proj = workspace.get_project(pid)
    if not proj:
        raise HTTPException(404)
    if sys.platform == "win32":
        os.startfile(proj["path"])  # opens Explorer on the local machine
    else:
        subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", proj["path"]])
    return {"ok": True}


class MkdirIn(BaseModel):
    parent: str
    name: str


@app.post("/api/fs/mkdir")
def fs_mkdir(body: MkdirIn):
    import re
    name = body.name.strip()
    if not name or re.search(r'[<>:"/\\|?*]', name) or name in (".", ".."):
        raise fail(400, "invalid_name", "Invalid folder name")
    parent = Path(body.parent).expanduser().resolve()
    if not parent.is_dir():
        raise fail(400, "folder_not_found", "Parent folder not found")
    target = parent / name
    try:
        target.mkdir()
    except FileExistsError:
        raise fail(409, "name_exists", "A folder with this name already exists")
    except OSError as e:
        raise to_http(e, 400)
    return {"path": str(target)}


@app.get("/api/fs/dirs")
def fs_dirs(path: str = ""):
    try:
        return workspace.list_dirs(path)
    except ValueError as e:
        raise to_http(e, 400)


@app.get("/api/search")
def search_chats(q: str = "", limit: int = 40):
    """Full-text search over every chat's messages (sidebar search): newest hits first, each with its chat."""
    return {"results": db.search(q[:200], max(1, min(limit, 100))) if q.strip() else []}


@app.get("/api/sessions")
def list_sessions(project_id: str | None = None):
    cols = "id, project_id, title, created, updated, pinned, archived, context_used, unread, title_auto"
    if project_id:
        return db.query(f"SELECT {cols} FROM sessions WHERE project_id=? AND archived=0 "
                        "ORDER BY pinned DESC, updated DESC", (project_id,))
    return db.query(f"SELECT {cols} FROM sessions WHERE archived=0 ORDER BY pinned DESC, updated DESC LIMIT 200")


@app.post("/api/sessions")
def create_session(body: SessionIn):
    sid, now = uuid.uuid4().hex[:12], time.time()
    db.execute("INSERT INTO sessions(id,project_id,title,created,updated) VALUES(?,?,?,?,?)",
               (sid, body.project_id, body.title or "", now, now))
    return db.query("SELECT * FROM sessions WHERE id=?", (sid,))[0]


def _session(sid: str) -> dict:
    rows = db.query("SELECT * FROM sessions WHERE id=?", (sid,))
    if not rows:
        raise fail(404, "session_not_found", "Chat not found")
    return rows[0]


STEP_DETAIL_SHOWN = 2000  # characters of a stored step's detail sent with the chat; the rest loads when opened


def _light_steps(row: dict) -> None:
    """A chat page carries every step of every answer: whole files written, long command outputs and notes made a
    long chat megabytes to load and render. Long details go out cut; the step loads in full when the user opens it."""
    for i, s in enumerate((row.get("meta") or {}).get("steps") or []):
        d = s.get("detail")
        if isinstance(d, str) and len(d) > STEP_DETAIL_SHOWN:
            s["detail"] = d[:STEP_DETAIL_SHOWN]
            s["lazy"] = {"mid": row["id"], "i": i, "chars": len(d)}


@app.get("/api/messages/{mid}/steps/{i}")
def message_step(mid: int, i: int):
    """One stored step in full (opened in the trace after the chat loaded it cut)."""
    rows = db.query("SELECT meta FROM messages WHERE id=?", (mid,))
    steps = (json.loads(rows[0]["meta"] or "{}").get("steps") or []) if rows else []
    if not 0 <= i < len(steps):
        raise fail(404, "not_found", "No such step")
    return steps[i]


@app.get("/api/sessions/{sid}/messages")
def get_messages(sid: str, limit: int = 0, before: int | None = None):
    """All messages, or (limit > 0) the latest `limit` ones before message id `before`: a long chat opens with
    its last page and loads older pages while the user scrolls up. The 'X-Has-More' answer says if older exist."""
    if limit > 0:
        rows = db.query("SELECT * FROM messages WHERE session_id=? AND id<? ORDER BY id DESC LIMIT ?",
                        (sid, before or 1 << 62, limit + 1))
        more = len(rows) > limit
        rows = list(reversed(rows[:limit]))
    else:
        rows, more = db.query("SELECT * FROM messages WHERE session_id=? ORDER BY id", (sid,)), False
    for r in rows:
        r["meta"] = json.loads(r["meta"] or "{}")
        if limit > 0:
            _light_steps(r)
    if sid and limit > 0:
        db.execute("UPDATE sessions SET unread=0 WHERE id=?", (sid,))
        return {"messages": rows, "has_more": more}
    return rows


@app.delete("/api/sessions/{sid}/messages/{mid}")
def delete_message(sid: str, mid: int):
    """Removes one message from the chat (and so from what later turns send to the model)."""
    if orchestrator.active_run(sid):
        run = orchestrator.active_run(sid)
        rows = db.query("SELECT MAX(id) AS m FROM messages WHERE session_id=? AND role='user'", (sid,))
        if rows and rows[0]["m"] == mid and run:
            raise fail(409, "run_busy", "This message belongs to the running task")
    n = db.execute("DELETE FROM messages WHERE session_id=? AND id=?", (sid, mid)).rowcount
    if not n:
        raise fail(404, "message_not_found", "Message not found")
    return {"ok": True}


class SessionPatch(BaseModel):
    title: str | None = None
    pinned: bool | None = None
    archived: bool | None = None
    unread: bool | None = None
    project_id: str | None = None
    move: bool = False  # project_id is applied only with move=true (null = no project)


@app.patch("/api/sessions/{sid}")
def patch_session(sid: str, body: SessionPatch):
    data = body.model_dump(exclude_none=True)
    move = data.pop("move", False)
    data.pop("project_id", None)
    for k, v in data.items():
        if k == "title":  # typed by the user: plain text, and the app never renames this chat again
            v = orchestrator.clean_title(str(v)) or str(v)[:70]
            db.execute("UPDATE sessions SET title_auto=0 WHERE id=?", (sid,))
        db.execute(f"UPDATE sessions SET {k}=? WHERE id=?", (int(v) if isinstance(v, bool) else v, sid))
    if move:
        if orchestrator.active_run(sid):
            raise fail(409, "run_busy", "This chat is still working; wait for it or stop it first")
        if body.project_id and not workspace.get_project(body.project_id):
            raise fail(404, "project_not_found", "Project not found")
        db.execute("UPDATE sessions SET project_id=? WHERE id=?", (body.project_id or None, sid))
    return _session(sid)


@app.post("/api/sessions/{sid}/fork")
def fork_session(sid: str):
    """A separate copy of the chat: same project, messages and summary; later work in either stays apart."""
    src = _session(sid)
    new, now = uuid.uuid4().hex[:12], time.time()
    db.execute("INSERT INTO sessions(id,project_id,title,created,updated,summary,summary_upto,context_used,context_stats) "
               "VALUES(?,?,?,?,?,?,?,?,?)", (new, src["project_id"], (src["title"] or "")[:54] + " (2)", now, now,
                                             src["summary"], 0, src["context_used"], src["context_stats"]))
    upto = src["summary_upto"] or 0
    mapped = 0
    for r in db.query("SELECT role, content, meta, id FROM messages WHERE session_id=? ORDER BY id", (sid,)):
        mid = db.add_message(new, r["role"], r["content"], json.loads(r["meta"] or "{}"))
        if r["id"] <= upto:
            mapped = mid
    db.execute("UPDATE sessions SET summary_upto=? WHERE id=?", (mapped, new))
    if not src["project_id"]:
        # A chat without a project works in its own folder: the copy gets its files too (the copied messages name
        # them), plus the working state, but not rebuildable dependency folders.
        try:
            old_root, new_root = sessions.CHAT_DIR / sid, sessions.CHAT_DIR / new
            if old_root.is_dir():
                shutil.copytree(old_root, new_root, dirs_exist_ok=True,
                                ignore=shutil.ignore_patterns("node_modules", ".venv", "venv", "__pycache__", ".git",
                                                              "messages.jsonl", "session.json"))
        except OSError as e:
            import logging
            logging.getLogger("aiiq").warning("fork: copying the chat folder failed: %s", e)
    return _session(new)


@app.get("/api/sessions/{sid}/export")
def export_session(sid: str):
    """The chat as Markdown (share / copy)."""
    s = _session(sid)
    out = [f"# {s['title'] or 'Chat'}\n"]
    for r in db.query("SELECT role, content, created FROM messages WHERE session_id=? ORDER BY id", (sid,)):
        who = "**User**" if r["role"] == "user" else "**AI IQ 300**"
        out.append(f"{who} · {time.strftime('%Y-%m-%d %H:%M', time.localtime(r['created']))}\n\n{r['content'] or ''}\n")
    return {"title": s["title"], "markdown": "\n---\n\n".join(out)}


@app.get("/api/sessions/{sid}/active")
def active(sid: str):
    return orchestrator.active_run(sid) or {}


@app.get("/api/sessions/{sid}/context")
async def session_context(sid: str, model: str):
    sess = _session(sid) if sid != "new" else {}
    # A running task: its live count and model, never the stored value from the end of the previous task (opening
    # the panel mid-task used to reset a red meter to the old, lower number).
    live = orchestrator.live_context(sid) if sess else None
    if live and live["model"]:
        model = live["model"]
    info = await router.context_info(model)
    used = live["used"] if live else (
        sess.get("context_used") or (orchestrator.estimate_tokens(orchestrator._history(sid)) if sess else 0))
    stats = (live or {}).get("stats") or (json.loads(sess["context_stats"]) if sess.get("context_stats") else {})
    outputs: dict[str, dict] = {}
    if sess:  # files this chat wrote (newest first), from the recorded tool steps
        for row in db.query("SELECT meta FROM messages WHERE session_id=? AND role='assistant' ORDER BY id DESC", (sid,)):
            for st in json.loads(row["meta"] or "{}").get("steps", []):
                d = st.get("data") or {}
                if d.get("tool") in ("write_file", "edit_file", "make_doc") and d.get("path") and st.get("status") == "done":
                    outputs.setdefault(d["path"], {"path": d["path"], "ts": st.get("ts")})
    tasks = [p for p in manager.list() if str(p.get("owner", "")).startswith(f"{sid}:")]
    return {**info, "used": used, "summarized": bool(sess.get("summary")), "stats": stats,
            "outputs": list(outputs.values())[:100], "tasks": tasks}


class CompressIn(BaseModel):
    model: str


@app.post("/api/sessions/{sid}/compress")
async def compress_session(sid: str, body: CompressIn):
    from .llm.providers import ProviderError
    _session(sid)
    if orchestrator.active_run(sid):
        raise fail(409, "compress_busy", "Cannot compress while the chat is running")
    try:
        return await orchestrator.compress(sid, body.model, keep_recent=2)
    except ProviderError as e:
        raise to_http(e, 502)


class IdsIn(BaseModel):
    ids: list = []
    all: bool = False


@app.post("/api/sessions/delete")
async def delete_sessions(body: IdsIn):
    """Several chats at once (the selection in the chat list): each with everything it has, like delete_session."""
    sids = [str(x) for x in body.ids][:500]
    # All of them stop at once (not one after another, each waiting up to 8 s for its task), and the folders go in
    # the background: the chats disappear right away instead of after minutes of node_modules being deleted.
    await asyncio.gather(*(orchestrator.cancel_session(s, wait=3.0) for s in sids), return_exceptions=True)
    done = 0
    for sid in sids:
        try:
            await delete_session(sid, cancelled=True)
            done += 1
        except Exception:  # a chat already gone
            continue
    return {"ok": True, "deleted": done}


@app.post("/api/sessions/{sid}/messages/delete")
async def delete_messages(sid: str, body: IdsIn):
    """Selected messages (or all) of a chat, with what was built from them: their lines in the chat record
    (messages.jsonl), a summary that covers them, the saved progress of an interrupted task and, when the chat is
    emptied, its whole history record (state, summaries, checkpoints). The files of its working folder stay."""
    _session(sid)
    if orchestrator.active_run(sid):
        # The user confirmed the deletion while the chat works: the task stops (it would write about messages that
        # no longer exist), then the messages go. Refusing with "stop it first" looked like nothing happened.
        await orchestrator.cancel_session(sid, wait=3.0)
    ids = [int(x) for x in body.ids if str(x).isdigit()]
    if body.all:
        n = db.execute("DELETE FROM messages WHERE session_id=?", (sid,)).rowcount
    elif ids:
        n = db.execute(f"DELETE FROM messages WHERE session_id=? AND id IN ({','.join('?' * len(ids))})",
                       (sid, *ids)).rowcount
    else:
        return {"ok": True, "deleted": 0}
    left = db.query("SELECT COUNT(*) AS c FROM messages WHERE session_id=?", (sid,))[0]["c"]
    row = db.query("SELECT summary_upto FROM sessions WHERE id=?", (sid,))
    upto = (row[0]["summary_upto"] or 0) if row else 0
    reset = body.all or not left or any(i <= upto for i in ids)
    if reset:  # the summary was made of deleted messages: it goes too, so nothing of them reaches the model again
        db.execute("UPDATE sessions SET summary=NULL, summary_upto=0, context_used=0, context_stats=NULL WHERE id=?", (sid,))
    try:
        rec = sessions.path(sid, create=False)
        if rec.exists():
            if not left:  # an emptied chat: its whole history record
                for f in rec.iterdir():
                    if f.is_file():
                        f.unlink(missing_ok=True)
                    else:
                        shutil.rmtree(f, ignore_errors=True)
            else:
                for name in ("run_state.json", "partial_call.json"):
                    (rec / name).unlink(missing_ok=True)
                if reset:
                    (rec / "summary.md").unlink(missing_ok=True)
                tr = rec / "messages.jsonl"
                if tr.exists() and ids:  # the record keeps only the messages that still exist
                    gone = set(ids)

                    def keep(ln: str) -> bool:  # a half-written line (crash mid-append) must not stop the cleanup
                        try:
                            return json.loads(ln).get("id") not in gone
                        except ValueError:
                            return True
                    lines = [ln for ln in tr.read_text(encoding="utf-8").splitlines() if ln.strip() and keep(ln)]
                    tr.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    except (ValueError, OSError):
        pass
    return {"ok": True, "deleted": n, "left": left}


@app.delete("/api/sessions/{sid}")
async def delete_session(sid: str, cancelled: bool = False):
    """Deletes the chat, its messages and its whole chat/<id>/ folder (files and record). The chat is gone at once
    (database rows, event to every window); its folder is moved aside and removed in a worker thread, so a chat with
    an Expo / node_modules tree (tens of thousands of files) no longer freezes the whole app while it is deleted."""
    if not cancelled:
        await orchestrator.cancel_session(sid, wait=3.0)
    # Dev servers this chat started hold its files open (Windows cannot delete them): stopped first.
    owned = [p["id"] for p in manager.list()
             if str(p.get("owner", "")).startswith(f"{sid}:") and p.get("state") in ("queued", "running")]
    if owned:
        await asyncio.gather(*(manager.stop(i) for i in owned), return_exceptions=True)
    rows = db.query("SELECT project_id FROM sessions WHERE id=?", (sid,))
    db.execute("DELETE FROM messages WHERE session_id=?", (sid,))
    db.execute("DELETE FROM sessions WHERE id=?", (sid,))
    bus.publish("session", "deleted", {"session_id": sid})
    own_root = bool(rows and not rows[0]["project_id"])

    def remove_files() -> None:
        if own_root:
            workspace.remove_chat_root(sid)
        try:
            sessions.remove(sid)
        except ValueError:
            pass
    _bg(asyncio.to_thread(remove_files))
    return {"ok": True}


# ---------- chat runs ----------
class ChatIn(BaseModel):
    text: str
    model: str | None = None
    account_id: str | None = None  # Cloudflare Workers AI
    permission_mode: str | None = None
    plan_mode: bool = False
    goal_mode: bool = False
    attachments: list[dict] = []
    images: list[str] = []
    ui_lang: str | None = None
    chips: list[dict] = []  # composer mode / template chips: shown as chips in the sent message


@app.post("/api/sessions/{sid}/chat")
async def chat(sid: str, body: ChatIn):
    session = {**_session(sid), "context_used": 0}
    if orchestrator.active_run(sid):
        # The chat is working: the message does not start a second task (two would write over each other) and does
        # not stop the first; it reaches the running task as guidance.
        run = orchestrator.steer(sid, body.text)
        if run:
            return {"run_id": run.id, "steered": True, "cwd": str(workspace.session_root(session))}
        raise fail(409, "run_busy", "This chat is still working; wait for it or stop it first")
    if not (body.model or load_settings().get("active_model")):
        raise fail(400, "no_model", "No model selected; pick a model under the message box")
    if body.permission_mode and body.permission_mode not in policy.MODES:
        raise fail(400, "bad_permission_mode", "Invalid permission mode")
    if not session["title"]:
        title_src = body.text
        strip = next((c.get("strip") for c in body.chips if isinstance(c, dict) and c.get("strip")), "")
        if strip and title_src.startswith(strip):  # the chips' labels, not the instruction behind them
            labels = " · ".join(str(c.get("label") or "") for c in body.chips if isinstance(c, dict) and c.get("label"))
            title_src = f"{labels}: {title_src[len(strip):].strip()}" if labels else title_src[len(strip):]
        db.execute("UPDATE sessions SET title=? WHERE id=?", (orchestrator.clean_title(title_src)[:60], sid))
    root = workspace.session_root(session)
    # Reading and copying attachments (pictures, videos) runs off the event loop: a large file copied here held
    # every other chat's stream and the websocket until it was done.
    text = await asyncio.to_thread(_with_attachments, body.text, body.attachments, root)
    run = orchestrator.start_run(session, text, body.model_dump() | {"text": text, "display_text": body.text})
    return {"run_id": run.id, "cwd": str(root)}


def _with_attachments(text: str, attachments: list, root: Path) -> str:
    saved: list[str] = []
    for a in attachments:  # inline small text attachments as context
        p = Path(a.get("path", ""))
        if p.is_file() and p.stat().st_size < 200_000 and a.get("kind") == "text":
            text += f"\n\n[Attached file: {p.name}]\n```\n{p.read_text(encoding='utf-8', errors='replace')}\n```"
        elif p.is_file() and a.get("kind") in ("image", "binary"):
            # Pictures and other files are also copied into the working folder: tools (inspect_media, image editing,
            # a "make one like this") find them there in this and later messages ("the file is not in the folder").
            try:
                dest = root / "attachments" / p.name
                if not dest.exists() or dest.stat().st_size != p.stat().st_size:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(p, dest)
                saved.append(dest.relative_to(root).as_posix())
            except (OSError, ValueError):
                pass
    if saved:
        text += "\n\n[Attached files, saved in the working folder: " + ", ".join(saved) + "]"
    return text


@app.post("/api/runs/{run_id}/cancel")
async def cancel(run_id: str):
    return {"ok": await orchestrator.cancel_run(run_id)}


class ApprovalIn(BaseModel):
    hash: str
    approved: bool


@app.post("/api/approvals/{aid}")
def approve(aid: str, body: ApprovalIn):
    if not approvals.resolve(aid, body.hash, body.approved):
        raise fail(409, "approval_stale", "This approval is no longer valid")
    return {"ok": True}


# ---------- uploads ----------
@app.post("/api/sessions/{sid}/upload")
async def upload(sid: str, file: UploadFile):
    _session(sid)
    try:
        dest_dir = sessions.path(sid) / "uploads"
    except ValueError:
        raise fail(400, "bad_request", "Invalid chat id")
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = policy.resolve_in(dest_dir, Path(file.filename or "file").name)
    data = await file.read()
    dest.write_bytes(data)
    is_image = (file.content_type or "").startswith("image/")
    kind = "image" if is_image else "text" if _looks_text(data) else "binary"
    return {"name": dest.name, "path": str(dest), "size": len(data), "kind": kind}


@app.get("/api/sessions/{sid}/upload/raw")
def upload_raw(sid: str, name: str):
    """An attachment uploaded earlier (a saved composer draft brings its image back after a reload)."""
    _session(sid)
    try:
        dest = policy.resolve_in(sessions.path(sid) / "uploads", Path(name).name)
    except ValueError:
        raise fail(400, "bad_request", "Invalid name")
    if not dest.is_file():
        raise fail(404, "not_found", "Attachment not found")
    return FileResponse(dest)


def _looks_text(data: bytes) -> bool:
    try:
        data[:4096].decode("utf-8")
        return b"\x00" not in data[:4096]
    except UnicodeDecodeError:
        return False


# ---------- files (Monaco) ----------
def _root(sid: str, project_id: str | None = None) -> Path:
    """sid 'new' = a chat not created yet: the project folder if one is selected (else no folder yet)."""
    if sid == "new":
        return workspace.session_root(None, project_id)
    return workspace.session_root(_session(sid))


def _resolve(sid: str, path: str, project_id: str | None = None) -> Path:
    try:
        return policy.resolve_in(_root(sid, project_id), path)
    except PermissionError as e:
        raise to_http(e, 403)


def _find_file(sid: str, path: str, project_id: str | None = None) -> Path:
    """A file the model mentioned: the exact path, else the one file under the working folder whose path ends
    with it (models often write `report.xlsx` for `multitask/report.xlsx`). Newest wins when several match."""
    p = _resolve(sid, path, project_id)
    if p.is_file() or not path.strip() or ".." in path:
        return p
    root = _root(sid, project_id).resolve()
    tail = re.sub(r"^(\./)+", "", Path(path.replace("\\", "/")).as_posix())
    best, seen = None, 0
    for d, dirs, names in os.walk(root):
        dirs[:] = [x for x in dirs if x not in HIDDEN_DIRS and not x.startswith(".")]
        for n in names:
            seen += 1
            if n == Path(tail).name:
                c = Path(d) / n
                if c.relative_to(root).as_posix().endswith(tail) and (best is None or c.stat().st_mtime > best.stat().st_mtime):
                    best = c
        if seen > 20_000:
            break
    return best or p


@app.get("/api/sessions/{sid}/files")
def files(sid: str, project_id: str | None = None):
    root = _root(sid, project_id)
    if sid == "new" and not project_id:
        return {"root": "", "items": [], "pending": True}
    return {"root": str(root), "items": workspace.tree(root, 3000)}


@app.get("/api/sessions/{sid}/file")
def read_file(sid: str, path: str, project_id: str | None = None):
    p = _resolve(sid, path, project_id)
    if not p.is_file():
        raise HTTPException(404)
    return {"path": path, "content": p.read_text(encoding="utf-8", errors="replace")}


class FileIn(BaseModel):
    path: str
    content: str


@app.put("/api/sessions/{sid}/file")
def write_file(sid: str, body: FileIn, project_id: str | None = None):
    p = _resolve(sid, body.path, project_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body.content, encoding="utf-8", newline="")
    return {"ok": True}


# ---------- file manager ----------
HIDDEN_DIRS = {".git", "node_modules", "__pycache__", ".venv", ".aiiq", ".session"}


def _entry(p: Path, root: Path) -> dict:
    try:
        st = p.stat()
    except OSError:
        return {}
    is_dir = p.is_dir()
    return {"name": p.name, "path": p.relative_to(root).as_posix(), "dir": is_dir,
            "size": 0 if is_dir else st.st_size, "mtime": st.st_mtime,
            "ext": "" if is_dir else p.suffix.lstrip(".").lower(),
            "children": (any(True for c in p.iterdir() if not (c.is_dir() and c.name in HIDDEN_DIRS)) if is_dir else False)}


@app.get("/api/sessions/{sid}/fs/list")
def fs_list(sid: str, path: str = "", project_id: str | None = None, hidden: bool = False):
    root = _root(sid, project_id).resolve()
    if sid == "new" and not project_id:
        # A chat that does not exist yet has no folder: chat/<id>/ is made with its first message.
        return {"root": "", "path": "", "items": [], "pending": True}
    d = _resolve(sid, path or ".", project_id)
    if not d.is_dir():
        raise fail(404, "folder_not_found", "Folder not found")
    items = []
    try:
        for c in d.iterdir():
            if not hidden and (c.name in HIDDEN_DIRS or (c.name.startswith(".") and c.name != ".gitkeep")):
                continue
            e = _entry(c, root)
            if e:
                items.append(e)
    except PermissionError as e:
        raise to_http(e, 403)
    items.sort(key=lambda e: (not e["dir"], e["name"].lower()))
    return {"root": str(root), "path": "" if d == root else d.relative_to(root).as_posix(), "items": items[:5000]}


class FsOp(BaseModel):
    op: str  # mkdir | newfile | rename | delete
    path: str
    name: str | None = None


@app.post("/api/sessions/{sid}/fs/op")
def fs_op(sid: str, body: FsOp, project_id: str | None = None):
    import re
    root = _root(sid, project_id).resolve()
    target = _resolve(sid, body.path or ".", project_id)
    name = (body.name or "").strip()
    if body.op in ("mkdir", "newfile", "rename") and (not name or re.search(r'[<>:"/\\|?*]', name) or name in (".", "..")):
        raise fail(400, "invalid_name", "Invalid name")
    try:
        if body.op in ("mkdir", "newfile"):
            new = target / name
            if new.exists():
                raise fail(409, "name_exists", "An item with this name already exists")
            new.mkdir() if body.op == "mkdir" else new.write_text("", encoding="utf-8")
            return _entry(new, root)
        if target == root:
            raise fail(400, "root_protected", "The root folder cannot be changed")
        if body.op == "rename":
            new = target.with_name(name)
            if new.exists():
                raise fail(409, "name_exists", "An item with this name already exists")
            target.rename(new)
            return _entry(new, root)
        if body.op == "delete":
            from .config import rmtree_long
            rmtree_long(target, strict=True) if target.is_dir() else target.unlink()
            return {"ok": True}
    except OSError as e:
        raise to_http(e, 400)
    raise fail(400, "unknown_op", "Unknown operation")


@app.post("/api/sessions/{sid}/fs/upload")
async def fs_upload(sid: str, file: UploadFile, path: str = "", project_id: str | None = None):
    d = _resolve(sid, path or ".", project_id)
    if path and not d.exists():  # folder uploads recreate their structure
        d.mkdir(parents=True, exist_ok=True)
    if not d.is_dir():
        raise fail(404, "folder_not_found", "Folder not found")
    dest = _resolve(sid, (Path(path or ".") / Path(file.filename or "file").name).as_posix(), project_id)
    dest.write_bytes(await file.read())
    return _entry(dest, _root(sid, project_id).resolve())


@app.api_route("/api/sessions/{sid}/fs/raw", methods=["GET", "HEAD"])
def fs_raw(sid: str, path: str, project_id: str | None = None, download: bool = False):
    p = _find_file(sid, path, project_id)
    if not p.is_file():
        raise HTTPException(404)
    return FileResponse(p, filename=p.name if download else None,
                        content_disposition_type="attachment" if download else "inline")


@app.get("/api/sessions/{sid}/fs/exists")
def fs_exists(sid: str, path: str, project_id: str | None = None):
    """Whether a file the answer names exists (its chip opens it): an answer, not a 404 for every missing name."""
    try:
        return {"exists": _find_file(sid, path, project_id).is_file()}
    except HTTPException:
        return {"exists": False}


# ---------- video studio (Settings-free, per chat folder) ----------
# The studio and the edit_video tool share one project format: <name>.timeline.json next to <name>.mp4.
_PROBE_CACHE: dict[str, tuple[float, dict]] = {}


async def _probe_cached(p: Path) -> dict:
    from .tools import video_edit
    key, mt = str(p), p.stat().st_mtime
    hit = _PROBE_CACHE.get(key)
    if hit and hit[0] == mt:
        return hit[1]
    try:
        info = await asyncio.to_thread(video_edit._probe_sync, p)
    except Exception:  # noqa: BLE001  not a readable media file
        info = {"duration": 0, "video": False, "audio": False}
    _PROBE_CACHE[key] = (mt, info)
    return info


@app.get("/api/sessions/{sid}/video/media")
async def video_media(sid: str, project_id: str | None = None):
    """Pictures, videos and sounds in the working folder, with their length (for the studio's media bin)."""
    from .tools import video_edit
    root = _root(sid, project_id).resolve()
    out = []
    if root.is_dir():
        files = [p for p in root.rglob("*") if p.is_file() and not any(part.startswith(".") for part in p.relative_to(root).parts)
                 and p.suffix.lower() in video_edit.IMAGE_EXT | video_edit.VIDEO_EXT | video_edit.AUDIO_EXT
                 and not p.stem.endswith("_preview")]
        files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        for p in files[:400]:
            kind = video_edit._kind_of(p.name)
            info = await _probe_cached(p) if kind != "image" else {"duration": 0}
            out.append({"path": p.relative_to(root).as_posix(), "kind": kind, "duration": round(info.get("duration") or 0, 2),
                        "audio": bool(info.get("audio")), "size": p.stat().st_size})
    return {"media": out}


@app.get("/api/sessions/{sid}/video/project")
async def video_project(sid: str, path: str = "", project_id: str | None = None):
    """Opens a studio project: a .timeline.json, the project of a rendered video, or a new one around a video."""
    import json as _json

    from .tools import video_edit
    root = _root(sid, project_id).resolve()
    data: dict = {"aspect": "16:9", "look": "none", "scenes": [], "clips": [], "output": "videos/studio.mp4"}
    proj = None
    if path:
        p = _resolve(sid, path, project_id)
        cand = p if p.name.endswith(".timeline.json") else video_edit.project_path(p)
        if not cand.is_file() and not p.name.endswith(".timeline.json"):
            # a video opened before in the studio: its edit project (<name>_edit.timeline.json) opens again
            edit = p.with_name(f"{p.stem}_edit.timeline.json")
            cand = edit if edit.is_file() else cand
        if cand.is_file():
            try:
                data = {**data, **_json.loads(cand.read_text(encoding="utf-8"))}
                proj = cand.relative_to(root).as_posix()
            except (ValueError, OSError):
                pass
        elif p.is_file():
            kind = video_edit._kind_of(p.name)
            rel = p.relative_to(root).as_posix()
            if kind == "audio":
                data["music"] = {"src": rel}
            else:
                data["scenes"] = [{"src": rel, **({"dur": 5} if kind == "image" else {})}]
                if kind == "video":
                    info = await _probe_cached(p)
                    data["scenes"][0]["dur"] = round(info.get("duration") or 5, 2)
            data["output"] = (Path(rel).parent / f"{Path(rel).stem}_edit.mp4").as_posix()
    data.setdefault("scenes", [])
    data.setdefault("clips", [])
    return {"timeline": data, "project": proj}


class StudioIn(BaseModel):
    timeline: dict
    project_id: str | None = None


def _studio_target(sid: str, tl: dict, project_id: str | None) -> Path:
    out = str(tl.get("output") or "videos/studio.mp4").strip() or "videos/studio.mp4"
    if Path(out).suffix.lower() not in (".mp4", ".mov", ".mkv"):
        out += ".mp4"
    tl["output"] = out
    return _resolve(sid, out, project_id)


@app.put("/api/sessions/{sid}/video/project")
async def video_project_save(sid: str, body: StudioIn):
    from .tools import video_edit
    root = _root(sid, body.project_id).resolve()
    target = _studio_target(sid, body.timeline, body.project_id)
    p = video_edit.save_project(body.timeline, root, target)
    return {"project": p.relative_to(root).as_posix() if p else None}


@app.post("/api/sessions/{sid}/video/render")
async def video_render(sid: str, body: StudioIn):
    """Renders the studio's timeline with the same engine the edit_video tool uses."""
    from .tools import video_edit
    root = _root(sid, body.project_id).resolve()
    target = _studio_target(sid, body.timeline, body.project_id)
    sources = {str(x.get("src")) for x in (body.timeline.get("scenes") or []) + (body.timeline.get("clips") or [])
               if isinstance(x, dict)}
    if target.relative_to(root).as_posix() in sources:
        raise fail(400, "video_output_is_source", "The output file is also a source of this video: pick another output name")
    t0 = time.monotonic()
    try:
        res = await video_edit.render(body.timeline, root, target, load_settings().get("language") or "tr")
    except video_edit.TimelineError as e:
        raise fail(400, "timeline", str(e)) from None
    except RuntimeError as e:
        raise fail(500, "render_failed", str(e)[-600:]) from None
    rel = lambda p: p.relative_to(root).as_posix() if p else None  # noqa: E731
    return {"path": rel(target), "preview": rel(res.get("preview")), "project": rel(res.get("project")),
            "duration": res["duration"], "width": res["width"], "height": res["height"], "size": res["size"],
            "audio": res["audio"], "gaps": res["gaps"], "scenes": res["scenes"], "animated": res.get("animated"),
            "ms": int((time.monotonic() - t0) * 1000)}


STUDIO_AI = """You are the live editor inside a video studio. You get the video's project (JSON), the media files the
user has and a request. Reply with ONE JSON object and nothing else:
{"message": "<one short sentence in LANG saying what you changed>", "patch": {...}}
The patch changes ONLY what was asked; everything else stays. Patch format:
- "scenes": {"2": {"caption": "new text"}}  (use each scene's "#" number from the project; null removes a field or
  a scene)
- scene text fields: title, subtitle, caption, lower_third, text. A plain string uses the house style; an object
  places and styles it: {"text", "x": "6%", "y": "74%" (top-left in % of the frame, or "center"), "size_pct": 2-30
  (% of the short side), "color": "#ffffff", "box": "#C0392B@0.9" or null, "outline": "black", "bold": true,
  "font": "sans|serif|display|mono|script|condensed", "align": "center", "animation": "fade|slide_up|slide_left|pop|none"}
  To restyle only, send just the style fields: {"caption": {"color": "#ffd34d"}} keeps the text.
- other scene fields: dur, motion (zoom_in|zoom_out|pan_left|pan_right|pan_up|pan_down|none|auto), transition (fade,
  dissolve, slideleft, slideright, slideup, circleopen, wipeleft, smoothleft, zoomin, radial, fadeblack, cut, auto),
  fit (cover|blur|contain), say (a voice-over line), effects [..], animate (true: the photo really moves, AI, slow)
- "clips": {"1": {...}} change a layer by its "#" number (text styles only on a "type": "text" clip); "add_clips": [{"type": "text", "text", "start", "dur", ...style fields},
  {"type": "image", "src": "<a media path>", "start", "dur", "x", "y", "scale": 0.05-1, "opacity"}]; "remove_clips": [n]
- "logo": {"src": "<image path>", "position": "top_right|top_left|bottom_right|bottom_left", "size": 0.15}
- "add_scenes": [{"src": "<media path>", "dur": 4}], "remove_scenes": [n]
- whole video: "aspect" (16:9|9:16|1:1|4:5), "look" (none|warm|cinematic|vivid|bw|vintage|cool), "music"
  (generated original music: "corporate"|"upbeat"|"lofi"|"cinematic"|"acoustic"|"electronic"|"ambient"|"calm", or an
  <audio path>, or null; or {"src", "volume", "in", "start", "seed"}), "effects" (grain, old_film, vhs,
  glitch, shake, letterbox, glow, light_leak, sepia, bw, dreamy, vignette, sharpen, flash_in), "transition",
  "voice" ({"voice": "" (the user's default) | "piper:tr_TR-fettah-medium" (female) | "piper:tr_TR-99eren99-medium"
  (male) | "kokoro:af_heart" (English) | "tr-TR-EmelNeural" (online), "gender": female|male, "rate": 1, "pitch": 0,
  "emotion": 0.5, "studio": "video"}), "subtitles" (true: the voice-over's sentences burned in with real timings),
  "animate" (true: every photo really moves)
Use only media paths from the list. If the request needs pictures or clips that are not in the list (find, download,
generate), or information from the web, reply {"need_agent": true, "message": "<short sentence in LANG>"} instead."""


def _first_json(text: str) -> dict:
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", (text or "").strip())
    start = text.find("{")
    if start < 0:
        raise ValueError("no JSON in the answer")
    depth, in_str, esc = 0, False, False
    for i, ch in enumerate(text[start:], start):
        if in_str:
            esc = (ch == "\\") and not esc
            if ch == '"' and not esc:
                in_str = False
            elif ch != "\\":
                esc = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[start:i + 1])
    raise ValueError("unfinished JSON in the answer")


class StudioAIIn(BaseModel):
    timeline: dict
    request: str
    model: str
    project_id: str | None = None
    lang: str | None = None


@app.post("/api/sessions/{sid}/video/ai")
async def video_ai(sid: str, body: StudioAIIn):
    """Live AI edit in the studio: the model answers with a patch, applied at once (no render). Requests that need
    new media or the web come back as need_agent, and the studio hands them to the chat agent."""
    from .tools import video_edit
    if not body.request.strip():
        raise fail(400, "empty", "Say what to change")
    media = (await video_media(sid, body.project_id)).get("media", [])[:80]
    lang = (body.lang or load_settings().get("language") or "tr").lower()
    lang_name = {"tr": "Turkish", "en": "English"}.get(lang, lang)
    tl = video_edit.numbered_view({k: v for k, v in body.timeline.items() if k != "output"})
    user = json.dumps({"project": tl, "media": [{"path": m["path"], "kind": m["kind"], "seconds": m["duration"]}
                                                for m in media], "request": body.request.strip()}, ensure_ascii=False)
    messages = [{"role": "system", "content": STUDIO_AI.replace("LANG", lang_name)}, {"role": "user", "content": user}]
    t0 = time.monotonic()
    for attempt in range(2):  # one retry: a bad answer goes back to the model with the error
        try:
            reply = await asyncio.wait_for(router.complete(body.model, messages, {"temperature": 0.2}), 150)
        except Exception as e:  # noqa: BLE001  the model is busy / out of quota / offline
            raise fail(502, "studio_ai", f"{type(e).__name__}: {str(e)[:300]}") from None
        try:
            data = _first_json(reply)
            if data.get("need_agent"):
                return {"need_agent": True, "message": str(data.get("message") or ""),
                        "ms": int((time.monotonic() - t0) * 1000)}
            patch = data.get("patch") if isinstance(data.get("patch"), dict) else \
                {k: v for k, v in data.items() if k != "message"}
            new = video_edit.merge_patch(body.timeline, patch)
            if new.get("logo") or new.get("watermark"):
                new = video_edit.normalize(new, _root(sid, body.project_id).resolve())
            break
        except (ValueError, video_edit.TimelineError) as e:
            if attempt:
                code = "timeline" if isinstance(e, video_edit.TimelineError) else "studio_ai_format"
                raise fail(400 if code == "timeline" else 502, code, f"{e}: {reply[:300]}") from None
            messages += [{"role": "assistant", "content": reply[:4000]},
                         {"role": "user", "content": f"That patch failed: {e}. Use the \"#\" numbers shown in the "
                                                     "project. Reply with the corrected JSON object only."}]
    return {"timeline": new, "patch": patch, "message": str(data.get("message") or ""),
            "ignored": video_edit.ignored_keys(new), "ms": int((time.monotonic() - t0) * 1000)}


@app.get("/api/video/music")
async def video_music(kind: str = "ambient", seconds: int = 30, seed: int = 0):
    """Original background music of a style for the studio's live preview (the render makes the same track)."""
    from .config import DATA_DIR
    from .tools import video_edit
    if kind not in video_edit.GENERATED:
        raise fail(400, "bad_music", "unknown music style")
    seconds = max(5, min(int(seconds), 600))
    d = DATA_DIR / "music_cache"
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{kind}-{seconds}-{int(seed)}.wav"
    if not p.is_file():
        p = await video_edit.make_music(kind, seconds, p, int(seed))
    return FileResponse(p, media_type="audio/wav")


@app.get("/api/video/engines")
async def video_engines():
    """The free AI video engines (Hugging Face ZeroGPU Spaces) and their live state, for Settings > Web research:
    image-to-video (animate_image, the studio's "Animate with AI") and text-to-video (generate_video = a FLUX first
    frame + Wan 2.2). A Space that sleeps wakes on the first call; one that errors is skipped."""
    import httpx
    from .config import get_secret
    from .tools import animate

    async def state(c, space, kind):
        try:
            r = await c.get(f"https://huggingface.co/api/spaces/{space}", params={"expand[]": "runtime"})
            rt = (r.json().get("runtime") or {}) if r.status_code == 200 else {}
            stage = rt.get("stage") or ("MISSING" if r.status_code == 404 else f"HTTP {r.status_code}")
        except Exception as e:  # noqa: BLE001
            stage = f"offline: {type(e).__name__}"
        return {"id": space, "kind": kind, "stage": stage, "hardware": ((rt or {}).get("hardware") or {}).get("current"),
                "url": f"https://huggingface.co/spaces/{space}"} if isinstance(stage, str) else {}

    async with httpx.AsyncClient(timeout=10) as c:
        rows = await asyncio.gather(*(state(c, s, k) for s, k in animate.SPACES))
    return {"engines": [r for r in rows if r], "token": bool(get_secret("huggingface_api_key"))}


# ---------- royalty-free music library (Openverse: Jamendo, Freesound, Wikimedia; commercial-use licences) ----------
@app.get("/api/music/library")
async def music_library(q: str = "", page: int = 1):
    import httpx
    params = {"q": (q or "background music").strip()[:80], "license_type": "commercial", "category": "music",
              "page_size": 20, "page": max(1, min(int(page), 20)), "mature": "false"}
    # Openverse answers some query combinations with a passing 500: retry, then ask from Jamendo (all music) directly.
    tries = [params, params, {**params, "source": "jamendo"}, {k: v for k, v in params.items() if k != "category"}]
    rows, err = None, None
    async with httpx.AsyncClient(timeout=20, headers={"User-Agent": "AI-IQ-300 (music library)"}) as c:
        for p in tries:
            try:
                r = await c.get("https://api.openverse.org/v1/audio/", params=p)
                r.raise_for_status()
                rows = r.json().get("results") or []
                break
            except Exception as e:  # noqa: BLE001
                err = e
                if isinstance(e, httpx.HTTPStatusError) and e.response.status_code < 500:
                    break
    if rows is None:
        raise fail(502, "music_library", f"{type(err).__name__}: {str(err)[:200]}")
    out = []
    for x in rows:
        url = x.get("url") or ""
        if not url:
            continue
        lic = (("" if (x.get("license") or "").lower() in ("cc0", "pdm") else "CC ") + f"{(x.get('license') or '').upper()} {x.get('license_version') or ''}").strip()
        out.append({"title": x.get("title") or "?", "creator": x.get("creator") or "?", "license": lic,
                    "duration": round((x.get("duration") or 0) / 1000, 1), "url": url, "source": x.get("foreign_landing_url") or url,
                    "provider": x.get("source") or x.get("provider") or "", "genres": x.get("genres") or []})
    return {"tracks": out}


class TrackIn(BaseModel):
    url: str
    title: str = "track"
    creator: str = ""
    license: str = ""
    source: str = ""
    project_id: str | None = None


@app.post("/api/sessions/{sid}/music/download")
async def music_download(sid: str, body: TrackIn):
    """A library track into the chat's music/ folder, its credit written to music/CREDITS.txt."""
    import httpx
    if not re.match(r"https://", body.url):
        raise fail(400, "bad_url", "https only")
    slug = re.sub(r"[^a-z0-9]+", "-", body.title.lower()).strip("-")[:40] or "track"
    target = _resolve(sid, f"music/{slug}.mp3", body.project_id)
    if not target.is_file():
        try:
            async with httpx.AsyncClient(timeout=60, follow_redirects=True) as c:
                r = await c.get(body.url)
            r.raise_for_status()
            if not r.headers.get("content-type", "").startswith(("audio/", "application/octet-stream")):
                raise ValueError(f"not an audio file ({r.headers.get('content-type')})")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(r.content)
        except Exception as e:  # noqa: BLE001
            raise fail(502, "music_download", f"{type(e).__name__}: {str(e)[:200]}") from None
        with open(target.parent / "CREDITS.txt", "a", encoding="utf-8") as f:
            f.write(f"{target.name}: \"{body.title}\" by {body.creator} - {body.license} - {body.source}\n")
    root = _root(sid, body.project_id).resolve()
    info = await _probe_cached(target)
    return {"path": target.relative_to(root).as_posix(), "duration": round(info.get("duration") or 0, 2)}


class VoiceClipIn(BaseModel):
    text: str
    voice: str = ""
    rate: float = 1.0
    project_id: str | None = None


@app.post("/api/sessions/{sid}/video/voice")
async def video_voice(sid: str, body: VoiceClipIn):
    """A voice-over clip for the studio: the text read by the chosen free neural voice, saved under media/voice/."""
    import hashlib
    from .tools import speech
    if not body.text.strip():
        raise fail(400, "empty", "Nothing to read")
    from .voice.render import lang_of, settings as voice_settings
    lang = (lang_of(body.voice) if body.voice else (load_settings().get("language") or "tr")).lower()
    tone = {k: voice_settings()[k] for k in ("pitch", "emotion", "studio", "room", "pause")}
    h = hashlib.sha1(f"{body.voice}|{body.rate}|{tone}|{body.text}".encode()).hexdigest()[:10]
    target = _resolve(sid, f"media/voice/voice-{h}.mp3", body.project_id)
    if not target.is_file():
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            await speech.text_to_speech(body.text.strip(), target, lang, body.voice, "", float(body.rate or 1.0))
        except Exception as e:  # noqa: BLE001
            raise fail(502, "tts_failed", str(e)[:300]) from None
    root = _root(sid, body.project_id).resolve()
    info = await _probe_cached(target)
    return {"path": target.relative_to(root).as_posix(), "duration": round(info.get("duration") or 0, 2)}


@app.post("/api/stt")
async def stt(file: UploadFile, language: str = "", model: str = "base"):
    """Speech to text for any recording or video (offline faster-whisper): text with times, and SRT subtitles."""
    import tempfile
    from .tools import speech
    if model not in ("tiny", "base", "small", "medium"):
        model = "base"
    d = Path(tempfile.mkdtemp(prefix="aiiq-stt-"))
    try:
        src = d / (Path(file.filename or "audio").name or "audio")
        src.write_bytes(await file.read())
        try:
            res = await speech.speech_to_text(src, d, language or None, model)
        except Exception as e:  # noqa: BLE001
            raise fail(500, "stt_failed", f"{type(e).__name__}: {str(e)[:300]}") from None
        plain = res["txt"].read_text(encoding="utf-8") if res.get("txt") else ""
        srt = res["srt"].read_text(encoding="utf-8") if res.get("srt") else ""
        return {"language": res.get("language"), "text": plain.strip(), "srt": srt, "segments": res.get("segments"),
                "seconds": res.get("duration")}
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ---------- logo maker ----------
class LogoIconIn(BaseModel):
    prompt: str
    style: str = "minimal"
    colors: str = ""
    n: int = 3


@app.post("/api/logo/icons")
async def logo_icons(body: LogoIconIn):
    """Logo symbols drawn by the image services (keyed ones first, free FLUX last), background removed (PNG)."""
    import base64
    import random
    from .tools import imagegen, logo
    prompt = (f"{body.prompt.strip()[:300]}, {body.style} logo symbol, flat vector icon, simple bold shapes, centered, "
              f"isolated on a pure white background, no text, no letters, no words, no watermark"
              + (f", colors {body.colors[:80]}" if body.colors else ""))
    async def one(seed: int):
        try:
            data, sid, _ = await imagegen.generate(prompt, 768, 768, seed)
            png = await asyncio.to_thread(logo.cutout, data)
            return {"png": "data:image/png;base64," + base64.b64encode(png).decode(), "service": sid}
        except Exception as e:  # noqa: BLE001
            return {"error": str(e)[:200]}
    res = await asyncio.gather(*(one(random.randint(1, 10**6)) for _ in range(max(1, min(body.n, 4)))))
    icons = [r for r in res if r.get("png")]
    if not icons:
        raise fail(502, "logo_icons", "; ".join(r.get("error", "") for r in res)[:400])
    return {"icons": icons, "errors": [r["error"] for r in res if r.get("error")]}


@app.post("/api/logo/cutout")
async def logo_cutout(file: UploadFile):
    """Transparent background for an uploaded logo / picture (the plain background around it is removed)."""
    import base64
    from .tools import logo
    data = await file.read()
    try:
        png = await asyncio.to_thread(logo.cutout, data)
    except Exception as e:  # noqa: BLE001
        raise fail(400, "cutout", str(e)[:200]) from None
    return {"png": "data:image/png;base64," + base64.b64encode(png).decode()}


class LogoSuggestIn(BaseModel):
    brand: str
    slogan: str = ""
    industry: str = ""
    model: str
    lang: str | None = None


@app.post("/api/logo/suggest")
async def logo_suggest(body: LogoSuggestIn):
    """Three brand directions from the selected model: fonts, colours, layout, symbol prompt (the maker draws them)."""
    from .tools import logo
    lang = {"tr": "Turkish", "en": "English"}.get((body.lang or "tr").lower(), "English")
    messages = [{"role": "system", "content": logo.SUGGEST.replace("LANG", lang)},
                {"role": "user", "content": json.dumps({"brand": body.brand, "slogan": body.slogan, "industry": body.industry},
                                                       ensure_ascii=False)}]
    try:
        reply = await asyncio.wait_for(router.complete(body.model, messages, {"temperature": 0.8}), 120)
        data = _first_json(reply)
    except Exception as e:  # noqa: BLE001
        raise fail(502, "logo_suggest", f"{type(e).__name__}: {str(e)[:300]}") from None
    return {"variants": logo.clean_variants(data.get("variants") or [])}


@app.get("/api/sessions/{sid}/fs/preview")
def fs_preview(sid: str, path: str, project_id: str | None = None):
    """A web page from the working folder, served on the separate preview origin (assets load relatively)."""
    p = _find_file(sid, path, project_id)
    if not p.is_file():
        raise fail(404, "file_not_found", "File not found")
    from . import preview_server
    root = _root(sid, project_id).resolve()
    return {"url": preview_server.url_for(root, p.resolve().relative_to(root).as_posix())}


@app.get("/api/sessions/{sid}/fs/slides")
def fs_slides(sid: str, path: str, project_id: str | None = None):
    """PowerPoint preview: every slide's title, text lines and notes (browsers cannot render .pptx)."""
    p = _find_file(sid, path, project_id)
    if not p.is_file() or p.suffix.lower() != ".pptx":
        raise fail(404, "file_not_found", "File not found")
    from .tools import slides_view
    try:
        return slides_view.slides(p)  # positioned shapes: text, pictures, tables, charts, backgrounds
    except Exception as e:
        raise fail(400, "bad_document", f"Unreadable presentation: {e}")


@app.get("/api/sessions/{sid}/history")
async def history(sid: str, project_id: str | None = None):
    root = _root(sid, project_id)
    return [] if root.parent == workspace.CHATS_DIR or not root.exists() else await workspace.git_history(root)


@app.post("/api/sessions/{sid}/rollback/{sha}")
async def rollback(sid: str, sha: str, project_id: str | None = None):
    try:
        return {"sha": await workspace.git_rollback(_root(sid, project_id), sha)}
    except (ValueError, RuntimeError) as e:
        raise to_http(e, 400)


# ---------- processes ----------
class ProcIn(BaseModel):
    command: str
    shell: str = "powershell"
    cwd: str = "."
    session_id: str


@app.get("/api/processes")
def processes():
    return manager.list()


@app.post("/api/processes")
async def start_process(body: ProcIn):
    """User-initiated command from the UI terminal. Forbidden commands are still refused."""
    from .tools.registry import ToolContext, build_argv
    if policy.decide_command(body.command, "full").action == "deny":
        raise fail(403, "forbidden_command", "Command forbidden by policy")
    root = _root(body.session_id)
    cwd = policy.resolve_in(root, body.cwd)
    ctx = ToolContext("user", root, "full", asyncio.Event())
    info = await manager.start(build_argv(ctx, body.shell, body.command), str(cwd), policy.minimal_env(),
                               owner=f"{body.session_id}:user")
    return info.public()


@app.post("/api/processes/{pid}/stop")
async def stop_process(pid: str):
    return {"ok": await manager.stop(pid)}


# ---------- models, settings, catalog ----------
@app.get("/api/models")
async def models():
    return await router.list_all_models()


@app.get("/api/web/search")
async def web_search_test(q: str):
    """Settings > Web: try the configured search engines with a query."""
    from .tools import web
    t0 = time.perf_counter()
    web._CACHE.pop(" ".join(q.split()).lower(), None)  # a test always asks the engines
    report: dict = {}
    results, engines = await web.search(q, report=report)
    return {"engines": engines, "count": len(results), "ms": int((time.perf_counter() - t0) * 1000), "results": results[:8],
            "report": report}


class EngineTestIn(BaseModel):
    q: str = ""


@app.post("/api/web/test/{engine}")
async def web_engine_test(engine: str, body: EngineTestIn):
    from .tools import web
    return await web.test_engine(engine, body.q.strip() or "OpenAI API documentation")


@app.post("/api/maps/test/{provider}")
async def maps_test(provider: str, body: EngineTestIn):
    """One place provider alone with a sample search, its own error shown (Settings > Web research)."""
    from .tools import maps
    t0 = time.monotonic()
    q = body.q.strip() or "eczane"
    try:
        res = await maps.find_places(q, near="Kadıköy, İstanbul", radius=2000, limit=5,
                                     lang=load_settings().get("language") or "tr", provider=provider)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)[:300]}
    ok = bool(res["results"]) and res["provider"] != "-"
    return {"ok": ok, "count": len(res["results"]), "ms": int((time.monotonic() - t0) * 1000), "provider": res["provider"],
            "results": [{"title": r.get("name", ""), "url": r.get("maps_url") or r.get("url") or ""} for r in res["results"][:5]],
            **({} if ok else {"error": "; ".join(res["notes"]) or "no results"})}


@app.post("/api/media/test/{service}")
async def media_test(service: str, body: EngineTestIn):
    """One image service alone (Settings > Web > Image services): a small picture, or its own error."""
    from .tools import imagegen, services
    t0 = time.monotonic()
    if service != "pollinations" and service in services.CATALOG and not services.has_key(service):
        return {"ok": False, "error": "no key saved for this service: enter and save the key first"}
    try:
        data = await imagegen.generate_with(service, body.q.strip() or "a cup of coffee on a wooden table, photo", 256, 256)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)[:300]}
    clean = service != "pollinations" or bool(imagegen.token())
    return {"ok": True, "ms": int((time.monotonic() - t0) * 1000), "count": 1, "provider": service,
            "results": [{"title": f"{len(data) // 1024} KB" + (" · logo-free" if clean else " · with the free tier's logo"),
                         "url": ""}]}


@app.get("/api/media/models/{kind}/{service}")
async def media_models(kind: str, service: str):
    """The models an image / video service may use (only that kind), its default and the current choice."""
    from .tools import mediamodels
    if kind not in mediamodels.MODELS or service not in mediamodels.MODELS[kind]:
        return {"choices": [], "default": "", "current": ""}
    return {"choices": await mediamodels.choices(kind, service), "default": await mediamodels.default(kind, service),
            "current": await mediamodels.current(kind, service)}


@app.post("/api/video/test/{service}")
async def video_test(service: str, body: EngineTestIn, real: bool = False):
    """One AI video service alone (Settings > Web > AI video). Without real: a key / availability check that costs
    nothing. With real=true: a real 2-4 s clip from a small generated picture (paid services charge for it)."""
    import httpx
    from .config import get_secret
    from .tools import animate, services
    t0 = time.monotonic()
    spec = services.CATALOG.get(service)
    if not spec or spec["kind"] != "video":
        return {"ok": False, "error": "unknown video service"}
    if not services.has_key(service):
        return {"ok": False, "error": "no key saved for this service: enter and save the key first"}
    try:
        if real:
            from PIL import Image, ImageDraw
            import tempfile
            pic = Path(tempfile.mkdtemp()) / "test.jpg"
            im = Image.new("RGB", (768, 432), (40, 90, 160))
            d = ImageDraw.Draw(im)
            d.ellipse((300, 120, 470, 290), fill=(250, 200, 60))
            d.rectangle((0, 330, 768, 432), fill=(30, 130, 60))
            im.save(pic, quality=90)
            clip = await services.call(service, lambda: animate.make_with(service, pic, body.q.strip() or
                                       "the sun slowly rises over green hills, gentle camera move", 4.0))
            size = Path(clip).stat().st_size
            return {"ok": size > 1000, "ms": int((time.monotonic() - t0) * 1000), "count": 1, "provider": service,
                    "results": [{"title": f"MP4 {size // 1024} KB", "url": ""}]}
        async with httpx.AsyncClient(timeout=20) as c:
            if spec.get("free"):
                r = await c.get(f"https://huggingface.co/api/spaces/{spec['space']}", params={"expand[]": "runtime"})
                stage = ((r.json().get("runtime") or {}).get("stage") if r.status_code == 200 else f"HTTP {r.status_code}")
                ok, info = stage == "RUNNING" or stage in ("SLEEPING", "PAUSED"), str(stage)
            elif service == "veo":
                from .tools import mediamodels
                names = mediamodels.of_kind("video", await mediamodels.gemini_models())
                ok, info = bool(names), ", ".join(names[:4]) or "this Gemini key lists no Veo model"
            elif service == "replicate":
                r = await c.get("https://api.replicate.com/v1/account",
                                headers={"Authorization": f"Bearer {get_secret('replicate_api_key')}"})
                ok, info = r.status_code == 200, (r.json().get("username") if r.status_code == 200 else f"HTTP {r.status_code}: {r.text[:120]}")
            elif service == "runway":
                r = await c.get("https://api.dev.runwayml.com/v1/organization",
                                headers={"Authorization": f"Bearer {get_secret('runway_api_key')}", "X-Runway-Version": "2024-11-06"})
                ok = r.status_code == 200
                info = (f"credits: {r.json().get('creditBalance')}" if ok else f"HTTP {r.status_code}: {r.text[:120]}")
            else:  # fal.ai: an unknown request id answers 404 with a valid key, 401 / 403 with a wrong one
                r = await c.get("https://queue.fal.run/fal-ai/fast-sdxl/requests/00000000-0000-0000-0000-000000000000/status",
                                headers={"Authorization": f"Key {get_secret('fal_api_key')}"})
                ok, info = r.status_code not in (401, 403), ("key accepted" if r.status_code not in (401, 403) else f"HTTP {r.status_code}: {r.text[:120]}")
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)[:300]}
    return {"ok": ok, "ms": int((time.monotonic() - t0) * 1000), "count": 1, "provider": service,
            "results": [{"title": info, "url": ""}], **({} if ok else {"error": info})}


@app.post("/api/stock/test/{service}")
async def stock_test(service: str, body: EngineTestIn):
    """One photo service alone (Settings > Web > Photo services): a sample search with its own error."""
    from .tools import stock, services
    t0 = time.monotonic()
    if service in services.CATALOG and not services.has_key(service):
        return {"ok": False, "error": "no key saved for this service: enter and save the key first"}
    try:
        items = await stock.test_service(service, body.q.strip() or "coffee cup")
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)[:300]}
    return {"ok": bool(items), "ms": int((time.monotonic() - t0) * 1000), "count": len(items), "provider": service,
            "results": [{"title": f"{x['title'][:60]} · {x['author']} · {x['license']}", "url": x.get("source", "")}
                        for x in items[:5]],
            **({} if items else {"error": "no photo found for this query"})}


@app.get("/api/services")
def services_status():
    """Quota and status of the keyed image and photo services (usage counters, blocks, remaining quota headers)."""
    from .tools import services
    return {"services": services.status()}


@app.get("/api/models/providers")
def model_providers():
    """Fast (no network): which providers are usable now. The UI then loads each one's models in parallel."""
    return router.usable_providers()


@app.get("/api/models/of/{pid}")
async def models_of(pid: str, refresh: bool = False):
    return await router.models_for(pid, refresh)


@app.get("/api/models/context")
async def model_context(model: str):
    return await router.context_info(model)


class ModelIn(BaseModel):
    model: str
    num_ctx: int | None = None


@app.post("/api/models/activate")
async def activate_model(body: ModelIn):
    save_settings({"active_model": body.model})
    _bg(router.activate(body.model))
    _bg(router.context_info(body.model))  # its window is known before the first message
    return {"ok": True}


class ProfileIn(BaseModel):
    model: str
    thinking: str = "auto"
    vision: str = "auto"
    streaming: str = "auto"
    tools: str = "auto"
    temperature: float | None = None
    max_tokens: int | None = None
    effort: str | None = None


@app.put("/api/models/profile")
def put_model_profile(body: ProfileIn):
    """Model profile: per-model thinking / vision / streaming / tool-call overrides and sampling limits.
    Everything on 'auto' (and no numbers) removes the profile."""
    if ":" not in body.model:
        raise fail(400, "bad_model", "Model id must be 'provider:model'")
    data = body.model_dump()
    for k, choices in router.PROFILE_CHOICES.items():
        if data[k] not in choices:
            raise fail(400, "bad_profile", f"{k} must be one of {', '.join(choices)}")
    if body.temperature is not None and not 0 <= body.temperature <= 2:
        raise fail(400, "bad_profile", "temperature must be between 0 and 2")
    if body.effort is not None and body.effort not in router.EFFORT_LEVELS:
        raise fail(400, "bad_profile", f"effort must be one of {', '.join(router.EFFORT_LEVELS)}")
    if body.max_tokens is not None and not 1 <= body.max_tokens <= 1_000_000:
        raise fail(400, "bad_profile", "max_tokens must be between 1 and 1000000")
    prof = {k: v for k, v in data.items() if k != "model" and v not in ("auto", None)}
    save_settings({"model_profiles": {body.model: None}})  # replace, do not merge with the old profile
    if prof:
        save_settings({"model_profiles": {body.model: prof}})
    return {"model": body.model, "profile": prof}


@app.put("/api/models/context")
async def set_model_context(body: ModelIn):
    info = await router.context_info(body.model)
    n = max(2048, min(int(body.num_ctx or info["max"]), info["max"]))
    save_settings({"context": {"num_ctx": {body.model: n}}})
    return {**info, "current": n}


# ---------- voices: local (Piper, Kokoro, Chatterbox) + Microsoft's online voices ----------
async def _all_voices(lang: str = "") -> tuple[list[dict], str | None]:
    """Every voice for the pickers: local ones (installed or downloadable) first, then the online ones."""
    from . import tts
    from .voice import catalog
    local = await catalog.local_voices(lang)
    err = None
    try:
        edge = [{**v, "engine": "edge", "lang": v["locale"][:2].lower(), "country": v["locale"].split("-")[-1],
                 "quality": "high", "offline": False, "installed": True} for v in await tts.voices(lang)]
    except tts.TTSError as e:  # offline: the local voices still work
        edge, err = [], str(e)
    return local + edge, err


@app.get("/api/tts/voices")
async def tts_voices(lang: str = ""):
    voices, err = await _all_voices(lang)
    return {"ok": bool(voices), "voices": voices, **({"error": err} if err and not voices else {})}


def _studio_presets():
    from .voice.studio import PRESETS
    return PRESETS


@app.get("/api/voices")
async def voices_list(lang: str = ""):
    from .voice import catalog, render
    voices, err = await _all_voices(lang)
    return {"voices": voices, "online_error": err, "progress": catalog.PROGRESS, "settings": render.settings(),
            "presets": list(_studio_presets()),
            "engines": {"piper": sum(1 for v in voices if v["engine"] == "piper" and v["installed"]),
                        "kokoro": catalog.kokoro_installed(), "chatterbox": catalog.cbx_python() is not None,
                        "edge": not err}}


class VoiceIdIn(BaseModel):
    id: str


_VOICE_TASKS: set = set()


@app.post("/api/voices/install")
async def voices_install(body: VoiceIdIn):
    """Download a local voice in the background; GET /api/voices shows the progress."""
    from .voice import catalog
    if not re.fullmatch(r"(piper|kokoro|chatterbox):[\w.@-]{1,80}", body.id):
        raise fail(400, "bad_voice", "Unknown voice")
    cur = catalog.PROGRESS.get(body.id)
    if cur and cur.get("state") in ("downloading", "measuring", "installing"):
        return {"ok": True, "progress": cur}

    async def job() -> None:
        try:
            await catalog.install(body.id)
            bus.publish("system", "voice", {"id": body.id, "state": "done"})
        except Exception as e:  # noqa: BLE001
            bus.publish("system", "voice", {"id": body.id, "state": "error", "error": str(e)[:300]})
    t = asyncio.create_task(job())
    _VOICE_TASKS.add(t)
    t.add_done_callback(_VOICE_TASKS.discard)
    await asyncio.sleep(0)
    return {"ok": True, "progress": catalog.PROGRESS.get(body.id)}


@app.delete("/api/voices/{vid:path}")
def voices_remove(vid: str):
    from .voice import catalog, engines
    if vid.startswith("ref:"):
        name = vid[4:]
        if not re.fullmatch(r"[\w-]{1,40}", name):
            raise fail(400, "bad_voice", "Unknown voice")
        (catalog.REFS_DIR / f"{name}.wav").unlink(missing_ok=True)
        return {"ok": True}
    if not re.fullmatch(r"(piper|kokoro|chatterbox):[\w.@-]{1,80}", vid):
        raise fail(400, "bad_voice", "Unknown voice")
    if vid.startswith("chatterbox:"):
        engines.CBX.stop()
    engines._PIPER.pop(vid.split(":", 1)[1], None)
    if vid.startswith("kokoro:"):
        engines._KOKORO.clear()
    catalog.remove(vid)
    return {"ok": True}


class VoicePreviewIn(BaseModel):
    text: str
    voice: str
    rate: float = 1.0
    pitch: float | None = None
    emotion: float | None = None
    preset: str | None = None
    room: bool | None = None
    pause: float | None = None


@app.post("/api/voices/preview")
async def voices_preview(body: VoicePreviewIn):
    from . import tts
    tone = {k: v for k, v in body.model_dump().items() if k in ("pitch", "emotion", "preset", "room", "pause") and v is not None}
    try:
        audio = await tts.synthesize(body.text, body.voice, body.rate, tone)
    except tts.TTSError as e:
        raise fail(400 if str(e) in ("nothing to read", "unknown voice") else 502, "tts_failed", str(e))
    return Response(audio, media_type="audio/mpeg", headers={"Cache-Control": "no-store"})


@app.post("/api/voices/reference")
async def voices_reference(file: UploadFile, name: str = Form(...), consent: bool = Form(False)):
    """The user's own voice (or one they have permission to use) as a Chatterbox reference: 5-30 s, cleaned to
    24 kHz mono WAV; its pitch gives the gender label."""
    from .voice import catalog, engines
    if not consent:
        raise fail(400, "consent_required", "Confirm that this is your voice or that you have permission to use it")
    name = re.sub(r"[^\w-]+", "-", name.strip())[:40].strip("-")
    if not name:
        raise fail(400, "bad_name", "Give the voice a name")
    data = await file.read()
    if len(data) > 30 * 1024 * 1024:
        raise fail(400, "too_large", "Reference clip is too large")
    try:
        x, sr = await asyncio.to_thread(engines.decode, data, 24000)
    except Exception as e:  # noqa: BLE001
        raise fail(400, "bad_audio", f"Could not read the audio: {str(e)[:200]}")
    secs = len(x) / sr
    if secs < 4:
        raise fail(400, "too_short", "The clip must be at least 5 seconds of speech")
    x = x[: int(sr * 30)]
    catalog.REFS_DIR.mkdir(parents=True, exist_ok=True)
    import wave
    import numpy as np
    with wave.open(str(catalog.REFS_DIR / f"{name}.wav"), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((np.clip(x / max(1e-6, float(np.abs(x).max())) * 0.9, -1, 1) * 32767).astype(np.int16).tobytes())
    hz = catalog.pitch_hz(x, sr)
    return {"ok": True, "name": name, "seconds": round(min(secs, 30), 1), "gender": catalog.save_reference(name, catalog.REFS_DIR / f"{name}.wav", hz)}


# ---------- document templates (make_doc template=<id>; the gallery above the composer) ----------
@app.get("/api/doc-templates")
def doc_templates_list(kind: str = "", lang: str = "tr"):
    from .tools import doc_templates as dt
    return {"templates": [{"id": t["id"], "kinds": t["kinds"], "name": dt.text(t, "name", lang),
                           "desc": dt.text(t, "desc", lang), "outline": dt.text(t, "outline", lang) or [],
                           "colors": t["colors"], "user": bool(t.get("user")),
                           "instruction": dt.instruction(t, lang)} for t in dt.all_templates(kind)]}


@app.get("/api/doc-templates/{tid}/preview")
def doc_template_preview(tid: str, kind: str = "", lang: str = "tr"):
    """The template's thumbnail: real HTML in its colours, type and cover (shown scaled in an iframe)."""
    from .tools import doc_templates as dt
    t = dt.get(tid)
    if not t:
        raise fail(404, "not_found", "No such template")
    return Response(dt.preview_html(t, lang, kind), media_type="text/html",
                    headers={"Cache-Control": "max-age=300"})


@app.delete("/api/doc-templates/{tid}")
def doc_template_delete(tid: str):
    from .tools import doc_templates as dt
    if not dt.delete_user(tid):
        raise fail(404, "not_found", "Only templates you made can be deleted")
    return {"ok": True}


class TTSIn(BaseModel):
    text: str
    voice: str
    rate: float = 1.0


@app.post("/api/tts")
async def tts_speak(body: TTSIn):
    from . import tts
    try:
        audio = await tts.synthesize(body.text, body.voice, body.rate)
    except tts.TTSError as e:
        bad_input = str(e) in ("nothing to read", "unknown voice")
        raise fail(400 if bad_input else 502, "tts_failed", str(e))
    return Response(audio, media_type="audio/mpeg", headers={"Cache-Control": "no-store"})


class TTSFileIn(BaseModel):
    text: str
    voice: str
    path: str
    rate: float = 1.0
    pitch: float | None = None
    emotion: float | None = None
    preset: str | None = None
    pause: float | None = None


@app.post("/api/sessions/{sid}/tts-file")
async def tts_file(sid: str, body: TTSFileIn):
    """The voice picker under a generated audio: the same text again with the voice the user chose, written over the
    file in the chat's folder (only .mp3 inside the folder)."""
    from .tools import speech
    root = workspace.session_root(_session(sid)).resolve()
    target = (root / body.path).resolve()
    if root not in target.parents or target.suffix.lower() != ".mp3":
        raise fail(400, "bad_path", "Only an .mp3 inside the chat's folder")
    try:
        res = await speech.text_to_speech(body.text[:20000], target, "", body.voice, "", body.rate, pitch=body.pitch,
                                          emotion=body.emotion, preset=body.preset or None, pause=body.pause)
    except Exception as e:  # offline, unknown voice
        raise fail(502, "tts_failed", str(e)[:300])
    # The chosen voice is kept with the answer, so the card shows it after a reload too.
    for row in db.query("SELECT id, meta FROM messages WHERE session_id=? AND role='assistant' ORDER BY id DESC LIMIT 20",
                        (sid,)):
        try:
            meta = json.loads(row["meta"] or "{}")
        except ValueError:
            continue
        hit = [s for s in meta.get("steps") or [] if (s.get("data") or {}).get("tts") and s["data"].get("path") == body.path]
        if hit:
            for s in hit:
                s["data"]["tts"]["voice"] = res["voice"]
            db.execute("UPDATE messages SET meta=? WHERE id=?", (json.dumps(meta, ensure_ascii=False), row["id"]))
            break
    return {"ok": True, "path": body.path, "voice": res["voice"], "bytes": res["bytes"]}


# ---------- providers ----------
class ProviderIn(BaseModel):
    name: str
    kind: str = "openai"
    base_url: str = ""
    enabled: bool = True
    local: bool = False
    streaming: bool = True
    auth_header: str | None = None
    model: str | None = None
    account_id: str | None = None  # Cloudflare Workers AI


@app.put("/api/providers/{pid}")
def put_provider(pid: str, body: ProviderIn):
    import re
    if not re.fullmatch(r"[a-z0-9_-]{1,40}", pid) or body.kind not in ("openai", "ollama", "anthropic", "gemini", "cloudflare"):
        raise fail(400, "invalid_provider", "Invalid provider id or protocol")
    router.invalidate_models(pid)
    patch = {"providers": {pid: body.model_dump(exclude_none=True)}}
    if pid == "cloudflare":
        _sync_shared(patch)
    return save_settings(patch)


@app.delete("/api/providers/{pid}")
def delete_provider(pid: str):
    set_secret(f"{pid}_api_key", None)
    router.invalidate_models(pid)
    return save_settings({"providers": {pid: None}})


@app.get("/api/providers/{pid}/terms")
async def provider_terms(pid: str):
    """EVREN: current terms status + text, so the user can read them before accepting."""
    from .llm.providers import ProviderError
    prov = router.get_provider(pid, require_enabled=False)
    if not hasattr(prov, "terms"):
        raise fail(400, "no_terms", "This provider has no terms to accept")
    try:
        return await prov.terms()
    except ProviderError as e:
        raise to_http(e, 502)


class TermsIn(BaseModel):
    version: int


@app.post("/api/providers/{pid}/terms/accept")
async def provider_terms_accept(pid: str, body: TermsIn):
    """Called only from the UI after the user read the terms and clicked accept."""
    from .llm.providers import ProviderError
    try:
        r = await router.get_provider(pid, require_enabled=False).accept_terms(body.version)
        router.invalidate_models(pid)
        return r
    except (ProviderError, AttributeError) as e:
        raise to_http(e, 502)


@app.post("/api/providers/{pid}/test")
async def test_provider(pid: str):
    from .llm.providers import ProviderError
    t0 = time.perf_counter()
    try:
        out = await asyncio.wait_for(router.get_provider(pid, require_enabled=False).test(), 20)
        router.invalidate_models(pid)  # the model list is re-read at once, so an old error does not linger
        return {"ok": True, "ms": int((time.perf_counter() - t0) * 1000), **out}
    except ProviderError as e:
        return {"ok": False, "code": e.code, "error": str(e)}
    except asyncio.TimeoutError:
        return {"ok": False, "code": "timeout", "error": "Timed out after 20 s"}
    except Exception as e:
        return {"ok": False, "code": "error", "error": f"{type(e).__name__}: {e}"}


@app.get("/api/models/health")
async def models_health():
    """Asked by the UI at start and on focus (the server pushes changes itself, see _health_watch)."""
    return await _health_now()


async def _health_watch() -> None:
    """Watches local servers and the settings file in the background and pushes a 'health' event to every window
    only when something changed (a local server started / stopped, a model was pulled, settings saved elsewhere).
    The page used to ask every 3 s, which filled the server log with health requests during long tasks."""
    last = None
    while True:
        try:
            now = await _health_now()
            if now != last:
                if last is not None:
                    bus.publish("health", "changed", now)
                last = now
        except Exception:  # noqa: BLE001 - a failing check never stops the watcher
            pass
        await asyncio.sleep(4)


async def _health_now() -> dict:
    """Is each enabled local server up (and its model list fingerprint), and the settings revision."""
    import httpx
    from .config import SETTINGS_FILE
    settings = load_settings()

    async def ping(pid: str, cfg: dict) -> tuple[bool, str]:
        """(up, fingerprint of the model list): the list call itself is the ping, so a model pulled in Ollama or
        loaded in LM Studio shows up too, not only a server that starts."""
        base = (cfg.get("base_url") or "").rstrip("/")
        ollama = cfg.get("kind", pid) == "ollama"
        url = f"{base}/api/tags" if ollama else f"{base}/models"
        try:
            async with httpx.AsyncClient(timeout=1.5) as c:
                r = await c.get(url)
        except httpx.HTTPError:
            return False, ""
        if r.status_code >= 500:
            return False, ""
        try:
            data = r.json()
            names = sorted(str(m.get("name") or m.get("id") or "") for m in (data.get("models") if ollama else data.get("data")) or [])
        except (ValueError, AttributeError, TypeError):
            names = []
        return True, str(hash(tuple(names)) & 0xFFFFFFFF)
    # Every local server is watched, also one that is switched off: a server that starts (LM Studio ships off) is
    # turned on by itself, unless the user switched it off.
    local = {pid: cfg for pid, cfg in settings["providers"].items() if cfg.get("local")}
    res = dict(zip(local, await asyncio.gather(*(ping(p, c) for p, c in local.items()))))
    woke = [p for p, (up, _) in res.items() if up and not local[p].get("enabled") and not local[p].get("user_disabled")]
    if woke:
        save_settings({"providers": {p: {"enabled": True} for p in woke}})
        for p in woke:
            router.invalidate_models(p)
    try:
        rev = SETTINGS_FILE.stat().st_mtime_ns
    except OSError:
        rev = 0
    on = {p for p, c in local.items() if c.get("enabled") or p in woke}
    return {"local": {p: res[p][0] for p in on}, "models_rev": {p: res[p][1] for p in on if res[p][0]},
            "settings_rev": str(rev)}


@app.get("/api/system/memory")
async def system_memory():
    """Settings > local model memory: this computer's RAM / VRAM as the guard sees it, and for the chosen local model
    whether its weights fit (and the largest window that does)."""
    from .llm import memguard
    out = {"machine": await asyncio.to_thread(memguard.machine), "guard": load_settings().get("local_guard") or {},
           "model": None}
    active = load_settings().get("active_model") or ""
    pname = active.partition(":")[0]
    if (load_settings()["providers"].get(pname) or {}).get("local"):
        try:
            info = await router.context_info(active)
            if ram := info.get("ram"):
                out["model"] = {"id": active, "need_gb": ram.get("weights_gb"), "free_gb": ram.get("free_gb"),
                                "fits": not ram.get("short"), "max_ctx": ram.get("max"), "window": info.get("current")}
        except Exception:  # noqa: BLE001 - the server may be off: the machine part is still useful
            pass
    return out


@app.get("/api/local/{pid}/runtime")
async def local_runtime_get(pid: str):
    from .llm import local_runtime
    cfg = load_settings()["providers"].get(pid) or {}
    if not cfg.get("local"):
        raise fail(404, "not_local", "Not a local provider")
    if cfg.get("kind") == "ollama":
        return {"kind": "ollama", **await local_runtime.ollama_status(cfg.get("base_url", "").rstrip("/"))}
    return {"kind": "lmstudio", "runtime": cfg.get("runtime") or {}, "lms": bool(router._lms())}


class RuntimeIn(BaseModel):
    values: dict


@app.put("/api/local/{pid}/runtime")
async def local_runtime_put(pid: str, body: RuntimeIn):
    from .llm import local_runtime
    cfg = load_settings()["providers"].get(pid) or {}
    if not cfg.get("local"):
        raise fail(404, "not_local", "Not a local provider")
    try:
        if cfg.get("kind") == "ollama":
            local_runtime.write_vars(body.values)
            return {"kind": "ollama", **await local_runtime.ollama_status(cfg.get("base_url", "").rstrip("/"))}
        rt = local_runtime.clean_lms(body.values)
    except ValueError as e:
        raise fail(400, "bad_runtime", str(e))
    save_settings({"providers": {pid: {"runtime": None}}})
    save_settings({"providers": {pid: {"runtime": rt}}})
    return {"kind": "lmstudio", "runtime": rt, "lms": bool(router._lms())}


@app.post("/api/local/{pid}/restart")
async def local_runtime_restart(pid: str):
    from .llm import local_runtime
    cfg = load_settings()["providers"].get(pid) or {}
    if cfg.get("kind") != "ollama" or not cfg.get("local"):
        raise fail(400, "not_ollama", "Only a local Ollama server can be restarted from here")
    out = await local_runtime.restart_ollama(cfg.get("base_url", "").rstrip("/"))
    router.invalidate_models(pid)
    return out


@app.get("/api/usage")
async def get_usage():
    """Quota screen: per-provider usage in the 5-hour and weekly windows with reset times, configured limits,
    cooldowns after quota/rate errors and the providers' own rate-limit headers; plus pool availability."""
    from .llm import usage
    settings = load_settings()
    mm = settings.get("multi_model") or {}
    pool = []
    for e in router.pool() if mm.get("enabled") else []:
        ok, why = router.availability(e["model"])
        pool.append({**e, "available": ok, "reason": why, "cooldown": usage.cooldown(e["model"]),
                     "limit": usage.over_limit(e["model"], mm.get("limits") or {}),
                     "headroom": round(usage.headroom(e["model"], mm.get("limits") or {}), 3)})
    # Shown: providers with usage, cooldowns or limits, plus cloud providers ready to use (key set).
    ready = {pid for pid, cfg in settings["providers"].items() if not cfg.get("local") and router.usable(pid, cfg)}
    snap = usage.snapshot(settings["providers"], mm.get("limits") or {}, ready)
    # The providers' own account data (credits, balance, free tier): asked in parallel, at most 8 s.
    accounts = await asyncio.gather(*(usage.account(pid, settings["providers"][pid]) for pid in snap), return_exceptions=True)
    for pid, acc in zip(list(snap), accounts):
        if isinstance(acc, dict) and acc:
            snap[pid]["account"] = acc
    return {"providers": snap, "pool": pool, "now": time.time()}


@app.post("/api/usage/clear")
async def clear_usage_cooldowns(model: str | None = None, probe: bool = True):
    """'Try again now': forget the cooldown of a model (or a whole provider, 'pid:'), then really ask the provider
    with a one-token request, so the user sees at once whether it works again or why not."""
    from .llm import usage
    from .llm.providers import ProviderError
    usage.clear(model)
    if not probe or not model:
        return {"ok": True}
    target = model
    if model.endswith(":"):  # a provider: its first model (the active one when it belongs to it)
        active = load_settings().get("active_model") or ""
        if active.startswith(model):
            target = active
        else:
            listing = await router.models_for(model[:-1])
            if not listing["models"]:
                return {"ok": False, "error": listing.get("error") or "no models"}
            target = model + listing["models"][0]["id"]
    t0 = time.monotonic()
    try:
        await asyncio.wait_for(router.complete(target, [{"role": "user", "content": "ping"}], {"max_tokens": 8}), 45)
    except ProviderError as e:
        return {"ok": False, "model": target, "code": e.code, "error": str(e)[:400]}
    except asyncio.TimeoutError:
        return {"ok": False, "model": target, "code": "timeout", "error": "no answer in 45 s"}
    return {"ok": True, "model": target, "ms": int((time.monotonic() - t0) * 1000)}


# ---------- MCP servers ----------
class McpIn(BaseModel):
    name: str
    transport: str = "stdio"
    command: str = ""
    args: list[str] = []
    cwd: str = ""
    url: str = ""
    enabled: bool = True
    env: dict[str, str] | None = None  # None: keep the saved values
    headers: dict[str, str] | None = None


def _mcp_view() -> dict:
    from . import mcp_client
    st = mcp_client.status()
    out = {}
    for sid, cfg in (load_settings().get("mcp_servers") or {}).items():
        sec = mcp_client.secret_parts(sid)
        out[sid] = {**{k: v for k, v in cfg.items() if k not in ("env", "headers")},
                    "env_keys": sorted(sec.get("env") or {}), "header_keys": sorted(sec.get("headers") or {}),
                    **st.get(sid, {"running": False, "error": None, "tools": []})}
    return out


@app.get("/api/mcp")
def mcp_list():
    return _mcp_view()


@app.put("/api/mcp/{sid}")
async def mcp_put(sid: str, body: McpIn):
    import json as _json
    import re
    from . import mcp_client
    if not re.fullmatch(r"[a-z0-9_-]{1,32}", sid) or body.transport not in ("stdio", "http"):
        raise fail(400, "invalid_mcp", "Invalid server id or transport")
    if body.transport == "stdio" and not body.command.strip():
        raise fail(400, "invalid_mcp", "A command is required for stdio servers")
    if body.transport == "http" and not re.match(r"https?://", body.url):
        raise fail(400, "invalid_mcp", "An http(s) URL is required")
    cfg = body.model_dump(exclude={"env", "headers"})
    save_settings({"mcp_servers": {sid: None}})
    save_settings({"mcp_servers": {sid: cfg}})
    if body.env is not None or body.headers is not None:
        sec = mcp_client.secret_parts(sid)
        if body.env is not None:
            sec["env"] = {k.strip(): v for k, v in body.env.items() if k.strip()}
        if body.headers is not None:
            sec["headers"] = {k.strip(): v for k, v in body.headers.items() if k.strip()}
        set_secret(f"mcp_{sid}", _json.dumps(sec) if (sec.get("env") or sec.get("headers")) else None)
    await mcp_client.restart(sid) if body.enabled else await mcp_client.ensure()
    return _mcp_view().get(sid)


@app.delete("/api/mcp/{sid}")
async def mcp_delete(sid: str):
    from . import mcp_client
    save_settings({"mcp_servers": {sid: None}})
    set_secret(f"mcp_{sid}", None)
    set_secret(f"mcp_oauth_{sid}", None)
    await mcp_client.ensure()
    return {"ok": True}


@app.post("/api/mcp/{sid}/oauth")
async def mcp_oauth_start(sid: str, request: Request):
    """Browser sign-in for an HTTP MCP server (OAuth with PKCE): returns the URL the UI opens in a new tab."""
    from . import mcp_client
    redirect = str(request.base_url).rstrip("/") + "/api/mcp/oauth/callback"
    try:
        return {"url": await mcp_client.oauth_start(sid, redirect)}
    except mcp_client.MCPError as e:
        raise fail(400, "mcp_oauth", str(e)) from None
    except Exception as e:  # noqa: BLE001  network, bad metadata
        raise fail(502, "mcp_oauth", f"{type(e).__name__}: {str(e)[:200]}") from None


@app.get("/api/mcp/oauth/callback")
async def mcp_oauth_callback(state: str = "", code: str = "", error: str = "", error_description: str = ""):
    from html import escape

    from . import mcp_client
    lang = load_settings().get("language") or "tr"
    ok_txt = ("Bağlandı. Bu sekmeyi kapatabilirsiniz; MCP sunucusu kullanıma hazır." if lang == "tr"
              else "Connected. You can close this tab; the MCP server is ready.")
    msg, ok = ok_txt, True
    if error or not code:
        msg, ok = f"{error or 'no code'}: {error_description}", False
    else:
        try:
            sid = await mcp_client.oauth_finish(state, code)
            await mcp_client.restart(sid)
        except Exception as e:  # noqa: BLE001
            msg, ok = str(e)[:300], False
    color = "#16a34a" if ok else "#dc2626"
    page = (f"<!doctype html><meta charset=utf-8><title>AI IQ 300 · MCP</title><body style=\"font-family:system-ui;"
            f"display:grid;place-items:center;height:100vh;margin:0;background:#f7f7f8\"><div style=\"max-width:460px;"
            f"padding:28px;border-radius:16px;background:#fff;box-shadow:0 8px 30px #0001;text-align:center\">"
            f"<div style=\"font-size:40px;color:{color}\">{'✓' if ok else '✕'}</div><p>{escape(msg)}</p></div>"
            f"<script>setTimeout(()=>window.close(),{2500 if ok else 60000})</script>")
    return HTMLResponse(page, status_code=200 if ok else 400)


# ---------- Connections (Settings > Connections: GitHub, Google, Microsoft) ----------
class ConnIn(BaseModel):
    token: str | None = None
    client_id: str = ""
    client_secret: str = ""
    services: list[str] = []
    org: bool = False
    forget_client: bool = False
    full_name: str = ""
    branch: str = ""
    stash: bool = False


async def _conn(coro):
    from . import connections
    try:
        return await coro if asyncio.iscoroutine(coro) else coro
    except connections.ConnError as e:
        raise fail(400, e.code, str(e)) from None


@app.get("/api/connections")
def connections_status():
    from . import connections
    return connections.status()


@app.post("/api/connections/github")
async def connections_github(body: ConnIn):
    from . import connections
    return await _conn(connections.github_connect(body.token))


@app.delete("/api/connections/github")
async def connections_github_off():
    from . import connections
    await connections.github_disconnect()
    return connections.status()


@app.get("/api/connections/github/repos")
async def connections_github_repos(q: str = ""):
    from . import connections
    return await _conn(connections.github_repos(q))


@app.post("/api/connections/github/import")
async def connections_github_import(body: ConnIn):
    from . import connections
    return await _conn(connections.github_import(body.full_name, body.branch))


@app.get("/api/connections/github/projects")
def connections_github_projects():
    from . import connections
    return connections._github_projects()


@app.get("/api/projects/{pid}/git")
async def project_git_status(pid: str, fetch: bool = True):
    from . import connections
    return await _conn(connections.project_git(pid, fetch))


@app.post("/api/projects/{pid}/git/pull")
async def project_git_pull(pid: str, body: ConnIn):
    from . import connections
    return await _conn(connections.project_pull(pid, body.stash))


@app.get("/api/connections/google/apis")
async def connections_google_apis(force: bool = False):
    from . import connections
    return await connections.google_api_check(force)


@app.put("/api/connections/google/client")
def connections_google_client(body: ConnIn):
    from . import connections
    try:
        return connections.google_client(body.client_id, body.client_secret)
    except connections.ConnError as e:
        raise fail(400, e.code, str(e)) from None


@app.post("/api/connections/google")
def connections_google(body: ConnIn, request: Request):
    from . import connections
    redirect = str(request.base_url).rstrip("/") + "/api/connections/google/callback"
    try:
        return {"url": connections.google_start(redirect, body.services)}
    except connections.ConnError as e:
        raise fail(400, e.code, str(e)) from None


@app.get("/api/connections/google/callback")
async def connections_google_callback(state: str = "", code: str = "", error: str = ""):
    from html import escape

    from . import connections
    tr = (load_settings().get("language") or "tr") == "tr"
    ok, msg = True, ("Google bağlandı. Bu sekmeyi kapatabilirsiniz." if tr else "Google is connected. You can close this tab.")
    if error or not code:
        ok, msg = False, error or "no code"
    else:
        try:
            await connections.google_finish(state, code)
        except Exception as e:  # noqa: BLE001
            ok, msg = False, str(e)[:300]
    color = "#16a34a" if ok else "#dc2626"
    page = (f"<!doctype html><meta charset=utf-8><title>AI IQ 300 · Google</title><body style=\"font-family:system-ui;"
            f"display:grid;place-items:center;height:100vh;margin:0;background:#f7f7f8\"><div style=\"max-width:460px;"
            f"padding:28px;border-radius:16px;background:#fff;box-shadow:0 8px 30px #0001;text-align:center\">"
            f"<div style=\"font-size:40px;color:{color}\">{'✓' if ok else '✕'}</div><p>{escape(msg)}</p></div>"
            f"<script>setTimeout(()=>window.close(),{2500 if ok else 60000})</script>")
    return HTMLResponse(page, status_code=200 if ok else 400)


@app.delete("/api/connections/google")
async def connections_google_off(forget_client: bool = False):
    from . import connections
    await connections.google_disconnect(forget_client)
    return connections.status()


@app.post("/api/connections/microsoft")
async def connections_microsoft(body: ConnIn):
    from . import connections
    return await _conn(connections.microsoft_connect(body.org))


@app.delete("/api/connections/microsoft")
async def connections_microsoft_off():
    from . import connections
    await connections.microsoft_disconnect()
    return connections.status()


@app.delete("/api/mcp/{sid}/oauth")
async def mcp_oauth_signout(sid: str):
    from . import mcp_client
    mcp_client.oauth_signout(sid)
    await mcp_client.restart(sid)
    return _mcp_view().get(sid)


@app.post("/api/mcp/{sid}/restart")
async def mcp_restart(sid: str):
    from . import mcp_client
    if sid not in (load_settings().get("mcp_servers") or {}):
        raise fail(404, "not_found", "Unknown MCP server")
    await mcp_client.restart(sid)
    return _mcp_view().get(sid)


@app.get("/api/mcp-catalog")
def mcp_catalog_list():
    """The ready-made servers (one click adds one)."""
    from .mcp_catalog import catalog
    return catalog()


@app.get("/api/mcp-registry")
async def mcp_registry(q: str = ""):
    """Search the official MCP registry (+ npm, GitHub) for a need: the same search the model's mcp_search uses."""
    from . import mcp_client
    try:
        return {"results": await mcp_client.search_servers(q, 12)}
    except Exception as e:  # noqa: BLE001  offline, registry down
        raise fail(502, "mcp_registry", f"{type(e).__name__}: {str(e)[:200]}") from None


class McpCallIn(BaseModel):
    tool: str
    arguments: dict = {}


@app.post("/api/mcp/{sid}/call")
async def mcp_call(sid: str, body: McpCallIn):
    """The user runs an MCP tool directly (Settings > MCP > Try): the same call the model makes with the mcp tool."""
    from . import mcp_client
    if sid not in (load_settings().get("mcp_servers") or {}):
        raise fail(404, "not_found", "Unknown MCP server")
    t0 = time.monotonic()
    try:
        ok, text = await mcp_client.call(sid, body.tool, body.arguments or {})
    except Exception as e:  # noqa: BLE001  not running, bad arguments, timeout
        return {"ok": False, "text": str(e)[:4000], "ms": round((time.monotonic() - t0) * 1000)}
    return {"ok": ok, "text": text[:200000], "ms": round((time.monotonic() - t0) * 1000)}


@app.get("/api/settings")
def get_settings():
    return {**load_settings(), "secrets": secret_status()}


@app.patch("/api/settings")
def patch_settings(body: dict):
    body.pop("secrets", None)
    if body.get("permission_mode") and body["permission_mode"] not in policy.MODES:
        raise fail(400, "bad_permission_mode", "Invalid permission mode")
    current = load_settings()["providers"]
    _sync_shared(body)
    for pid, patch in (body.get("providers") or {}).items():
        router.invalidate_models(pid)
        # A local server the user switched off stays off; otherwise it is turned on by itself when it starts
        # (see models_health).
        if isinstance(patch, dict) and "enabled" in patch and (current.get(pid) or patch).get("local"):
            patch["user_disabled"] = not patch["enabled"]
    return save_settings(body)


class SecretIn(BaseModel):
    name: str
    value: str | None = None


def _sync_shared(body: dict) -> None:
    """One value for what a provider and a media service share (they are one account): the Cloudflare account id
    typed in the image card is the provider's account id and the other way round."""
    media = body.get("media") if isinstance(body.get("media"), dict) else None
    cf = ((body.get("providers") or {}).get("cloudflare") or {}) if isinstance(body.get("providers"), dict) else {}
    if media and "cloudflare_account" in media:
        body.setdefault("providers", {}).setdefault("cloudflare", {})["account_id"] = str(media["cloudflare_account"]).strip()
    elif isinstance(cf, dict) and "account_id" in cf:
        body.setdefault("media", {})["cloudflare_account"] = str(cf["account_id"] or "").strip()


# A key shared by a chat provider and the media services: saving it in either place turns on both
SHARED_KEYS = {"gemini_api_key": ("gemini", ["media"]), "cloudflare_api_key": ("cloudflare", ["media"]),
               "huggingface_api_key": ("huggingface", ["media", "video"]), "together_api_key": ("together", ["media"]),
               "openai_api_key": ("openai", ["media"])}


@app.put("/api/secrets")
def put_secret(body: SecretIn):
    set_secret(body.name, body.value)
    pid = body.name.removesuffix("_api_key")
    s = load_settings()
    # Cloud providers ship disabled; saving a key for one turns it on (also when the key was typed in a media card).
    if body.value and pid != body.name and (cfg := s["providers"].get(pid)) and not cfg.get("enabled"):
        save_settings({"providers": {pid: {"enabled": True}}})
    if body.value:
        # ... and the media services that use the same key are switched on too (a disabled one comes back)
        sid = SHARED_KEYS.get(body.name, (pid, []))[0]
        for section in ("media", "video"):
            off = list((s.get(section) or {}).get("disabled") or [])
            if sid in off:
                save_settings({section: {"disabled": [x for x in off if x != sid]}})
    router.invalidate_models(pid)
    return secret_status()


@app.get("/api/agents")
def agents():
    return catalog.public(catalog.agents(), "agents")


@app.get("/api/skills")
def skills():
    return catalog.public(catalog.skills(), "skills")


@app.get("/api/catalog/{kind}/{name}")
def catalog_read(kind: str, name: str):
    try:
        return {"name": name, "content": catalog.read(kind, name)}
    except FileNotFoundError:
        return {"name": name, "content": catalog.template(kind, name), "new": True}
    except ValueError as e:
        raise to_http(e, 400)


class CatalogIn(BaseModel):
    content: str


@app.put("/api/catalog/{kind}/{name}")
async def catalog_write(kind: str, name: str, body: CatalogIn):
    try:
        catalog.write(kind, name, body.content)
    except ValueError as e:
        raise to_http(e, 400)
    _localize_later(kind, name)
    return {"ok": True}


def _localize_later(kind: str, name: str) -> None:
    """Translate a new/changed item's title and description into every installed language in the background."""
    path = catalog.DIRS[kind] / f"{name}.md"

    async def job():
        try:
            await asyncio.to_thread(catalog.localize, i18n.installed_languages(), [path])
        except Exception:
            pass  # offline: the item keeps its generic text
    _bg(job())  # callers are async endpoints, so a loop is running


@app.delete("/api/catalog/{kind}/{name}")
def catalog_delete(kind: str, name: str):
    try:
        catalog.delete(kind, name)
    except ValueError as e:
        raise to_http(e, 400)
    return {"ok": True}


class ImportIn(BaseModel):
    url: str


@app.post("/api/catalog/{kind}/import")
async def catalog_import(kind: str, body: ImportIn):
    try:
        name = await catalog.import_url(kind, body.url.strip())
    except Exception as e:
        raise to_http(e, 400)
    _localize_later(kind, name)
    return {"name": name}


class RepoSkillsIn(BaseModel):
    spec: str
    paths: list[str] = []


@app.post("/api/skills/repo")
async def skills_repo_list(body: RepoSkillsIn):
    """The SKILL.md files of a GitHub repository ('npx skills add owner/repo', owner/repo or its URL)."""
    try:
        return await catalog.repo_skills(body.spec)
    except Exception as e:
        raise to_http(e, 400)


@app.post("/api/skills/repo/import")
async def skills_repo_import(body: RepoSkillsIn):
    try:
        names = await catalog.import_repo_skills(body.spec, body.paths)
    except Exception as e:
        raise to_http(e, 400)
    for n in names:
        _localize_later("skills", n)
    return {"names": names}


@app.post("/api/catalog/{kind}/upload")
async def catalog_upload(kind: str, file: UploadFile):
    data = await file.read()
    try:
        content = data.decode("utf-8")
        name = catalog.name_from(content, Path(file.filename or "imported").stem)
        catalog.write(kind, name, content)
    except (UnicodeDecodeError, ValueError) as e:
        raise to_http(e, 400)
    _localize_later(kind, name)
    return {"name": name}


# ---------- i18n ----------
@app.get("/api/languages")
def languages():
    out = []
    for f in sorted(LANG_DIR.glob("*.json")):
        data = json.loads(f.read_text(encoding="utf-8"))
        out.append({"code": f.stem, "name": data.get("_meta", {}).get("name", f.stem)})
    return out


@app.get("/api/languages/{code}")
def language(code: str):
    f = policy.resolve_in(LANG_DIR, f"{code}.json")
    if not f.is_file():
        raise HTTPException(404)
    return json.loads(f.read_text(encoding="utf-8"))


class LangIn(BaseModel):
    code: str
    name: str


@app.post("/api/languages")
async def add_language(body: LangIn):
    """Auto-translate en.json into a new language with deep-translator (needs internet)."""
    import re
    if not re.fullmatch(r"[a-z]{2,3}(-[A-Za-z]{2,4})?", body.code):
        raise fail(400, "invalid_language", "Invalid language code")
    src = json.loads((LANG_DIR / "en.json").read_text(encoding="utf-8"))
    keys = [k for k in src if not k.startswith("_")]
    try:
        values = await asyncio.to_thread(i18n.translate_all, [src[k] for k in keys], body.code)
    except Exception as e:
        raise fail(502, "translate_failed", f"Translation failed: {e}")
    out = {"_meta": {"name": body.name, "code": body.code}} | dict(zip(keys, values))
    (LANG_DIR / f"{body.code}.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    try:  # agent/skill titles and descriptions in the new language too
        await asyncio.to_thread(catalog.localize, [body.code])
    except Exception:
        pass  # the language is usable; catalog items fall back to their generic text
    return {"code": body.code, "name": body.name}


@app.delete("/api/languages/{code}")
def delete_language(code: str):
    if code in ("tr", "en"):
        raise fail(400, "default_language", "Default languages cannot be deleted")
    f = policy.resolve_in(LANG_DIR, f"{code}.json")
    if f.is_file():
        f.unlink()
    catalog.drop_language(code)
    return {"ok": True}


@app.put("/api/languages/{code}")
def save_language(code: str, body: dict):
    f = policy.resolve_in(LANG_DIR, f"{code}.json")
    f.write_text(json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True}


# ---------- events websocket ----------
@app.websocket("/ws/events")
async def events_ws(ws: WebSocket):
    if not _origin_ok(ws.headers.get("origin"), ws.headers.get("host")):
        await ws.close(code=4403)
        return
    await ws.accept()
    try:
        since = max(0, int(ws.query_params.get("since", 0)))
    except ValueError:
        since = 0
    boot = ws.query_params.get("boot") or ""
    q, replay, truncated = bus.subscribe(since)
    # No await between subscribe() and the snapshots below: everything published later arrives through the queue, so
    # the state the client gets is exact (nothing twice, nothing missing).
    # A new page, a client from before a restart, or one that was away longer than the replay buffer reaches: it
    # gets the state itself - every running task as a snapshot (text, steps, to-dos, waiting approvals) - instead of
    # a partial replay. A short reconnect gets exactly the events it missed.
    fresh = truncated or not since or (bool(boot) and boot != bus.boot)
    now = time.time()
    first = [{"seq": bus.last_seq, "ts": now, "topic": "system", "type": "hello",
              "payload": {"boot": bus.boot, "reset": fresh, "net": _net_snapshot()}}]
    if fresh:
        first += [{"seq": bus.last_seq, "ts": now, "topic": "run", "type": "snapshot", "payload": r.snapshot()}
                  for r in orchestrator.RUNS.values()]
        first += bus.recent("process")  # the process panel keeps its output after a reload
    else:
        first += replay
    try:
        for i in range(0, len(first), 200):
            await ws.send_json(first[i:i + 200])
        while True:
            try:
                batch = [await asyncio.wait_for(q.get(), 15)]
            except asyncio.TimeoutError:
                # Keep-alive: the client reconnects by itself when nothing arrives for a while (a connection that
                # died without closing - sleep, network change - used to leave the chat frozen until a reload).
                await ws.send_json({"seq": 0, "ts": time.time(), "topic": "system", "type": "ping", "payload": {}})
                continue
            while len(batch) < 300 and not q.empty():
                batch.append(q.get_nowait())
            batch = _coalesce(batch)
            await ws.send_json(batch if len(batch) > 1 else batch[0])
    except (WebSocketDisconnect, RuntimeError):
        pass
    except Exception:  # noqa: BLE001 - a connection that broke mid-send
        pass
    finally:
        bus.unsubscribe(q)  # disconnect does not stop runs or processes


def _coalesce(batch: list[dict]) -> list[dict]:
    """Text pieces of one answer that are waiting together go out as one event (a fast model or a slow client:
    hundreds of tiny messages became one). The merged event carries the last piece's sequence number."""
    out: list[dict] = []
    for e in batch:
        last = out[-1] if out else None
        if (last and e["type"] == "delta" and last["type"] == "delta" and e["topic"] == "run" == last["topic"]
                and e["payload"].get("run_id") == last["payload"].get("run_id")):
            out[-1] = {**e, "payload": {**e["payload"], "text": last["payload"]["text"] + e["payload"]["text"]}}
        else:
            out.append(e)
    return out


@app.post("/api/location/{request_id}")
def location_answer(request_id: str, body: dict):
    """The app's answer to a location request: {lat, lon, accuracy} or {error}."""
    from . import location
    return {"ok": location.answer(request_id, body)}


@app.get("/api/browser/status")
def browser_status():
    """The browser agent window (browser_* tools): is it open, which tabs, how big its saved-sign-in profile is."""
    from .tools.browser import AGENT
    return AGENT.status()


@app.post("/api/browser/close")
async def browser_close():
    """Close the browser window now (its profile, and the sign-ins in it, are kept)."""
    from .tools.browser import AGENT
    await AGENT.close()
    return {"ok": True}


@app.post("/api/browser/reset")
async def browser_reset():
    """Forget every sign-in: close the window and delete its profile folder."""
    from .tools.browser import AGENT
    if AGENT.running() and orchestrator.any_run_active():
        raise fail(409, "browser_busy", "A task is using the browser right now")
    ok = await AGENT.reset_profile()
    return {"ok": ok}


def _pct(values: list[float], q: float) -> int | None:
    v = sorted(x for x in values if x is not None)
    return int(v[min(len(v) - 1, int(q * len(v)))]) if v else None


@app.get("/api/perf")
def perf(last: int = 100):
    """Where chats spend their time, over the latest tasks: first answer, preparation, waiting for the model's first
    token, model total, tools (per tool), team runs, side calls and the app's own overhead (p50 / p95 / max)."""
    rows = list(orchestrator.PERF)[-max(1, min(last, 300)):]
    keys = ("total_ms", "first_ms", "prep_ms", "model_wait_ms", "slowest_wait_ms", "model_ms", "tools_ms", "team_ms",
            "side_ms", "retry_ms", "overhead_ms")
    out = {"tasks": len(rows), "statuses": {}}
    for k in keys:
        vals = [r.get(k) for r in rows if r.get(k) is not None and (k != "team_ms" or r.get(k))]
        out[k] = {"p50": _pct(vals, 0.5), "p95": _pct(vals, 0.95), "max": int(max(vals)) if vals else None}
    tools: dict[str, dict] = {}
    for r in rows:
        out["statuses"][r["status"]] = out["statuses"].get(r["status"], 0) + 1
        for name, t in (r.get("tools") or {}).items():
            x = tools.setdefault(name, {"calls": 0, "ms": 0, "max_ms": 0, "failed": 0})
            x["calls"] += t["n"]
            x["ms"] += t["ms"]
            x["max_ms"] = max(x["max_ms"], t["max_ms"])
            x["failed"] += t["failed"]
    out["tools"] = {k: {**v, "avg_ms": int(v["ms"] / v["calls"])} for k, v in sorted(tools.items(), key=lambda kv: -kv[1]["ms"])}
    by_model: dict[str, list] = {}
    for r in rows:
        by_model.setdefault(r.get("model") or "?", []).append(r.get("first_ms"))
    out["first_ms_by_model"] = {m: {"p50": _pct(v, 0.5), "p95": _pct(v, 0.95), "tasks": len(v)} for m, v in by_model.items()}
    return out


@app.get("/api/models/stats")
def model_stats():
    """Per model: tasks, failures (also tasks that had to move to another model), first-token wait, turn time and
    prompt reading speed - Settings > Models; the pool prefers the fast, reliable ones."""
    from .llm import modelstats
    orchestrator._speed_file()
    stats = modelstats.all_stats()
    for m, v in orchestrator.SPEED.items():
        stats.setdefault(m, {"tasks": 0, "ok": 0, "failed": 0, "fail_pct": 0})["read_ms_per_1k"] = v[0]
    return {"models": stats}


@app.delete("/api/models/stats")
def model_stats_reset(model: str = ""):
    from .llm import modelstats
    from .config import atomic_write
    modelstats.reset(model or None)
    orchestrator._speed_file()
    if model:  # the measured reading speed goes with it (it is part of the same record in Settings)
        orchestrator.SPEED.pop(model, None)
    else:
        orchestrator.SPEED.clear()
    try:
        atomic_write(orchestrator._speed_file(), json.dumps(orchestrator.SPEED, indent=1))
    except OSError:
        pass
    return {"ok": True}


@app.get("/api/health")
def health():
    p = perf(50)
    from .config import VERSION
    return {"ok": True, "version": VERSION, "runs": list(orchestrator.RUNS), "processes": len(manager.procs),
            "perf": {k: p[k] for k in ("tasks", "first_ms", "model_wait_ms", "tools_ms", "overhead_ms")}}


# ---------- frontend ----------
if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}")
    def spa(full_path: str):
        f = (FRONTEND_DIST / full_path).resolve()
        if full_path and f.is_file() and FRONTEND_DIST.resolve() in f.parents and f.name != "index.html":
            return FileResponse(f)
        # index.html must never be cached: it points at the current hashed bundle (stale UI after updates otherwise)
        return FileResponse(FRONTEND_DIST / "index.html", headers={"Cache-Control": "no-cache, no-store, must-revalidate"})
