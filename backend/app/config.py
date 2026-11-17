"""Paths and persisted settings. Secrets are stored backend-only and never returned unmasked."""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get("AIIQ_DATA") or ROOT / "data")  # AIIQ_DATA: separate data dir (tests)
# Old layout (before v0.10.3): only read once to move its files into chat/ (see workspace.migrate_layout).
WORKSPACE_DIR = DATA_DIR / "workspace" if os.environ.get("AIIQ_DATA") else ROOT / "workspace"
LANG_DIR = ROOT / "languages"
SKILLS_DIR = ROOT / "skills"
FRONTEND_DIST = ROOT / "frontend" / "dist"
for _d in (DATA_DIR, LANG_DIR, SKILLS_DIR):
    _d.mkdir(parents=True, exist_ok=True)

SETTINGS_FILE = DATA_DIR / "settings.json"
try:  # the single source of the app version (set_version.py writes it everywhere else)
    VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
except OSError:
    VERSION = "0.0.0"
SECRETS_FILE = DATA_DIR / "secrets.json"

# Provider catalog: kind selects the adapter; everything else is user-editable.
DEFAULT_SETTINGS: dict[str, Any] = {
    "language": "tr",
    "permission_mode": "auto",  # ask | auto | full
    "active_model": "",  # empty: the UI picks the first available model
    "vision_model": "",
    "cloud_fallback": False,
    # server_ttl_minutes: servers the agent started (start tool) and left running are stopped this long after the
    # task ends (0 = never).
    # stream_timeout: seconds a cloud model may stay silent mid-answer (also while it writes a tool call) before the
    # request counts as stalled and is retried; first_token_timeout: the wait for the first token (a long prompt is
    # read first); local_stream_timeout: the same for local servers (0 = no limit, CPU models are slow);
    # provider_retries: retries of a stalled/busy request before the task stops (the work done so far is kept).
    "agent": {"max_iterations": 60, "max_debug_attempts": 5, "command_timeout": 300, "server_ttl_minutes": 10,
              "stream_timeout": 300, "first_token_timeout": 300, "local_stream_timeout": 0, "provider_retries": 5,
              # parallel_tools: independent read/lookup calls of one turn run at the same time; unlimited_*: no step /
              # debug-attempt cap (identical repeated failures still stop the loop).
              "parallel_tools": True, "unlimited_iterations": False, "unlimited_debug": False,
              # split_write_chars: files longer than this are written in parts (0 = never: one call, however large)
              "split_write_chars": 0,
              # prompt_mode: how much the first request carries. "auto" = the lean prompt for local models, small
              # windows and models measured as slow, the full one otherwise; "lean" / "full" force one.
              "prompt_mode": "auto"},
    # RAM / VRAM guard for local models (llm/memguard.py). Under pressure the app frees its own caches, unloads
    # unused models and makes the window of the model in use smaller - the model itself stays loaded. Only with
    # emergency_unload does it unload the model in use as the very last step (the task keeps its checkpoint).
    # low / critical: free memory in percent of the total (kept inside absolute bounds, see memguard.limits).
    "local_guard": {"enabled": True, "emergency_unload": False, "low": 12, "critical": 6},
    # Browser agent (browser_* tools): a real, visible Chromium window with its own lasting profile, so sign-ins
    # the user makes in it stay for later tasks. channel: "" (bundled Chromium), "chrome" or "msedge".
    "browser": {"visible": True, "channel": "", "dismiss_popups": True},
    "allowed_origins": ["http://127.0.0.1:8300", "http://localhost:8300", "http://localhost:5173", "http://127.0.0.1:5173"],
    "context": {"compress_threshold": 80, "num_ctx": {}, "keep_recent": 6},
    # Web research: IDs the search APIs need besides their keys (keys live in secrets.json), and engines switched off.
    "search": {"google_cx": "", "yandex_folder": "", "searxng_url": "", "disabled": []},
    "maps": {"disabled": []},  # place search providers switched off (google, yandex, osm)
    "media": {"disabled": []},  # image generation services switched off (pollinations)
    "fallback_model": "",  # cloud_fallback: the model used when the selected provider cannot be reached
    # Multi-model (cloud only): pool [{model, tags}], per-agent models, per-provider 5 h / weekly limits.
    "rules": "",  # global rules: added to every chat (project rules live in <project>/AIIQ.md)
    "multi_model": {"enabled": False, "auto_switch": True, "delegate": True, "prefer_fast": True, "pool": [], "agents": {}, "limits": {}},
    # Model profiles: per-model overrides {model_id: {thinking, vision, streaming, tools, temperature, max_tokens}}.
    "model_profiles": {},
    # MCP servers: {id: {name, transport: stdio|http, command, args, env, cwd, url, headers, enabled}}
    "mcp_servers": {},
    "providers": json.loads((Path(__file__).parent / "providers_default.json").read_text(encoding="utf-8")),
}

_lock = threading.Lock()


def _merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in override.items():
        out[k] = _merge(base[k], v) if isinstance(v, dict) and isinstance(base.get(k), dict) else v
    return out


_FILES: dict[str, tuple[tuple, str]] = {}  # path -> ((mtime_ns, size), text): a file is read again only when it changed


def _read(path: Path) -> dict:
    """The parsed JSON file. Settings and secrets are asked for many times per second while a task streams (every
    model turn, every step, every tool result): the text is kept until the file changes on disk, so that costs one
    stat() instead of a read. A fresh dict is returned every time (callers may change it)."""
    try:
        st = path.stat()
        sig = (st.st_mtime_ns, st.st_size)
        hit = _FILES.get(str(path))
        if not hit or hit[0] != sig:
            hit = _FILES[str(path)] = (sig, path.read_text(encoding="utf-8"))
        return json.loads(hit[1])
    except (OSError, json.JSONDecodeError):
        return {}


def _clean(s: dict) -> dict:
    s["providers"] = {k: v for k, v in s["providers"].items() if v}  # None = removed by user
    s["model_profiles"] = {k: v for k, v in (s.get("model_profiles") or {}).items() if v}
    s["mcp_servers"] = {k: v for k, v in (s.get("mcp_servers") or {}).items() if v}
    defaults = DEFAULT_SETTINGS["providers"]
    for pid, cfg in s["providers"].items():
        # Migrate settings saved by older versions: the separate 'evren' adapter became OpenAI-compatible,
        # and an empty URL falls back to the documented default address.
        if cfg.get("kind") == "evren":
            cfg["kind"] = "openai"
            cfg.pop("auth_header", None)
        if not cfg.get("base_url") and defaults.get(pid, {}).get("base_url"):  # Cloudflare has no fixed URL
            cfg["base_url"] = defaults[pid]["base_url"]
    return s


def load_settings() -> dict[str, Any]:
    with _lock:
        return _clean(_merge(DEFAULT_SETTINGS, _read(SETTINGS_FILE)))


def atomic_write(path: Path, text: str) -> None:
    """Write to a temporary file, flush it to disk, then swap it in: a crash or power cut mid-write (a blue screen
    once left VERSION as 8 zero bytes) keeps the old file instead of an empty or zeroed one."""
    import os
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    _FILES.pop(str(path), None)


def save_settings(patch: dict[str, Any]) -> dict[str, Any]:
    with _lock:
        merged = _merge(_merge(DEFAULT_SETTINGS, _read(SETTINGS_FILE)), patch)
        atomic_write(SETTINGS_FILE, json.dumps(merged, indent=2, ensure_ascii=False))
        return _clean(merged)


def get_secret(name: str) -> str | None:
    return _read(SECRETS_FILE).get(name) or None


def set_secret(name: str, value: str | None) -> None:
    with _lock:
        data = _read(SECRETS_FILE)
        if value:
            data[name] = value
        else:
            data.pop(name, None)
        atomic_write(SECRETS_FILE, json.dumps(data, indent=2))


def secret_status() -> dict[str, bool]:
    return {k: True for k in _read(SECRETS_FILE)}


_SECRET_VALUES: tuple[float, list[str]] = (-1.0, [])


def redact(text: str) -> str:
    """Saved API keys and tokens never leave the app through tool output (a command that prints secrets.json, an
    env dump, a page echoing a header): each stored value is replaced before the text reaches a model or the chat."""
    global _SECRET_VALUES
    if not text:
        return text
    try:
        mtime = SECRETS_FILE.stat().st_mtime
    except OSError:
        return text
    if mtime != _SECRET_VALUES[0]:
        values = [str(v) for v in _read(SECRETS_FILE).values() if isinstance(v, str) and len(v) >= 8]
        _SECRET_VALUES = (mtime, sorted(set(values), key=len, reverse=True))
    for v in _SECRET_VALUES[1]:
        if v in text:
            text = text.replace(v, "[secret hidden]")
    return text
