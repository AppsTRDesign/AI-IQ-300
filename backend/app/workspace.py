"""Projects, per-session workspace folders, PROJECT_STATE.md and git time machine."""
from __future__ import annotations

import asyncio
import re
import shutil
import time
import uuid
from pathlib import Path

from . import db
from .config import WORKSPACE_DIR
from .errors import AppError

IGNORED = {".git", "node_modules", ".venv", "__pycache__", ".aiiq", "dist", "vendor"}


def slugify(name: str) -> str:
    s = re.sub(r"[^\w\-]+", "-", name.strip(), flags=re.UNICODE).strip("-")
    return s[:60] or "project"


def create_project(name: str, folder: str | None = None) -> dict:
    """A chosen local folder becomes the project root (outputs are written there);
    otherwise a new folder is created under workspace/."""
    pid = uuid.uuid4().hex[:10]
    if folder:
        path = Path(folder).expanduser().resolve()
        if not path.is_dir():
            raise AppError("folder_not_found", f"Folder not found: {folder}")
        if path == Path.home().resolve() or path == Path(path.anchor):
            raise AppError("folder_too_broad", "The home folder or a drive root cannot be a project folder")
    else:
        path = WORKSPACE_DIR / f"{slugify(name)}-{pid[:4]}"
        path.mkdir(parents=True, exist_ok=True)
    db.execute("INSERT INTO projects(id,name,path,created) VALUES(?,?,?,?)", (pid, name, str(path), time.time()))
    return {"id": pid, "name": name, "path": str(path)}


def get_project(project_id: str | None) -> dict | None:
    if not project_id:
        return None
    rows = db.query("SELECT * FROM projects WHERE id=?", (project_id,))
    return rows[0] if rows else None


def session_root(session: dict | None = None, project_id: str | None = None) -> Path:
    """Project chats work in the project folder; chats without a project work in workspace/."""
    proj = get_project((session or {}).get("project_id") or project_id)
    return Path(proj["path"]) if proj else WORKSPACE_DIR


def tree(root: Path, max_entries: int = 2000) -> list[dict]:
    out: list[dict] = []

    def walk(d: Path, depth: int) -> None:
        if len(out) >= max_entries or depth > 8:
            return
        try:
            entries = sorted(d.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
        except OSError:
            return
        for p in entries:
            if p.name in IGNORED:
                continue
            out.append({"path": p.relative_to(root).as_posix(), "dir": p.is_dir()})
            if p.is_dir():
                walk(p, depth + 1)

    walk(root, 0)
    return out


def list_dirs(path: str | None) -> dict:
    """Folder browser for the project dialog. Empty path lists drives (Windows) or '/'."""
    import os
    import string
    if not path:
        if os.name == "nt":
            drives = [f"{d}:\\" for d in string.ascii_uppercase if Path(f"{d}:\\").exists()]
            return {"path": "", "parent": None, "dirs": [{"name": d, "path": d} for d in drives],
                    "home": str(Path.home())}
        path = "/"
    p = Path(path).expanduser().resolve()
    try:
        dirs = sorted((c for c in p.iterdir() if c.is_dir() and not c.name.startswith((".", "$"))),
                      key=lambda c: c.name.lower())
    except OSError as e:
        raise ValueError(str(e))
    parent = None if p.parent == p else str(p.parent)
    if os.name == "nt" and p.parent == p:
        parent = ""
    return {"path": str(p), "parent": parent, "dirs": [{"name": c.name, "path": str(c)} for c in dirs[:500]],
            "home": str(Path.home())}


def summarize_tree(root: Path, limit: int = 150) -> str:
    items = tree(root, limit)
    return "\n".join(("📁 " if i["dir"] else "   ") + i["path"] for i in items) or "(empty)"


def write_state(state: Path, root: Path, name: str, last: str, files: list[str], commands: list[str],
                status: str = "ok") -> None:
    """state: the PROJECT_STATE.md file (kept in the chat's session folder); root: the working folder."""
    history = ""
    if state.exists():
        old = state.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"## Geçmiş\n(.*)", old, re.S)
        history = m.group(1) if m else ""
        # Files from earlier turns stay listed, so "continue" knows everything the task already produced.
        prev = re.search(r"## Değişen Dosyalar\n(.*?)\n\n", old, re.S)
        earlier = re.findall(r"^- `([^`]+)`", prev.group(1), re.M) if prev else []
        files = list(dict.fromkeys(earlier + list(files)))
    stamp = time.strftime("%Y-%m-%d %H:%M")
    entry = f"- {stamp} [{status}] {last[:200]}\n"
    body = (f"# {name} - PROJECT_STATE.md\n\n## Mevcut Durum\n- **Tarih:** {stamp}\n- **Son İşlem:** {last}\n"
            f"- **Durum:** {status}\n\n## Değişen Dosyalar\n" + "".join(f"- `{f}`\n" for f in files[-50:])
            + "\n## Çalıştırılan Komutlar\n" + "".join(f"- `{c[:160]}`\n" for c in commands[-30:])
            + "\n## Dosya Yapısı\n```\n" + summarize_tree(root, 80) + "\n```\n\n## Geçmiş\n"
            + entry + "".join(history.splitlines(keepends=True)[:200]))
    state.write_text(body, encoding="utf-8")


async def _git(root: Path, *args: str) -> tuple[int, str]:
    if not shutil.which("git"):
        return 127, "git not installed"
    p = await asyncio.create_subprocess_exec("git", *args, cwd=str(root), stdout=asyncio.subprocess.PIPE,
                                             stderr=asyncio.subprocess.STDOUT)
    out, _ = await p.communicate()
    return p.returncode or 0, out.decode(errors="replace")


async def git_snapshot(root: Path, message: str) -> str | None:
    """Commit everything in a project folder. Never in the user's home, and never into a git repository
    the user already owns (only repos this app initialised, marked by .aiiq/git_owned)."""
    marker = root / ".aiiq" / "git_owned"
    if root.resolve() == Path.home().resolve():
        return None
    if (root / ".git").exists() and not marker.exists():
        return None
    if not (root / ".git").exists():
        await _git(root, "init", "-q")
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("1", encoding="utf-8")
        (root / ".gitignore").exists() or (root / ".gitignore").write_text(
            "node_modules/\n.venv/\n__pycache__/\n.aiiq/\n", encoding="utf-8")
    await _git(root, "add", "-A")
    code, _ = await _git(root, "-c", "user.name=AI IQ 300", "-c", "user.email=aiiq@localhost",
                         "commit", "-q", "-m", message[:200])
    if code != 0:
        return None
    _, sha = await _git(root, "rev-parse", "--short", "HEAD")
    return sha.strip()


async def git_history(root: Path, limit: int = 50) -> list[dict]:
    code, out = await _git(root, "log", f"-{limit}", "--pretty=format:%h|%ct|%s")
    if code != 0:
        return []
    return [dict(zip(("sha", "ts", "message"), l.split("|", 2))) for l in out.splitlines() if l.count("|") >= 2]


async def git_rollback(root: Path, sha: str) -> str | None:
    """Restore the tree to a snapshot as a NEW commit, so the rollback itself can be undone."""
    if not re.fullmatch(r"[0-9a-f]{4,40}", sha):
        raise ValueError("invalid sha")
    code, out = await _git(root, "restore", f"--source={sha}", "--staged", "--worktree", "--", ".")
    if code != 0:
        raise RuntimeError(out)
    return await git_snapshot(root, f"rollback to {sha}")
