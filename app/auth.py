"""Вход через GitHub: настройки, обмен кода на токен, профиль и зависимость current_user.

Все обращения к GitHub собраны здесь — тесты подменяют `exchange_code` и `fetch_user`.
"""

import os
import sqlite3
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx
from fastapi import Request

from app import db

AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
TOKEN_URL = "https://github.com/login/oauth/access_token"
USER_URL = "https://api.github.com/user"
REDIRECT_URI = "http://127.0.0.1:8000/auth/callback"
SESSION_MAX_AGE = 7 * 24 * 60 * 60
TIMEOUT = 10


@dataclass(frozen=True)
class Settings:
    client_id: str
    client_secret: str
    session_secret: str


def _require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(
            f"Не задана переменная окружения {name}: добавьте её в окружение или в файл .env"
        )
    return value


def settings() -> Settings:
    return Settings(
        client_id=_require("GITHUB_CLIENT_ID"),
        client_secret=_require("GITHUB_CLIENT_SECRET"),
        session_secret=_require("SESSION_SECRET"),
    )


class AuthError(Exception):
    """GitHub не подтвердил вход."""


class LoginRequired(Exception):
    """Запрос без входа — обработчик в main перенаправляет на /login."""


def authorize_url(state: str) -> str:
    # scope не передаётся: нужен только публичный профиль
    query = urlencode(
        {"client_id": settings().client_id, "redirect_uri": REDIRECT_URI, "state": state}
    )
    return f"{AUTHORIZE_URL}?{query}"


def exchange_code(code: str) -> str:
    s = settings()
    try:
        r = httpx.post(
            TOKEN_URL,
            data={
                "client_id": s.client_id,
                "client_secret": s.client_secret,
                "code": code,
                "redirect_uri": REDIRECT_URI,
            },
            headers={"Accept": "application/json"},
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        token = r.json().get("access_token")
    except (httpx.HTTPError, ValueError) as e:
        raise AuthError("GitHub не выдал токен") from e
    if not token:
        raise AuthError("GitHub не выдал токен")
    return token


def fetch_user(token: str) -> dict:
    try:
        r = httpx.get(
            USER_URL,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
            },
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        data = r.json()
        return {"id": int(data["id"]), "login": str(data["login"])}
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as e:
        raise AuthError("Не удалось получить профиль GitHub") from e


def current_user(request: Request) -> sqlite3.Row:
    user_id = request.session.get("user_id")
    user = db.get_user(user_id) if isinstance(user_id, int) else None
    if user is None:
        # убираем только user_id: oauth_state незавершённого входа должен сохраниться
        request.session.pop("user_id", None)
        raise LoginRequired
    return user
