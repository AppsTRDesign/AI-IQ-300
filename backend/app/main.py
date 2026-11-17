"""AI IQ 300 FastAPI backend: REST control API, event WebSocket, static frontend."""
from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import approvals, db, i18n, policy, sessions, workspace
from .errors import fail, to_http
from .agents import catalog, orchestrator
from .config import FRONTEND_DIST, LANG_DIR, load_settings, save_settings, secret_status, set_secret
from .events import bus
from .llm import router
from .process_manager import manager


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Processes from a previous backend instance (dev servers the agent started, then the app was closed hard) are
    # no longer supervised: stop the ones still alive, then mark them orphaned. A dev server left on localhost:8000
    # kept running and locked its chat folder.
    # Before v0.10.3 chat files lived in workspace/: move them into chat/<id>/ once.
    await asyncio.to_thread(workspace.migrate_layout)
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
    yield
    warm.cancel()
    guard.cancel()
    await orchestrator.shutdown()  # tasks store their checkpoint and message before the loop closes
    await manager.shutdown()
    from . import mcp_client
    await mcp_client.shutdown()
    db.checkpoint()  # the write-ahead log is folded into the database file
    from .llm import modelstats
    modelstats.flush()


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
    done = 0
    for sid in [str(x) for x in body.ids][:500]:
        try:
            await delete_session(sid)
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
        raise fail(409, "run_busy", "This chat is still working; stop it first")
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
                    lines = [ln for ln in tr.read_text(encoding="utf-8").splitlines()
                             if ln.strip() and json.loads(ln).get("id") not in gone]
                    tr.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    except (ValueError, OSError):
        pass
    return {"ok": True, "deleted": n, "left": left}


@app.delete("/api/sessions/{sid}")
async def delete_session(sid: str):
    """Deletes the chat, its messages and its whole chat/<id>/ folder (files and record)."""
    await orchestrator.cancel_session(sid)
    rows = db.query("SELECT project_id FROM sessions WHERE id=?", (sid,))
    db.execute("DELETE FROM messages WHERE session_id=?", (sid,))
    db.execute("DELETE FROM sessions WHERE id=?", (sid,))
    if rows and not rows[0]["project_id"]:
        workspace.remove_chat_root(sid)
    try:
        sessions.remove(sid)
    except ValueError:
        pass
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
        db.execute("UPDATE sessions SET title=? WHERE id=?", (orchestrator.clean_title(body.text)[:60], sid))
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
    import shutil
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
            shutil.rmtree(target) if target.is_dir() else target.unlink()
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


@app.get("/api/sessions/{sid}/fs/raw")
def fs_raw(sid: str, path: str, project_id: str | None = None, download: bool = False):
    p = _find_file(sid, path, project_id)
    if not p.is_file():
        raise HTTPException(404)
    return FileResponse(p, filename=p.name if download else None,
                        content_disposition_type="attachment" if download else "inline")


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
    from pptx import Presentation
    try:
        prs = Presentation(str(p))
    except Exception as e:
        raise fail(400, "bad_document", f"Unreadable presentation: {e}")
    slides = []
    for s in prs.slides:
        title = s.shapes.title.text_frame.text.strip() if s.shapes.title is not None and s.shapes.title.has_text_frame else ""
        lines = [para.text.strip() for sh in s.shapes if sh.has_text_frame and sh != s.shapes.title
                 for para in sh.text_frame.paragraphs if para.text.strip()]
        notes = s.notes_slide.notes_text_frame.text.strip() if s.has_notes_slide and s.notes_slide.notes_text_frame else ""
        slides.append({"title": title, "lines": lines[:40], "notes": notes[:2000]})
    return {"slides": slides}


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
    """Image generation service test (Settings > Web research): a small picture, whether it came without the logo."""
    from .tools import imagegen
    t0 = time.monotonic()
    try:
        data, clean = await imagegen.generate(body.q.strip() or "a cup of coffee on a wooden table, photo", 256, 256)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)[:300]}
    return {"ok": True, "ms": int((time.monotonic() - t0) * 1000), "count": 1, "provider": service,
            "results": [{"title": f"{len(data) // 1024} KB" + (" · logo-free (token)" if clean else " · with the free tier's logo"),
                         "url": ""}]}


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


# ---------- spoken replies (edge-tts) ----------
@app.get("/api/tts/voices")
async def tts_voices(lang: str = ""):
    from . import tts
    try:
        return {"ok": True, "voices": await tts.voices(lang)}
    except tts.TTSError as e:
        return {"ok": False, "voices": [], "error": str(e)}


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
        res = await speech.text_to_speech(body.text[:20000], target, "", body.voice, "", body.rate)
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
    return save_settings({"providers": {pid: body.model_dump(exclude_none=True)}})


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
    """Polled by the UI every few seconds: is each enabled local server up, and the settings revision. A local
    server that starts or stops, or settings changed in another window, are picked up without a page reload."""
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
    await mcp_client.ensure()
    return {"ok": True}


@app.post("/api/mcp/{sid}/restart")
async def mcp_restart(sid: str):
    from . import mcp_client
    if sid not in (load_settings().get("mcp_servers") or {}):
        raise fail(404, "not_found", "Unknown MCP server")
    await mcp_client.restart(sid)
    return _mcp_view().get(sid)


@app.get("/api/settings")
def get_settings():
    return {**load_settings(), "secrets": secret_status()}


@app.patch("/api/settings")
def patch_settings(body: dict):
    body.pop("secrets", None)
    if body.get("permission_mode") and body["permission_mode"] not in policy.MODES:
        raise fail(400, "bad_permission_mode", "Invalid permission mode")
    current = load_settings()["providers"]
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


@app.put("/api/secrets")
def put_secret(body: SecretIn):
    set_secret(body.name, body.value)
    pid = body.name.removesuffix("_api_key")
    # Cloud providers ship disabled; saving a key for one turns it on.
    if body.value and pid != body.name and (cfg := load_settings()["providers"].get(pid)) and not cfg.get("enabled"):
        save_settings({"providers": {pid: {"enabled": True}}})
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
              "payload": {"boot": bus.boot, "reset": fresh}}]
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
