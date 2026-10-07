---
title: 'Заметки принадлежат пользователю'
type: 'feature'
ticket: '2'
created: '2026-10-07'
status: 'built'
baseline_revision: 'b4c6cd43463a55cd364aee626eb6b3e6e298a53e'
route: 'full'
route_source: 'auto'
risk: 'medium'
review: 'thorough'
review_source: 'pinned'
lenses_ran: ['blind-hunter', 'edge-case-hunter', 'verification-gap', 'intent-alignment']
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** После записи 1.1 пользователи входят через GitHub, но заметки общие: любой вошедший видит, ищет, правит и удаляет все заметки (CAP-2 спецификации `spec-github-auth`).

**Approach:** Колонка `notes.owner_id` (NULL допустим), добавляемая миграцией без потери данных. Все функции заметок в `app/db.py` принимают владельца и фильтруют по нему; маршруты передают `user["id"]`, чужая или отсутствующая заметка — 404 на просмотре, правке и удалении.

## Boundaries & Constraints

**Always:** Миграция идемпотентна и сохраняет все строки `notes` с их `id`, `created_at`, `updated_at`; путь к базе по-прежнему из `NOTES_DB`. Фильтр по владельцу стоит в самих SQL-запросах (`WHERE ... AND owner_id = ?`), включая `UPDATE` и `DELETE`, а не только в проверке маршрута. Чужая заметка отвечает 404, не 403. `create_note` принимает необязательного владельца, `seed.py` работает без правок. `uv run pytest` без сети.

**Never:** Перенос заметок без владельца кому-либо (запись 1.3) — до неё они не видны никому. Правки `seed.py`, `app/auth.py`, шаблонов. Совместный доступ, роли. Пересоздание таблицы `notes` или удаление данных при миграции.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Своя заметка | A создаёт заметку | `owner_id` = id A; видна A в списке, поиске, на `/notes/{id}` | — |
| Чужая в списке и поиске | заметка A, вошёл B | список B пуст, поиск B по её тексту — «Ничего не найдено» | — |
| Чужая по URL | вошёл B, GET `/notes/{id A}`, POST `/notes/{id A}`, POST `/notes/{id A}/delete` | заметка A не изменена и не удалена | 404 на каждом |
| Несуществующая | POST `/notes/999/delete` | ничего не удаляется | 404 |
| Старая схема | `notes.db` без `owner_id`, N заметок | после `init_db` колонка есть, все N строк на месте, `owner_id` NULL | — |
| Повторный запуск | `init_db` на уже мигрированной базе | без ошибок, данные не меняются | — |
| Без владельца | строка с `owner_id` NULL, вошёл любой | не видна в списке и поиске | 404 по URL |

</frozen-after-approval>

## Code Map

- `app/db.py` -- `SCHEMA` (таблица `notes` без владельца), `init_db()` создаёт таблицы; `list_notes`, `search_notes` (функция `fold` для кириллицы — сохранить), `get_note`, `create_note(title, body, created_at=None)`, `update_note`, `delete_note`. `users`/`upsert_user`/`get_user` не трогать.
- `app/main.py` -- маршруты `index`, `create`, `edit`, `update`, `delete` уже получают `user: User = Depends(current_user)` (это `sqlite3.Row`, id — `user["id"]`); `delete` сейчас не проверяет существование и всегда отвечает редиректом.
- `seed.py` -- вызывает `db.init_db()`, `DELETE FROM notes`, `db.create_note(title, body, created_at=ts)` без владельца; должен работать как есть.
- `tests/conftest.py` -- фикстуры `app_client` (база в `tmp_path`), `login(github_id, login)` возвращает тот же клиент; повторный `login` с другим `github_id` переключает пользователя в сессии. Переиспользовать.
- `tests/test_notes.py` -- 10 тестов под одним пользователем, опираются на `/notes/1`; должны пройти без правок.

## Tasks & Acceptance

**Execution:**
- [x] `app/db.py` -- `owner_id INTEGER REFERENCES users(id)` в `SCHEMA` для новых баз; в `init_db` для старых: если `PRAGMA table_info(notes)` не содержит `owner_id`, `ALTER TABLE notes ADD COLUMN owner_id INTEGER REFERENCES users(id)`; индекс `CREATE INDEX IF NOT EXISTS notes_owner ON notes(owner_id)`. Функции заметок получают `owner_id` и фильтруют по нему: `list_notes(owner_id)`, `search_notes(owner_id, query)`, `get_note(note_id, owner_id)`, `create_note(title, body, created_at=None, owner_id=None)`, `update_note(note_id, owner_id, title, body)`, `delete_note(note_id, owner_id) -> bool` (удалена ли строка) -- изоляция на уровне данных.
- [x] `app/main.py` -- передавать `user["id"]` во все вызовы; `delete` отвечает 404, если `delete_note` вернул False -- чужое и отсутствующее неразличимы.
- [x] `tests/test_ownership.py` (новый) -- каждая строка I/O-матрицы: два пользователя через `login`, миграция на файле базы, созданном старым `SCHEMA` (без `owner_id`) с несколькими заметками до первого запуска приложения.

**Acceptance Criteria:**
- Given копия рабочей `notes.db` со старой схемой, when запускается `init_db`, then число заметок и их содержимое не изменились.
- Given новая база, when `uv run python seed.py`, then скрипт завершается без ошибок и пишет число добавленных заметок.
- Given чистый checkout, when `uv run pytest`, then все тесты, включая прежние 10 в `tests/test_notes.py` и тесты входа, проходят без сети.

## Implementation Notes

## Plan Change Log

## Review Triage Log

Проход 1 (thorough): high 0, medium 2, low 6, false 6, maybe-false 0.

- medium, patch — verification-gap + intent-alignment: фильтр `owner_id` в SQL `update_note` не закреплён тестом — мутант `OR 1` проходит все 42 теста, т.к. 404 даёт предпроверка `get_note`. Добавлен прямой тест `db.update_note` с чужим и пустым владельцем.
- medium, patch — verification-gap: перестановка `note_id`/`user["id"]` в маршрутах не ловится — во всех позитивных тестах id заметки = id пользователя = 1. Добавлен тест, где они различаются.
- false — blind-hunter: позиционные `note_id, owner_id` могут перепутать будущие вызовы. Текущие вызовы верны; реальный риск закрыт тестом выше.
- false — blind-hunter: необязательный `owner_id` в `create_note` скрывает забытого владельца. Необязательность требует сама запись (для `seed.py`); маршрут `create` передаёт владельца и это проверяет `test_own_note_visible`.
- false — blind-hunter: нет теста двух пользователей с совпадающим поиском на ошибку скобок `OR`. Без скобок `test_foreign_note_hidden_in_list_and_search` (совпадение только по `body`) показал бы заметку Алисы Бобу и упал.
- false — blind-hunter: прежние заметки исчезают у всех без сигнала. Так задано записью: без владельца до записи 1.3.
- false — blind-hunter: тест миграции не проверяет продолжение `AUTOINCREMENT`. `ADD COLUMN` не трогает `sqlite_sequence`; дефекта нет.
- false — intent-alignment R4 («без потери данных» как видимость): запись явно оставляет заметки без владельца до 1.3, строки сохранены.
- low, rejected — edge-case + blind-hunter: гонка `PRAGMA`/`ALTER` при одновременном старте двух процессов на старой базе. Приложение запускается одним uvicorn, окно — однократный старт; фикс добавляет обработку исключения.
- low, rejected — edge-case + blind-hunter: заметку удалили между `get_note` и `update_note` → 303 без сохранения. Требует параллельного удаления своей же заметки; фикс добавляет ветку.
- low, rejected — blind-hunter: `REFERENCES users(id)` не применяется без `PRAGMA foreign_keys`. `owner_id` пишется только из существующего `user["id"]`, удаления пользователей нет.
- low, rejected — blind-hunter: индекс не составной с сортировкой. Негативно только на больших объёмах, не для приложения на десятки заметок.
- low, rejected — blind-hunter + intent-alignment: `seed.py` не прогоняется тестом, нет теста POST правки несуществующего id. `seed.py` проверен запуском дважды; 404 правки несуществующей идёт через тот же `get_note`, что проверен на GET.
- low, rejected — blind-hunter: тест миграции не проверяет наличие индекса `notes_owner`. Индекс — оптимизация без влияния на поведение.

## Design Notes

`ALTER TABLE ... ADD COLUMN` в SQLite не переписывает строки и допустим с `REFERENCES`, если значение по умолчанию NULL — поэтому миграция безопасна и дешева; проверка через `PRAGMA table_info` делает её идемпотентной. Сравнение `owner_id = ?` с NULL ложно, поэтому заметки без владельца автоматически не видны никому — отдельной ветки не нужно. Маршрут `update` проверяет `get_note(note_id, owner_id)` до `clean`, чтобы чужой id давал 404, а не 400 на пустом заголовке.

## Verification

**Commands:**
- `uv run pytest` -- expected: все тесты зелёные, сеть не нужна.
- `cp notes.db "$TMPDIR/notes-copy.db" && sqlite3 "$TMPDIR/notes-copy.db" "select count(*) from notes" && NOTES_DB="$TMPDIR/notes-copy.db" uv run python -c "from app import db; db.init_db()" && sqlite3 "$TMPDIR/notes-copy.db" "select count(*), count(owner_id) from notes"` -- expected: то же число заметок, `count(owner_id)` = 0.

**Manual checks (if no CLI):**
- Два GitHub-аккаунта по очереди на http://127.0.0.1:8000: заметка первого не видна второму в списке, поиске и по её URL (404).
