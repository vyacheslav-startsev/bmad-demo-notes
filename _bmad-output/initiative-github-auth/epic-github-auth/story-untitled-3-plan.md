---
title: 'Прежние заметки — первому пользователю'
type: 'feature'
ticket: '3'
created: '2026-10-07'
status: 'built'
baseline_revision: '18d3e637db61f38a3c96946171fd3397f1ba11db'
route: 'oneshot'
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

**Problem:** После записи 1.2 заметки без владельца (все прежние из `notes.db` и созданные `seed.py`) не видны никому — CAP-4 спецификации `spec-github-auth` требует, чтобы они достались первому вошедшему пользователю, а второй их не видел.

**Approach:** При каждом входе, если вошедший — первый зарегистрированный пользователь (наименьший `users.id`), все заметки с `owner_id IS NULL` переходят к нему одним `UPDATE`. `seed.py` пишет заметки первому пользователю, если он есть, иначе без владельца, и удаляет перед этим только заметки того, кому пишет.

</frozen-after-approval>

## Tasks & Acceptance

**Execution:**
- [x] `app/db.py` -- `claim_orphan_notes(user_id) -> int`: `UPDATE notes SET owner_id = ? WHERE owner_id IS NULL AND ? = (SELECT MIN(id) FROM users)`, возвращает `rowcount`; `first_user_id() -> int | None` -- проверка «первый ли» в самом SQL, чтобы второй пользователь не получил ничего.
- [x] `app/main.py` -- в `auth_callback` после `upsert_user` вызвать `db.claim_orphan_notes(user_id)`.
- [x] `seed.py` -- `owner = db.first_user_id()`; удалять `WHERE owner_id = ?` либо `WHERE owner_id IS NULL`; `create_note(..., owner_id=owner)`; сброс `sqlite_sequence` только если таблица `notes` пуста; в выводе указать, чьи заметки.
- [x] `tests/test_ownership.py` -- тесты: старая база с заметками без владельца → первый вошедший видит все, второй ни одной (в т.ч. сиротская заметка, появившаяся после первого входа, не уходит второму при его входе, но уходит первому при повторном); `seed.main()` без пользователей → заметки без владельца; при существующих двух пользователях → заметки первому, заметки второго не тронуты.

**Acceptance Criteria:**
- Given база с заметками без владельца, when первым входит A, затем B, then A видит их все, B — ни одной.
- Given существуют A (первый) и B со своими заметками, when `seed.py`, then заметки сида принадлежат A, прежние заметки A заменены, заметки B не изменились.
- Given чистый checkout, when `uv run pytest`, then все тесты зелёные без сети.

## Implementation Notes

Маршрут oneshot: изменение ≈80 строк в 4 файлах, одна операция над данными плюс правка сида; схема не меняется.

- Изменены `app/db.py` (`first_user_id`, `claim_orphan_notes`), `app/main.py` (вызов в `auth_callback`), `seed.py`, `tests/test_ownership.py` (+4 теста, фикстура `old_db`).
- Перенос — при каждом входе первого пользователя, а не только при первом: так заметки, созданные `seed.py` до появления пользователей или позже без владельца, тоже доходят до него.
- Сюрприз: `app_client` выставляет `NOTES_DB` на `tmp_path/test.db` после других фикстур, поэтому `old_db` пишет старую базу на тот же путь и должна идти в аргументах теста первой.
- В рабочей `notes.db` уже есть пользователь 1 (ручная проверка 1.1), поэтому 14 прежних заметок перейдут к нему при его следующем входе; сид на копии этой базы пишет заметки ему.
- После ревью: при существующем первом пользователе сид удаляет и его заметки, и заметки без владельца (они его по решению эпика), иначе после входа заметки удваивались.

## Review Triage Log

Проход 1 (quick): high 0, medium 1, low 1, false 0, maybe-false 0.

- medium, patch: при существующем первом пользователе `seed.py` оставлял заметки без владельца, а `claim_orphan_notes` при входе отдавал их ему же, и на копии рабочей базы выходило 28 заметок (каждая дважды). Теперь сид удаляет `owner_id = ? OR owner_id IS NULL`; тест сида дополнен сиротской заметкой; на копии базы 14.
- low, patch: перед `if __name__` осталась одна пустая строка (E305). Вернул две.

## Verification

**Commands:**
- `uv run pytest` -- expected: все тесты зелёные.
- `cp notes.db "$TMPDIR/n.db" && NOTES_DB="$TMPDIR/n.db" uv run python seed.py` -- expected: сид пишет 14 заметок первому пользователю (в рабочей базе он уже есть); без пользователей — без владельца (тест).
