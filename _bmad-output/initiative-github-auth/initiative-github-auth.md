---
type: initiative
title: "Вход через GitHub"
parent: none
covers: [CAP-1, CAP-2, CAP-3, CAP-4]
after: []
assignee: ""
risk: medium
---

# Вход через GitHub

## Description

Каждый человек входит в приложение заметок своим GitHub-аккаунтом, видит только свои заметки и может выйти; заметки, накопленные до появления входа, не теряются. Возможности, ограничения и non-goals — в спецификации `spec-github-auth`.

## Outcome

Приложением могут пользоваться несколько человек, не видя заметок друг друга; сигнал — success signal спецификации.

## Done when

1. Success signal спецификации проходит вручную на http://127.0.0.1:8000 с двумя реальными GitHub-аккаунтами.
2. CAP-1…CAP-4 работают без флагов и обходных путей.
3. Прежние заметки из `notes.db` целы и принадлежат первому вошедшему.

## Boundaries

Одна эпика `epic-github-auth`: работа укладывается в одно приложение (`app/`, `seed.py`, тесты) и одного владельца. Non-goals — в спецификации.

- Touch point: GitHub OAuth App — уже зарегистрирован с callback http://127.0.0.1:8000/auth/callback, только потребляется; owner: epic-github-auth
- Touch point: `.env` — читаются `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`, `SESSION_SECRET`, уже заполнены; owner: epic-github-auth
- Touch point: `notes.db` (путь из `NOTES_DB`) — меняется схема, данные сохраняются; owner: epic-github-auth

## References

- spec — _bmad-output/initiative-github-auth/spec-github-auth/spec-github-auth.md
- constraint — та же спецификация, раздел Constraints

## Notes

- Decision: одна эпика на всю инициативу — один модуль и один владелец (2026-10-07).
- Decision: платформенной базовой эпики нет — приложение, тесты и запуск уже есть (2026-10-07).
- Decision: доставка — локальный запуск на http://127.0.0.1:8000 и коммит в main; деплой — non-goal спецификации (2026-10-07).
