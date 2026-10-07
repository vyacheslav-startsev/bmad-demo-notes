---
title: 'Вход и выход через GitHub'
type: 'feature'
ticket: '1'
created: '2026-10-07'
status: 'built'
baseline_revision: '2c68c5f20a495f7d5f12b033790aea11e3a05a5e'
route: 'full'
route_source: 'auto'
risk: 'medium'
review: 'quick'
review_source: 'pinned'
lenses_ran: ['quick']
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Приложение не знает, кто им пользуется: входа нет, любой посетитель видит все страницы заметок (CAP-1, CAP-3 спецификации `spec-github-auth`).

**Approach:** OAuth-поток GitHub с проверкой `state`, таблица `users` по GitHub user id, подписанная cookie-сессия на 7 дней с ключом из `SESSION_SECRET`. Страницы заметок без входа перенаправляют на страницу входа; в шапке логин и кнопка «Выйти». Общая тестовая фикстура входа под заданным пользователем через подменённый GitHub, существующие тесты переходят на неё.

## Boundaries & Constraints

**Always:** `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`, `SESSION_SECRET` читаются только из окружения или `.env`. Callback строго `http://127.0.0.1:8000/auth/callback`. Пользователь определяется по неизменному GitHub `id`, логин обновляется при каждом входе. Запрашивается только профиль, без дополнительных scope. Существующие данные `notes.db` сохраняются (новая таблица через `CREATE TABLE IF NOT EXISTS`). `uv run pytest` не обращается к сети.

**Never:** Владелец заметок и фильтрация по пользователю (запись 1.2), перенос прежних заметок (1.3), правки `seed.py`. Другие провайдеры, пароли, списки разрешённых аккаунтов, обращения к GitHub API кроме `GET /user`.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Первый вход | callback с верными `code` и `state`, GitHub id новый | создаётся строка `users`, сессия, редирект 303 на `/` с логином в шапке | — |
| Повторный вход | тот же GitHub id, логин сменился | та же строка `users`, логин обновлён | — |
| Подделка | `state` неверный, отсутствует или уже использован | сессия не создаётся | 400 |
| Отказ на GitHub | callback с `error=access_denied` или без `code` | сессия не создаётся | 400 с текстом «Вход не удался» и ссылкой на `/login` |
| Без входа | GET/POST любой страницы заметок | редирект 303 на `/login` | — |
| Выход | POST `/logout` | сессия очищена, редирект 303 на `/login`; затем `/` снова требует входа | — |
| Пользователь удалён из БД | cookie с несуществующим `user_id` | считается не вошедшим | редирект на `/login` |

</frozen-after-approval>

## Code Map

- `app/main.py` -- маршруты; `lifespan` вызывает `db.init_db()`; `index`, `create`, `edit`, `update`, `delete` получают защиту входом; `templates` (Jinja2) переиспользовать для `login.html`.
- `app/db.py` -- `SCHEMA`, `connect()`, `init_db()`, `now()`; сюда таблица `users` и функции `upsert_user`, `get_user`. Функции заметок не трогать (1.2).
- `app/templates/base.html` -- шапка `.top` с `.logo`; добавить логин и форму «Выйти», если в контексте есть `user`.
- `app/static/style.css` -- стили `.top`, кнопок; дополнить для шапки и страницы входа.
- `tests/test_notes.py` -- фикстура `client` с `NOTES_DB` в `tmp_path`; все 10 тестов перевести на вошедший клиент.
- `pyproject.toml` / `uv.lock` -- в зависимостях нет `itsdangerous` (нужен `SessionMiddleware`) и `python-dotenv`; `httpx` только в dev.
- `.env` -- уже содержит три ключа, в `.gitignore`; не менять.

## Tasks & Acceptance

**Execution:**
- [x] `pyproject.toml`, `uv.lock` -- `uv add itsdangerous httpx python-dotenv` -- сессии, запросы к GitHub, загрузка `.env`.
- [x] `app/db.py` -- таблица `users (id, github_id UNIQUE, login, created_at)` в `init_db`; `upsert_user(github_id, login) -> int`, `get_user(user_id)` -- хранение пользователей.
- [x] `app/auth.py` (новый) -- чтение настроек с понятной ошибкой при отсутствии ключа; `exchange_code(code) -> token` и `fetch_user(token) -> {id, login}` через httpx; зависимость `current_user`, которая при отсутствии пользователя прерывает запрос редиректом на `/login` -- изолирует GitHub и точку подмены в тестах.
- [x] `app/main.py` -- `load_dotenv()`, `SessionMiddleware` (max_age 7 дней, same_site lax), маршруты `GET /login`, `GET /auth/login` (генерирует `state`, кладёт в сессию, редирект на GitHub с `redirect_uri`), `GET /auth/callback`, `POST /logout`; `current_user` на всех маршрутах заметок, `user` в контекст шаблонов.
- [x] `app/templates/login.html`, `app/templates/base.html`, `app/static/style.css` -- страница входа с кнопкой «Войти через GitHub»; логин и «Выйти» в шапке.
- [x] `tests/conftest.py` (новый) -- env-переменные до импорта app, фикстуры `client` (без входа) и `login(github_id, login)`, проходящей `/auth/login` → `/auth/callback` с подменёнными `exchange_code`/`fetch_user`; `tests/test_notes.py` на вошедший клиент.
- [x] `tests/test_auth.py` (новый) -- все строки I/O-матрицы.

**Acceptance Criteria:**
- Given подменённый GitHub, when пользователь проходит вход, then в `users` одна строка с его GitHub id и главная показывает его логин и «Выйти».
- Given вошедший пользователь, when он выходит, then GET `/` перенаправляет на `/login`.
- Given cookie сессии, when проверяются её атрибуты, then срок жизни 7 дней (`Max-Age=604800`).
- Given чистый checkout, when `uv run pytest`, then все тесты проходят без сети.
- Given реальный `.env`, when вход реальным аккаунтом на http://127.0.0.1:8000, then шапка показывает GitHub-логин (ручная проверка человеком, hitl).

## Implementation Notes

## Plan Change Log

## Review Triage Log

Проход 1 (quick): high 0, medium 2, low 2, false 2, maybe-false 0.

- medium, patch — `app/auth.py` `current_user`: `session.clear()` у анонимного запроса стирает `oauth_state`, и вход, начатый до загрузки защищённой страницы, падает с 400. Теперь удаляется только `user_id`, добавлен тест.
- medium, patch — `tests/test_auth.py` `test_used_state_rejected`: повтор `state` отклонялся бы и без `pop`, так как сессию очищают успешный callback и `/logout`. Тест переписан на повтор после неудачной попытки.
- low, patch — `app/main.py` `auth_callback`: ветка `error`/без `code` проверялась раньше `state`, поэтому поддельный callback получал не тот ответ 400. Теперь `state` проверяется первым.
- low, patch — `pyproject.toml`: `httpx` объявлен и в runtime, и в dev. Запись в dev удалена.
- false — grep из Verification находит значения в `tests/conftest.py`. Это фиктивные тестовые ключи, а не секреты. Исправить можно только правкой плана этой сборки, поэтому отклонено.
- false — `uv.lock` не попал в дифф ревью. Дефекта в коде нет: `uv lock --check` проходит.

## Design Notes

`current_user` как обычная зависимость не может вернуть редирект, поэтому она бросает собственное исключение `LoginRequired`, а обработчик `app.exception_handler(LoginRequired)` отвечает `RedirectResponse("/login", 303)`. `state` -- `secrets.token_urlsafe(32)`, извлекается из сессии через `pop` и сравнивается `secrets.compare_digest`, поэтому одноразовый. Сессия хранит только `user_id`; пользователь читается из БД на каждый запрос. `same_site="lax"` нужен, чтобы cookie с `state` пришла на верхнеуровневый GET-редирект от GitHub.

## Verification

**Commands:**
- `uv run pytest` -- expected: все тесты зелёные, сеть не нужна.
- `git grep -nE "SESSION_SECRET|CLIENT_SECRET" -- ':!_bmad*' ':!.env'` -- expected: только чтение имён переменных, никаких значений.

**Manual checks (if no CLI):**
- `uv run uvicorn app.main:app` → http://127.0.0.1:8000 перенаправляет на вход; вход через GitHub показывает логин в шапке; «Выйти» возвращает на вход.
