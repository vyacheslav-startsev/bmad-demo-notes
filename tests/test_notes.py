import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("NOTES_DB", str(tmp_path / "test.db"))
    from app.main import app

    with TestClient(app) as c:
        yield c


def test_empty_list(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "Заметок пока нет" in r.text


def test_create_and_list(client):
    r = client.post("/notes", data={"title": "Покупки", "body": "Молоко"})
    assert r.status_code == 200
    assert "Покупки" in r.text
    assert "Молоко" in r.text


def test_empty_title_rejected(client):
    r = client.post("/notes", data={"title": "   ", "body": "текст"})
    assert r.status_code == 400


def test_edit_note(client):
    client.post("/notes", data={"title": "Старое", "body": ""})
    r = client.post("/notes/1", data={"title": "Новое", "body": "текст"})
    assert r.status_code == 200
    assert "Новое" in r.text
    assert "Старое" not in r.text


def test_missing_note_404(client):
    assert client.get("/notes/999").status_code == 404


def test_delete_note(client):
    client.post("/notes", data={"title": "Удалить меня", "body": ""})
    r = client.post("/notes/1/delete")
    assert "Удалить меня" not in r.text


def test_search_by_title_and_body(client):
    client.post("/notes", data={"title": "Покупки", "body": "Молоко"})
    client.post("/notes", data={"title": "Работа", "body": "Отчёт"})
    r = client.get("/", params={"q": "молоко"})
    assert "Покупки" in r.text
    assert "Работа" not in r.text
    r = client.get("/", params={"q": "РАБ"})
    assert "Работа" in r.text
    assert "Покупки" not in r.text


def test_search_special_chars_are_literal(client):
    client.post("/notes", data={"title": "Скидка 50%", "body": ""})
    client.post("/notes", data={"title": "Другое", "body": ""})
    r = client.get("/", params={"q": "%"})
    assert "Скидка 50%" in r.text
    assert "Другое" not in r.text


def test_search_nothing_found(client):
    client.post("/notes", data={"title": "Покупки", "body": ""})
    r = client.get("/", params={"q": "нет такого"})
    assert "Ничего не найдено" in r.text
    assert 'value="нет такого"' in r.text
    assert "Сбросить" in r.text


def test_blank_search_shows_all(client):
    client.post("/notes", data={"title": "Покупки", "body": ""})
    r = client.get("/", params={"q": "   "})
    assert "Покупки" in r.text
    assert "Все заметки" in r.text
    assert "Сбросить" not in r.text
