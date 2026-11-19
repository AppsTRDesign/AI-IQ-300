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
              ("sessions", "context_used INTEGER DEFAULT 0"), ("sessions", "context_stats TEXT"),
              ("sessions", "unread INTEGER DEFAULT 0"), ("projects", "pinned INTEGER DEFAULT 0"),
              # 1 = the first words of the first message, 2 = a title the model wrote, 0 = the user's own (never changed)
              ("sessions", "title_auto INTEGER DEFAULT 1")]


def conn() -> sqlite3.Connection:
    c = getattr(_local, "c", None)
    if c is None:
        c = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=15)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        c.executescript(SCHEMA)
        for table, col in MIGRATIONS:
            try:
                c.execute(f"ALTER TABLE {table} ADD COLUMN {col}")
            except sqlite3.OperationalError:
                pass  # already exists
        # Every chat query filters by session: without this index each one read the whole messages table (with the
        # steps of every answer stored in it), so opening a chat and starting a task got slower as the history grew.
        c.execute("CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_sessions_project ON sessions(project_id, archived)")
        _fts_setup(c)
        c.commit()
        _local.c = c
    return c


FTS = {"ok": None}  # whether this SQLite build has FTS5 (search falls back to LIKE without it)


def _fts_setup(c: sqlite3.Connection) -> None:
    """Full-text index over message texts, kept in step by triggers; built once for an existing database."""
    if FTS["ok"] is False:
        return
    try:
        c.executescript("""
CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(content, content='messages', content_rowid='id',
    tokenize='unicode61 remove_diacritics 2');
CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages BEGIN
    INSERT INTO messages_fts(rowid, content) VALUES (new.id, new.content); END;
CREATE TRIGGER IF NOT EXISTS messages_ad AFTER DELETE ON messages BEGIN
    INSERT INTO messages_fts(messages_fts, rowid, content) VALUES ('delete', old.id, old.content); END;
CREATE TRIGGER IF NOT EXISTS messages_au AFTER UPDATE OF content ON messages BEGIN
    INSERT INTO messages_fts(messages_fts, rowid, content) VALUES ('delete', old.id, old.content);
    INSERT INTO messages_fts(rowid, content) VALUES (new.id, new.content); END;
""")
        if FTS["ok"] is None:
            built = c.execute("SELECT count(*) FROM messages_fts_docsize").fetchone()[0]
            if not built and c.execute("SELECT 1 FROM messages LIMIT 1").fetchone():
                c.execute("INSERT INTO messages_fts(messages_fts) VALUES('rebuild')")
        FTS["ok"] = True
    except sqlite3.OperationalError:
        FTS["ok"] = False


def search(q: str, limit: int = 40) -> list[dict[str, Any]]:
    """Messages matching every word of q (prefix match), newest first, with a short snippet around the hit."""
    words = [w for w in "".join(ch if ch.isalnum() else " " for ch in q).split() if w][:8]
    if not words:
        return []
    base = ("SELECT m.id, m.session_id, m.role, m.created, s.title, s.project_id, s.archived, {snip} AS snippet "
            "FROM {src} JOIN sessions s ON s.id = m.session_id WHERE {cond} ORDER BY m.id DESC LIMIT ?")
    conn()
    if FTS["ok"]:
        match = " ".join(f'"{w}"*' for w in words)
        sql = base.format(snip="snippet(messages_fts, 0, '[[', ']]', '…', 14)",
                          src="messages_fts JOIN messages m ON m.id = messages_fts.rowid", cond="messages_fts MATCH ?")
        try:
            return query(sql, (match, limit))
        except sqlite3.OperationalError:
            pass
    cond = " AND ".join("m.content LIKE ?" for _ in words)
    sql = base.format(snip="substr(m.content, 1, 160)", src="messages m", cond=cond)
    return query(sql, (*[f"%{w}%" for w in words], limit))


def checkpoint() -> None:
    """Folds the write-ahead log into the database file (at shutdown; the log otherwise only grows until its limit)."""
    try:
        conn().execute("PRAGMA wal_checkpoint(TRUNCATE)")
    except sqlite3.Error:
        pass


def execute(sql: str, params: tuple = ()) -> sqlite3.Cursor:
    c = conn()
    cur = c.execute(sql, params)
    c.commit()
    return cur


def query(sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    return [dict(r) for r in conn().execute(sql, params).fetchall()]


def add_message(session_id: str, role: str, content: str, meta: dict | None = None) -> int:
    now = time.time()
    if not execute("UPDATE sessions SET updated=? WHERE id=?", (now, session_id)).rowcount:
        # The chat was deleted while its task was still finishing: no orphan message (and no folder) comes back.
        return 0
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
