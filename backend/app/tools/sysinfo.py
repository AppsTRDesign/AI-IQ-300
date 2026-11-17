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


def report() -> str:
    data = _clean(collect())
    return json.dumps(data, ensure_ascii=False, indent=1, default=str)[:12000]


if __name__ == "__main__":  # manual check
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    print(report())
