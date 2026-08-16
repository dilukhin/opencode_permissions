# Stage 0A.1 — шаблон задания локальному агенту

Назначение: deterministic read-only minimal inventory. Это не архитектурная задача.

## Scope

Рабочий repository — текущий checkout. До выполнения докажи, что remote/repo соответствует `dilukhin/opencode_permissions` и что committed `tools/stage0_inventory.py` доступен.

Прочитай:

1. `AGENTS.md`;
2. `opencode_permissions_agent_guide_ru.md`;
3. `docs/stage0_baseline_audit_ru.md`.

Не переходи к 0A.2/0B/0C/0D и не меняй OpenCode config.

## Выполнить

1. Зафиксировать repo root, branch, HEAD, `git status`.
2. Запустить **только**:

```text
python tools/stage0_inventory.py --project-dir . --output stage0_inventory.json
```

3. Проверить, что output — валидный JSON.
4. Проверить, что output не содержит API keys, tokens, passwords, private keys или `OPENCODE_CONFIG_CONTENT` value.
5. Не читать `auth.json`, OpenCode logs и secret-like files.
6. Не запускать `--resolved-permissions`; это отдельный 0A.2 только после version-lock и явного задания ChatGPT Web.
7. Не выполнять install/update, `--auto`, model/agent prompts или permission test commands.
8. Не исправлять найденные config/installation проблемы.

## Acceptance

Отчёт должен содержать только:

```text
Environment
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
- stage0_inventory.json

Git status after work
- ожидается только один явно созданный evidence file

Decision needed from Web
- none | exact blocker
```

Если состояние неожиданное — остановить affected path и вернуть evidence, не импровизировать.
