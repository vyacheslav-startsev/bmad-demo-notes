import sqlite3

import pytest
from fastapi.testclient import TestClient

from app import db

# Схема notes до записи 1.2: без владельца
OLD_SCHEMA = """
CREATE TABLE notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    body TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""

OLD_ROWS = [
    (3, "Первая", "текст один", "2026-09-01T10:00:00", "2026-09-02T11:00:00"),
    (7, "Вторая", "", "2026-09-03T12:00:00", "2026-09-03T12:00:00"),
    (9, "Третья", "Секрет", "2026-09-04T13:00:00", "2026-09-05T14:00:00"),
]


def note_id(title: str) -> int:
    with db.connect() as conn:
        return conn.execute("SELECT id FROM notes WHERE title = ?", (title,)).fetchone()["id"]


def all_notes() -> list[tuple]:
    with db.connect() as conn:
        return [
            tuple(r)
            for r in conn.execute(
                "SELECT id, title, body, created_at, updated_at FROM notes ORDER BY id"
            )
        ]


def columns() -> set[str]:
    with db.connect() as conn:
        return {r["name"] for r in conn.execute("PRAGMA table_info(notes)")}


@pytest.fixture
def alice_note(login):
    client = login(1, "alice")
    client.post("/notes", data={"title": "Тайна Алисы", "body": "клад под дубом"})
    return note_id("Тайна Алисы")


def test_own_note_visible(login):
    client = login(1, "alice")
    client.post("/notes", data={"title": "Моя", "body": "текст"})
    nid = note_id("Моя")
    with db.connect() as conn:
        owner = conn.execute("SELECT owner_id FROM notes WHERE id = ?", (nid,)).fetchone()[0]
        alice = conn.execute("SELECT id FROM users WHERE github_id = 1").fetchone()[0]
    assert owner == alice
    assert "Моя" in client.get("/").text
    assert "Моя" in client.get("/", params={"q": "текст"}).text
    assert client.get(f"/notes/{nid}").status_code == 200


def test_foreign_note_hidden_in_list_and_search(login, alice_note):
    client = login(2, "bob")
    r = client.get("/")
    assert "Тайна Алисы" not in r.text
    assert "Заметок пока нет" in r.text
    r = client.get("/", params={"q": "клад"})
    assert "Тайна Алисы" not in r.text
    assert "Ничего не найдено" in r.text


def test_foreign_note_by_url_404(login, alice_note):
    before = all_notes()
    client = login(2, "bob")
    assert client.get(f"/notes/{alice_note}").status_code == 404
    r = client.post(f"/notes/{alice_note}", data={"title": "Взлом", "body": ""})
    assert r.status_code == 404
    # чужой id даёт 404 раньше проверки пустого заголовка
    r = client.post(f"/notes/{alice_note}", data={"title": "  ", "body": ""})
    assert r.status_code == 404
    assert client.post(f"/notes/{alice_note}/delete").status_code == 404
    assert all_notes() == before
    # владелец по-прежнему видит заметку
    client = login(1, "alice")
    assert "Тайна Алисы" in client.get("/").text


def test_missing_note_delete_404(login):
    client = login(1, "alice")
    client.post("/notes", data={"title": "Остаётся", "body": ""})
    before = all_notes()
    assert client.post("/notes/999/delete").status_code == 404
    assert all_notes() == before


def test_ownerless_note_invisible(login):
    client = login(1, "alice")
    nid = db.create_note("Ничья", "без владельца")
    assert "Ничья" not in client.get("/").text
    assert "Ничего не найдено" in client.get("/", params={"q": "ничья"}).text
    assert client.get(f"/notes/{nid}").status_code == 404
    assert client.post(f"/notes/{nid}", data={"title": "x", "body": ""}).status_code == 404
    assert client.post(f"/notes/{nid}/delete").status_code == 404
    assert note_id("Ничья") == nid


def test_migration_keeps_old_notes(tmp_path, monkeypatch):
    path = tmp_path / "old.db"
    with sqlite3.connect(path) as conn:
        conn.execute(OLD_SCHEMA)
        conn.executemany(
            "INSERT INTO notes (id, title, body, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            OLD_ROWS,
        )
    conn.close()
    monkeypatch.setenv("NOTES_DB", str(path))
    assert "owner_id" not in columns()

    from app.main import app

    with TestClient(app):  # lifespan вызывает init_db
        pass

    assert "owner_id" in columns()
    assert all_notes() == OLD_ROWS
    with db.connect() as conn:
        assert conn.execute("SELECT count(owner_id) FROM notes").fetchone()[0] == 0

    # повторный запуск на мигрированной базе
    db.init_db()
    db.init_db()
    assert all_notes() == OLD_ROWS


def test_seed_style_create_without_owner(app_client):
    nid = db.create_note("Сид", "текст", created_at="2026-09-12T09:15:00")
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM notes WHERE id = ?", (nid,)).fetchone()
    assert row["owner_id"] is None
    assert row["created_at"] == row["updated_at"] == "2026-09-12T09:15:00"


def user_id(github_id: int) -> int:
    with db.connect() as conn:
        return conn.execute(
            "SELECT id FROM users WHERE github_id = ?", (github_id,)
        ).fetchone()["id"]


def test_update_filters_owner_in_sql(login, alice_note):
    login(2, "bob")
    bob = user_id(2)
    orphan = db.create_note("Ничья", "без владельца", created_at="2026-09-01T10:00:00")
    before = all_notes()
    db.update_note(alice_note, bob, "x", "y")
    db.update_note(orphan, bob, "x", "y")
    assert all_notes() == before


def test_routes_use_note_id_not_user_id(login):
    client = login(1, "alice")
    client.post("/notes", data={"title": "Алиса 1", "body": ""})
    client.post("/notes", data={"title": "Алиса 2", "body": ""})
    client = login(2, "bob")
    client.post("/notes", data={"title": "Боб", "body": "старое"})
    bob_nid = note_id("Боб")
    assert bob_nid != user_id(2)
    alice_rows = [r for r in all_notes() if r[1].startswith("Алиса")]

    r = client.get(f"/notes/{bob_nid}")
    assert r.status_code == 200
    assert "Боб" in r.text

    r = client.post(f"/notes/{bob_nid}", data={"title": "Боб новый", "body": "новое"})
    assert r.status_code == 200
    rows = {r[0]: r for r in all_notes()}
    assert rows[bob_nid][1:3] == ("Боб новый", "новое")
    assert [r for r in all_notes() if r[0] != bob_nid] == alice_rows

    r = client.post(f"/notes/{bob_nid}/delete")
    assert r.status_code == 200
    assert all_notes() == alice_rows
