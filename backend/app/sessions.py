"""Per-chat session folders: chat/<session_id>-session/

  session.json       metadata (title, project, model, compression stats)
  messages.jsonl     append-only transcript archive
  summary.md         every context compression (what was summarized, when, token savings)
  PROJECT_STATE.md   the chat's working state (last task, changed files, commands, tree)
  uploads/ scripts/ screenshots/

The SQLite DB stays the query index; these files are the durable, human-readable session record.
Deleting a chat deletes its folder completely."""
from __future__ import annotations

import json
import re
import shutil
import time
from pathlib import Path

import os

from .config import DATA_DIR, ROOT

# chat/ lives next to the app; a separate AIIQ_DATA (tests, portable installs) keeps its chats with its data.
CHAT_DIR = DATA_DIR / "chat" if os.environ.get("AIIQ_DATA") else ROOT / "chat"
CHAT_DIR.mkdir(parents=True, exist_ok=True)


def path(session_id: str, create: bool = True) -> Path:
    if not re.fullmatch(r"[0-9a-f]{6,32}", session_id or ""):
        raise ValueError("invalid session id")
    p = CHAT_DIR / f"{session_id}-session"
    if create:
        p.mkdir(parents=True, exist_ok=True)
    return p


def write_meta(session: dict, **extra) -> None:
    p = path(session["id"]) / "session.json"
    try:
        meta = json.loads(p.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        meta = {"id": session["id"], "created": session.get("created") or time.time()}
    meta.update({k: session.get(k) for k in ("title", "project_id") if k in session}, updated=time.time(), **extra)
    p.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def append_message(session_id: str, msg_id: int, role: str, content: str, meta: dict) -> None:
    rec = {"id": msg_id, "ts": time.time(), "role": role, "content": content,
           "status": meta.get("status"), "model": meta.get("model"),
           "attachments": [a.get("name") for a in meta.get("attachments", [])] or None,
           "steps": [{"kind": s["kind"], "title": s["title"], "status": s["status"]} for s in meta.get("steps", [])] or None}
    with open(path(session_id) / "messages.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({k: v for k, v in rec.items() if v is not None}, ensure_ascii=False) + "\n")


def append_summary(session_id: str, summary: str, stats: dict) -> None:
    p = path(session_id) / "summary.md"
    head = "" if p.exists() else "# Bağlam sıkıştırma geçmişi\n\n"
    n = (p.read_text(encoding="utf-8").count("\n## ") if p.exists() else 0) + 1
    with open(p, "a", encoding="utf-8") as f:
        f.write(f"{head}## Sıkıştırma #{n} — {time.strftime('%Y-%m-%d %H:%M')}\n"
                f"- Özetlenen mesaj: {stats.get('compressed')}\n"
                f"- Token: ~{stats.get('before', 0):,} → ~{stats.get('after', 0):,}\n\n{summary}\n\n")


def state_file(session_id: str) -> Path:
    return path(session_id) / "PROJECT_STATE.md"


def remove(session_id: str) -> None:
    p = path(session_id, create=False)
    if p.exists() and CHAT_DIR.resolve() in p.resolve().parents:
        shutil.rmtree(p, ignore_errors=True)
