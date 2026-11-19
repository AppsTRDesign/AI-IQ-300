"""The computer's hardware and OS as one structured report (Windows, Linux, macOS), for the system_info tool.
Weak models asked "find my PC's specs" wrote locale-dependent pipelines (systeminfo | findstr "İşlemci") that fail
on non-English Windows; this reads the same facts through locale-independent sources."""
from __future__ import annotations

import json
import os
import platform
import re
import shutil
import time
import subprocess
import sys

GB = 1024 ** 3


def _out(argv: list[str], timeout: float = 20) -> str:
    try:
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        p = subprocess.run(argv, capture_output=True, timeout=timeout, creationflags=flags)
        return p.stdout.decode("utf-8", "replace") if p.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def _gb(n) -> str:
    try:
        return f"{int(n) / GB:.1f} GB"
    except (TypeError, ValueError):
        return "?"


WIN_QUERY = r"""
$ErrorActionPreference='SilentlyContinue'
[Console]::OutputEncoding=[Text.Encoding]::UTF8
$r=[ordered]@{}
$r.cpu=@(Get-CimInstance Win32_Processor | Select-Object Name,Manufacturer,NumberOfCores,NumberOfLogicalProcessors,MaxClockSpeed,L2CacheSize,L3CacheSize)
$r.gpu=@(Get-CimInstance Win32_VideoController | Select-Object Name,DriverVersion,AdapterRAM,VideoModeDescription,CurrentRefreshRate)
$r.ram=@(Get-CimInstance Win32_PhysicalMemory | Select-Object Manufacturer,PartNumber,Capacity,Speed,ConfiguredClockSpeed,DeviceLocator)
$r.board=Get-CimInstance Win32_BaseBoard | Select-Object Manufacturer,Product,Version
$r.bios=Get-CimInstance Win32_BIOS | Select-Object Manufacturer,SMBIOSBIOSVersion,ReleaseDate
$r.system=Get-CimInstance Win32_ComputerSystem | Select-Object Manufacturer,Model,SystemType,TotalPhysicalMemory
$r.os=Get-CimInstance Win32_OperatingSystem | Select-Object Caption,Version,BuildNumber,OSArchitecture,InstallDate,LastBootUpTime
$r.disks=@(Get-CimInstance Win32_DiskDrive | Select-Object Model,Size,InterfaceType,MediaType,SerialNumber)
$r.physical=@(Get-PhysicalDisk | Select-Object FriendlyName,MediaType,BusType,Size,HealthStatus)
$r.net=@(Get-CimInstance Win32_NetworkAdapter -Filter 'PhysicalAdapter=True' | Select-Object Name,Speed,NetEnabled)
$r.monitors=@(Get-CimInstance -Namespace root\wmi WmiMonitorID | ForEach-Object { (($_.UserFriendlyName | Where-Object {$_ -ne 0} | ForEach-Object {[char]$_}) -join '') })
$r.battery=@(Get-CimInstance Win32_Battery | Select-Object Name,EstimatedChargeRemaining)
$r | ConvertTo-Json -Depth 4 -Compress
"""


def _windows() -> dict:
    exe = shutil.which("powershell") or shutil.which("pwsh")
    if not exe:
        return {}
    raw = _out([exe, "-NoProfile", "-NonInteractive", "-Command", WIN_QUERY], 40)
    try:
        return json.loads(raw) if raw.strip() else {}
    except ValueError:
        return {}


def _linux() -> dict:
    d: dict = {}
    if lscpu := _out(["lscpu"]):
        d["cpu"] = {k.strip(): v.strip() for k, v in (ln.split(":", 1) for ln in lscpu.splitlines() if ":" in ln)
                    if k.strip() in ("Model name", "Vendor ID", "CPU(s)", "Core(s) per socket", "Socket(s)",
                                     "CPU max MHz", "L3 cache", "Architecture")}
    if lspci := _out(["lspci"]):
        d["gpu"] = [ln.split(": ", 1)[-1] for ln in lspci.splitlines() if "VGA" in ln or "3D controller" in ln]
    if lsblk := _out(["lsblk", "-d", "-J", "-o", "NAME,MODEL,SIZE,ROTA,TRAN"]):
        try:
            d["disks"] = json.loads(lsblk).get("blockdevices", [])
        except ValueError:
            pass
    for f, key in (("/sys/class/dmi/id/board_vendor", "board_vendor"), ("/sys/class/dmi/id/board_name", "board"),
                   ("/sys/class/dmi/id/product_name", "model"), ("/sys/class/dmi/id/bios_version", "bios")):
        try:
            d[key] = open(f, encoding="utf-8").read().strip()
        except OSError:
            pass
    return d


def _mac() -> dict:
    raw = _out(["system_profiler", "-json", "SPHardwareDataType", "SPDisplaysDataType", "SPStorageDataType"], 40)
    try:
        return json.loads(raw) if raw.strip() else {}
    except ValueError:
        return {}


def collect() -> dict:
    """Everything known about this computer; each source may be missing (no permission, no tool)."""
    import psutil
    vm = psutil.virtual_memory()
    out: dict = {
        "os": f"{platform.system()} {platform.release()} ({platform.version()}) {platform.machine()}",
        "hostname": platform.node(),
        "cpu_brand": platform.processor(),
        "cores": psutil.cpu_count(logical=False), "threads": psutil.cpu_count(),
        "ram_total": _gb(vm.total), "ram_free": _gb(vm.available), "ram_used_pct": vm.percent,
        "volumes": [],
    }
    for p in psutil.disk_partitions(all=False):
        try:
            u = psutil.disk_usage(p.mountpoint)
        except (OSError, PermissionError):
            continue
        out["volumes"].append({"mount": p.mountpoint, "fs": p.fstype, "total": _gb(u.total), "free": _gb(u.free)})
    try:
        from ..llm import memguard
        if v := memguard.vram():
            out["vram"] = {k: (_gb(x) if isinstance(x, int) and x > 10_000_000 else x) for k, x in v.items()}
    except Exception:  # noqa: BLE001 - optional
        pass
    if sys.platform == "win32":
        out["details"] = _windows()
    elif sys.platform == "darwin":
        out["details"] = _mac()
    else:
        out["details"] = _linux()
    return out


def _clean(x):
    """Drops empty values and turns byte counts into GB, so the report stays short and readable."""
    if isinstance(x, dict):
        r = {}
        for k, v in x.items():
            if k in ("SerialNumber", "AdapterRAM"):  # private / capped at 4 GB by WMI (the vram entry is right)
                continue
            v = _clean(v)
            if v in (None, "", [], {}):
                continue
            if isinstance(v, str) and (m := re.fullmatch(r"/Date\((\d+)\)/", v)):
                v = time.strftime("%Y-%m-%d %H:%M", time.localtime(int(m.group(1)) / 1000))
            if k in ("Capacity", "Size", "TotalPhysicalMemory") and str(v).isdigit():
                v = _gb(v)
            r[k] = v
        return r
    if isinstance(x, list):
        return [c for c in (_clean(v) for v in x) if c not in (None, "", [], {})]
    if isinstance(x, str):
        return x.strip()
    return x


def _python_packages() -> list[str]:
    """Packages of the app's own Python (the one shell=python and pip use)."""
    from importlib import metadata
    seen: dict[str, str] = {}
    for d in metadata.distributions():
        name = (d.metadata.get("Name") or "").strip()
        if name and name.lower() not in seen:
            seen[name.lower()] = f"{name} {d.version}"
    return sorted(seen.values(), key=str.lower)


def _npm_globals() -> list[str]:
    npm = shutil.which("npm")
    if not npm:
        return []
    raw = _out([npm, "ls", "-g", "--depth=0", "--json"], 25)
    try:
        deps = (json.loads(raw) if raw.strip() else {}).get("dependencies") or {}
    except ValueError:
        return []
    return [f"{k} {v.get('version', '')}".strip() for k, v in sorted(deps.items())]


SKIP_DIRS = {"node_modules", ".git", ".venv", "venv", "dist", "build", ".next", ".expo", "__pycache__", ".session"}


def _project_manifests(root) -> list[dict]:
    """Dependency files in the working folder (2 levels deep): what this project already uses."""
    from pathlib import Path
    root = Path(root)
    out: list[dict] = []
    if not root.is_dir():
        return out

    def walk(d: Path, depth: int) -> None:
        try:
            entries = sorted(d.iterdir())
        except OSError:
            return
        for p in entries:
            if p.is_dir():
                if depth < 2 and p.name not in SKIP_DIRS and not p.name.startswith("."):
                    walk(p, depth + 1)
                continue
            rel = p.relative_to(root).as_posix()
            try:
                if p.name == "package.json":
                    j = json.loads(p.read_text(encoding="utf-8", errors="replace"))
                    out.append({"file": rel, "name": j.get("name"), "scripts": list((j.get("scripts") or {}))[:15],
                                "dependencies": list((j.get("dependencies") or {}))[:60],
                                "devDependencies": list((j.get("devDependencies") or {}))[:40],
                                "installed": (p.parent / "node_modules").is_dir()})
                elif p.name in ("requirements.txt", "pyproject.toml", "composer.json", "go.mod", "Cargo.toml", "pubspec.yaml"):
                    lines = [ln.strip() for ln in p.read_text(encoding="utf-8", errors="replace").splitlines()
                             if ln.strip() and not ln.strip().startswith("#")]
                    out.append({"file": rel, "lines": lines[:40]})
            except (OSError, ValueError):
                continue

    walk(root, 0)
    return out[:12]


def environment(work_root=None) -> dict:
    """The software side of this computer and of the app, so a model never has to guess: where it works, which
    runtimes / CLIs / packages exist, which MCP servers, web search engines, media services, skills, agents and
    commands the app has, and how to get a project from GitHub."""
    from ..config import DATA_DIR, ROOT, load_settings
    from .. import hostinfo
    env: dict = {}
    host = hostinfo.info()
    env["app"] = {"app_folder": str(ROOT), "data_folder": str(DATA_DIR), "app_python": sys.executable,
                  "python_version": platform.python_version(),
                  "pip_rule": "pip install always goes into this app Python (.venv); a project's own venv uses its own pip"}
    if work_root:
        env["working_folder"] = {"path": str(work_root), "note": "relative paths of write_file / read_file / run are "
                                 "resolved here; this is the folder of this chat / project"}
        if manifests := _project_manifests(work_root):
            env["working_folder"]["manifests"] = manifests
    env["shells"] = host.get("shells") or {}
    env["cli_tools_on_path"] = host.get("tools") or {}
    try:
        env["python_packages"] = ", ".join(_python_packages())
    except Exception:  # noqa: BLE001 - optional
        pass
    if g := _npm_globals():
        env["npm_global_packages"] = g
    try:  # MCP servers connected in Settings > MCP and the tools each one offers
        from .. import mcp_client
        env["mcp_servers"] = {k: {"enabled": v["enabled"], "running": v["running"], "error": v["error"],
                                  "tools": [t["name"] for t in v["tools"]][:40]}
                              for k, v in mcp_client.status().items()} or "none connected (mcp_search finds one, mcp_add connects it)"
    except Exception:  # noqa: BLE001
        pass
    try:  # web research: the configured search APIs first, then the free engines, then the real browser
        from . import web
        cfg = load_settings().get("search", {})
        off = set(cfg.get("disabled") or [])
        apis = [n for n, _ in web.api_engines("x")]
        env["web_search"] = {
            "api_engines_with_keys": apis or "none (add keys in Settings > Web research)",
            "free_engines": [e for e in ["duckduckgo", "bing", "wikipedia", "wikidata",
                                         *(f"ddgs-{b}" for b in web.DDGS_BACKENDS)] if e not in off],
            "browser_fallback": "browser-duckduckgo / browser-bing / browser-brave when plain requests are blocked",
            "disabled": sorted(off),
            "tools": "web_search (fast results), research (search + read several pages), fetch_url (one page / file / "
                     "API), web_screenshot, browser_* (act in a real page)"}
    except Exception:  # noqa: BLE001
        pass
    try:  # image / stock photo services that are usable right now (a key, quota left)
        from . import services
        env["media_services"] = {"stock_photos": services.usable("stock"), "image_generation": services.usable("image")}
    except Exception:  # noqa: BLE001
        pass
    env["github"] = {
        "gh_cli": host.get("tools", {}).get("gh") or "not installed (winget install GitHub.cli / brew install gh)",
        "git": host.get("tools", {}).get("git") or "not installed",
        "find": "web_search 'site:github.com <topic>' or fetch_url https://api.github.com/search/repositories?q=<words>"
                "&sort=stars (JSON: full_name, description, stargazers_count, html_url)",
        "download": "git clone https://github.com/<owner>/<repo> (run), or without git: fetch_url "
                    "https://github.com/<owner>/<repo>/archive/refs/heads/<branch>.zip save=<file>.zip, then unzip; "
                    "never read a repository file by file",
        "read_one_file": "fetch_url https://raw.githubusercontent.com/<owner>/<repo>/<branch>/<path>"}
    try:  # what the user can invoke: /skills, @agents
        from ..agents import catalog
        env["skills"] = {k: v.get("title", "") for k, v in catalog.skills().items()}
        env["agents"] = {k: v.get("title", "") for k, v in catalog.agents().items()}
        env["commands"] = "/<skill> runs a skill, @<agent> adds an agent; the use_skill tool loads a skill's instructions"
    except Exception:  # noqa: BLE001
        pass
    try:  # model providers that are switched on, and the chosen model
        s = load_settings()
        env["models"] = {"active": s.get("active_model"),
                         "providers_on": [p for p, c in s.get("providers", {}).items() if c.get("enabled")]}
    except Exception:  # noqa: BLE001
        pass
    return env


def report(part: str = "all", work_root=None) -> str:
    part = (part or "all").lower()
    data: dict = {}
    if part in ("all", "hardware", "hw", "donanım"):
        data["hardware"] = _clean(collect())
    if part in ("all", "software", "sw", "environment", "env", "yazılım"):
        data["software"] = environment(work_root)
    if not data:
        data = {"hardware": _clean(collect()), "software": environment(work_root)}
    return json.dumps(data, ensure_ascii=False, indent=1, default=str)[:30000]


if __name__ == "__main__":  # manual check
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    print(report())
