"""What this computer really is, so the model writes commands that exist here: the OS release and build, the
command shells with their versions, and the developer tools (git, Python, Node, ...) with their versions.
Detected once in the background at startup (each probe with a short timeout, all in parallel) and cached."""
from __future__ import annotations

import platform
import re
import shutil
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

_INFO: dict | None = None
_LOCK = threading.Lock()
MAC_NAMES = {"11": "Big Sur", "12": "Monterey", "13": "Ventura", "14": "Sonoma", "15": "Sequoia", "26": "Tahoe"}


def _out(argv: list[str], timeout: float = 4) -> str:
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, encoding="utf-8", errors="replace",
                           creationflags=0x08000000 if sys.platform == "win32" else 0)  # no console window
        return (r.stdout or r.stderr).strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def _version(text: str) -> str:
    m = re.search(r"(\d+\.\d+(?:\.\d+)?)", text or "")
    return m.group(1) if m else ""


def _os() -> dict:
    if sys.platform == "win32":
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion") as k:
                def val(*names: str) -> str:  # the first value that exists (DisplayVersion is 20H2+, ReleaseId older)
                    for n in names:
                        try:
                            return str(winreg.QueryValueEx(k, n)[0])
                        except OSError:
                            continue
                    return ""
                product, build = val("ProductName"), val("CurrentBuild")
                display, ubr = val("DisplayVersion", "ReleaseId"), val("UBR")
        except OSError:
            product, build, display, ubr = f"Windows {platform.release()}", platform.version().split(".")[-1], "", ""
        if build.isdigit() and int(build) >= 22000:  # Windows 11 still says "Windows 10" in ProductName
            product = product.replace("Windows 10", "Windows 11")
        return {"family": "Windows", "name": product, "release": display, "build": f"{build}.{ubr}" if ubr else build,
                "arch": platform.machine()}
    if sys.platform == "darwin":
        ver = platform.mac_ver()[0]
        return {"family": "macOS", "name": f"macOS {ver} {MAC_NAMES.get(ver.split('.')[0], '')}".strip(), "release": ver,
                "build": _out(["sw_vers", "-buildVersion"]), "arch": platform.machine()}
    pretty = ""
    try:
        for line in Path("/etc/os-release").read_text().splitlines():
            if line.startswith("PRETTY_NAME="):
                pretty = line.split("=", 1)[1].strip('"')
    except OSError:
        pass
    return {"family": "Linux", "name": pretty or "Linux", "release": platform.release(), "build": "", "arch": platform.machine()}


def git_bash() -> str | None:
    """Git for Windows' bash (never System32\\bash.exe, which is WSL)."""
    if sys.platform != "win32":
        return shutil.which("bash")
    git = shutil.which("git")
    candidates = []
    if git:  # git.exe lives in Git\cmd, Git\bin, Git\mingw64\bin or Git\ucrt64\bin: look upwards for Git\bin\bash.exe
        for up in list(Path(git).parents)[:3]:
            candidates += [up / "bin" / "bash.exe", up / "usr" / "bin" / "bash.exe"]
    candidates += [Path(r"C:\Program Files\Git\bin\bash.exe"), Path(r"C:\Program Files (x86)\Git\bin\bash.exe")]
    return next((str(p) for p in candidates if p.is_file()), None)


def _detect() -> dict:
    probes: dict[str, list[str]] = {}
    win = sys.platform == "win32"
    if win:
        if ps := shutil.which("powershell"):
            probes["powershell5"] = [ps, "-NoProfile", "-NonInteractive", "-Command", "$PSVersionTable.PSVersion.ToString()"]
        probes["cmd"] = ["cmd", "/d", "/c", "ver"]
    if pwsh := shutil.which("pwsh"):
        probes["pwsh"] = [pwsh, "-NoProfile", "-Command", "$PSVersionTable.PSVersion.ToString()"]
    if bash := git_bash():
        probes["bash"] = [bash, "--version"]
    for name, exe, arg in (("git", "git", "--version"), ("node", "node", "--version"), ("npm", "npm", "--version"),
                           ("pnpm", "pnpm", "--version"), ("yarn", "yarn", "--version"), ("bun", "bun", "--version"),
                           ("python", "python3" if not win else "python", "--version"), ("php", "php", "--version"),
                           ("java", "java", "-version"), ("dotnet", "dotnet", "--version"), ("go", "go", "version"),
                           ("rustc", "rustc", "--version"), ("docker", "docker", "--version"), ("composer", "composer", "--version"),
                           ("winget", "winget", "--version"), ("brew", "brew", "--version"), ("tesseract", "tesseract", "--version")):
        if path := shutil.which(exe):
            probes[name] = [path, arg]
    with ThreadPoolExecutor(8) as ex:
        found = dict(zip(probes, ex.map(lambda a: _out(a), probes.values())))
    shells, tools = {}, {}
    for name, text in found.items():
        v = _version(text) or ("?" if text else "")
        if not v:
            continue
        (shells if name in ("powershell5", "pwsh", "cmd", "bash") else tools)[name] = v
    if tools.get("python") and Path(shutil.which("python") or "").resolve().parent == Path(sys.executable).resolve().parent:
        tools.pop("python")  # that is the app's own venv, listed below
    return {"os": _os(), "shells": shells, "tools": tools, "app_python": platform.python_version(),
            "git_bash": git_bash() if win else None}


def info() -> dict:
    global _INFO
    with _LOCK:
        if _INFO is None:
            _INFO = _detect()
        return _INFO


def warm() -> None:
    threading.Thread(target=info, daemon=True).start()


def prompt_section() -> str:
    i = info()
    o = i["os"]
    osline = f"{o['name']}" + (f" {o['release']}" if o["release"] and o["release"] not in o["name"] else "") \
             + (f" (build {o['build']})" if o["build"] else "") + f", {o['arch']}"
    sh = i["shells"]
    shells = []
    if sys.platform == "win32":
        if "pwsh" in sh:
            shells.append(f'shell="powershell" = PowerShell {sh["pwsh"]} (pwsh)')
            if "powershell5" in sh:
                shells.append(f'shell="powershell5" = Windows PowerShell {sh["powershell5"]}')
        elif "powershell5" in sh:
            shells.append(f'shell="powershell" = Windows PowerShell {sh["powershell5"]} (no && / ||, no ternary, '
                          'no ?? ; Unix-style rm -rf / mkdir -p / ls -la are accepted)')
        shells.append(f'shell="cmd" = cmd.exe {sh.get("cmd", "")}'.rstrip())
        shells.append(f'shell="bash" = Git Bash {sh["bash"]}' if "bash" in sh else 'shell="bash": not installed (no Git Bash)')
    else:
        shells.append(f'shell="bash" = bash {sh.get("bash", "")}'.rstrip())
        if "pwsh" in sh:
            shells.append(f'shell="pwsh" = PowerShell {sh["pwsh"]}')
    shells.append(f'shell="python" = Python {i["app_python"]} (the app\'s own, with its packages)')
    tools = ", ".join(f"{k} {v}" for k, v in i["tools"].items()) or "none detected"
    return ("# This computer (detected)\n"
            f"OS: {osline}\nShells: " + "; ".join(shells) + f"\nTools on PATH: {tools}\n"
            "Write commands for exactly these versions. Tools not listed are not installed: check or install them first. "
            "When unsure whether a command or flag exists in this version, check `<tool> --help` or the vendor docs for "
            "this exact version (the host-commands skill) instead of guessing.")
