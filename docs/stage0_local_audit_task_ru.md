# Stage 0A — шаблон задания локальному агенту

Назначение: deterministic read-only inventory. Это не архитектурная задача.

## Scope

Рабочий repository — текущий checkout. До выполнения докажи, что remote/repo соответствует `dilukhin/opencode_permissions` и что committed `tools/stage0_inventory.py` доступен.

Прочитай:

1. `AGENTS.md`;
2. `opencode_permissions_agent_guide_ru.md`;
3. `docs/stage0_baseline_audit_ru.md`.

Не переходи к Stage 0B/0C/0D и не меняй OpenCode config.

## Выполнить

1. Зафиксировать repo root, branch, HEAD, `git status`.
2. Запустить:

```text
python tools/stage0_inventory.py --project-dir . --output stage0_inventory.json
python tools/stage0_inventory.py --project-dir . --resolved-permissions --output stage0_permissions_inventory.json
```

3. Проверить, что оба output — валидный JSON.
4. Проверить, что output не содержит API keys, tokens, passwords, private keys, `OPENCODE_CONFIG_CONTENT` value или raw provider config.
5. Не читать `auth.json`, OpenCode logs и secret-like files.
6. Не выполнять install/update, `--auto`, model/agent prompts или destructive permission tests.
7. Не исправлять найденные config/installation проблемы.

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
- resolved_permissions status
- permission-related view, если script безопасно получил её

Unexpected / skipped
- exact reason

Artifacts
- stage0_inventory.json
- stage0_permissions_inventory.json

Git status after work
- ожидаются только два явно созданных evidence files

Decision needed from Web
- none | exact blocker
```

Если состояние неожиданное — остановить affected path и вернуть evidence, не импровизировать.
