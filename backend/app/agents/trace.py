"""Agent traces: one JSON-lines file per task, what happened in order, for evaluation and debugging.

chat/<id>/.session/traces/<run_id>.jsonl
  line 1   {"type": "run", run, model, status, request, started, ended, timing, files, commands, error}
  then     {"type": "turn", i, wait_ms, total_ms, in_tokens, out_tokens, tps} one per model request
           {"type": "step", t, ms, kind, tool, title, status, path, error}    one per step, in time order

Written by the app from the task's own records (steps, per-turn timing), never by the model. Long values are cut,
secrets in commands are already redacted in the steps. Writing a trace never fails a task. The last KEEP traces of
a chat are kept.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from .. import sessions

DIR = "traces"
KEEP = 30
_ARG_CHARS = 300


def _dir(session_id: str, create: bool = False) -> Path:
    return sessions.path(session_id, create=create) / DIR


def _short(v):
    if isinstance(v, str):
        return v if len(v) <= _ARG_CHARS else v[:_ARG_CHARS] + f"…(+{len(v) - _ARG_CHARS})"
    if isinstance(v, (int, float, bool)) or v is None:
        return v
    return _short(json.dumps(v, ensure_ascii=False, default=str))


def _first_error(step: dict) -> str:
    if step.get("status") != "error":
        return ""
    text = str((step.get("data") or {}).get("output") or step.get("detail") or "")
    line = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
    return line[:300]


def events(steps: list[dict], perf: dict | None) -> list[dict]:
    out: list[dict] = []
    for i, t in enumerate((perf or {}).get("turns") or []):
        out.append({"type": "turn", "i": i + 1, **{k: (round(t[k]) if isinstance(t.get(k), float) else t.get(k))
                                                   for k in ("wait_ms", "total_ms", "in_tokens", "out_tokens", "tps")
                                                   if k in t}})
    for s in sorted(steps or [], key=lambda s: s.get("t0") or s.get("ts") or 0):
        d = s.get("data") or {}
        ev = {"type": "step", "t": round(s.get("t0") or s.get("ts") or 0, 3), "ms": s.get("ms"), "kind": s.get("kind"),
              "title": _short(str(s.get("title") or "")), "status": s.get("status")}
        if d.get("tool"):
            ev["tool"] = d["tool"]
            args = d.get("args") or {}
            if isinstance(args, dict) and args:
                ev["args"] = {k: _short(v) for k, v in list(args.items())[:8]}
            if d.get("command"):
                ev["command"] = _short(d["command"])
        if s.get("kind") in ("retry", "fallback", "debug", "budget") and s.get("detail"):
            ev["detail"] = _short(str(s["detail"]))
        if err := _first_error(s):
            ev["error"] = err
        out.append(ev)
    return out


def record(session_id: str, run_id: str, *, model: str, status: str, request: str, started: float,
           timing: dict, steps: list[dict], perf: dict | None, files: list[str] | None = None,
           commands: list | None = None, error: str = "") -> Path | None:
    """Writes the task's trace; returns its path (None when it could not be written)."""
    try:
        folder = _dir(session_id, create=True)
        folder.mkdir(parents=True, exist_ok=True)
        head = {"type": "run", "run": run_id, "model": model, "status": status, "request": _short(request or ""),
                "started": round(started, 3), "ended": round(time.time(), 3), "timing": timing or {},
                "files": list(dict.fromkeys(files or []))[:200], "commands": len(commands or []),
                **({"error": error[:500]} if error else {})}
        lines = [head, *events(steps, perf)]
        path = folder / f"{run_id}.jsonl"
        tmp = path.with_suffix(".tmp")
        tmp.write_text("\n".join(json.dumps(x, ensure_ascii=False, default=str) for x in lines) + "\n", encoding="utf-8")
        tmp.replace(path)
        old = sorted(folder.glob("*.jsonl"), key=lambda p: p.stat().st_mtime)[:-KEEP]
        for p in old:
            p.unlink(missing_ok=True)
        return path
    except Exception:  # noqa: BLE001 - a trace never breaks a task
        return None


def load(session_id: str, run_id: str) -> list[dict]:
    path = _dir(session_id) / f"{run_id}.jsonl"
    if not path.is_file():
        return []
    out = []
    for ln in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            out.append(json.loads(ln))
        except ValueError:
            continue
    return out


def time_split(lines: list[dict]) -> dict:
    """Where a task's time went, in seconds, so a slow task shows whether the provider or the work was slow:
    wait_s       until each request's first token: provider queue + reading the prompt (grows with in_tokens)
    gen_s        streaming the answers after the first token (output speed)
    tools_s      running tools;  retry_s  waiting after provider errors;  app_s  the rest (the app's own work)
    max_wait_s   the slowest single wait;  wait_per_1k  wait seconds per 1,000 prompt tokens (median of turns
                 with a known prompt size); a high value with small prompts points at the provider (queue/latency)."""
    head = next((x for x in lines if x.get("type") == "run"), {})
    timing = head.get("timing") or {}
    turns = [x for x in lines if x.get("type") == "turn"]
    s = lambda ms: round((ms or 0) / 1000, 1)  # noqa: E731
    wait = sum(t.get("wait_ms") or 0 for t in turns) if turns else timing.get("model_wait_ms")
    model = sum(t.get("total_ms") or 0 for t in turns) if turns else timing.get("model_ms")
    per_k = sorted((t["wait_ms"] / 1000) / (t["in_tokens"] / 1000) for t in turns
                   if (t.get("in_tokens") or 0) >= 500 and t.get("wait_ms"))
    # Tools of one turn run in parallel: their wall time, not the sum of their durations (four research calls of
    # 20 s each showed 66 s of tools in a 59 s task).
    spans = sorted((x["t"], x["t"] + x["ms"] / 1000) for x in lines
                   if x.get("type") == "step" and x.get("tool") and x.get("t") and x.get("ms"))
    tools_ms, end = timing.get("tools_ms"), None
    if spans:
        wall = 0.0
        for a, b in spans:
            if end is None or a > end:
                wall += b - a
                end = b
            elif b > end:
                wall += b - end
                end = b
        tools_ms = wall * 1000
    return {"wait_s": s(wait), "gen_s": s(max(0, (model or 0) - (wait or 0))), "tools_s": s(tools_ms),
            "retry_s": s(timing.get("retry_ms")), "app_s": s(timing.get("overhead_ms")),
            "max_wait_s": s(max((t.get("wait_ms") or 0 for t in turns), default=timing.get("slowest_wait_ms") or 0)),
            "wait_per_1k": round(per_k[len(per_k) // 2], 2) if per_k else None}


def summary(lines: list[dict]) -> dict:
    """Counts from a trace: turns, tool calls (failed), tokens out, retries, model switches, error kinds."""
    head = next((x for x in lines if x.get("type") == "run"), {})
    steps = [x for x in lines if x.get("type") == "step"]
    tools = [x for x in steps if x.get("tool")]
    errs: dict[str, int] = {}
    for x in tools:
        if x.get("status") == "error":
            errs[x["tool"]] = errs.get(x["tool"], 0) + 1
    timing = head.get("timing") or {}
    return {**time_split(lines),"status": head.get("status"), "model": head.get("model"), "seconds": round((timing.get("total_ms") or 0) / 1000, 1),
            "turns": timing.get("turns") or sum(x.get("type") == "turn" for x in lines),
            "out_tokens": timing.get("out_tokens") or 0, "tool_calls": len(tools),
            "tool_errors": sum(errs.values()), "errors_by_tool": errs,
            "retries": sum(x.get("kind") == "retry" for x in steps),
            "fallbacks": sum(x.get("kind") == "fallback" for x in steps),
            "debug_rounds": sum(x.get("kind") == "debug" for x in steps)}
