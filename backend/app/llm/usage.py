"""Model usage, quotas and availability for the multi-model system.

- Every model call is recorded (requests, input/output tokens) in rolling 5-hour and 7-day windows; the window
  resets when its oldest call ages out, so the UI can show "resets at ...".
- Users can set limits per provider (requests/tokens per 5 h and per week): Ollama Cloud, Claude/ChatGPT-style plans
  and free tiers count usage in exactly these windows.
- Quota, rate-limit and auth errors put a model (or its whole provider) on a cooldown until it is usable again,
  taken from the provider's reset headers when present.
- Rate-limit headers (OpenAI/OpenRouter/Groq x-ratelimit-*, Anthropic anthropic-ratelimit-*, retry-after) are kept
  per host to show remaining requests/tokens.
Persisted in data/usage.json so restarts keep the picture."""
from __future__ import annotations

import json
import re
import threading
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

from ..config import DATA_DIR

FILE = DATA_DIR / "usage.json"
WINDOWS = {"5h": 5 * 3600, "week": 7 * 86400}
KEEP = WINDOWS["week"]
_lock = threading.Lock()
_state: dict | None = None
_saved_at = 0.0


def _load() -> dict:
    global _state
    if _state is None:
        try:
            _state = json.loads(FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            _state = {}
        _state.setdefault("calls", {})      # model_id -> [[ts, input, output], ...]
        _state.setdefault("cooldowns", {})  # model_id or "provider:*" -> {until, code, message}
        _state.setdefault("headers", {})    # host -> parsed rate-limit info
    return _state


def _save(force: bool = False) -> None:
    global _saved_at
    if not force and time.time() - _saved_at < 2:
        return
    _saved_at = time.time()
    try:
        FILE.parent.mkdir(parents=True, exist_ok=True)
        FILE.write_text(json.dumps(_state, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def provider_of(model_id: str) -> str:
    return model_id.partition(":")[0]


def record(model_id: str, inp: int = 0, out: int = 0) -> None:
    now = time.time()
    with _lock:
        s = _load()
        calls = [c for c in s["calls"].get(model_id, []) if now - c[0] < KEEP]
        calls.append([round(now, 1), int(inp or 0), int(out or 0)])
        s["calls"][model_id] = calls[-5000:]
        cd = s["cooldowns"]
        # A successful call ends a model's own cooldown, and a provider-wide one.
        for key in (model_id, f"{provider_of(model_id)}:*"):
            cd.pop(key, None)
        _save()


def _next_utc_midnight(now: float) -> float:
    d = datetime.fromtimestamp(now, timezone.utc)
    return (d.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)).timestamp()


def fail(model_id: str, code: str, message: str = "", reset_at: float | None = None) -> None:
    """Remember why a model cannot be used right now and until when."""
    now = time.time()
    if code in ("quota", "payment"):
        if reset_at:
            until = reset_at
        elif re.search(r"per.?day|daily|günlük", message, re.I):
            until = _next_utc_midnight(now)
        else:
            until = now + 3600
        # No balance at all: every model of that provider is out. A daily/free-tier limit ("... add credits to
        # unlock more") is per model, so other models of the same provider may still answer.
        out_of_money = code == "payment" or re.search(r"insufficient|balance|no credits|out of credits|bakiye|"
                                                      r"add usage credits|subscribe", message, re.I)
        key = f"{provider_of(model_id)}:*" if out_of_money else model_id
    elif code == "rate_limit":
        until, key = reset_at or now + 60, model_id
    elif code == "plan_required":  # this model needs a paid plan: other models of the provider still work
        until, key = now + 86400, model_id
    elif code == "auth":
        until, key = now + 86400, f"{provider_of(model_id)}:*"
    elif code in ("overloaded", "unavailable"):
        until, key = reset_at or now + 30, model_id
    else:
        return
    with _lock:
        _load()["cooldowns"][key] = {"until": round(until, 1), "code": code, "message": message[:300]}
        _save(force=True)


def clear(model_id: str | None = None) -> None:
    with _lock:
        s = _load()
        if model_id:
            s["cooldowns"].pop(model_id, None)
            s["cooldowns"].pop(f"{provider_of(model_id)}:*", None)
        else:
            s["cooldowns"].clear()
        _save(force=True)


def cooldown(model_id: str) -> dict | None:
    now = time.time()
    s = _load()
    for key in (model_id, f"{provider_of(model_id)}:*"):
        c = s["cooldowns"].get(key)
        if c and c["until"] > now:
            return {**c, "scope": "provider" if key.endswith(":*") else "model"}
    return None


def window(prefix: str, name: str) -> dict:
    """Usage of a model ('prov:model') or a whole provider ('prov:') in a window, with its reset time."""
    now, span = time.time(), WINDOWS[name]
    s = _load()
    calls = [c for mid, cs in s["calls"].items() if mid == prefix or (prefix.endswith(":") and mid.startswith(prefix))
             for c in cs if now - c[0] < span]
    if not calls:
        return {"requests": 0, "tokens": 0, "reset_at": None}
    return {"requests": len(calls), "tokens": sum(c[1] + c[2] for c in calls),
            "reset_at": round(min(c[0] for c in calls) + span, 1)}


def over_limit(model_id: str, limits: dict) -> str | None:
    """'5h' / 'week' when the provider's own configured limit is used up."""
    lim = limits.get(provider_of(model_id)) or {}
    for name in WINDOWS:
        w = window(provider_of(model_id) + ":", name)
        if lim.get(f"requests_{name}") and w["requests"] >= lim[f"requests_{name}"]:
            return name
        if lim.get(f"tokens_{name}") and w["tokens"] >= lim[f"tokens_{name}"]:
            return name
    return None


def headroom(model_id: str, limits: dict) -> float:
    """0..1, how much of the tightest configured or reported limit is left (1 = unknown/unused)."""
    lim = limits.get(provider_of(model_id)) or {}
    left = [1.0]
    for name in WINDOWS:
        w = window(provider_of(model_id) + ":", name)
        for kind in ("requests", "tokens"):
            if lim.get(f"{kind}_{name}"):
                left.append(max(0.0, 1 - w[kind] / lim[f"{kind}_{name}"]))
    return min(left)


# --- provider rate-limit headers -------------------------------------------------------------------------

def _duration(v: str) -> float | None:
    """'1s', '6m0s', '1h2m3.5s', '20ms', '30' (seconds) or an RFC 3339 time -> seconds from now."""
    v = (v or "").strip()
    if not v:
        return None
    if re.fullmatch(r"\d+(\.\d+)?", v):
        return float(v)
    if m := re.fullmatch(r"(?:(\d+)h)?(?:(\d+)m(?!s))?(?:([\d.]+)s)?(?:(\d+)ms)?", v):
        h, mi, s, ms = m.groups()
        if any(m.groups()):
            return int(h or 0) * 3600 + int(mi or 0) * 60 + float(s or 0) + int(ms or 0) / 1000
    try:
        return datetime.fromisoformat(v.replace("Z", "+00:00")).timestamp() - time.time()
    except ValueError:
        return None


def observe(url: str, headers) -> None:
    """Called for every provider response (httpx event hook)."""
    h = {k.lower(): v for k, v in headers.items() if "ratelimit" in k.lower() or k.lower() == "retry-after"}
    if not h:
        return
    now = time.time()
    info: dict = {"at": round(now, 1)}
    for kind in ("requests", "tokens"):
        limit = h.get(f"x-ratelimit-limit-{kind}") or h.get(f"anthropic-ratelimit-{kind}-limit")
        remaining = h.get(f"x-ratelimit-remaining-{kind}") or h.get(f"anthropic-ratelimit-{kind}-remaining")
        reset = h.get(f"x-ratelimit-reset-{kind}") or h.get(f"anthropic-ratelimit-{kind}-reset")
        if limit or remaining:
            secs = _duration(reset) if reset else None
            info[kind] = {"limit": _num(limit), "remaining": _num(remaining),
                          "reset_at": round(now + secs, 1) if secs is not None else None}
    if (ra := _duration(h.get("retry-after", ""))) is not None:
        info["retry_at"] = round(now + ra, 1)
    host = urlsplit(url).netloc
    with _lock:
        _load()["headers"][host] = info
        _save()


def _num(v) -> int | None:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def reset_hint(url: str) -> float | None:
    """When the last response from this host said the limit resets (for cooldowns after a 429)."""
    info = _load()["headers"].get(urlsplit(url).netloc) or {}
    times = [x.get("reset_at") for x in (info.get("requests"), info.get("tokens")) if x and x.get("remaining") == 0]
    now = time.time()  # an earlier response's reset time that has already passed says nothing about this error
    times = [t for t in times + [info.get("retry_at")] if t and t > now]
    return max(times) if times else None


def snapshot(providers: dict, limits: dict, show: set[str] | None = None) -> dict:
    """Everything the quota screen shows, grouped by provider."""
    s = _load()
    out = {}
    models_by_provider: dict[str, list[str]] = {}
    for mid in s["calls"]:
        models_by_provider.setdefault(provider_of(mid), []).append(mid)
    for pid, cfg in providers.items():
        host = urlsplit(cfg.get("base_url") or "").netloc
        cds = {k: v for k, v in s["cooldowns"].items() if (k == f"{pid}:*" or k.startswith(pid + ":"))
               and v["until"] > time.time()}
        if not (models_by_provider.get(pid) or cds or limits.get(pid) or pid in (show or set())):
            continue
        out[pid] = {
            "name": cfg.get("name", pid), "local": bool(cfg.get("local")),
            "windows": {n: window(pid + ":", n) for n in WINDOWS},
            "limits": limits.get(pid) or {},
            "models": {mid: {n: window(mid, n) for n in WINDOWS} for mid in models_by_provider.get(pid, [])},
            "cooldowns": cds,
            "headers": s["headers"].get(host),
        }
    return out
