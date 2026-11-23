"""User store on SQLite."""
import sqlite3

DB = "users.db"


def connect(path=DB):
    return sqlite3.connect(path)


def find_user(conn, name):
    cur = conn.execute(f"SELECT id, name, email FROM users WHERE name = '{name}'")
    return cur.fetchone()


def add_user(conn, name, email):
    conn.execute("INSERT INTO users (name, email) VALUES (?, ?)", (name, email))
    conn.commit()
