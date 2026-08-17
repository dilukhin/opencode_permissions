# Stage 0A.1 — шаблон задания локальному агенту

Назначение: deterministic read-only minimal inventory. Это не архитектурная задача.

## Scope

Рабочий repository — текущий checkout. До выполнения докажи, что remote/repo соответствует `dilukhin/opencode_permissions` и что committed `tools/stage0_inventory.py` доступен.

Стандартный layout:

```text
<workspace>/
  opencode_permissions/   # Git repository
  evidence/
    stage0/               # raw local evidence
```

Прочитай:

1. `AGENTS.md`;
2. `opencode_permissions_agent_guide_ru.md`;
3. `docs/workspace_evidence_policy_ru.md`;
4. `docs/stage0_baseline_audit_ru.md`.

Не переходи к 0A.2/0B/0C/0D и не меняй OpenCode config.

## Выполнить

1. Зафиксировать workspace root, repo root, branch, HEAD, `git status`.
2. Создать `<workspace>/evidence/stage0/`, если каталога ещё нет. Это разрешённый workspace-only output directory; он находится вне Git repository.
3. Запустить **только** inventory tool, записав результат вне repository. Для стандартного Windows layout из корня репозитория:

```text
python tools/stage0_inventory.py --project-dir . --output ..\evidence\stage0\stage0_inventory.json
```

Эквивалентный абсолютный output path допустим, если он указывает именно на `<workspace>/evidence/stage0/`.

4. Проверить, что output — валидный JSON.
5. Проверить, что output не содержит API keys, tokens, passwords, private keys или `OPENCODE_CONFIG_CONTENT` value.
6. Не читать `auth.json`, OpenCode logs и secret-like files.
7. Не запускать `--resolved-permissions`; это отдельный 0A.2 только после version-lock и явного задания ChatGPT Web.
8. Не выполнять install/update, `--auto`, model/agent prompts или permission test commands.
9. Не исправлять найденные config/installation проблемы.
10. Не копировать raw evidence в repository и не выполнять `git add` для него.

## Acceptance

Отчёт должен содержать только:

```text
Environment
- workspace root
- repo root / branch / HEAD
- platform/shell
- opencode path/version
- opencode2 presence/version

Config inventory
- existing config paths (metadata only)
- OPENCODE_CONFIG* presence flags
- advertised CLI capabilities

Unexpected / skipped
- exact reason

Artifact
- <workspace>/evidence/stage0/stage0_inventory.json

Git status after work
- repository должен остаться без новых raw evidence files

Decision needed from Web
- none | exact blocker
```

Если состояние неожиданное — остановить affected path и вернуть evidence, не импровизировать.
