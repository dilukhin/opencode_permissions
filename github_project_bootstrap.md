---
document_type: github_project_bootstrap
version: 2.0
status: active
language: ru
updated_at: 2026-08-16
---

# GitHub: bootstrap проекта ChatGPT

## Настройка

```yaml
target_repository:
  full_name: dilukhin/opencode_permissions
  default_branch: main
knowledge_repository:
  full_name: dilukhin/github-connector-knowledge
  default_branch: main
  runtime_bundle_path: dist/projects/dilukhin__opencode_permissions.md
  incident_directory: src/incidents/dilukhin__opencode_permissions/
```

Этот файл задаёт project-specific GitHub bootstrap. Архитектурная policy проекта находится в `opencode_permissions_project_baseline_ru.md`.

## Начало GitHub-задачи

1. Использовать GitHub Connector первым.
2. Не запускать `git` или `gh` как пробу remote-доступа.
3. Через Connector попытаться прочитать `runtime_bundle_path`.
4. Проверить, что bundle относится к `target_repository`.
5. Применять bundle как рабочий GitHub-regламент.
6. Если bundle ещё не сгенерирован/недоступен, использовать минимальные правила ниже; отсутствие bundle само по себе не является дефектом `opencode_permissions`.

## Минимальные правила

- Connector — первичный remote-транспорт.
- Локальный Git — только подтверждённый checkout, diff/history/tests либо доказанный Connector gap.
- Для multi-file publication предпочтителен verified Git Data flow `blob -> tree -> commit -> ref`, когда доступен.
- Перед `update_ref` перечитать HEAD.
- Не force-update `main`, protected branch, чужую/неизвестную ветку.
- После значимого write выполнить targeted read-back через Connector.
- После 4xx/truncation/unsupported operation изменить стратегию, не повторять идентичный запрос вслепую.
- CI/check state подтверждать специализированными GitHub данными, а не предположением.
- Не включать secrets или лишние фрагменты закрытого кода в incident/report.

## Новое наблюдение

Публиковать knowledge incident только если обнаружена новая проблема/обход GitHub Connector, которой нет в runtime bundle, либо изменившееся поведение известного правила.

Предпочтительная схема:

```text
knowledge repository
-> branch incident/YYYYMMDD-opencode_permissions-<fingerprint>
-> one new YAML incident
-> commit -> PR -> checks -> merge -> read-back
```

Прямое изменение knowledge `main` по умолчанию не использовать.

## Fallback при невозможности knowledge-write

1. Не переходить автоматически к `git`/`gh`.
2. Зафиксировать требуемую Connector operation и точную ошибку.
3. Создать локальный/чат-артефакт:
   `pending_github_incident_<UTC>_opencode_permissions_<fingerprint>.yaml`.
4. Не включать secrets.
5. После восстановления доступа проверить duplicate по fingerprint и импортировать через PR.

## Завершение GitHub-задачи

Подтвердить GitHub-side итог и указать, появились ли новые неучтённые замечания по Connector workflow.
