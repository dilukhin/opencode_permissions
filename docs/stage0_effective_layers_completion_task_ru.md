# Stage 0 — completion check effective permission layers

Статус: ready for local execution after merge  
Проект: `dilukhin/opencode_permissions`  
Target runtime: OpenCode `1.18.18`  
Назначение: закрыть оставшиеся локально проверяемые permission-capable layers перед финальным Stage 0 review.

## 1. Почему нужен этот шаг

Предыдущий sanitized extract подтвердил `~/.config/opencode/opencode.json` и `opencode.jsonc`, но exact OpenCode 1.18.18 source показывает ещё три relevant inputs:

1. legacy global `~/.config/opencode/config.json`, который загружается перед `opencode.json`/`opencode.jsonc`;
2. managed config directory (`%ProgramData%\opencode` на Windows), где позже загружаются `opencode.json` и `opencode.jsonc`;
3. `OPENCODE_PERMISSION`, который final-merge-ится в permission config.

Значения permission-bearing environment variables нельзя выводить. Достаточно presence-only evidence; если `OPENCODE_PERMISSION` присутствует, Web не должен считать effective policy полностью установленной этим extractor.

Remote well-known/account config не извлекается этим шагом: его получение требует auth/account/runtime paths. Его статус оценивает Web по source audit + runtime observations и фиксирует как bounded residual uncertainty при закрытии gate.

## 2. Preconditions

1. Работать из canonical local checkout `dilukhin/opencode_permissions`.
2. Прочитать `AGENTS.md` и local `../docs/workspace_layout_local.md`.
3. Проверить branch/HEAD/tracked state.
4. Обновить `main` только `git pull --ff-only`, если branch=`main`, tracked tree clean, remote canonical и update fast-forward.
5. Не использовать reset/clean/stash/rebase/force.
6. Убедиться, что `tools/stage0_permission_config_extract.py` поддерживает `--managed-defaults` и schema 2.
7. Не удалять существующие D04 fixture или `__pycache__`.

## 3. Exact action

В repo root выполнить ровно:

```powershell
python tools/stage0_permission_config_extract.py --user-global-defaults --managed-defaults --output ..\evidence\stage0\stage0_effective_permission_layers_20260818.json
```

Если фактическая дата отличается, изменить только date suffix.

Не запускать без `--output`.

## 4. Что проверить в sanitized output

Прочитать только созданный output JSON.

Проверить:

```text
schema == 2
raw_config_retained == false
environment_values_retained == false
```

Вернуть presence booleans для:

```text
OPENCODE_CONFIG
OPENCODE_CONFIG_DIR
OPENCODE_CONFIG_CONTENT
OPENCODE_DISABLE_PROJECT_CONFIG
OPENCODE_PERMISSION
```

Никогда не возвращать значения этих переменных.

Для каждого source вернуть только:

```text
path
status
permission_view (только если status=ok)
```

Ожидаемые source candidates:

```text
~/.config/opencode/config.json
~/.config/opencode/opencode.json
~/.config/opencode/opencode.jsonc
%ProgramData%/opencode/opencode.json
%ProgramData%/opencode/opencode.jsonc
```

`not_found` — нормальный evidence result.

Если `refused`, `parse_failed` или `read_failed` — остановить affected path и вернуть sanitized status/reason. Не читать source вручную.

## 5. Stop condition по OPENCODE_PERMISSION

Если:

```text
environment_presence.OPENCODE_PERMISSION == true
```

не выводить его value и не пытаться парсить env вручную.

Вернуть Web:

```text
blocking_residual: OPENCODE_PERMISSION present; value intentionally not inspected
```

Это не failure extractor и не повод обходить safety boundary.

## 6. Forbidden

Не:

- открывать raw `config.json`, `opencode.json`, `opencode.jsonc` через editor/read/Get-Content/type/cat;
- читать/копировать `auth.json`, `.env`, logs;
- запускать `opencode debug config` или `--resolved-permissions`;
- выводить `OPENCODE_PERMISSION`/`OPENCODE_CONFIG_CONTENT` values;
- модифицировать config или permission policy;
- использовать `--auto`/`always`;
- выполнять remote/ssh probe;
- удалять residues.

## 7. Report

Передать ChatGPT Web:

1. `stage0_effective_permission_layers_<YYYYMMDD>.json`;
2. краткий report:

```text
Environment
- repo / branch / HEAD
- OpenCode version

Extraction
- exit code
- schema
- raw_config_retained
- environment_values_retained

Environment presence
- five booleans only

Sources
- path/status
- permission_view only for ok

Safety
- raw configs not displayed
- env values not displayed
- no auth/log/.env
- no debug/resolved config
- no mutation

Git status
- tracked state
- pre-existing residues only

Decision needed from Web
- none | exact sanitized failure | OPENCODE_PERMISSION presence residual
```

## 8. Acceptance

Шаг пригоден для final Stage 0 review, если:

- global `config.json`, `opencode.json`, `opencode.jsonc` имеют explicit status;
- managed `opencode.json`, `opencode.jsonc` имеют explicit status;
- permission-related env presence зафиксирована без values;
- `raw_config_retained=false`;
- `environment_values_retained=false`;
- raw/secret-bearing sources не отображались;
- tracked repository state не изменён;
- stop conditions не обходились.

После этого только ChatGPT Web закрывает или не закрывает Stage 0.
