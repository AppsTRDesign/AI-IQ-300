"""Keyed image and stock-photo services: which one is used now, and what is left of its quota.

Each kind (image, stock) has an ordered list of services (CATALOG order). A call goes to the first one that is usable:
keyed (or free), switched on in Settings, not blocked and inside its local window. A quota or rate-limit answer (HTTP
429 or 402, or a 403 that names a limit) blocks that service until its reset: the Retry-After or reset header when the
API sends one, otherwise the end of its local window or the next day. The next service is then tried. When none is
left, the system's own free service runs (Pollinations for pictures; Openverse and Wikimedia Commons for photos). The
system's own service is never blocked.

Usage is counted per service (today, this month, the current window); the quota headers are read when present. The
counters live in data/service_usage.json. API keys are never written there (they stay in secrets.json).
"""
from __future__ import annotations

import re
import threading
import time
from datetime import datetime, timedelta
from typing import Awaitable, Callable, TypeVar

from ..config import DATA_DIR, atomic_write, get_secret, load_settings

T = TypeVar("T")


class QuotaError(Exception):
    """The service said no more calls are allowed (quota used up, rate limit): it is blocked until its reset."""

    def __init__(self, message: str, retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after


class ServiceError(Exception):
    """Any other failure (bad key, server error, no result): the next service is tried, nothing is blocked."""


# window_s / window_max: the local cap of a free tier (0 = none: the API's own answer decides). month_max: likewise.
# system: the free service the app keeps for itself; it is the last resort and needs no key.
CATALOG: dict[str, dict] = {
    "pexels": {"kind": "stock", "name": "Pexels", "secret": "pexels_api_key", "window_s": 3600, "window_max": 200, "month_max": 20000},
    "pixabay": {"kind": "stock", "name": "Pixabay", "secret": "pixabay_api_key", "window_s": 60, "window_max": 100, "month_max": 0},
    "unsplash": {"kind": "stock", "name": "Unsplash", "secret": "unsplash_api_key", "window_s": 3600, "window_max": 50, "month_max": 0},
    "gemini": {"kind": "image", "name": "Gemini (image)", "secret": "gemini_api_key"},
    "cloudflare": {"kind": "image", "name": "Cloudflare Workers AI (FLUX)", "secret": "cloudflare_api_key"},
    "huggingface": {"kind": "image", "name": "Hugging Face (FLUX)", "secret": "huggingface_api_key"},
    "together": {"kind": "image", "name": "Together AI (FLUX)", "secret": "together_api_key"},
    "openai": {"kind": "image", "name": "OpenAI (gpt-image-1)", "secret": "openai_api_key"},
    "stability": {"kind": "image", "name": "Stability AI", "secret": "stability_api_key"},
    "pollinations": {"kind": "image", "name": "Pollinations (FLUX)", "secret": "pollinations_token", "system": True},
    "openverse": {"kind": "stock", "name": "Openverse", "system": True},
    "commons": {"kind": "stock", "name": "Wikimedia Commons", "system": True},
    # Image-to-video: paid keyed services first (in this order), then the free Hugging Face GPU Spaces. Each one can
    # be switched off in Settings; the first usable one makes the clip and the next is tried only if it fails.
    "veo": {"kind": "video", "name": "Google Veo (Gemini API)", "secret": "gemini_api_key"},
    "fal": {"kind": "video", "name": "fal.ai (Wan · Kling · Hailuo · Seedance · Veo)", "secret": "fal_api_key"},
    "replicate": {"kind": "video", "name": "Replicate (Wan · Kling · Hailuo · Seedance)", "secret": "replicate_api_key"},
    "runway": {"kind": "video", "name": "Runway (Gen-4 Turbo)", "secret": "runway_api_key"},
    "hf_wan": {"kind": "video", "name": "Wan 2.2 (Hugging Face, free)", "free": True,
               "space": "zerogpu-aoti/wan2-2-fp8da-aoti-faster", "call": "wan"},
    "hf_wan2": {"kind": "video", "name": "Wan 2.2 Lightning (Hugging Face, free)", "free": True,
                "space": "Saravutw/WAN2.2_I2V_LIGHTNING_4-8step_custom", "call": "wan"},
    "hf_svd": {"kind": "video", "name": "AnimateLCM-SVD (Hugging Face, free)", "free": True,
               "space": "wangfuyun/AnimateLCM-SVD", "call": "svd"},
}
# where the on/off switches live (media.disabled, stock.disabled, video.disabled)
SETTINGS_SECTION = {"image": "media", "stock": "stock", "video": "video"}
RETRY_429 = 900  # seconds a 429 without a reset header blocks a service
_LOCK = threading.Lock()
_STATE: dict[str, dict] = {}
_LOADED = False
_QUOTA_WORDS = re.compile(r"limit|quota|exceed|credit|billing|balance|too many|rate", re.I)


def _path():
    return DATA_DIR / "service_usage.json"


def _load() -> None:
    global _LOADED
    if _LOADED:
        return
    _LOADED = True
    import json
    try:
        _STATE.update(json.loads(_path().read_text(encoding="utf-8")))
    except (OSError, ValueError):
        pass


def _save() -> None:
    import json
    try:
        atomic_write(_path(), json.dumps(_STATE, ensure_ascii=False, indent=1))
    except OSError:
        pass  # a counter that cannot be written costs nothing but the next restart's history


def _entry(sid: str) -> dict:
    """The counters of one service, rolled over to today and this month."""
    _load()
    now = datetime.now()
    e = _STATE.setdefault(sid, {"today": 0, "day": "", "month_n": 0, "month": "", "window": [],
                                "blocked_until": 0.0, "reason": "", "remaining": None, "limit": None,
                                "last_error": "", "last_ok": 0.0})
    if e["day"] != now.strftime("%Y-%m-%d"):
        e["day"], e["today"] = now.strftime("%Y-%m-%d"), 0
    if e["month"] != now.strftime("%Y-%m"):
        e["month"], e["month_n"] = now.strftime("%Y-%m"), 0
    return e


def _disabled(kind: str) -> set[str]:
    return set((load_settings().get(SETTINGS_SECTION[kind]) or {}).get("disabled") or [])


def _window_wait(sid: str, now: float) -> float:
    """Seconds until this service may be called again inside its local window or month (0 = now)."""
    spec = CATALOG[sid]
    e = _entry(sid)
    wait = 0.0
    if spec.get("window_max"):
        e["window"] = [t for t in e["window"] if now - t < spec["window_s"]]
        if len(e["window"]) >= spec["window_max"]:
            wait = max(wait, spec["window_s"] - (now - e["window"][0]))
    if spec.get("month_max") and e["month_n"] >= spec["month_max"]:
        nxt = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        nxt = (nxt + timedelta(days=32)).replace(day=1)
        wait = max(wait, nxt.timestamp() - now)
    return wait


def has_key(sid: str) -> bool:
    spec = CATALOG[sid]
    if spec.get("system") and not spec.get("secret"):
        return True
    if not spec.get("secret"):
        return True
    return bool(get_secret(spec["secret"]))


def ordered(kind: str) -> list[str]:
    """The user-facing services of a kind, in priority order (system services excluded)."""
    return [sid for sid, s in CATALOG.items() if s["kind"] == kind and not s.get("system")]


def usable(kind: str) -> list[str]:
    """Services that may be called now: keyed, switched on, not blocked, inside their local window."""
    now = time.time()
    off = _disabled(kind)
    out = []
    for sid in ordered(kind):
        if sid in off or not has_key(sid):
            continue
        if _entry(sid)["blocked_until"] > now:
            continue
        if _window_wait(sid, now) > 0:
            continue
        out.append(sid)
    return out


def _block(sid: str, seconds: float | None, reason: str) -> None:
    now = time.time()
    if seconds is None or seconds <= 0:
        # no reset time from the API: a 429 waits a while, anything else (quota used up) waits until tomorrow
        if RETRY_429 and re.search(r"429|too many|rate", reason, re.I):
            seconds = RETRY_429
        else:
            tomorrow = (datetime.now() + timedelta(days=1)).replace(hour=0, minute=5, second=0, microsecond=0)
            seconds = tomorrow.timestamp() - now
    e = _entry(sid)
    e["blocked_until"] = now + seconds
    e["reason"] = reason[:200]
    e["last_error"] = reason[:200]
    _save()


def note_headers(sid: str, headers) -> None:
    """Quota figures the API sends with a successful answer (Pexels, Unsplash: X-Ratelimit-*)."""
    try:
        rem = headers.get("X-Ratelimit-Remaining")
        lim = headers.get("X-Ratelimit-Limit")
        if rem is not None or lim is not None:
            e = _entry(sid)
            if rem is not None:
                e["remaining"] = int(float(rem))
            if lim is not None:
                e["limit"] = int(float(lim))
            _save()
    except (TypeError, ValueError):
        pass


def check(sid: str, r) -> None:
    """Raises QuotaError / ServiceError for an HTTP answer that is not a success (call it on every response)."""
    if r.status_code < 400:
        note_headers(sid, r.headers)
        return
    from ..llm.providers import message_of  # the sentence inside the JSON, never the JSON itself
    text = (message_of((r.text or "")[:4000]) or (r.text or ""))[:300]
    retry = None
    for h in ("Retry-After", "X-Ratelimit-Reset"):
        if (v := r.headers.get(h)):
            try:
                retry = float(v) if h == "Retry-After" else max(0.0, float(v) - time.time())
            except ValueError:
                pass
            break
    if r.status_code in (429, 402) or (r.status_code == 403 and _QUOTA_WORDS.search(text)):
        raise QuotaError(f"HTTP {r.status_code}: {text}", retry)
    raise ServiceError(f"HTTP {r.status_code}: {text}")


async def call(sid: str, fn: Callable[[], Awaitable[T]]) -> T:
    """Runs one service's call and records it. A quota answer blocks the service; any failure raises ServiceError."""
    wait = _window_wait(sid, time.time())
    if wait > 0:
        raise QuotaError(f"{CATALOG[sid]['name']}: local limit reached, free again in {int(wait)} s", wait)
    try:
        out = await fn()
    except QuotaError as e:
        _block(sid, e.retry_after, str(e))
        raise
    except ServiceError as e:
        _entry(sid)["last_error"] = str(e)[:200]
        _save()
        raise
    except Exception as e:  # timeouts, network: the service is not blocked, the next one is tried
        msg = f"{type(e).__name__}: {str(e)[:160]}"
        _entry(sid)["last_error"] = msg
        _save()
        raise ServiceError(msg) from e
    e = _entry(sid)
    e["today"] += 1
    e["month_n"] += 1
    e["window"].append(time.time())
    e["last_ok"] = time.time()
    e["last_error"] = ""
    _save()
    return out


async def run(kind: str, make: Callable[[str], Awaitable[T]], system: Callable[[], Awaitable[T]], system_id: str,
              ) -> tuple[T, str]:
    """Tries the usable services of a kind in order, then the system's own. Returns (result, service id used)."""
    tried: list[str] = []
    for sid in usable(kind):
        try:
            return await call(sid, lambda sid=sid: make(sid)), sid
        except (QuotaError, ServiceError) as e:
            tried.append(f"{CATALOG[sid]['name']}: {str(e)[:140]}")
    try:
        return await system(), system_id
    except Exception as e:
        tried.append(f"{CATALOG[system_id]['name']}: {str(e)[:140]}")
        raise RuntimeError("; ".join(tried)) from e


def _model_of(kind: str, sid: str) -> str:
    from . import mediamodels
    return mediamodels.current_sync(kind, sid) if sid in mediamodels.MODELS.get(kind, {}) else ""


def status() -> list[dict]:
    """Settings view: every user-facing service with its key, switch, block and counters."""
    now = time.time()
    out = []
    for sid in ordered("image") + ordered("stock") + ordered("video"):
        spec = CATALOG[sid]
        e = _entry(sid)
        blocked = e["blocked_until"] > now
        window_used = len([t for t in e["window"] if now - t < spec.get("window_s", 0)]) if spec.get("window_max") else None
        until = datetime.fromtimestamp(e["blocked_until"]).strftime("%H:%M %d.%m") if blocked else ""
        out.append({"id": sid, "kind": spec["kind"], "name": spec["name"], "keyed": has_key(sid),
                    "enabled": sid not in _disabled(spec["kind"]), "blocked": blocked, "blocked_until": until,
                    "reason": e["reason"] if blocked else "", "today": e["today"], "month": e["month_n"],
                    "window_used": window_used, "window_max": spec.get("window_max") or None,
                    "month_max": spec.get("month_max") or None, "remaining": e["remaining"], "limit": e["limit"],
                    "last_error": e["last_error"], "last_ok": e["last_ok"], "free": bool(spec.get("free")),
                    "model": _model_of(spec["kind"], sid),
                    "active": sid in usable(spec["kind"])})
    return out
