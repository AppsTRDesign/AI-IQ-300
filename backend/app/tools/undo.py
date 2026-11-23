"""Undo of one task's file changes (v0.19.0).

Before a task first changes a file through the file tools (write_file, edit_file, delete_file), the file's state at
that moment is kept: its bytes, or "did not exist". After each change the new sha is noted. "Undo this task's changes"
then puts every file back - but only a file that is still exactly as the task left it: a file the user (or a later
task) changed since is skipped and reported, never overwritten.

Kept in chat/<id>/.session/undo/<run id>/ for the last KEEP tasks of the chat. Changes made by shell commands (a build,
npm install, a script) are not tracked here; projects also have the git time machine for those.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from . import safe_io

KEEP = 5
MAX_BYTES = 5 * 1024 * 1024  # a bigger file is listed as not undoable instead of being copied


def _run_id(ctx) -> str:
    parts = (getattr(ctx, "owner", "") or "").split(":")
    return parts[1] if len(parts) > 1 and parts[1] else ""


def _dir(session_dir: Path, run_id: str) -> Path:
    return Path(session_dir) / "undo" / run_id


def _load(d: Path) -> dict:
    try:
        return json.loads((d / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save(d: Path, man: dict) -> None:
    safe_io.atomic_write_text(d / "manifest.json", json.dumps(man, ensure_ascii=False, indent=1))


def _rel(ctx, target: Path) -> str | None:
    try:
        return Path(target).resolve().relative_to(Path(ctx.root).resolve()).as_posix()
    except (OSError, ValueError):
        return None


def _prune(base: Path, keep_name: str) -> None:
    try:
        runs = sorted((p for p in base.iterdir() if p.is_dir() and p.name != keep_name), key=lambda p: p.stat().st_mtime)
        for p in runs[: max(0, len(runs) - (KEEP - 1))]:
            shutil.rmtree(p, ignore_errors=True)
    except OSError:
        pass


def before(ctx, target: Path) -> None:
    """Keep the file's state before this task's first change to it. Never raises."""
    try:
        run, sdir, rel = _run_id(ctx), getattr(ctx, "session_dir", None), _rel(ctx, target)
        if not run or not sdir or not rel:
            return
        d = _dir(sdir, run)
        man = _load(d)
        if rel in man:
            return  # the state before the task's FIRST change is what undo goes back to
        if not man:
            d.mkdir(parents=True, exist_ok=True)
            _prune(d.parent, run)
        t = Path(target)
        if t.is_file():
            size = t.stat().st_size
            if size > MAX_BYTES:
                man[rel] = {"existed": True, "skip": f"larger than {MAX_BYTES // 1048576} MB"}
            else:
                name = f"{len(man):04d}.bin"
                (d / name).write_bytes(t.read_bytes())
                man[rel] = {"existed": True, "copy": name}
        else:
            man[rel] = {"existed": False}
        _save(d, man)
    except (OSError, ValueError):
        pass


def after(ctx, target: Path) -> None:
    """Note the file's state after this task changed it (None: deleted)."""
    try:
        run, sdir, rel = _run_id(ctx), getattr(ctx, "session_dir", None), _rel(ctx, target)
        if not run or not sdir or not rel:
            return
        d = _dir(sdir, run)
        man = _load(d)
        if rel in man:
            man[rel]["after"] = safe_io.sha_file(target)
            _save(d, man)
    except (OSError, ValueError):
        pass


def changed_files(session_dir: Path, run_id: str) -> list[str]:
    return list(_load(_dir(session_dir, run_id)))


def restore(session_dir: Path, root: Path, run_id: str) -> dict:
    """Put the task's files back. Returns {"restored": [...], "removed": [...], "skipped": [{"path", "reason"}]}."""
    d = _dir(session_dir, run_id)
    man = _load(d)
    out: dict = {"restored": [], "removed": [], "skipped": []}
    if not man:
        out["skipped"].append({"path": "", "reason": "nothing to undo for this task"})
        return out
    base = Path(root).resolve()
    for rel, e in man.items():
        target = (base / rel).resolve()
        if base not in target.parents:
            out["skipped"].append({"path": rel, "reason": "outside the working folder"})
            continue
        if "after" not in e:
            continue  # noted but never changed (a refused write)
        if safe_io.sha_file(target) != e["after"]:
            out["skipped"].append({"path": rel, "reason": "changed after the task; left as it is"})
            continue
        if e.get("skip"):
            out["skipped"].append({"path": rel, "reason": e["skip"]})
            continue
        try:
            if e.get("existed"):
                data = (d / e["copy"]).read_bytes()
                target.parent.mkdir(parents=True, exist_ok=True)
                safe_io.atomic_write_text(target, data.decode("utf-8", errors="surrogateescape")) if _utf8(data) \
                    else target.write_bytes(data)
                out["restored"].append(rel)
            else:
                target.unlink(missing_ok=True)
                out["removed"].append(rel)
        except (OSError, ValueError) as err:
            out["skipped"].append({"path": rel, "reason": str(err)[:160]})
    shutil.rmtree(d, ignore_errors=True)  # undone once; a second undo would fight the first
    return out


def _utf8(data: bytes) -> bool:
    try:
        data.decode("utf-8")
        return True
    except UnicodeDecodeError:
        return False
