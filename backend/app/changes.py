"""Everything a task changed in its working folder, whoever changed it: the file tools, but also commands, scripts,
formatters, package managers and code generators. A snapshot (size and modification time of every file, plus the
text of text files) is taken when the task starts, in a worker thread while the model writes its first reply; at the
end the folder is compared with it and each change gets a line count and a unified diff for the review card.

Unchanged files are never read twice: their text is cached per folder between tasks."""
from __future__ import annotations

import difflib
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

# Dependency, build and tool folders: huge and not the user's own work.
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", ".aiiq", "dist", "build", ".next", ".nuxt",
             ".svelte-kit", ".cache", ".parcel-cache", ".turbo", "vendor", "target", ".gradle", ".idea", ".mypy_cache",
             ".pytest_cache", ".ruff_cache", "coverage", ".tox", "bower_components", ".expo", ".angular"}
BINARY_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".bmp", ".pdf", ".zip", ".gz", ".7z", ".rar", ".exe",
               ".dll", ".so", ".dylib", ".woff", ".woff2", ".ttf", ".otf", ".mp3", ".mp4", ".wav", ".mov", ".db",
               ".sqlite", ".pyc", ".class", ".jar", ".docx", ".xlsx", ".pptx", ".odt", ".ods", ".odp", ".psd", ".wasm"}
MAX_FILES = 20000
TEXT_MAX = 300_000  # per file
TEXT_BUDGET = 40_000_000  # all kept texts of one folder
TIME_LIMIT = 3.0  # seconds for one walk (a huge folder is compared partly, and says so)
MAX_DIFF = 12000
MAX_LIST = 200

# folder -> {rel: (size, mtime_ns, text or None)}: texts survive between tasks, so only changed files are read
_TEXTS: dict[str, dict[str, tuple[int, int, str | None]]] = {}


@dataclass
class Snapshot:
    root: str
    files: dict[str, tuple[int, int]] = field(default_factory=dict)
    texts: dict[str, str | None] = field(default_factory=dict)
    partial: bool = False


def _read_text(path: str, size: int) -> str | None:
    if size > TEXT_MAX or Path(path).suffix.lower() in BINARY_EXTS:
        return None
    try:
        data = Path(path).read_bytes()
    except OSError:
        return None
    if b"\x00" in data[:8000]:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("cp1254", "replace")


def take(root: Path) -> Snapshot:
    """Sizes, times and (cached) texts of the files under root."""
    snap = Snapshot(str(root))
    cache = _TEXTS.setdefault(str(root), {})
    kept, t0 = 0, time.monotonic()
    fresh: dict[str, tuple[int, int, str | None]] = {}
    for d, dirs, files in os.walk(root):
        dirs[:] = [x for x in dirs if x not in SKIP_DIRS and not (x.startswith(".") and x not in (".github", ".vscode"))]
        for name in files:
            full = os.path.join(d, name)
            try:
                st = os.stat(full)
            except OSError:
                continue
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            sig = (st.st_size, st.st_mtime_ns)
            snap.files[rel] = sig
            hit = cache.get(rel)
            text = hit[2] if hit and hit[:2] == sig else (_read_text(full, st.st_size) if kept < TEXT_BUDGET else None)
            if text is not None:
                kept += len(text)
            fresh[rel] = (*sig, text)
            snap.texts[rel] = text
            if len(snap.files) >= MAX_FILES or time.monotonic() - t0 > TIME_LIMIT:
                snap.partial = True
                break
        if snap.partial:
            break
    _TEXTS[str(root)] = fresh
    if len(_TEXTS) > 12:
        _TEXTS.pop(next(iter(_TEXTS)))
    return snap


def compare(before: Snapshot, after: Snapshot, by_tools: set[str]) -> dict:
    """{files: [...], added, removed, partial}: each change with its status, source, line counts and diff."""
    out = []
    paths = sorted(set(before.files) | set(after.files))
    for rel in paths:
        a, b = before.files.get(rel), after.files.get(rel)
        if a == b:
            continue
        status = "added" if a is None else "deleted" if b is None else "modified"
        old, new = before.texts.get(rel), after.texts.get(rel)
        if status == "modified" and old is not None and old == new:
            continue  # only the time changed (touched, re-saved unchanged)
        item = {"path": rel, "status": status, "source": "tool" if rel in by_tools else "command",
                "size": (b or a)[0], "added": 0, "removed": 0}
        known_before = status == "added" or old is not None
        known_after = status == "deleted" or new is not None
        if known_before and known_after:
            lines = list(difflib.unified_diff((old or "").splitlines(True), (new or "").splitlines(True),
                                              f"a/{rel}", f"b/{rel}", n=2))
            item["added"] = sum(1 for l in lines if l.startswith("+") and not l.startswith("+++"))
            item["removed"] = sum(1 for l in lines if l.startswith("-") and not l.startswith("---"))
            text = "".join(lines)
            item["diff"] = text if len(text) <= MAX_DIFF else text[:MAX_DIFF] + "\n... (diff truncated)"
        else:
            item["binary"] = True  # a binary or very large file: sizes only
            item["size_before"] = a[0] if a else 0
        out.append(item)
    out.sort(key=lambda x: (x["source"] != "command", x["path"]))  # changes the tools did not report come first
    return {"files": out[:MAX_LIST], "more": max(0, len(out) - MAX_LIST),
            "added": sum(x["added"] for x in out), "removed": sum(x["removed"] for x in out),
            "partial": before.partial or after.partial}
