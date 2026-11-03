"""SQLite persistence for projects, chat sessions, messages, processes and events."""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from typing import Any

from .config import DATA_DIR

DB_PATH = DATA_DIR / "aiiq.db"
_local = threading.local()

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects(id TEXT PRIMARY KEY, name TEXT, path TEXT, created REAL);
CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY, project_id TEXT, title TEXT, created REAL, updated REAL);
CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT, role TEXT,
    content TEXT, meta TEXT, created REAL);
CREATE TABLE IF NOT EXISTS processes(id TEXT PRIMARY KEY, pid INTEGER, argv TEXT, cwd TEXT, state TEXT,
    exit_code INTEGER, started REAL, ended REAL, owner TEXT);
CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY, ts REAL, topic TEXT, type TEXT, payload TEXT);
"""

MIGRATIONS = [("sessions", "summary TEXT"), ("sessions", "summary_upto INTEGER DEFAULT 0"),
              ("sessions", "pinned INTEGER DEFAULT 0"), ("sessions", "archived INTEGER DEFAULT 0"),
              ("sessions", "context_used INTEGER DEFAULT 0"), ("sessions", "context_stats TEXT")]


def conn() -> sqlite3.Connection:
    c = getattr(_local, "c", None)
    if c is None:
        c = sqlite3.connect(DB_PATH, check_same_thread=False)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        c.executescript(SCHEMA)
        for table, col in MIGRATIONS:
            try:
                c.execute(f"ALTER TABLE {table} ADD COLUMN {col}")
            except sqlite3.OperationalError:
                pass  # already exists
        _local.c = c
    return c


def execute(sql: str, params: tuple = ()) -> sqlite3.Cursor:
    c = conn()
    cur = c.execute(sql, params)
    c.commit()
    return cur


def query(sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    return [dict(r) for r in conn().execute(sql, params).fetchall()]


def add_message(session_id: str, role: str, content: str, meta: dict | None = None) -> int:
    now = time.time()
    execute("UPDATE sessions SET updated=? WHERE id=?", (now, session_id))
    mid = execute(
        "INSERT INTO messages(session_id, role, content, meta, created) VALUES(?,?,?,?,?)",
        (session_id, role, content, json.dumps(meta or {}, ensure_ascii=False), now),
    ).lastrowid
    try:
        from . import sessions
        sessions.append_message(session_id, mid, role, content, meta or {})
    except (OSError, ValueError):
        pass  # the archive is best-effort; the DB row is authoritative
    return mid
