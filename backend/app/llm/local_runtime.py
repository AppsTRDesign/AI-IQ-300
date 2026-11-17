"""Runtime settings of local model servers.

Ollama reads its tuning from environment variables of the server process (OLLAMA_FLASH_ATTENTION, OLLAMA_KV_CACHE_TYPE,
OLLAMA_VULKAN...). They are stored where Ollama itself looks for them:
  - Windows: the user's environment (HKCU\\Environment, same as `setx NAME value` / `reg delete ... /v NAME`);
  - macOS: `launchctl setenv` for the running session, plus data/ollama_env.json;
  - Linux: data/ollama_env.json (applied when AI IQ 300 restarts `ollama serve`; a systemd service needs an override).
"Auto" removes the variable, so Ollama uses its own default. Changes apply after Ollama restarts (button in the UI).

LM Studio has no server-wide variables: its options are load parameters, kept in the provider's "runtime" settings
and sent every time a model is loaded (REST /api/v1/models/load, or the lms CLI for GPU offload and idle TTL).
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import httpx

from ..config import DATA_DIR

ENV_FILE = DATA_DIR / "ollama_env.json"

# name -> allowed values ("" = automatic: the variable is removed). Numbers: allowed range.
OLLAMA_VARS: dict[str, dict] = {
    "OLLAMA_VULKAN": {"values": ["", "1", "0"]},
    "GGML_VK_DISABLE_F16": {"values": ["", "1"]},
    "OLLAMA_FLASH_ATTENTION": {"values": ["", "1", "0"]},
    "OLLAMA_KV_CACHE_TYPE": {"values": ["", "f16", "q8_0", "q4_0"]},
    "OLLAMA_NUM_PARALLEL": {"range": (1, 16)},
    "OLLAMA_MAX_LOADED_MODELS": {"range": (1, 8)},
    "OLLAMA_CONTEXT_LENGTH": {"range": (2048, 262144)},
}

_pending: set[str] = set()  # changed since Ollama was last restarted from here


def _valid(name: str, value) -> str:
    spec = OLLAMA_VARS.get(name)
    if spec is None:
        raise ValueError(f"unknown variable {name}")
    v = "" if value is None else str(value).strip()
    if not v and name == "OLLAMA_NUM_PARALLEL":
        # Default 1: every parallel slot keeps its own context memory (4 slots made a 35B model use more RAM than
        # the computer had). A higher value is the user's own choice.
        return "1"
    if not v:
        return ""
    v = _normal(name, v)
    if "values" in spec:
        if v not in spec["values"]:
            raise ValueError(f"{name} must be one of {', '.join(x or 'auto' for x in spec['values'])}")
        return v
    lo, hi = spec["range"]
    if not v.isdigit() or not lo <= int(v) <= hi:
        raise ValueError(f"{name} must be a number between {lo} and {hi}")
    return v


# ---------------------------------------------------------------- storage
def _file() -> dict:
    try:
        return json.loads(ENV_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _win_get(name: str) -> str:
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
            return str(winreg.QueryValueEx(k, name)[0])
    except OSError:
        return ""


def _win_set(name: str, value: str) -> None:
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_SET_VALUE) as k:
        if value:
            winreg.SetValueEx(k, name, 0, winreg.REG_SZ, value)
        else:
            try:
                winreg.DeleteValue(k, name)
            except FileNotFoundError:
                pass


def _win_broadcast() -> None:
    """Tell running programs (Explorer, the Ollama tray app on its next start) that the environment changed."""
    try:
        import ctypes
        ctypes.windll.user32.SendMessageTimeoutW(0xFFFF, 0x001A, 0, "Environment", 0x0002, 2000, None)
    except Exception:  # noqa: BLE001
        pass


_BOOL = {"true": "1", "yes": "1", "on": "1", "1": "1", "false": "0", "no": "0", "off": "0", "0": "0"}


def _normal(name: str, raw: str) -> str:
    """Values set by hand (setx OLLAMA_VULKAN false) are shown as the matching choice (1 / 0)."""
    v = (raw or "").strip()
    if "1" in OLLAMA_VARS[name].get("values", ()) and v.lower() in _BOOL:
        return _BOOL[v.lower()] if _BOOL[v.lower()] in OLLAMA_VARS[name]["values"] else v
    return v


def read_vars() -> dict[str, str]:
    if sys.platform == "win32":
        return {n: _normal(n, _win_get(n)) for n in OLLAMA_VARS}
    saved = _file()
    return {n: _normal(n, str(saved.get(n, ""))) for n in OLLAMA_VARS}


def write_vars(values: dict) -> dict[str, str]:
    clean = {n: _valid(n, v) for n, v in values.items()}
    current = read_vars()
    changed = {n: v for n, v in clean.items() if current.get(n, "") != v}
    if not changed:
        return current
    if sys.platform == "win32":
        for n, v in changed.items():
            _win_set(n, v)
        _win_broadcast()
    else:
        saved = {**_file(), **changed}
        ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
        ENV_FILE.write_text(json.dumps({k: v for k, v in saved.items() if v}, indent=2), encoding="utf-8")
        if sys.platform == "darwin":
            for n, v in changed.items():
                subprocess.run(["launchctl", "setenv" if v else "unsetenv", n, *([v] if v else [])], check=False)
    for n, v in changed.items():  # programs this app starts (ollama serve) see the new values at once
        if v:
            os.environ[n] = v
        else:
            os.environ.pop(n, None)
    _pending.update(changed)
    return read_vars()


# ---------------------------------------------------------------- the Ollama server
def _ollama_exe() -> tuple[str | None, str | None]:
    """(tray app, cli) paths. The tray app (Windows/macOS) starts the server with the user's environment."""
    app = None
    if sys.platform == "win32":
        p = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama app.exe"
        app = str(p) if p.exists() else None
    elif sys.platform == "darwin" and Path("/Applications/Ollama.app").exists():
        app = "/Applications/Ollama.app"
    return app, shutil.which("ollama")


async def server_info(base_url: str) -> dict:
    out: dict = {"running": False, "version": None, "loaded": []}
    try:
        async with httpx.AsyncClient(timeout=2.5) as c:
            r = await c.get(f"{base_url}/api/version")
            out["running"] = r.status_code < 500
            out["version"] = r.json().get("version")
            ps = (await c.get(f"{base_url}/api/ps")).json().get("models", [])
            # VRAM share tells whether the GPU (Vulkan/ROCm/CUDA) is really used.
            out["loaded"] = [{"name": m["name"], "size": m.get("size") or 0, "vram": m.get("size_vram") or 0,
                              "context": m.get("context_length")} for m in ps]
    except (httpx.HTTPError, ValueError):
        pass
    return out


def _kill_ollama() -> None:
    import psutil
    for p in psutil.process_iter(["name"]):
        name = (p.info.get("name") or "").lower()
        if name.startswith("ollama"):
            try:
                p.terminate()
            except psutil.Error:
                pass
    psutil.wait_procs([p for p in psutil.process_iter(["name"]) if (p.info.get("name") or "").lower().startswith("ollama")],
                      timeout=8)


async def restart_ollama(base_url: str) -> dict:
    """Stop every Ollama process and start it again with the saved variables."""
    app, cli = _ollama_exe()
    if not (app or cli):
        return {"ok": False, "error": "ollama_not_installed"}
    await asyncio.to_thread(_kill_ollama)
    env = {**os.environ, **{k: v for k, v in read_vars().items() if v}}
    for k, v in read_vars().items():
        if not v:
            env.pop(k, None)
    flags = 0
    if sys.platform == "win32":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
    if app and sys.platform == "darwin":
        argv = ["open", "-a", app]
    elif app:
        argv = [app]
    else:
        argv = [cli, "serve"]
    subprocess.Popen(argv, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     creationflags=flags, close_fds=True, start_new_session=sys.platform != "win32")
    t0 = time.monotonic()
    while time.monotonic() - t0 < 30:
        await asyncio.sleep(0.7)
        info = await server_info(base_url)
        if info["running"]:
            _pending.clear()
            return {"ok": True, **info}
    return {"ok": False, "error": "ollama_start_timeout"}


async def ollama_status(base_url: str) -> dict:
    app, cli = _ollama_exe()
    return {"vars": read_vars(), "pending": sorted(_pending), "installed": bool(app or cli),
            "platform": sys.platform, **await server_info(base_url)}


# ---------------------------------------------------------------- LM Studio load options
LMS_KEYS = {"gpu": ("", "max", "off", "0.25", "0.5", "0.75"), "flash_attention": ("", "on", "off"),
            "offload_kv": ("", "on", "off")}
LMS_NUMBERS = {"ttl": (0, 86400), "eval_batch": (32, 8192)}


def clean_lms(runtime: dict) -> dict:
    out: dict = {}
    for k, allowed in LMS_KEYS.items():
        v = str(runtime.get(k) or "")
        if v not in allowed:
            raise ValueError(f"{k} must be one of {', '.join(a or 'auto' for a in allowed)}")
        if v:
            out[k] = v
    for k, (lo, hi) in LMS_NUMBERS.items():
        v = runtime.get(k)
        if v in (None, "", 0):
            continue
        v = int(v)
        if not lo <= v <= hi:
            raise ValueError(f"{k} must be between {lo} and {hi}")
        out[k] = v
    return out


def lms_rest_body(model: str, num_ctx: int | None, rt: dict) -> dict | None:
    """Body for POST /api/v1/models/load, or None when no REST-only option is set (the CLI path is used)."""
    if not any(k in rt for k in ("flash_attention", "offload_kv", "eval_batch")):
        return None
    body: dict = {"model": model}
    if num_ctx:
        body["context_length"] = num_ctx
    if "flash_attention" in rt:
        body["flash_attention"] = rt["flash_attention"] == "on"
    if "offload_kv" in rt:
        body["offload_kv_cache_to_gpu"] = rt["offload_kv"] == "on"
    if "eval_batch" in rt:
        body["eval_batch_size"] = rt["eval_batch"]
    return body


def lms_cli_args(rt: dict) -> list[str]:
    args: list[str] = []
    if rt.get("gpu"):
        args += ["--gpu", rt["gpu"]]
    if rt.get("ttl"):
        args += ["--ttl", str(rt["ttl"])]
    return args
