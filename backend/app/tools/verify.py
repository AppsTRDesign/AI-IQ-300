"""Checks that files really are what their name says: an .mp4 that is a 1 KB text file, an empty PDF, a .docx that
is not a zip, an image Pillow cannot open, JSON that does not parse. Used after commands (files they created or
changed) and before write_file (text into a binary format is never a real file)."""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import time
import zipfile
from pathlib import Path

MEDIA = {".mp4", ".m4v", ".mkv", ".webm", ".mov", ".avi", ".flv", ".wmv", ".mpg", ".mpeg",
         ".mp3", ".wav", ".m4a", ".aac", ".ogg", ".oga", ".opus", ".flac", ".wma"}
IMAGES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tif", ".tiff", ".ico", ".avif"}
ZIPS = {".zip", ".docx", ".xlsx", ".pptx", ".odt", ".ods", ".odp", ".epub", ".jar", ".apk", ".whl", ".xlsm"}
OTHER_BINARY = {".pdf", ".exe", ".dll", ".so", ".dylib", ".bin", ".7z", ".rar", ".gz", ".tgz", ".bz2", ".xz",
                ".doc", ".xls", ".ppt", ".psd", ".ttf", ".otf", ".woff", ".woff2", ".sqlite", ".db", ".pyc", ".class",
                ".wasm", ".heic", ".mid", ".midi"}
BINARY = MEDIA | IMAGES | ZIPS | OTHER_BINARY
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", ".aiiq", ".doc-sources", "dist", "build", ".next"}

# How each binary format is really produced (told to a model that tried to write one as text).
MAKERS = {
    "media": "run ffmpeg / yt-dlp (or a Python library) to produce it",
    "image": "a photo for a page: stock_photo (real photos, saved into the folder you name, several in one call); "
             "a new picture: generate_image; a chart or drawing: run (shell=python, Pillow/matplotlib)",
    "office": "make_doc (pdf, docx, pptx, xlsx) or a Python library via run",
    "other": "the program or library that writes this format, via run",
}


def kind(path: Path) -> str:
    s = path.suffix.lower()
    if s in MEDIA:
        return "media"
    if s in IMAGES:
        return "image"
    if s in {".pdf", ".docx", ".xlsx", ".pptx", ".odt", ".ods", ".odp", ".xlsm", ".doc", ".xls", ".ppt"}:
        return "office"
    return "other"


def is_binary_name(path: Path) -> bool:
    return path.suffix.lower() in BINARY


def text_into_binary(path: Path) -> str:
    """The refusal for write_file: plain text saved under a binary format's name is a broken file."""
    return (f"{path.name} is a binary format ({path.suffix.lower()}): text written into it would only be a broken file "
            f"with the right name. Produce it for real - {MAKERS[kind(path)]} - then check the result.")


def _ffprobe() -> str | None:
    return shutil.which("ffprobe")


async def _probe(path: Path) -> str | None:
    exe = _ffprobe()
    if not exe:
        return None
    try:
        p = await asyncio.create_subprocess_exec(exe, "-v", "error", "-show_entries", "format=duration:stream=codec_type",
                                                 "-of", "json", str(path), stdout=asyncio.subprocess.PIPE,
                                                 stderr=asyncio.subprocess.PIPE)
        out, err = await asyncio.wait_for(p.communicate(), 20)
    except (OSError, asyncio.TimeoutError):
        return None
    try:
        data = json.loads(out or b"{}")
    except ValueError:
        data = {}
    streams = [s.get("codec_type") for s in data.get("streams", [])]
    if p.returncode != 0 or not streams:
        why = (err or b"").decode("utf-8", "replace").strip().splitlines()
        return "not a playable media file" + (f" (ffprobe: {why[-1][:160]})" if why else "")
    return None


def _looks_text(head: bytes) -> bool:
    if not head or b"\x00" in head:
        return False
    try:
        head.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


async def problem(path: Path) -> str | None:
    """What is wrong with this file (None when it looks real)."""
    try:
        size = path.stat().st_size
    except OSError:
        return None
    s = path.suffix.lower()
    if size == 0:
        return "empty (0 bytes)"
    try:
        with path.open("rb") as f:
            head = f.read(4096)
    except OSError:
        return None
    if s in BINARY and _looks_text(head):
        return f"plain text ({size} bytes), not real {s} data"
    try:
        if s == ".pdf":
            if not head.startswith(b"%PDF"):
                return "not a PDF (no %PDF header)"
            with path.open("rb") as f:
                f.seek(max(0, size - 2048))
                if b"%%EOF" not in f.read():
                    return "truncated PDF (no %%EOF)"
        elif s in ZIPS:
            if not zipfile.is_zipfile(path):
                return f"not a valid {s} (it is not a zip package)"
        elif s in IMAGES and s not in {".avif", ".heic"}:
            from PIL import Image
            try:
                with Image.open(path) as im:
                    im.verify()
            except Exception as e:  # noqa: BLE001 - any Pillow error means the image is broken
                return f"broken image ({str(e)[:120]})"
        elif s in MEDIA:
            return await _probe(path)
        elif s == ".json" and size < 20_000_000:
            json.loads(path.read_text(encoding="utf-8-sig"))
    except ValueError as e:
        return f"invalid JSON ({str(e)[:120]})"
    except OSError:
        return None
    return None


def changed_since(root: Path, t0: float, limit: int = 4000) -> list[Path]:
    """Files under root created or modified at/after t0 (a quick bounded walk)."""
    found, seen = [], 0
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
        for name in files:
            seen += 1
            if seen > limit:
                return found
            p = Path(dirpath) / name
            try:
                if p.stat().st_mtime >= t0 - 1:
                    found.append(p)
            except OSError:
                continue
    return found


async def check_outputs(root: Path, t0: float, max_files: int = 25) -> str:
    """A note listing broken files a command left behind ("" when all look real)."""
    t = time.monotonic()
    bad = []
    for p in changed_since(root, t0)[:max_files]:
        if time.monotonic() - t > 30:
            break
        if why := await problem(p):
            try:
                rel = p.relative_to(root).as_posix()
            except ValueError:
                rel = p.name
            bad.append(f"{rel}: {why}")
    if not bad:
        return ""
    return ("\n[File check] These files were written by this command but are NOT valid - do not report them as done; "
            "fix the command (codec/format/options) and produce them again:\n- " + "\n- ".join(bad))
