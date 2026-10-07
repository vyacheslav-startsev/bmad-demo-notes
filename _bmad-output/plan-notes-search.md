---
title: 'Поиск по заметкам'
type: 'feature'
ticket: ''
created: '2026-10-07'
status: 'built'
baseline_revision: '7250e535b694a1e9944d580f01a9f3542e3ee088'
route: 'oneshot'
route_source: 'auto'
risk: 'low'
review: 'quick'
review_source: 'pinned'
lenses_ran: ['quick']
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** На главной странице показываются все заметки подряд; когда их много, нужную не найти без прокрутки всего списка.

**Approach:** Добавить на главную поле поиска (GET-форма, параметр `q`). Список фильтруется по подстроке в заголовке или тексте без учёта регистра, включая кириллицу; пустой запрос показывает все заметки, ненайденный — сообщение «Ничего не найдено», введённый запрос остаётся в поле, рядом ссылка сброса.

</frozen-after-approval>

## Implementation Notes

Oneshot: изменение небольшое (около 60 строк в `app/db.py`, `app/main.py`, `app/templates/index.html`, `app/static/style.css` и тестах), без новых зависимостей и изменений схемы.

SQLite `LIKE` и встроенный `lower()` не приводят к нижнему регистру кириллицу, поэтому поиск в `db.search_notes` использует Python-функцию `casefold`, зарегистрированную в соединении через `create_function`, и `instr` вместо `LIKE` — это заодно избавляет от экранирования `%` и `_`.

## Verification

**Commands:**
- `uv run pytest` -- expected: все тесты проходят, включая новые тесты поиска

## Review Triage Log

Проход 1 (quick): high 0, medium 0, low 2, false 0, maybe-false 0.

- low, patch — `tests/test_notes.py`: ссылка «Сбросить» не покрыта тестами. Добавлены проверки её наличия при `q` и отсутствия при пустом запросе.
- low, patch — `app/static/style.css`: `.search input` без `min-width: 0` не сжимается в flex-строке, и строка поиска переполняется на ширине около 320px. Добавлен `min-width: 0`.
