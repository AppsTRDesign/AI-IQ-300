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
import re
import shutil
import sys
import zipfile
from pathlib import Path

import httpx

from ..config import DATA_DIR

ROOT = DATA_DIR / "mobile"
SDK = ROOT / "android-sdk"
AVD_NAME = "aiiq_pixel"
API = "36"  # compileSdk 36 (Android 16): the newest stable level, verified with AGP 8.11.1 (see COMPAT)
BUILD_TOOLS = "36.0.0"
IMAGE = f"system-images;android-{API};google_apis;" + ("arm64-v8a" if platform.machine().lower() in ("arm64", "aarch64") else "x86_64")
CMDLINE = {  # Google's command-line tools (sdkmanager / avdmanager)
    "win32": "https://dl.google.com/android/repository/commandlinetools-win-11076708_latest.zip",
    "darwin": "https://dl.google.com/android/repository/commandlinetools-mac-11076708_latest.zip",
    "linux": "https://dl.google.com/android/repository/commandlinetools-linux-11076708_latest.zip",
}
EXE = ".exe" if sys.platform == "win32" else ""
BAT = ".bat" if sys.platform == "win32" else ""


PATHS_FILE = ROOT / "paths.json"  # the SDK / JDK / Gradle the installer found on this machine (used before searching)

# Rough download sizes (MB): the weights of the setup phases, so one overall bar moves at the real pace
PKG_MB = {"platform-tools": 10, "emulator": 300, "platforms": 70, "build-tools": 60, "system-images": 1600}


def _mb(n: float) -> str:
    return f"{n / 1e6:.0f} MB" if n < 1e9 else f"{n / 1e9:.2f} GB"


class Meter:
    """The overall progress of setup(): phases with weights (about their download size); each phase reports its own
    0..1 and a detail line. cb(fraction 0..1, detail) - the installer draws it as one bar with an ETA."""

    def __init__(self, cb, phases: dict[str, float]) -> None:
        self.cb, self.w = cb, {k: v for k, v in phases.items() if v}
        self.total = sum(self.w.values()) or 1.0
        self.done, self.cur, self.last = 0.0, None, -1.0

    def start(self, phase: str, detail: str = "") -> None:
        if self.cur:
            self.done += self.w.get(self.cur, 0)
        self.cur = phase
        self.emit(0.0, detail)

    def emit(self, frac: float, detail: str = "") -> None:
        if not self.cb:
            return
        overall = (self.done + self.w.get(self.cur, 0) * max(0.0, min(1.0, frac))) / self.total
        self.cb(min(1.0, overall), detail)

    def finish(self, detail: str = "") -> None:
        if self.cur:
            self.done += self.w.get(self.cur, 0)
            self.cur = None
        if self.cb:
            self.cb(1.0, detail)


async def _fetch(url: str, path: Path, on=None, label: str = "") -> None:
    """Downloads with live progress: on(fraction, 'label · 45 MB / 190 MB')."""
    async with httpx.AsyncClient(follow_redirects=True, timeout=httpx.Timeout(30, read=300)) as c:
        async with c.stream("GET", url) as r:
            r.raise_for_status()
            total = int(r.headers.get("content-length") or 0)
            got, shown = 0, 0.0
            with open(path, "wb") as f:
                async for chunk in r.aiter_bytes(1 << 16):
                    f.write(chunk)
                    got += len(chunk)
                    if on and (got - shown > 2e6 or (total and got >= total)):
                        shown = got
                        on(got / total if total else 0.0,
                           f"{label} · {_mb(got)}" + (f" / {_mb(total)}" if total else ""))


async def _run_live(*argv: str, on_line, timeout: float = 3600, stdin: str | None = None) -> tuple[int, str]:
    """Like _run, but every output line (and every '\\r' progress redraw of sdkmanager) goes to on_line at once."""
    e = env()
    e.setdefault("JAVA_OPTS", "-Dfile.encoding=UTF-8 -Dstdout.encoding=UTF-8 -Dstderr.encoding=UTF-8")
    p = await asyncio.create_subprocess_exec(*argv, env=e, stdin=asyncio.subprocess.PIPE if stdin else None,
                                             stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
    if stdin:
        p.stdin.write(stdin.encode())
        await p.stdin.drain()
        p.stdin.close()
    tail, buf = [], ""

    async def pump() -> None:
        nonlocal buf
        while True:
            chunk = await p.stdout.read(4096)
            if not chunk:
                break
            buf += chunk.decode("utf-8", "replace")
            *parts, buf = re.split(r"[\r\n]", buf)
            for part in parts:
                if part.strip():
                    tail.append(part)
                    del tail[:-60]
                    on_line(part.strip())
    try:
        await asyncio.wait_for(asyncio.gather(pump(), p.wait()), timeout)
    except asyncio.TimeoutError:
        p.kill()
        return -1, "timed out"
    return p.returncode or 0, "\n".join(tail)[-4000:]


SDK_LINE = re.compile(r"(\d{1,3})%\s+(Downloading|Unzipping|Installing|Computing|Loading|Fetch\w*)?\s*(.*)", re.I)


def _pkg_of(text: str, wanted: list[str]) -> str | None:
    """Which wanted package a sdkmanager progress line is about (by the file / package name it prints)."""
    t = text.lower()
    keys = [("system-images", ("sys-img", "x86_64-", "arm64-v8a-", "system-images", "system image")),
            ("emulator", ("emulator",)), ("platform-tools", ("platform-tools",)),
            ("build-tools", ("build-tools", "build_tools")), ("platforms", ("platform-", "android sdk platform"))]
    for pkg, words in keys:
        if any(w in t for w in words) and any(x.startswith(pkg) for x in wanted):
            return pkg
    return None


def sdk_progress(wanted: list[str], on) -> callable:
    """A line handler for sdkmanager: the overall 0..1 over the wanted packages (weighted by size) and a detail."""
    sizes = {p.split(";")[0]: PKG_MB.get(p.split(";")[0], 50) for p in wanted} or {"all": 100}
    total = sum(sizes.values())
    state = {"done": set(), "cur": None, "pct": 0.0}

    def handle(line: str) -> None:
        m = SDK_LINE.search(line)
        pkg = _pkg_of(line, wanted) or state["cur"]
        if pkg and pkg != state["cur"]:
            if state["cur"]:
                state["done"].add(state["cur"])
            state["cur"], state["pct"] = pkg, 0.0
        if m:
            pct = int(m.group(1)) / 100
            phase = (m.group(2) or "").lower()
            state["pct"] = max(state["pct"], 0.8 * pct if phase.startswith("download") else
                               0.8 + 0.2 * pct if phase.startswith(("unzip", "install")) else state["pct"])
        done = sum(sizes.get(p, 0) for p in state["done"])
        cur = sizes.get(state["cur"], 0) * state["pct"] if state["cur"] else 0
        what = (m.group(3).strip(" .") if m and m.group(3) else line)[:70]
        on((done + cur) / total, f"{state['cur'] or 'sdkmanager'} · {int(state['pct'] * 100)}% · {what}")
    return handle


def _saved(key: str) -> Path | None:
    try:
        import json
        v = json.loads(PATHS_FILE.read_text(encoding="utf-8")).get(key)
        return Path(v) if v and Path(v).exists() else None
    except (OSError, ValueError):
        return None


def save_paths(**paths) -> None:
    import json
    try:
        old = json.loads(PATHS_FILE.read_text(encoding="utf-8")) if PATHS_FILE.exists() else {}
    except (OSError, ValueError):
        old = {}
    old.update({k: str(v) for k, v in paths.items() if v})
    ROOT.mkdir(parents=True, exist_ok=True)
    PATHS_FILE.write_text(json.dumps(old, indent=1), encoding="utf-8")


def existing_sdks() -> list[Path]:
    """Android SDKs already on this machine (Android Studio's, ANDROID_HOME, the app's own), best first."""
    home = Path.home()
    cands = [Path(os.environ[k]) for k in ("ANDROID_SDK_ROOT", "ANDROID_HOME") if os.environ.get(k)]
    if (s := _saved("sdk")):
        cands.insert(0, s)
    local = Path(os.environ.get("LOCALAPPDATA", home / "AppData/Local"))
    cands += [local / "Android/Sdk", home / "AppData/Local/Android/Sdk", home / "Library/Android/sdk", home / "Android/Sdk",
              Path("C:/Android/Sdk"), Path("C:/Android/android-sdk"), SDK]
    seen, out = set(), []
    for p in cands:
        key = str(p).lower()
        if key not in seen and p.is_dir() and any((p / d).is_dir() for d in ("platform-tools", "cmdline-tools", "platforms")):
            seen.add(key)
            out.append(p)
    return out


def sdk_root() -> Path:
    found = existing_sdks()
    return found[0] if found else SDK


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
    if (s := _saved("jdk")) and (s / "bin" / f"java{EXE}").exists():
        return s
    best = None
    # Android Studio's own runtime (jbr, Java 17 / 21): a machine with Studio needs no second JDK
    for jbr in ("C:/Program Files/Android/Android Studio/jbr", str(Path.home() / "AppData/Local/Programs/Android Studio/jbr"),
                "/Applications/Android Studio.app/Contents/jbr/Contents/Home", "/opt/android-studio/jbr"):
        if (Path(jbr) / "bin" / f"java{EXE}").exists() and (Path(jbr) / "release").exists():
            m = re.search(r'JAVA_VERSION="(\d+)', (Path(jbr) / "release").read_text(errors="replace"))
            if m and int(m.group(1)) >= 17:
                best = (int(m.group(1)), Path(jbr))
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
    if (g := gradle_bin()):
        extra.append(Path(g).parent)
    e["PATH"] = os.pathsep.join([*(str(p) for p in extra), e.get("PATH", "")])
    return e


def add_to_run_env(e: dict) -> None:
    """The toolchain the app keeps under data/mobile (Gradle, adb, emulator, sdkmanager, Maestro, the JDK) on the
    PATH of every run command, AFTER the user's own PATH (their tools win). Without it a model ran 'gradle -version',
    got "not recognized" and reported that Gradle was missing."""
    root = sdk_root()
    jh = java_home()
    extra = [root / "platform-tools", root / "emulator", root / "cmdline-tools" / "latest" / "bin",
             Path.home() / ".maestro" / "bin", *([Path(g).parent] if (g := gradle_bin()) else []),
             *([jh / "bin"] if jh else [])]
    key = next((k for k in e if k.upper() == "PATH"), "PATH")
    cur = e.get(key, "")
    known = {p.lower().rstrip("\\/") for p in cur.split(os.pathsep) if p}
    add = [str(p) for p in extra if p.is_dir() and str(p).lower().rstrip("\\/") not in known]
    if add:
        e[key] = os.pathsep.join([cur, *add]) if cur else os.pathsep.join(add)
    if root.is_dir():
        e.setdefault("ANDROID_HOME", str(root))
        e.setdefault("ANDROID_SDK_ROOT", str(root))
    if jh:
        e.setdefault("JAVA_HOME", str(jh))


def _which(name: str) -> str | None:
    return shutil.which(name, path=env()["PATH"])


async def _run(*argv: str, timeout: float = 600, stdin: str | None = None, cwd: str | None = None) -> tuple[int, str]:
    e = env()
    # Java tools (Maestro, sdkmanager, Gradle's client) print UTF-8 like the rest ("Tanmsz" for "Tanımsız" before)
    e.setdefault("JAVA_OPTS", "-Dfile.encoding=UTF-8 -Dstdout.encoding=UTF-8 -Dstderr.encoding=UTF-8")
    p = await asyncio.create_subprocess_exec(*argv, env=e, stdin=asyncio.subprocess.PIPE if stdin else None, cwd=cwd,
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


GRADLE_DIR = ROOT / "gradle"
GRADLE_VERSION = "8.13"
# Version sets for compileSdk 36 / 37. 36 was BUILT here (BUILD SUCCESSFUL, installed and tested on the emulator with
# Maestro, 2026-11-20): pinning it saves the minutes models spent reading Maven metadata and second-guessing.
COMPAT = {
    "36": {"status": "verified on this app (BUILD SUCCESSFUL, APK installed and tested)",
           "agp": "8.11.1", "kotlin": "2.1.21", "gradle": "8.13", "jdk": "17 or 21", "build_tools": "36.0.0 or 37.0.0",
           "plugins": 'id("com.android.application") version "8.11.1" apply false; '
                      'id("org.jetbrains.kotlin.android") version "2.1.21" apply false',
           "notes": "compileSdk = 36, targetSdk = 36, minSdk 24; set buildToolsVersion to an INSTALLED one (see "
                    "build_tools) or Gradle downloads another (33.0.1 was pulled in silently); kotlinOptions jvmTarget "
                    "= \"17\" with compileOptions VERSION_17; plain Views / AppCompat need no Compose compiler plugin."},
    "37": {"status": "from developer.android.com (AGP 9.5.0 release notes), not built on this machine yet",
           "agp": "9.5.0", "kotlin": "built into AGP 9 (no org.jetbrains.kotlin.android plugin)", "gradle": "9.6.0",
           "jdk": "17 or 21", "build_tools": "36.0.0+ (37.0.0 installed is fine)",
           "notes": "AGP 9 is a major release: new DSL defaults and built-in Kotlin. Prefer compileSdk 36 unless the "
                    "user needs 37; with 37 build once early and fix the first error."},
}
RULES = [
    "Run Gradle with JAVA_HOME and ANDROID_HOME from 'paths' set in the same command (PowerShell: $env:JAVA_HOME=...; "
    "$env:ANDROID_HOME=...), or write sdk.dir into local.properties. Use the gradle from 'paths.gradle' (or a "
    "wrapper made with it: gradle wrapper --gradle-version 8.13) instead of downloading a new one per project.",
    "Screenshots: mobile_env action=screenshot path=shots/NAME.png (a PNG in the working folder). Never 'adb shell "
    "screencap -p > file' in PowerShell: the redirection breaks the binary file.",
    "Maestro: mobile_env action=flow path=flows/x.yaml runs in the working folder, so '- takeScreenshot: shots/NAME' "
    "lands in shots/NAME.png there. Assert on texts the UI really shows (a NoActionBar app has no title text).",
    "UI text check without OCR: mobile_env action=adb args=\"shell uiautomator dump /sdcard/ui.xml\", then action=adb "
    "args=\"pull /sdcard/ui.xml ui.xml\" and read_file ui.xml (UTF-8).",
    "Emulator: start it once with action=start and leave it running until the task is done; it is not closed by the "
    "app. Close it only if the user asks (action=adb args=\"emu kill\").",
    "Never leave temporary files in the project (*.tmp, tmp*.txt, *.bak): write the real file directly.",
]


def _ls(d: Path) -> list[str]:
    try:
        return sorted(x.name for x in d.iterdir() if x.is_dir())
    except OSError:
        return []


def gradle_bin() -> str | None:
    """A Gradle the app installed (data/mobile/gradle/gradle-X/bin), else one on PATH / GRADLE_HOME."""
    import glob
    found = sorted(glob.glob(str(GRADLE_DIR / "gradle-*" / "bin" / f"gradle{BAT}")), reverse=True)
    if found:
        return found[0]
    gh = os.environ.get("GRADLE_HOME")
    if gh and (Path(gh) / "bin" / f"gradle{BAT}").exists():
        return str(Path(gh) / "bin" / f"gradle{BAT}")
    if (s := _saved("gradle")):
        return str(s)
    return shutil.which("gradle")  # (not _which: env() asks gradle_bin for its folder)


async def install_gradle(version: str = GRADLE_VERSION, on=None) -> str:
    """Gradle X into data/mobile/gradle once (shared by every project), instead of a 130 MB download per chat."""
    target = GRADLE_DIR / f"gradle-{version}" / "bin" / f"gradle{BAT}"
    if target.exists():
        return str(target)
    GRADLE_DIR.mkdir(parents=True, exist_ok=True)
    zpath = GRADLE_DIR / f"gradle-{version}-bin.zip"
    await _fetch(f"https://services.gradle.org/distributions/gradle-{version}-bin.zip", zpath,
                 (lambda f, d: on(f * 0.9, d)) if on else None, f"Gradle {version}")
    if on:
        on(0.92, f"Gradle {version} · unzipping")
    with zipfile.ZipFile(zpath) as z:
        z.extractall(GRADLE_DIR)
    zpath.unlink(missing_ok=True)
    if sys.platform != "win32":
        target.chmod(0o755)
    return str(target)


def sdk_inventory(root: Path) -> dict:
    """What the SDK really holds, read from its folders (no sdkmanager call: seconds, not minutes)."""
    images = []
    for api in _ls(root / "system-images"):
        for tag in _ls(root / "system-images" / api):
            images += [f"system-images;{api};{tag};{abi}" for abi in _ls(root / "system-images" / api / tag)]
    return {"platforms": _ls(root / "platforms"), "build_tools": _ls(root / "build-tools"),
            "system_images": images, "cmdline_tools": _ls(root / "cmdline-tools"),
            "platform_tools": (root / "platform-tools").is_dir(), "emulator": (root / "emulator").is_dir()}


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
    jh = java_home()
    tools = root / "cmdline-tools" / "latest" / "bin"
    inv = sdk_inventory(root)
    gradle = gradle_bin()
    return {"os": sys.platform, "java": jv or None, "java_ok": _java_major(jv) >= 17, "sdk": str(root),
            "adb": bool(adb), "emulator": bool(emulator),
            "avds": avds, "devices": devices, "maestro": bool(_which("maestro")), "flutter": bool(_which("flutter")),
            "node": bool(_which("node")), "xcode_simctl": sys.platform == "darwin" and bool(_which("xcrun")),
            "gradle": bool(gradle),
            # Every path a build or test needs, so no model has to search the disk for them (it used to, every task)
            "paths": {"ANDROID_HOME": str(root), "JAVA_HOME": str(jh) if jh else None, "java": java, "adb": adb,
                      "emulator": emulator, "gradle": gradle,
                      "sdkmanager": str(tools / f"sdkmanager{BAT}") if (tools / f"sdkmanager{BAT}").exists() else None,
                      "avdmanager": str(tools / f"avdmanager{BAT}") if (tools / f"avdmanager{BAT}").exists() else None,
                      "maestro": _which("maestro"), "avd_home": str(Path.home() / ".android" / "avd"),
                      "jdk_dir": str(JDK_DIR), "gradle_dir": str(GRADLE_DIR)},
            "installed": inv,
            "compat": COMPAT, "rules": RULES,
            "hint": (None if _java_major(jv) >= 17 else JAVA_HINT) or (
                None if gradle else "No Gradle yet: mobile_env action=gradle installs Gradle 8.13 once for all projects.")}


JAVA_HINT = ("Java 17+ is needed (the Android tools and Maestro refuse older ones): call mobile_env action=java - a "
             "portable Temurin 17 into the app's data folder, no installer, no admin, no MSI lock (winget / MSI often "
             "fails with 1618 'another installation is in progress'); setup does it by itself. If the user did not "
             "ask for an emulator / APK test, test the app in the browser first")
JDK_DIR = ROOT / "jdk"


async def install_java(major: int = 17, on=None) -> str:
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
    await _fetch(url, archive, (lambda f, d: on(f * 0.9, d)) if on else None, f"JDK {major}")
    if on:
        on(0.92, f"JDK {major} · unzipping")
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


async def setup(progress=None, meter=None) -> dict:
    """Android SDK + emulator + system image + AVD, Gradle and Maestro. Idempotent and frugal: an SDK already on the
    machine (Android Studio's, ANDROID_HOME) is used as it is - only missing packages are added and installed ones
    updated; a JDK 17+ already there (also Android Studio's jbr) is used; nothing is downloaded twice. The paths found
    are saved (data/mobile/paths.json) so `mobile_env status` reports them.
    progress(message): one line per phase. meter(fraction 0..1, detail): the live overall progress of the whole setup
    (downloads by bytes, sdkmanager by its own percentages, weighted by size)."""
    def say(msg):
        if progress:
            progress(msg)
    found = existing_sdks()
    sdk = found[0] if found else SDK
    jh = java_home()
    jdk_ok = bool(jh) and _java_major((await _run(str(jh / "bin" / f"java{EXE}"), "-version", timeout=20))[1]) >= 17
    sdk.mkdir(parents=True, exist_ok=True)
    pre = sdk_inventory(sdk)
    tools = sdk / "cmdline-tools" / "latest"
    if not (tools / "bin" / f"sdkmanager{BAT}").exists() and (alt := sorted((sdk / "cmdline-tools").glob("*/bin/sdkmanager*"))):
        tools = alt[-1].parent.parent  # an older cmdline-tools version folder of an existing SDK
    want = {"platform-tools": pre["platform_tools"], "emulator": pre["emulator"],
            f"platforms;android-{API}": f"android-{API}" in pre["platforms"],
            f"build-tools;{BUILD_TOOLS}": any(b.startswith(("36.", "37.")) for b in pre["build_tools"]),
            IMAGE: IMAGE in pre["system_images"]}
    missing = [p for p, have in want.items() if not have]
    avd_there = (Path.home() / ".android" / "avd" / f"{AVD_NAME}.avd").is_dir()
    # The plan with weights ~ download size in MB, so the bar moves at the real pace (the system image is ~1.6 GB)
    m = Meter(meter, {"jdk": 0 if jdk_ok else 190, "cmdline": 0 if (tools / "bin" / f"sdkmanager{BAT}").exists() else 150,
                      "licenses": 4, "packages": sum(PKG_MB.get(p.split(";")[0], 50) for p in missing),
                      "update": 120 if found else 0, "gradle": 0 if gradle_bin() else 135,
                      "avd": 0 if avd_there else 8, "maestro": 0 if _which("maestro") else 60})
    say(f"Android SDK: {sdk} ({'found on this machine' if found else 'new, user-level'})")
    if jdk_ok:
        say(f"JDK: {jh} (found, kept)")
    else:
        say("JDK 21 (LTS, portable, no admin)")
        m.start("jdk", "JDK 21")
        jh = Path(await install_java(21, on=m.emit))
    SDK_ = sdk  # noqa: N806 - the SDK this setup works on
    if not (tools / "bin" / f"sdkmanager{BAT}").exists():
        say("downloading Android command-line tools")
        m.start("cmdline", "Android command-line tools")
        url = CMDLINE["win32" if sys.platform == "win32" else "darwin" if sys.platform == "darwin" else "linux"]
        ROOT.mkdir(parents=True, exist_ok=True)
        zpath = ROOT / "cmdline-tools.zip"
        await _fetch(url, zpath, lambda f, d: m.emit(f * 0.9, d), "Android command-line tools")
        m.emit(0.93, "Android command-line tools · unzipping")
        tmp = SDK_ / "cmdline-tools" / "_tmp"
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
    m.start("licenses", "Android SDK licences")
    await _run(sdkm, f"--sdk_root={SDK_}", "--licenses", timeout=300, stdin="y\n" * 30)
    if missing:
        say("installing " + ", ".join(missing) + (" (several GB, once)" if IMAGE in missing else ""))
        m.start("packages", ", ".join(x.split(";")[0] for x in missing))
        code, out = await _run_live(sdkm, f"--sdk_root={SDK_}", *missing, timeout=3600, stdin="y\n" * 10,
                                    on_line=sdk_progress(missing, m.emit))
        if code:
            raise RuntimeError(f"sdkmanager failed: {out[-600:]}")
    else:
        say("all SDK packages present")
    if found:
        say("updating the installed SDK packages (only newer versions are downloaded)")
        m.start("update", "SDK update")
        await _run_live(sdkm, f"--sdk_root={SDK_}", "--update", timeout=3600, stdin="y\n" * 10,
                        on_line=sdk_progress(list(want), m.emit))
    if not gradle_bin():
        say(f"installing Gradle {GRADLE_VERSION} (shared by every project)")
        m.start("gradle", f"Gradle {GRADLE_VERSION}")
        await install_gradle(on=m.emit)
    else:
        say(f"Gradle: {gradle_bin()} (found, kept)")
    save_paths(sdk=SDK_, jdk=jh, gradle=gradle_bin())
    avdm = str(tools / "bin" / f"avdmanager{BAT}")
    if AVD_NAME not in (await status())["avds"]:
        say("creating the emulator (AVD)")
        m.start("avd", f"emulator {AVD_NAME}")
        code, out = await _run(avdm, "create", "avd", "-n", AVD_NAME, "-k", IMAGE, "-d", "pixel_6", "--force",
                               timeout=300, stdin="no\n")
        if code:
            raise RuntimeError(f"avdmanager failed: {out[-600:]}")
    if not _which("maestro"):
        say("installing Maestro (UI test flows)")
        m.start("maestro", "Maestro")
        await install_maestro(on=m.emit)
    m.finish("ready")
    return await status()


async def install_maestro(on=None) -> str:
    if sys.platform == "win32":
        # The official script is bash; on Windows the release zip is unpacked into ~/.maestro.
        url = "https://github.com/mobile-dev-inc/maestro/releases/latest/download/maestro.zip"
        dest = Path.home() / ".maestro"
        ROOT.mkdir(parents=True, exist_ok=True)
        zpath = ROOT / "maestro.zip"
        await _fetch(url, zpath, (lambda f, d: on(f * 0.9, d)) if on else None, "Maestro")
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


async def sdk_install(packages: list[str]) -> tuple[int, str]:
    """sdkmanager for any package by its exact name (platforms;android-37.2, build-tools;37.0.0, system-images;...),
    or '--list' (the available names, filtered to the newer levels so the answer stays short)."""
    tools = sdk_root() / "cmdline-tools" / "latest" / "bin"
    sdkm = tools / f"sdkmanager{BAT}"
    if not sdkm.exists():
        raise RuntimeError("no sdkmanager: call mobile_env action=setup first")
    if packages == ["--list"]:
        code, out = await _run(str(sdkm), f"--sdk_root={sdk_root()}", "--list", timeout=300)
        keep = [ln for ln in out.splitlines() if re.search(r"android-3[4-9]|build-tools;3[4-9]|Installed|Available", ln)]
        return code, "\n".join(keep)[-6000:]
    await _run(str(sdkm), f"--sdk_root={sdk_root()}", "--licenses", timeout=300, stdin="y\n" * 30)
    return await _run(str(sdkm), f"--sdk_root={sdk_root()}", *packages, timeout=3600, stdin="y\n" * 10)


async def start(avd: str = AVD_NAME, headless: bool = False) -> dict:
    emulator = _which("emulator")
    if not emulator:
        raise RuntimeError("no Android emulator: call mobile_env action=setup first")
    st = await status()
    if avd not in st["avds"] and st["avds"]:
        avd = st["avds"][0]  # the AVD the machine has (another name than the app's default)
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
