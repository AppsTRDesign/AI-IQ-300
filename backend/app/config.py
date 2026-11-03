"""Paths and persisted settings. Secrets are stored backend-only and never returned unmasked."""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get("AIIQ_DATA") or ROOT / "data")  # AIIQ_DATA: separate data dir (tests)
WORKSPACE_DIR = DATA_DIR / "workspace" if os.environ.get("AIIQ_DATA") else ROOT / "workspace"  # tests stay isolated
LANG_DIR = ROOT / "languages"
SKILLS_DIR = ROOT / "skills"
FRONTEND_DIST = ROOT / "frontend" / "dist"
for _d in (DATA_DIR, WORKSPACE_DIR, LANG_DIR, SKILLS_DIR):
    _d.mkdir(parents=True, exist_ok=True)

SETTINGS_FILE = DATA_DIR / "settings.json"
SECRETS_FILE = DATA_DIR / "secrets.json"

# Provider catalog: kind selects the adapter; everything else is user-editable.
DEFAULT_SETTINGS: dict[str, Any] = {
    "language": "tr",
    "permission_mode": "auto",  # ask | auto | full
    "active_model": "",  # empty: the UI picks the first available model
    "vision_model": "",
    "cloud_fallback": False,
    "agent": {"max_iterations": 60, "max_debug_attempts": 5, "command_timeout": 300},
    "allowed_origins": ["http://127.0.0.1:8300", "http://localhost:8300", "http://localhost:5173", "http://127.0.0.1:5173"],
    "context": {"compress_threshold": 80, "num_ctx": {}, "keep_recent": 6},
    "providers": json.loads((Path(__file__).parent / "providers_default.json").read_text(encoding="utf-8")),
}

_lock = threading.Lock()


def _merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in override.items():
        out[k] = _merge(base[k], v) if isinstance(v, dict) and isinstance(base.get(k), dict) else v
    return out


def _read(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _clean(s: dict) -> dict:
    s["providers"] = {k: v for k, v in s["providers"].items() if v}  # None = removed by user
    defaults = DEFAULT_SETTINGS["providers"]
    for pid, cfg in s["providers"].items():
        # Migrate settings saved by older versions: the separate 'evren' adapter became OpenAI-compatible,
        # and an empty URL falls back to the documented default address.
        if cfg.get("kind") == "evren":
            cfg["kind"] = "openai"
            cfg.pop("auth_header", None)
        if not cfg.get("base_url") and pid in defaults:
            cfg["base_url"] = defaults[pid]["base_url"]
    return s


def load_settings() -> dict[str, Any]:
    with _lock:
        return _clean(_merge(DEFAULT_SETTINGS, _read(SETTINGS_FILE)))


def save_settings(patch: dict[str, Any]) -> dict[str, Any]:
    with _lock:
        merged = _merge(_merge(DEFAULT_SETTINGS, _read(SETTINGS_FILE)), patch)
        SETTINGS_FILE.write_text(json.dumps(merged, indent=2, ensure_ascii=False), encoding="utf-8")
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
        SECRETS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def secret_status() -> dict[str, bool]:
    return {k: True for k in _read(SECRETS_FILE)}
