import os
from urllib.parse import parse_qs, urlparse

# Ключи задаются до импорта app: load_dotenv() не перезаписывает окружение,
# поэтому настоящий .env в тестах не используется.
os.environ["GITHUB_CLIENT_ID"] = "test-client-id"
os.environ["GITHUB_CLIENT_SECRET"] = "test-client-secret"
os.environ["SESSION_SECRET"] = "test-session-secret"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import auth  # noqa: E402


@pytest.fixture(autouse=True)
def no_github(monkeypatch):
    """Тесты не ходят в сеть: настоящий GitHub недоступен, пока его не подменят."""

    def offline(*args, **kwargs):
        raise AssertionError("тест обратился к GitHub без подмены")

    monkeypatch.setattr(auth, "exchange_code", offline)
    monkeypatch.setattr(auth, "fetch_user", offline)


@pytest.fixture
def app_client(tmp_path, monkeypatch):
    monkeypatch.setenv("NOTES_DB", str(tmp_path / "test.db"))
    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture
def client(app_client):
    """Клиент без входа на чистой базе (тестовые модули могут переопределить)."""
    return app_client


def start_login(client) -> str:
    """Проходит /auth/login и возвращает state из редиректа на GitHub."""
    r = client.get("/auth/login", follow_redirects=False)
    assert r.status_code == 303
    location = urlparse(r.headers["location"])
    assert f"{location.scheme}://{location.netloc}{location.path}" == auth.AUTHORIZE_URL
    return parse_qs(location.query)["state"][0]


@pytest.fixture
def login(app_client, monkeypatch):
    """Вход под заданным пользователем через подменённый GitHub; возвращает client."""

    def do_login(github_id: int = 1, login: str = "octocat"):
        monkeypatch.setattr(
            auth, "exchange_code", lambda code: f"token-for-{code}"
        )
        monkeypatch.setattr(
            auth, "fetch_user", lambda token: {"id": github_id, "login": login}
        )
        state = start_login(app_client)
        r = app_client.get(
            "/auth/callback",
            params={"code": "test-code", "state": state},
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert r.headers["location"] == "/"
        return app_client

    return do_login
