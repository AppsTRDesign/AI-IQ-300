"""Per-model track record: tasks, failures, how fast the first token comes and how long a model turn takes.
Kept in data/model_stats.json; shown in Settings > Models and used by the pool to prefer fast, reliable models."""
from __future__ import annotations

import json
import threading
import time

_LOCK = threading.Lock()
_STATS: dict[str, dict] = {}
_FILE = None
_DIRTY = 0


def _file():
    global _FILE
    if _FILE is None:
        from ..config import DATA_DIR
        _FILE = DATA_DIR / "model_stats.json"
        try:
            data = json.loads(_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                _STATS.update({k: v for k, v in data.items() if isinstance(v, dict)})
        except (OSError, ValueError):
            pass
    return _FILE


def _ema(old: float | None, new: float | None, w: float = 0.3) -> float | None:
    if new is None or new <= 0:
        return old
    return round(new if old is None else old * (1 - w) + new * w, 1)


def record(model: str, status: str, first_ms: float | None = None, turn_ms: float | None = None,
           error: str = "") -> None:
    """One finished task (or one failure that moved the task to another model: status 'switched')."""
    global _DIRTY
    if not model or model == "?":
        return
    _file()
    with _LOCK:
        s = _STATS.setdefault(model, {"tasks": 0, "ok": 0, "failed": 0, "first_ms": None, "turn_ms": None})
        s["tasks"] += 1
        if status == "ok":
            s["ok"] += 1
        elif status in ("error", "switched", "stalled"):
            s["failed"] += 1
            s["last_error"] = error[:160]
        s["first_ms"] = _ema(s.get("first_ms"), first_ms)
        s["turn_ms"] = _ema(s.get("turn_ms"), turn_ms)
        s["last"] = time.time()
        _DIRTY += 1
        if _DIRTY >= 3 or s["tasks"] <= 3:
            _save()


def _save() -> None:
    global _DIRTY
    try:
        from ..config import atomic_write
        atomic_write(_file(), json.dumps(_STATS, indent=1))
        _DIRTY = 0
    except OSError:
        pass


def flush() -> None:
    with _LOCK:
        if _DIRTY:
            _save()


def fail_rate(model: str) -> float:
    _file()
    s = _STATS.get(model) or {}
    n = s.get("tasks") or 0
    return (s.get("failed") or 0) / n if n >= 3 else 0.0


def rank_key(model: str) -> tuple[int, int]:
    """(reliability bucket, speed bucket) - smaller is better; unknown models sit in the middle, so new ones get tried."""
    _file()
    s = _STATS.get(model) or {}
    if (s.get("tasks") or 0) < 3:
        return 1, 3
    fr = fail_rate(model)
    first = s.get("first_ms") or 4000
    return (0 if fr < 0.15 else 1 if fr < 0.4 else 2), min(8, int(first // 1500))


def all_stats() -> dict:
    _file()
    with _LOCK:
        out = {}
        for m, s in _STATS.items():
            n = s.get("tasks") or 0
            out[m] = {**s, "fail_pct": round(100 * (s.get("failed") or 0) / n) if n else 0}
        return out


def reset(model: str | None = None) -> None:
    with _LOCK:
        if model:
            _STATS.pop(model, None)
        else:
            _STATS.clear()
        _save()
