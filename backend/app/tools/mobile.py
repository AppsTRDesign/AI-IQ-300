"""Mobile app test environment (Android emulator, iOS simulator on macOS, Maestro UI flows), user-level installs only.

- status: what is there (Java, Android SDK: adb / emulator / AVDs, Flutter, Node/Expo, Maestro, Xcode simctl).
- setup: Android command-line tools -> platform-tools, emulator, one system image and an AVD, plus Maestro, into
  data/mobile/ (no admin rights; several GB, 5-20 minutes once). Java 17+ is needed (winget / brew / apt hint).
- start: boots the AVD headless-capable and waits until Android reports boot completed.
- install / launch / screenshot / flow: adb install, monkey launch, screencap, `maestro test flow.yaml`.
iOS: only on macOS with Xcode (`xcrun simctl`); Maestro drives iOS simulators too.
"""
from __future__ import annotations

import asyncio
import os
import platform
import shutil
import sys
import zipfile
from pathlib import Path

import httpx

from ..config import DATA_DIR

ROOT = DATA_DIR / "mobile"
SDK = ROOT / "android-sdk"
AVD_NAME = "aiiq_pixel"
API = "34"
IMAGE = f"system-images;android-{API};google_apis;" + ("arm64-v8a" if platform.machine().lower() in ("arm64", "aarch64") else "x86_64")
CMDLINE = {  # Google's command-line tools (sdkmanager / avdmanager)
    "win32": "https://dl.google.com/android/repository/commandlinetools-win-11076708_latest.zip",
    "darwin": "https://dl.google.com/android/repository/commandlinetools-mac-11076708_latest.zip",
    "linux": "https://dl.google.com/android/repository/commandlinetools-linux-11076708_latest.zip",
}
EXE = ".exe" if sys.platform == "win32" else ""
BAT = ".bat" if sys.platform == "win32" else ""


def sdk_root() -> Path:
    for k in ("ANDROID_SDK_ROOT", "ANDROID_HOME"):
        if os.environ.get(k) and Path(os.environ[k]).is_dir():
            return Path(os.environ[k])
    home = Path.home()
    for p in (SDK, home / "AppData/Local/Android/Sdk", home / "Library/Android/sdk", home / "Android/Sdk"):
        if (p / "platform-tools").is_dir() or (p / "cmdline-tools").is_dir():
            return p
    return SDK


def java_home() -> Path | None:
    """The newest Java 17+ installed in the usual places (a just-installed JDK is not on this process's PATH yet,
    and an old Java 8 often comes first on PATH)."""
    import glob
    import re
    pats = (["C:/Program Files/Eclipse Adoptium/jdk-*", "C:/Program Files/Java/jdk-*", "C:/Program Files/Microsoft/jdk-*",
             "C:/Program Files/Zulu/zulu-*", str(Path.home() / ".jdks/*")] if sys.platform == "win32" else
            ["/Library/Java/JavaVirtualMachines/*/Contents/Home", "/usr/lib/jvm/*", "/opt/homebrew/opt/openjdk*/libexec/openjdk.jdk/Contents/Home",
             str(Path.home() / ".jdks/*")])
    pats.append(str(JDK_DIR / "jdk-*" / ("Contents/Home" if sys.platform == "darwin" else "")))  # install_java()
    best = None
    for pat in pats:
        for d in glob.glob(pat):
            m = re.search(r"(?:jdk|zulu|openjdk|temurin)[-@]?(\d+)", Path(d).name + d, re.I)
            v = int(m.group(1)) if m else 0
            if v >= 17 and (Path(d) / "bin" / f"java{EXE}").exists() and (best is None or v > best[0]):
                best = (v, Path(d))
    if best:
        return best[1]
    jh = os.environ.get("JAVA_HOME")
    return Path(jh) if jh and (Path(jh) / "bin" / f"java{EXE}").exists() else None


def env() -> dict:
    root = sdk_root()
    e = dict(os.environ)
    e["ANDROID_SDK_ROOT"] = e["ANDROID_HOME"] = str(root)
    jh = java_home()
    if jh:
        e["JAVA_HOME"] = str(jh)
    extra = ([jh / "bin"] if jh else []) + [root / "platform-tools", root / "emulator", root / "cmdline-tools/latest/bin",
                                            Path.home() / ".maestro/bin"]
    e["PATH"] = os.pathsep.join([*(str(p) for p in extra), e.get("PATH", "")])
    return e


def _which(name: str) -> str | None:
    return shutil.which(name, path=env()["PATH"])


async def _run(*argv: str, timeout: float = 600, stdin: str | None = None) -> tuple[int, str]:
    p = await asyncio.create_subprocess_exec(*argv, env=env(), stdin=asyncio.subprocess.PIPE if stdin else None,
                                             stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
    try:
        out, _ = await asyncio.wait_for(p.communicate(stdin.encode() if stdin else None), timeout)
    except asyncio.TimeoutError:
        p.kill()
        try:
            await asyncio.wait_for(p.wait(), 10)
        except asyncio.TimeoutError:
            pass
        return -1, "timed out"
    return p.returncode or 0, out.decode("utf-8", "replace")[-4000:]


async def status() -> dict:
    root = sdk_root()
    java = _which("java")
    jv = (await _run(java, "-version", timeout=20))[1].splitlines()[0] if java else ""
    adb = _which("adb")
    emulator = _which("emulator")
    avds = []
    if emulator:
        # One AVD name per line; the emulator also prints log lines ("INFO    | ...", "WARNING | ...").
        avds = [ln.strip() for ln in (await _run(emulator, "-list-avds", timeout=30))[1].splitlines()
                if ln.strip() and "|" not in ln and " " not in ln.strip()]
    devices = []
    if adb:
        devices = [ln.split()[0] for ln in (await _run(adb, "devices", timeout=20))[1].splitlines()[1:] if "\tdevice" in ln]
    return {"os": sys.platform, "java": jv or None, "java_ok": _java_major(jv) >= 17, "sdk": str(root),
            "adb": bool(adb), "emulator": bool(emulator),
            "avds": avds, "devices": devices, "maestro": bool(_which("maestro")), "flutter": bool(_which("flutter")),
            "node": bool(_which("node")), "xcode_simctl": sys.platform == "darwin" and bool(_which("xcrun")),
            "hint": None if _java_major(jv) >= 17 else JAVA_HINT}


JAVA_HINT = ("Java 17+ is needed (the Android tools and Maestro refuse older ones): call mobile_env action=java - a "
             "portable Temurin 17 into the app's data folder, no installer, no admin, no MSI lock (winget / MSI often "
             "fails with 1618 'another installation is in progress'); setup does it by itself. If the user did not "
             "ask for an emulator / APK test, test the app in the browser first")
JDK_DIR = ROOT / "jdk"


async def install_java(major: int = 17) -> str:
    """A portable JDK (Eclipse Temurin, Adoptium API) unpacked into data/mobile/jdk: no MSI, no admin, works while
    another installer holds the Windows Installer lock. java_home() finds it."""
    import tarfile
    if (jh := java_home()) and _java_major((await _run(str(jh / "bin" / f"java{EXE}"), "-version", timeout=20))[1]) >= 17:
        return str(jh)
    osname = {"win32": "windows", "darwin": "mac"}.get(sys.platform, "linux")
    arch = "aarch64" if platform.machine().lower() in ("arm64", "aarch64") else "x64"
    url = f"https://api.adoptium.net/v3/binary/latest/{major}/ga/{osname}/{arch}/jdk/hotspot/normal/eclipse"
    JDK_DIR.mkdir(parents=True, exist_ok=True)
    archive = JDK_DIR / ("jdk.zip" if osname == "windows" else "jdk.tar.gz")
    async with httpx.AsyncClient(follow_redirects=True, timeout=httpx.Timeout(30, read=300)) as c:
        async with c.stream("GET", url) as r:
            r.raise_for_status()
            with open(archive, "wb") as f:
                async for chunk in r.aiter_bytes(1 << 16):
                    f.write(chunk)
    if archive.suffix == ".zip":
        with zipfile.ZipFile(archive) as z:
            z.extractall(JDK_DIR)
    else:
        with tarfile.open(archive) as t:
            t.extractall(JDK_DIR)
    archive.unlink(missing_ok=True)
    jh = java_home()
    if not jh:
        raise RuntimeError("the portable JDK was unpacked but no bin/java was found in " + str(JDK_DIR))
    return str(jh)


def _java_major(version_line: str) -> int:
    import re
    m = re.search(r'version "(\d+)(?:\.(\d+))?', version_line or "")
    if not m:
        return 0
    major = int(m.group(1))
    return int(m.group(2) or 0) if major == 1 else major  # "1.8.0" is Java 8


async def setup(progress=None) -> dict:
    """User-level Android SDK + emulator + system image + AVD, and Maestro. Idempotent."""
    def say(msg):
        if progress:
            progress(msg)
    st0 = await status()
    if not st0["java_ok"]:
        say("installing a portable Java 17 (no installer, no admin)")
        await install_java()
        st0 = await status()
        if not st0["java_ok"]:
            raise RuntimeError(f"Java 17+ is still not usable after the portable install; found: {st0['java'] or 'none'}")
    SDK.mkdir(parents=True, exist_ok=True)
    tools = SDK / "cmdline-tools" / "latest"
    if not (tools / "bin" / f"sdkmanager{BAT}").exists():
        say("downloading Android command-line tools")
        url = CMDLINE["win32" if sys.platform == "win32" else "darwin" if sys.platform == "darwin" else "linux"]
        zpath = ROOT / "cmdline-tools.zip"
        async with httpx.AsyncClient(follow_redirects=True, timeout=httpx.Timeout(30, read=300)) as c:
            async with c.stream("GET", url) as r:
                r.raise_for_status()
                with open(zpath, "wb") as f:
                    async for chunk in r.aiter_bytes(1 << 16):
                        f.write(chunk)
        tmp = SDK / "cmdline-tools" / "_tmp"
        shutil.rmtree(tmp, ignore_errors=True)
        with zipfile.ZipFile(zpath) as z:
            z.extractall(tmp)
        shutil.rmtree(tools, ignore_errors=True)
        (tmp / "cmdline-tools").rename(tools)
        shutil.rmtree(tmp, ignore_errors=True)
        zpath.unlink(missing_ok=True)
        if sys.platform != "win32":
            for x in (tools / "bin").iterdir():
                x.chmod(0o755)
    sdkm = str(tools / "bin" / f"sdkmanager{BAT}")
    say("accepting licences")
    await _run(sdkm, f"--sdk_root={SDK}", "--licenses", timeout=300, stdin="y\n" * 30)
    say("installing platform-tools, emulator and the system image (several GB, once)")
    code, out = await _run(sdkm, f"--sdk_root={SDK}", "platform-tools", "emulator", f"platforms;android-{API}", IMAGE,
                           timeout=3600, stdin="y\n" * 10)
    if code:
        raise RuntimeError(f"sdkmanager failed: {out[-600:]}")
    avdm = str(tools / "bin" / f"avdmanager{BAT}")
    if AVD_NAME not in (await status())["avds"]:
        say("creating the emulator (AVD)")
        code, out = await _run(avdm, "create", "avd", "-n", AVD_NAME, "-k", IMAGE, "-d", "pixel_6", "--force",
                               timeout=300, stdin="no\n")
        if code:
            raise RuntimeError(f"avdmanager failed: {out[-600:]}")
    if not _which("maestro"):
        say("installing Maestro (UI test flows)")
        await install_maestro()
    return await status()


async def install_maestro() -> str:
    if sys.platform == "win32":
        # The official script is bash; on Windows the release zip is unpacked into ~/.maestro.
        url = "https://github.com/mobile-dev-inc/maestro/releases/latest/download/maestro.zip"
        dest = Path.home() / ".maestro"
        async with httpx.AsyncClient(follow_redirects=True, timeout=httpx.Timeout(30, read=300)) as c:
            r = await c.get(url)
            r.raise_for_status()
        zpath = ROOT / "maestro.zip"
        zpath.write_bytes(r.content)
        with zipfile.ZipFile(zpath) as z:
            z.extractall(dest.parent / "_maestro_tmp")
        inner = dest.parent / "_maestro_tmp" / "maestro"
        shutil.rmtree(dest, ignore_errors=True)
        inner.rename(dest)
        shutil.rmtree(dest.parent / "_maestro_tmp", ignore_errors=True)
        zpath.unlink(missing_ok=True)
        return str(dest / "bin")
    code, out = await _run("bash", "-c", "curl -fsSL https://get.maestro.mobile.dev | bash", timeout=600)
    return out[-300:]


async def start(avd: str = AVD_NAME, headless: bool = False) -> dict:
    emulator = _which("emulator")
    if not emulator:
        raise RuntimeError("no Android emulator: call mobile_env action=setup first")
    st = await status()
    if not st["devices"]:
        args = [emulator, "-avd", avd, "-no-snapshot-save", "-no-boot-anim", "-netdelay", "none", "-netspeed", "full"]
        if headless:
            args += ["-no-window", "-gpu", "swiftshader_indirect"]
        await asyncio.create_subprocess_exec(*args, env=env(), stdout=asyncio.subprocess.DEVNULL,
                                             stderr=asyncio.subprocess.DEVNULL)
    adb = _which("adb")
    if not adb:
        raise RuntimeError("adb not found: call mobile_env action=setup first")
    await _run(adb, "wait-for-device", timeout=300)
    for _ in range(120):
        if (await _run(adb, "shell", "getprop", "sys.boot_completed", timeout=20))[1].strip() == "1":
            return await status()
        await asyncio.sleep(3)
    raise RuntimeError("the emulator did not finish booting in 6 minutes (enable virtualization / HAXM / WHPX)")


async def adb(*args: str, timeout: float = 300) -> tuple[int, str]:
    a = _which("adb")
    if not a:
        raise RuntimeError("adb not found: call mobile_env action=setup first")
    return await _run(a, *args, timeout=timeout)


async def screenshot(target: Path) -> Path:
    a = _which("adb")
    if not a:
        raise RuntimeError("adb not found")
    p = await asyncio.create_subprocess_exec(a, "exec-out", "screencap", "-p", env=env(), stdout=asyncio.subprocess.PIPE)
    try:
        data, _ = await asyncio.wait_for(p.communicate(), 60)
    except asyncio.TimeoutError:
        p.kill()
        raise RuntimeError("no screenshot in 60 s (is the device responding?)") from None
    if not data.startswith(b"\x89PNG"):
        raise RuntimeError("no screenshot (is a device or emulator running?)")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return target
