"""AI IQ 300 FastAPI backend: REST control API, event WebSocket, static frontend."""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
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
    yield
    for run_id in list(orchestrator.RUNS):
        await orchestrator.cancel_run(run_id)
    await manager.shutdown()


app = FastAPI(title="AI IQ 300", lifespan=lifespan)


def _origin_ok(origin: str | None) -> bool:
    return origin is None or origin in load_settings()["allowed_origins"]


@app.middleware("http")
async def origin_guard(request: Request, call_next):
    # Blocks cross-site browser requests to the control API (backend binds to loopback by default).
    if request.url.path.startswith("/api") and not _origin_ok(request.headers.get("origin")):
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
                if d.get("tool") in ("write_file", "make_doc") and d.get("path") and st.get("status") == "done":
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
    p = _resolve(sid, path, project_id)
    if not p.is_file():
        raise HTTPException(404)
    return FileResponse(p, filename=p.name if download else None,
                        content_disposition_type="attachment" if download else "inline")


@app.get("/api/sessions/{sid}/fs/slides")
def fs_slides(sid: str, path: str, project_id: str | None = None):
    """PowerPoint preview: every slide's title, text lines and notes (browsers cannot render .pptx)."""
    p = _resolve(sid, path, project_id)
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
    results, engines = await web.search(q)
    return {"engines": engines, "count": len(results), "ms": int((time.perf_counter() - t0) * 1000), "results": results[:5]}


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


@app.put("/api/models/context")
async def set_model_context(body: ModelIn):
    info = await router.context_info(body.model)
    n = max(2048, min(int(body.num_ctx or info["max"]), info["max"]))
    save_settings({"context": {"num_ctx": {body.model: n}}})
    return {**info, "current": n}


# ---------- providers ----------
class ProviderIn(BaseModel):
    name: str
    kind: str = "openai"
    base_url: str
    enabled: bool = True
    local: bool = False
    streaming: bool = True
    auth_header: str | None = None
    model: str | None = None


@app.put("/api/providers/{pid}")
def put_provider(pid: str, body: ProviderIn):
    import re
    if not re.fullmatch(r"[a-z0-9_-]{1,40}", pid) or body.kind not in ("openai", "ollama", "anthropic", "gemini"):
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
    router.invalidate_models(body.name.removesuffix("_api_key"))
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
    if not _origin_ok(ws.headers.get("origin")):
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


@app.get("/api/health")
def health():
    return {"ok": True, "runs": list(orchestrator.RUNS), "processes": len(manager.procs)}


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
