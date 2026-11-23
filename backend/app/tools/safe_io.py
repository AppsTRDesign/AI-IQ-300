"""Safe file writes for every agent of the app (v0.19.0).

- One asyncio lock per file: two agents of a team (or two parallel tool calls) never interleave a read-modify-write
  of the same file. The lock is per resolved path and lives as long as the process.
- Atomic replace: the new text goes to a temporary file in the same folder, is flushed to disk, then swapped in with
  os.replace. A crash, a power cut or a killed process leaves the old file or the new one, never half of each. On
  Windows a file held open by another program (an editor, an antivirus scan) can refuse the swap for a moment: it is
  retried, then written in place as the last resort (the old behaviour) rather than failing the task.
- Read-back check: the bytes on disk are hashed after the write; a mismatch restores the previous content.
- Versions: every write through the tools records (sha, agent) per file. An agent that overwrites a whole file another
  agent changed after this agent last read or wrote it is refused once with what changed, so the other agent's work
  is never lost silently (last-writer-wins was the old behaviour). An edit_file is safe by itself: it applies its
  SEARCH/REPLACE to the file as it is under the lock.
"""
from __future__ import annotations

import asyncio
import hashlib
import os
import time
from pathlib import Path

_LOCKS: dict[str, asyncio.Lock] = {}
# resolved path -> {"sha": str, "agent": str, "at": float}
VERSIONS: dict[str, dict] = {}


def key(path: Path | str) -> str:
    try:
        return str(Path(path).resolve()).lower() if os.name == "nt" else str(Path(path).resolve())
    except (OSError, ValueError):
        return str(path)


def lock_for(path: Path | str) -> asyncio.Lock:
    k = key(path)
    lk = _LOCKS.get(k)
    if lk is None:
        lk = _LOCKS[k] = asyncio.Lock()
    return lk


def sha_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="surrogatepass")).hexdigest()


def sha_file(path: Path | str) -> str | None:
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


def clean_tail(text: str) -> str:
    """A streamed text cut off mid-character can end with a replacement character or half of a surrogate pair:
    those are dropped so the file never ends in a broken character."""
    while text and (text[-1] == "�" or 0xD800 <= ord(text[-1]) <= 0xDFFF):
        text = text[:-1]
    return text


class WriteError(OSError):
    pass


def atomic_write_text(path: Path | str, text: str, retries: int = 6) -> str:
    """Write `text` (UTF-8, line endings kept as given) atomically and verify it. Returns the sha256 of the bytes on
    disk. Raises WriteError when the file could not be written correctly (the previous content is restored)."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    data = text.encode("utf-8", errors="surrogatepass")
    want = hashlib.sha256(data).hexdigest()
    old = None
    try:
        old = target.read_bytes() if target.is_file() else None
    except OSError:
        old = None
    tmp = target.with_name(f".{target.name}.{os.getpid()}.{int(time.time() * 1000) % 100000}.aiiq-tmp")
    try:
        with open(tmp, "wb") as fh:
            fh.write(data)
            fh.flush()
            try:
                os.fsync(fh.fileno())
            except OSError:
                pass
        for i in range(retries):
            try:
                os.replace(tmp, target)
                break
            except PermissionError:
                if i == retries - 1:
                    target.write_bytes(data)  # held open by another program: in place, as before v0.19
                    break
                time.sleep(0.05 * (i + 1))
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
    got = sha_file(target)
    if got != want:
        if old is not None:
            try:
                target.write_bytes(old)
            except OSError:
                pass
        raise WriteError(f"{target.name}: the bytes on disk do not match what was written; the previous version was "
                         "restored")
    return want


def _agent(ctx) -> str:
    return f"{getattr(ctx, 'owner', '') or ''}|{getattr(ctx, 'agent', '') or ''}"


def _seen(ctx) -> dict:
    seen = getattr(ctx, "seen_sha", None)
    if seen is None:
        seen = {}
        try:
            ctx.seen_sha = seen
        except AttributeError:
            pass
    return seen


def note_seen(ctx, path: Path | str, sha: str | None = None) -> None:
    """This agent has the file's current content in front of it (it read it whole, or wrote it)."""
    sha = sha or sha_file(path)
    if sha:
        _seen(ctx)[key(path)] = sha


def wrote(ctx, path: Path | str, sha: str) -> None:
    k = key(path)
    VERSIONS[k] = {"sha": sha, "agent": _agent(ctx), "name": getattr(ctx, "agent", "") or "", "at": time.time()}
    _seen(ctx)[k] = sha


def stale_overwrite(ctx, path: Path | str) -> str:
    """'' when this agent may overwrite the whole file; otherwise why not: another agent of the same task (a team
    member, or the main agent while members work) wrote the file after this agent last saw it. Only files written through the tools are tracked (a file nobody wrote in this app
    session is the user's own and is handled by the backup / unread-rewrite notes)."""
    k = key(path)
    last = VERSIONS.get(k)
    if not last or last["agent"] == _agent(ctx):
        return ""
    if last["agent"].split("|")[0] != _agent(ctx).split("|")[0]:
        return ""  # an earlier task of the chat: no parallel writer (the backups and unread-rewrite notes cover it)
    now = sha_file(path)
    if now is None or now != last["sha"]:
        return ""  # changed outside the tools since (the user, a command): not this check's business
    if _seen(ctx).get(k) == now:
        return ""
    who = last.get("name") or "another task"
    return (f"Not written (parallel change): {Path(path).name} was changed by {who} after you last read it, and a "
            f"full rewrite would erase that change. Read it again with read_file, then change only your part with "
            f"edit_file (or write the merged file).")
