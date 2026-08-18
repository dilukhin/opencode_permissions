# Stage 0 — final remote-config activation check

Статус: ready for local execution after merge  
Проект: `dilukhin/opencode_permissions`  
Target runtime: OpenCode `1.18.18`  
Назначение: снять последний material residual uncertainty Stage 0 — активны ли remote permission-config layers.

## 1. Почему нужен этот шаг

Exact OpenCode 1.18.18 source показывает два remote config paths, способных добавлять/override permission rules:

1. well-known remote config — только если effective auth store содержит entry `type=wellknown`;
2. account/org remote config — только если current account state имеет active organization.

Получать сам remote config, tokens, provider IDs, account IDs или URLs для Stage 0 не требуется.

Для safe presence-only проверки используется:

```text
tools/stage0_remote_activation_extract.py
```

Он читает secret-bearing local structures внутри процесса, но наружу выдаёт только booleans/status и metadata без identifiers/secrets.

## 2. Exact semantics source

Для target 1.18.18:

- auth store: `Global.Path.data/auth.json`;
- `Global.Path.data`: `XDG_DATA_HOME/opencode` или `~/.local/share/opencode`;
- `OPENCODE_AUTH_CONTENT`, если присутствует, заменяет file auth source;
- well-known remote path активируется только для auth entry с `type=wellknown`;
- account state хранится в OpenCode SQLite database;
- account remote config path выполняется только при `active_org_id`;
- `OPENCODE_DB` может переопределять database path.

## 3. Preconditions

1. Работать из canonical local checkout `dilukhin/opencode_permissions`.
2. Прочитать `AGENTS.md` и local `../docs/workspace_layout_local.md`.
3. Проверить branch/HEAD/tracked state.
4. Обновить `main` только `git pull --ff-only`, если branch=`main`, tracked tree clean, remote canonical и update fast-forward.
5. Не использовать reset/clean/stash/rebase/force.
6. Убедиться, что `tools/stage0_remote_activation_extract.py` и его tests присутствуют.
7. Не удалять D04 fixture и существующие `__pycache__` residues.

## 4. Exact action

Из repo root выполнить ровно:

```powershell
python tools/stage0_remote_activation_extract.py --output ..\evidence\stage0\stage0_remote_config_activation_20260818.json
```

Если фактическая дата отличается, изменить только suffix даты.

Не печатать output в terminal без необходимости. После запуска читать только sanitized JSON.

## 5. Что проверить и вернуть

Проверить:

```text
schema == 1
raw_auth_retained == false
secret_values_retained == false
account_identifier_values_retained == false
environment_values_retained == false
```

Вернуть только sanitized поля:

```text
environment_presence.OPENCODE_AUTH_CONTENT
environment_presence.OPENCODE_DB
auth.status
auth.wellknown_auth_present
account_database_source
account_databases[*].name
account_databases[*].status
account_databases[*].active_account_present
account_databases[*].active_org_present
remote_activation.wellknown_remote_possible
remote_activation.account_remote_possible
remote_activation.remote_permission_layer_activation_observed
remote_activation.fully_determined
```

Не возвращать raw auth, provider/server keys, URL, token, account ID, org ID или database row contents.

## 6. Decision interpretation

### Candidate for Stage 0 closure

Если:

```text
remote_activation.fully_determined == true
remote_activation.remote_permission_layer_activation_observed == false
```

то remote permission layer не активирован по локально проверяемым activation conditions; вернуть evidence Web для final closure.

### Blocking residual

Если:

```text
remote_permission_layer_activation_observed == true
```

или:

```text
fully_determined == false
```

не получать remote config и не раскрывать secret-bearing sources. Остановиться и вернуть sanitized evidence Web.

Примеры blocking residual:

- `OPENCODE_AUTH_CONTENT` present;
- well-known auth present;
- active organization present;
- `OPENCODE_DB=:memory:`;
- auth/database parse/read failure.

## 7. Forbidden

Не:

- открывать `auth.json` вручную через read/editor/Get-Content/type/cat;
- печатать auth/account/database contents;
- читать tokens, URLs, provider IDs, account IDs, org IDs;
- запускать `opencode debug config` / `--resolved-permissions`;
- запрашивать remote config/network endpoints;
- менять auth/account/config/permission state;
- использовать `--auto`/`always`;
- делать SSH/remote probe;
- обходить sanitizer другим parser/script;
- удалять residues.

## 8. Report

Передать ChatGPT Web:

1. `stage0_remote_config_activation_<YYYYMMDD>.json`;
2. краткий report:

```text
Environment
- repo / branch / HEAD
- OpenCode version

Extraction
- exit code
- schema
- four retained=false safety flags

Activation evidence
- OPENCODE_AUTH_CONTENT presence only
- OPENCODE_DB presence only
- auth status / wellknown boolean
- database sanitized states
- remote_activation booleans

Safety
- raw auth not displayed
- no identifiers/tokens/URLs displayed
- no remote/config/debug call
- no mutation

Git status
- tracked state
- pre-existing residues only

Decision needed from Web
- none | exact blocking residual
```

## 9. Acceptance

Шаг пригоден для final Stage 0 review, если:

- target version/repo state подтверждены;
- sanitizer завершился без утечки raw/secret/identifier values;
- activation booleans имеют determined result либо точный blocking residual;
- remote config не извлекался;
- tracked repository state не изменён;
- stop conditions не обходились.

Только ChatGPT Web после evidence закрывает или не закрывает Stage 0.
