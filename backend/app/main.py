"""AI IQ 300 FastAPI backend: REST control API, event WebSocket, static frontend."""
from __future__ import annotations

import asyncio
import json
import os
import re
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
    # Processes from a previous backend instance are no longer supervised: mark them as such.
    db.execute("UPDATE processes SET state='orphaned' WHERE state IN ('queued','running','cancelling')")
    from .tools import syntax
    syntax.warm()  # tree-sitter grammars load in the background (first run downloads them)
    from . import hostinfo
    hostinfo.warm()  # OS build, shells and tool versions for the system prompt, detected once in the background
    from . import mcp_client
    if mcp_client.servers_cfg():  # connected MCP servers start in the background (Settings shows their state)
        asyncio.create_task(mcp_client.ensure())
    yield
    for run_id in list(orchestrator.RUNS):
        await orchestrator.cancel_run(run_id)
    await manager.shutdown()
    from . import mcp_client
    await mcp_client.shutdown()


app = FastAPI(title="AI IQ 300", lifespan=lifespan)


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
    name: str


class SessionIn(BaseModel):
    project_id: str | None = None
    title: str | None = None


@app.get("/api/projects")
def list_projects():
    return db.query("SELECT * FROM projects ORDER BY created DESC")


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
    db.execute("UPDATE projects SET name=? WHERE id=?", (body.name.strip(), pid))
    return {"ok": True}


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


@app.get("/api/sessions")
def list_sessions(project_id: str | None = None):
    cols = "id, project_id, title, created, updated, pinned, archived, context_used"
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


@app.get("/api/sessions/{sid}/messages")
def get_messages(sid: str):
    rows = db.query("SELECT * FROM messages WHERE session_id=? ORDER BY id", (sid,))
    for r in rows:
        r["meta"] = json.loads(r["meta"] or "{}")
    return rows


class SessionPatch(BaseModel):
    title: str | None = None
    pinned: bool | None = None
    archived: bool | None = None


@app.patch("/api/sessions/{sid}")
def patch_session(sid: str, body: SessionPatch):
    for k, v in body.model_dump(exclude_none=True).items():
        db.execute(f"UPDATE sessions SET {k}=? WHERE id=?", (int(v) if isinstance(v, bool) else v, sid))
    return _session(sid)


@app.get("/api/sessions/{sid}/active")
def active(sid: str):
    return orchestrator.active_run(sid) or {}


@app.get("/api/sessions/{sid}/context")
async def session_context(sid: str, model: str):
    info = await router.context_info(model)
    sess = _session(sid) if sid != "new" else {}
    used = sess.get("context_used") or (orchestrator.estimate_tokens(orchestrator._history(sid)) if sess else 0)
    stats = json.loads(sess["context_stats"]) if sess.get("context_stats") else {}
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


@app.delete("/api/sessions/{sid}")
async def delete_session(sid: str):
    """Deletes the chat, its messages and its whole chat/<id>-session folder."""
    await orchestrator.cancel_session(sid)
    db.execute("DELETE FROM messages WHERE session_id=?", (sid,))
    db.execute("DELETE FROM sessions WHERE id=?", (sid,))
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
    if not (body.model or load_settings().get("active_model")):
        raise fail(400, "no_model", "No model selected; pick a model under the message box")
    if body.permission_mode and body.permission_mode not in policy.MODES:
        raise fail(400, "bad_permission_mode", "Invalid permission mode")
    if not session["title"]:
        db.execute("UPDATE sessions SET title=? WHERE id=?", (body.text.strip()[:60], sid))
    text = body.text
    root = workspace.session_root(session)
    for a in body.attachments:  # inline small text attachments as context
        p = Path(a.get("path", ""))
        if p.is_file() and p.stat().st_size < 200_000 and a.get("kind") == "text":
            text += f"\n\n[Attached file: {p.name}]\n```\n{p.read_text(encoding='utf-8', errors='replace')}\n```"
    run = orchestrator.start_run(session, text, body.model_dump() | {"text": text, "display_text": body.text})
    return {"run_id": run.id, "cwd": str(root)}


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
    """sid 'new' = a chat not created yet: the project folder if one is selected, else workspace/."""
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
HIDDEN_DIRS = {".git", "node_modules", "__pycache__", ".venv", ".aiiq"}


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
    return [] if root == workspace.WORKSPACE_DIR else await workspace.git_history(root)


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
    asyncio.create_task(router.activate(body.model))
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
        return {"ok": True, "ms": int((time.perf_counter() - t0) * 1000), **out}
    except ProviderError as e:
        return {"ok": False, "code": e.code, "error": str(e)}
    except asyncio.TimeoutError:
        return {"ok": False, "code": "timeout", "error": "Timed out after 20 s"}
    except Exception as e:
        return {"ok": False, "code": "error", "error": f"{type(e).__name__}: {e}"}


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
    return {"providers": usage.snapshot(settings["providers"], mm.get("limits") or {}, ready), "pool": pool,
            "now": time.time()}


@app.post("/api/usage/clear")
def clear_usage_cooldowns(model: str | None = None):
    """'Try again now': forget the cooldown of a model (or all) after the user topped up or a limit reset."""
    from .llm import usage
    usage.clear(model)
    return {"ok": True}


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
    for pid in (body.get("providers") or {}):
        router.invalidate_models(pid)
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
    asyncio.create_task(job())  # callers are async endpoints, so a loop is running


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
    since = int(ws.query_params.get("since", 0))
    q, replay, truncated = bus.subscribe(since)
    try:
        if truncated:
            await ws.send_json({"seq": 0, "topic": "system", "type": "history_truncated", "payload": {}})
        for e in replay:
            await ws.send_json(e)
        while True:
            await ws.send_json(await q.get())
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        bus.unsubscribe(q)  # disconnect does not stop runs or processes


@app.post("/api/location/{request_id}")
def location_answer(request_id: str, body: dict):
    """The app's answer to a location request: {lat, lon, accuracy} or {error}."""
    from . import location
    return {"ok": location.answer(request_id, body)}


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


@app.get("/api/health")
def health():
    p = perf(50)
    return {"ok": True, "runs": list(orchestrator.RUNS), "processes": len(manager.procs),
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
