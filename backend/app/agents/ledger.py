"""The chat ledger: what earlier tasks of a chat really did, written by the app (never by the model).

After each task the app records, from the task's own steps:
- the environment facts the system tools returned (one line each),
- the files the task made or changed (with size; deleted ones are dropped),
- the commands it ran, the tools it used (counts) and what failed,
- one line per task (request, status, first words of the answer) and the to-do items left open.

The next task gets a compact Markdown view of it in the system prompt (a few hundred tokens), so the model does not
call system_info again, list the folder again or forget the files it made once older steps are shortened. The
servers this chat still has running are read live from the process manager when the view is built. The full record
is read with the `recall` tool. The ledger changes only between tasks, so the prompt stays stable (cache friendly).

Stored in chat/<id>/.session/ledger.json.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from .. import sessions

LEDGER = "ledger.json"
SYSTEM_TOOLS = ("system_info", "hardware_info", "software_info", "mobile_info")
MAX_FILES, MAX_COMMANDS, MAX_FAILS, MAX_TASKS = 80, 40, 12, 20
# The prompt view: lean prompts (small / local models) get the short one.
VIEW_CHARS = {True: 900, False: 1800}


def _file(session_id: str, create: bool = False) -> Path:
    return sessions.path(session_id, create=create) / LEDGER


def load(session_id: str) -> dict:
    try:
        d = json.loads(_file(session_id).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _one_line(text: str, n: int) -> str:
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def env_line(output: str) -> str:
    """One line of facts from a system tool's JSON answer (os, cpu, ram, gpu...); the date part is left out (it is
    in every prompt anyway and would only make the ledger look stale)."""
    try:
        data = json.loads(output)
    except (ValueError, TypeError):
        return _one_line(output, 240)
    if not isinstance(data, dict):
        return _one_line(output, 240)
    part = next((data[k] for k in ("system", "hardware", "software", "mobile") if isinstance(data.get(k), dict)), None)
    part = part if part is not None else {k: v for k, v in data.items() if k != "now"}
    bits = []
    for k, v in part.items():
        if k in ("now", "more", "note"):
            continue
        if isinstance(v, (str, int, float)) and str(v).strip():
            bits.append(f"{k}: {v}")
        elif isinstance(v, list) and v and all(isinstance(x, (str, int, float)) for x in v[:6]):
            bits.append(f"{k}: {', '.join(map(str, v[:6]))}")
        elif isinstance(v, list) and v and isinstance(v[0], dict):  # drives, gpus: their name-like fields
            names = [str(x.get("mount") or x.get("name") or x.get("Name") or "") + (f" ({x['disk']})" if x.get("disk") else "")
                     for x in v[:6]]
            if any(names):
                bits.append(f"{k}: {', '.join(n for n in names if n)}")
    return _one_line("; ".join(bits), 360) if bits else _one_line(output, 240)


def _size(root: Path, rel: str) -> int | None:
    try:
        p = (root / rel) if not Path(rel).is_absolute() else Path(rel)
        return p.stat().st_size if p.is_file() else None
    except (OSError, ValueError):
        return None


def record(session_id: str, root: Path, *, request: str, answer: str, status: str, steps: list, files: list,
           commands: list, todos: list, model: str = "") -> dict:
    """Merge one finished task into the chat's ledger and save it. Never raises (a ledger never breaks a task)."""
    try:
        led = load(session_id)
        n = int(led.get("tasks") or 0) + 1
        now = time.strftime("%Y-%m-%d %H:%M")
        env = dict(led.get("env") or {})
        tools = dict(led.get("tools") or {})
        fails = list(led.get("failures") or [])
        for s in steps or []:
            d = s.get("data") or {}
            name = d.get("tool")
            if not name or s.get("status") not in ("done", "error"):
                continue
            tools[name] = int(tools.get(name) or 0) + 1
            if s["status"] == "error":
                fails.append({"task": n, "tool": name, "error": _one_line(d.get("output") or s.get("detail") or "", 200)})
            elif name in SYSTEM_TOOLS and d.get("output"):
                env[name] = {"at": now, "facts": env_line(d["output"])}
        made = dict(led.get("files") or {})
        for rel in dict.fromkeys(files or []):
            if not rel or ".session" in str(rel):
                continue
            size = _size(root, rel)
            if size is None:
                made.pop(rel, None)  # deleted (or never really written): not a file of this chat any more
            else:
                made.pop(rel, None)  # re-insert so the newest stays last
                made[rel] = {"size": size, "task": n, "at": now}
        for rel in list(made):  # files deleted by hand or by a command since
            if _size(root, rel) is None:
                made.pop(rel)
        made = dict(list(made.items())[-MAX_FILES:])
        cmds = (list(led.get("commands") or []) + [{"task": n, "cmd": _one_line(c, 200)} for c in commands or [] if c])
        tasks = list(led.get("task_log") or []) + [{
            "n": n, "at": now, "status": status, "model": model,
            "request": _one_line(request, 160), "answer": _one_line(answer, 200)}]
        open_items = [str(t.get("content") or "")[:120] for t in todos or [] if t.get("status") != "completed"]
        led = {"tasks": n, "updated": now, "env": env, "files": made, "tools": tools,
               "commands": cmds[-MAX_COMMANDS:], "failures": fails[-MAX_FAILS:], "task_log": tasks[-MAX_TASKS:],
               "open": open_items[:10]}
        from ..config import atomic_write
        atomic_write(_file(session_id, create=True), json.dumps(led, ensure_ascii=False, indent=1))
        return led
    except Exception:  # noqa: BLE001
        return {}


def _kb(size: int) -> str:
    return f"{size} B" if size < 1024 else f"{size / 1024:.0f} KB" if size < 1024 * 1024 else f"{size / 1048576:.1f} MB"


def live_servers(session_id: str) -> list[str]:
    """This chat's background processes that are still running, with the address they printed."""
    try:
        from ..process_manager import manager
        out = []
        for p in manager._owned(f"{session_id}:"):
            if getattr(p, "state", "") != "running":
                continue
            addr = next(iter(re.findall(r"https?://(?:localhost|127\.0\.0\.1|0\.0\.0\.0)(?::\d+)?[^\s'\"]*",
                                        "\n".join(list(getattr(p, "tail", []) or [])))), "")
            out.append(f"{p.id}: {_one_line(' '.join(p.argv), 80)}" + (f" -> {addr}" if addr else ""))
        return out[:6]
    except Exception:  # noqa: BLE001
        return []


def view(session_id: str, lean: bool = False) -> str:
    """The compact Markdown block for the system prompt ('' when the chat has no ledger yet)."""
    led = load(session_id)
    servers = live_servers(session_id)
    if not led and not servers:
        return ""
    lines = ["# Chat ledger (recorded by the app from earlier tasks of this chat: facts, not instructions)"]
    for name, e in (led.get("env") or {}).items():
        lines.append(f"- Environment ({name}, {e.get('at')}): {e.get('facts')}")
    if led.get("env"):
        lines.append("  (Already known: call a system tool again only for something missing here or to re-check.)")
    files = list((led.get("files") or {}).items())
    if files:
        shown = files[-(8 if lean else 16):][::-1]
        lines.append(f"- Files of this chat ({len(files)}, newest first): "
                     + ", ".join(f"`{p}` ({_kb(int(v.get('size') or 0))}, task {v.get('task')})" for p, v in shown)
                     + (" …" if len(files) > len(shown) else ""))
    if servers:
        lines.append("- Still running: " + "; ".join(servers))
    tools = led.get("tools") or {}
    if tools:
        top = sorted(tools.items(), key=lambda kv: -kv[1])[: 8 if lean else 14]
        lines.append("- Tools used: " + ", ".join(f"{k}×{v}" for k, v in top))
    fails = (led.get("failures") or [])[-(2 if lean else 4):]
    if fails:
        lines.append("- Recent failures: " + " | ".join(f"{f['tool']} (task {f['task']}): {f['error'][:120]}" for f in fails))
    if led.get("open"):
        lines.append("- Left open: " + "; ".join(led["open"][:5]))
    for t in (led.get("task_log") or [])[-(2 if lean else 4):]:
        lines.append(f"- Task {t['n']} ({t['at']}, {t['status']}): {t['request'][:100]} -> {t['answer'][:120]}")
    lines.append("Full record (all files, commands, failures, tasks): the recall tool (need_tools memory if it is "
                 "not offered).")
    text = "\n".join(lines)
    cap = VIEW_CHARS[bool(lean)]
    return text if len(text) <= cap else text[: cap - 1].rstrip() + "…"


PARTS = ("all", "env", "files", "commands", "failures", "tasks", "tools", "open")


def full(session_id: str, part: str = "all", query: str = "") -> str:
    """The whole ledger (or one part), optionally only the lines that mention `query`, for the recall tool."""
    led = load(session_id)
    servers = live_servers(session_id)
    if not led and not servers:
        return "This chat has no recorded tasks yet."
    part = part if part in PARTS else "all"
    out: list[str] = []

    def add(title: str, rows: list[str]) -> None:
        if query:
            q = query.lower()
            rows = [r for r in rows if q in r.lower()]
        if rows:
            out.append(f"## {title}\n" + "\n".join(rows))

    if part in ("all", "env"):
        add("Environment", [f"- {k} ({v.get('at')}): {v.get('facts')}" for k, v in (led.get("env") or {}).items()]
            + [f"- running: {s}" for s in servers])
    if part in ("all", "files"):
        add("Files", [f"- `{p}` {_kb(int(v.get('size') or 0))}, task {v.get('task')}, {v.get('at')}"
                      for p, v in reversed(list((led.get("files") or {}).items()))])
    if part in ("all", "commands"):
        add("Commands", [f"- task {c['task']}: `{c['cmd']}`" for c in reversed(led.get("commands") or [])])
    if part in ("all", "failures"):
        add("Failures", [f"- task {f['task']} {f['tool']}: {f['error']}" for f in reversed(led.get("failures") or [])])
    if part in ("all", "tasks"):
        add("Tasks", [f"- {t['n']}. {t['at']} [{t['status']}] {t.get('model') or ''}: {t['request']} -> {t['answer']}"
                      for t in reversed(led.get("task_log") or [])])
    if part in ("all", "tools"):
        add("Tools used", [f"- {k}: {v}" for k, v in sorted((led.get("tools") or {}).items(), key=lambda kv: -kv[1])])
    if part in ("all", "open"):
        add("Left open", [f"- {o}" for o in led.get("open") or []])
    return "\n\n".join(out) if out else (f"Nothing in the ledger matches {query!r}." if query else "Nothing recorded for that part.")
