import os
import sqlite3
from datetime import datetime

SCHEMA = """
CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    body TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""

USERS_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    github_id INTEGER NOT NULL UNIQUE,
    login TEXT NOT NULL,
    created_at TEXT NOT NULL
)
"""


def db_path() -> str:
    return os.environ.get("NOTES_DB", "notes.db")


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(db_path())
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.execute(SCHEMA)
        conn.execute(USERS_SCHEMA)


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def upsert_user(github_id: int, login: str) -> int:
    """Создаёт пользователя по GitHub id или обновляет его логин; возвращает users.id."""
    with connect() as conn:
        conn.execute(
            "INSERT INTO users (github_id, login, created_at) VALUES (?, ?, ?)"
            " ON CONFLICT(github_id) DO UPDATE SET login = excluded.login",
            (github_id, login, now()),
        )
        row = conn.execute(
            "SELECT id FROM users WHERE github_id = ?", (github_id,)
        ).fetchone()
        return row["id"]


def get_user(user_id: int) -> sqlite3.Row | None:
    with connect() as conn:
        return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


def list_notes() -> list[sqlite3.Row]:
    with connect() as conn:
        return conn.execute(
            "SELECT * FROM notes ORDER BY updated_at DESC, id DESC"
        ).fetchall()


def search_notes(query: str) -> list[sqlite3.Row]:
    # SQLite lower()/LIKE не понимают регистр кириллицы, поэтому сравниваем через casefold
    with connect() as conn:
        conn.create_function("fold", 1, lambda s: s.casefold(), deterministic=True)
        return conn.execute(
            "SELECT * FROM notes"
            " WHERE instr(fold(title), ?) > 0 OR instr(fold(body), ?) > 0"
            " ORDER BY updated_at DESC, id DESC",
            (query.casefold(), query.casefold()),
        ).fetchall()


def get_note(note_id: int) -> sqlite3.Row | None:
    with connect() as conn:
        return conn.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()


def create_note(title: str, body: str, created_at: str | None = None) -> int:
    ts = created_at or now()
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO notes (title, body, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (title, body, ts, ts),
        )
        return cur.lastrowid


def update_note(note_id: int, title: str, body: str) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE notes SET title = ?, body = ?, updated_at = ? WHERE id = ?",
            (title, body, now(), note_id),
        )


def delete_note(note_id: int) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM notes WHERE id = ?", (note_id,))
