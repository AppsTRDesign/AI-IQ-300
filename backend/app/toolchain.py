"""Command-line tools the agent relies on, made available without manual setup.

At app start (in the background, never blocking):
  - ffmpeg / ffprobe: when not on PATH, the static-ffmpeg package downloads a build for this OS (Windows, macOS,
    Linux) once and its folder is added to PATH, so `run` commands, subtitles and file checks find them.
  - composer (PHP): when PHP is installed but Composer is not, composer.phar is downloaded from getcomposer.org
    (checked against its published SHA-256) into data/bin with a `composer` launcher.
  - data/bin and the app's Node packages (frontend/node_modules: sharp, @resvg/resvg-js, opentype.js...) are put on
    PATH / NODE_PATH for every command the agent runs.
The installers (install.bat / install.sh) also install ffmpeg, git, GitHub CLI and PHP with winget / brew / apt
when they are missing; this module is the fallback for an existing install.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import shutil
import sys
from pathlib import Path

import httpx

from .config import DATA_DIR, ROOT as ROOT_DIR

log = logging.getLogger(__name__)
BIN = DATA_DIR / "bin"
NODE_MODULES = ROOT_DIR / "frontend" / "node_modules"
STATUS: dict[str, str] = {}


def _add_path(folder: str | Path) -> None:
    folder = str(folder)
    parts = os.environ.get("PATH", "").split(os.pathsep)
    if folder not in parts:
        os.environ["PATH"] = os.pathsep.join([folder, *parts])


def setup_paths() -> None:
    BIN.mkdir(parents=True, exist_ok=True)
    _add_path(BIN)
    if (BIN / "php.ini").exists():  # written by an earlier start (see _php_ini); refreshed by ensure()
        os.environ["PHPRC"] = str(BIN)
    if NODE_MODULES.is_dir():
        cur = [p for p in os.environ.get("NODE_PATH", "").split(os.pathsep) if p]
        if str(NODE_MODULES) not in cur:
            os.environ["NODE_PATH"] = os.pathsep.join([*cur, str(NODE_MODULES)])


def _ffmpeg() -> str:
    if shutil.which("ffmpeg") and shutil.which("ffprobe"):
        return "system"
    try:
        import static_ffmpeg
        from static_ffmpeg import run as sf_run
    except ImportError:
        return "missing"
    ffmpeg, _ffprobe = sf_run.get_or_fetch_platform_executables_else_raise()
    _add_path(Path(ffmpeg).parent)
    del static_ffmpeg
    return "static-ffmpeg"


PHP_EXTS = ("openssl", "curl", "mbstring", "zip", "fileinfo", "intl", "gd", "sodium", "pdo_sqlite", "sqlite3",
            "pdo_mysql", "mysqli", "pdo_pgsql", "exif", "sockets")


def _php_ini(php: str) -> str:
    """A PHP without php.ini (the Windows zip / winget build) has openssl, curl, mbstring... switched off, so
    Composer cannot download anything. Then a php.ini that turns the bundled extensions on is written to data/bin
    and PHPRC points to it, for every php the app or the agent runs. A PHP with its own php.ini is left alone."""
    import subprocess
    try:
        env = {k: v for k, v in os.environ.items() if k != "PHPRC"}  # judge PHP's own configuration
        out = subprocess.run([php, "--ini"], capture_output=True, text=True, timeout=10, env=env).stdout
    except (OSError, subprocess.SubprocessError):
        return "php-error"
    if "Loaded Configuration File:" in out and "(none)" not in out.split("Loaded Configuration File:")[1].splitlines()[0]:
        return "own-ini"
    ext = Path(php).resolve().parent / "ext"
    if not ext.is_dir():
        return "no-ext-dir"
    have = [e for e in PHP_EXTS if (ext / f"php_{e}.dll").exists() or (ext / f"{e}.so").exists()]
    ini = BIN / "php.ini"
    ini.write_text(f'; written by AI IQ 300 (toolchain.py): extensions of {php}\nextension_dir = "{ext}"\n'
                   + "".join(f"extension={e}\n" for e in have) + "memory_limit = 1G\n", encoding="utf-8")
    os.environ["PHPRC"] = str(BIN)
    return f"ini:{len(have)}"


async def _composer() -> str:
    php = shutil.which("php")
    if php:
        STATUS["php"] = await asyncio.to_thread(_php_ini, php)
    if shutil.which("composer"):
        return "system"
    if not php:
        return "no-php"
    phar = BIN / "composer.phar"
    if not phar.exists():
        async with httpx.AsyncClient(timeout=60, follow_redirects=True) as c:
            data = (await c.get("https://getcomposer.org/download/latest-stable/composer.phar")).content
            want = (await c.get("https://getcomposer.org/download/latest-stable/composer.phar.sha256")).text.split()[0]
        if hashlib.sha256(data).hexdigest() != want.strip().lower():
            return "checksum-mismatch"
        phar.write_bytes(data)
    if sys.platform == "win32":
        (BIN / "composer.bat").write_text(f'@"{php}" "%~dp0composer.phar" %*\r\n', encoding="utf-8")
    else:
        sh = BIN / "composer"
        sh.write_text(f'#!/bin/sh\nexec "{php}" "$(dirname "$0")/composer.phar" "$@"\n', encoding="utf-8")
        sh.chmod(0o755)
    return "composer.phar"


async def ensure() -> dict[str, str]:
    """Run once at start in the background; failures only leave a note (the tool stays unavailable)."""
    setup_paths()
    try:
        STATUS["ffmpeg"] = await asyncio.to_thread(_ffmpeg)
    except Exception as e:  # noqa: BLE001
        STATUS["ffmpeg"] = f"error: {e}"
    try:
        STATUS["composer"] = await _composer()
    except Exception as e:  # noqa: BLE001
        STATUS["composer"] = f"error: {e}"
    log.info("toolchain: %s", STATUS)
    return STATUS
