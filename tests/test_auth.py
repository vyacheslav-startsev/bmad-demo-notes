import sqlite3
from urllib.parse import parse_qs, urlparse

import pytest

from app import auth, db
from conftest import start_login


def users() -> list[sqlite3.Row]:
    with db.connect() as conn:
        return conn.execute("SELECT * FROM users").fetchall()


def fake_github(monkeypatch, github_id=1, login="octocat"):
    monkeypatch.setattr(auth, "exchange_code", lambda code: "token")
    monkeypatch.setattr(
        auth, "fetch_user", lambda token: {"id": github_id, "login": login}
    )


def has_session(client) -> bool:
    return bool(client.cookies.get("session")) and client.get(
        "/", follow_redirects=False
    ).status_code == 200


# --- Первый и повторный вход ---


def test_first_login_creates_user_and_shows_login(login, tmp_path):
    client = login(github_id=42, login="octocat")
    rows = users()
    assert [(r["github_id"], r["login"]) for r in rows] == [(42, "octocat")]
    r = client.get("/")
    assert r.status_code == 200
    assert "octocat" in r.text
    assert "Выйти" in r.text


def test_repeat_login_updates_login_same_row(login, tmp_path):
    login(github_id=42, login="old-name")
    first_id = users()[0]["id"]
    client = login(github_id=42, login="new-name")
    rows = users()
    assert len(rows) == 1
    assert rows[0]["id"] == first_id
    assert rows[0]["login"] == "new-name"
    assert "new-name" in client.get("/").text


def test_authorize_redirect_params(client):
    r = client.get("/auth/login", follow_redirects=False)
    assert r.status_code == 303
    query = parse_qs(urlparse(r.headers["location"]).query)
    assert query["client_id"] == ["test-client-id"]
    assert query["redirect_uri"] == ["http://127.0.0.1:8000/auth/callback"]
    assert len(query["state"][0]) >= 32
    assert "scope" not in query


def test_session_cookie_lives_7_days(client, monkeypatch):
    fake_github(monkeypatch)
    state = start_login(client)
    r = client.get(
        "/auth/callback",
        params={"code": "c", "state": state},
        follow_redirects=False,
    )
    cookie = r.headers["set-cookie"]
    assert "Max-Age=604800" in cookie
    assert "samesite=lax" in cookie.lower()


# --- Подделка state ---


@pytest.mark.parametrize("bad_state", ["wrong", None])
def test_bad_or_missing_state_rejected(client, monkeypatch, tmp_path, bad_state):
    fake_github(monkeypatch)
    start_login(client)
    params = {"code": "c"}
    if bad_state is not None:
        params["state"] = bad_state
    r = client.get("/auth/callback", params=params, follow_redirects=False)
    assert r.status_code == 400
    assert users() == []
    assert not has_session(client)


def test_state_without_login_start_rejected(client, monkeypatch, tmp_path):
    fake_github(monkeypatch)
    r = client.get(
        "/auth/callback", params={"code": "c", "state": "x"}, follow_redirects=False
    )
    assert r.status_code == 400
    assert users() == []


def test_used_state_rejected(client, monkeypatch, tmp_path):
    fake_github(monkeypatch)
    state = start_login(client)
    failed = client.get(
        "/auth/callback",
        params={"error": "access_denied", "state": state},
        follow_redirects=False,
    )
    assert failed.status_code == 400
    replay = client.get(
        "/auth/callback", params={"code": "c", "state": state}, follow_redirects=False
    )
    assert replay.status_code == 400
    assert users() == []
    assert not has_session(client)


def test_forged_state_with_error_rejected_as_state(client):
    start_login(client)
    r = client.get(
        "/auth/callback",
        params={"error": "access_denied", "state": "wrong"},
        follow_redirects=False,
    )
    assert r.status_code == 400
    assert "Вход не удался" not in r.text


def test_protected_page_during_login_keeps_state(client, monkeypatch, tmp_path):
    fake_github(monkeypatch)
    state = start_login(client)
    assert client.get("/", follow_redirects=False).status_code == 303
    r = client.get(
        "/auth/callback", params={"code": "c", "state": state}, follow_redirects=False
    )
    assert r.status_code == 303
    assert r.headers["location"] == "/"
    assert len(users()) == 1


# --- Отказ на GitHub ---


@pytest.mark.parametrize(
    "params",
    [{"error": "access_denied"}, {}],
    ids=["access_denied", "no_code"],
)
def test_github_refusal(client, tmp_path, params):
    state = start_login(client)
    r = client.get(
        "/auth/callback", params={**params, "state": state}, follow_redirects=False
    )
    assert r.status_code == 400
    assert "Вход не удался" in r.text
    assert 'href="/login"' in r.text
    assert users() == []
    assert not has_session(client)


def test_github_token_failure(client, monkeypatch, tmp_path):
    def broken(code):
        raise auth.AuthError("нет токена")

    monkeypatch.setattr(auth, "exchange_code", broken)
    state = start_login(client)
    r = client.get(
        "/auth/callback", params={"code": "c", "state": state}, follow_redirects=False
    )
    assert r.status_code == 400
    assert "Вход не удался" in r.text
    assert users() == []


# --- Без входа ---


@pytest.mark.parametrize(
    "method,path,data",
    [
        ("get", "/", None),
        ("get", "/?q=x", None),
        ("post", "/notes", {"title": "t", "body": ""}),
        ("post", "/notes", {}),
        ("get", "/notes/1", None),
        ("post", "/notes/1", {"title": "t", "body": ""}),
        ("post", "/notes/1/delete", None),
    ],
)
def test_anonymous_redirected_to_login(client, method, path, data):
    kwargs = {"follow_redirects": False}
    if data is not None:
        kwargs["data"] = data
    r = getattr(client, method)(path, **kwargs)
    assert r.status_code == 303
    assert r.headers["location"] == "/login"


def test_anonymous_cannot_create_note(client, login):
    client.post("/notes", data={"title": "Чужая", "body": ""})
    assert "Чужая" not in login().get("/").text


def test_login_page(client):
    r = client.get("/login")
    assert r.status_code == 200
    assert "Войти через GitHub" in r.text
    assert 'href="/auth/login"' in r.text


# --- Выход ---


def test_logout(login):
    client = login()
    r = client.post("/logout", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/login"
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/login"


# --- Пользователь удалён из БД ---


def test_deleted_user_treated_as_anonymous(login, tmp_path):
    client = login()
    with db.connect() as conn:
        conn.execute("DELETE FROM users")
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/login"


# --- Настройки ---


def test_missing_setting_has_clear_error(monkeypatch):
    monkeypatch.delenv("SESSION_SECRET")
    with pytest.raises(RuntimeError, match="SESSION_SECRET"):
        auth.settings()
