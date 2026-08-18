# Stage 0 — sanitized permission config evidence task

Статус: ready for local execution after merge  
Проект: `dilukhin/opencode_permissions`  
Target runtime: OpenCode `1.18.18`  
Назначение: закрыть последний gap Stage 0 по локальным effective permission/config layers без raw resolved-config bootstrap.

## 1. Почему нужен этот шаг

Stage 0A.1 подтвердил наличие стандартных user-global config candidates и отсутствие project/`OPENCODE_CONFIG*` overrides, но по safety contract не читал их contents.

Stage 0B доказал, что `opencode --pure debug config` в 1.18.18 не является read-only mechanism и поэтому не разрешён для 0A.2.

Stage 0D уже дал runtime prompt baseline. Перед Native-policy gate остаётся установить фактические permission-related поля локальных global config files, не раскрывая provider/auth/model/prompt/instructions/secrets.

Для этого используется отдельный extractor:

```text
tools/stage0_permission_config_extract.py
```

Он не запускает OpenCode и не получает resolved config.

## 2. Safety boundary extractor

Extractor:

- читает только файлы с basename `opencode.json` или `opencode.jsonc`;
- поддерживает JSON и JSONC comments/trailing commas;
- наружу сохраняет только:
  - `permission`;
  - `permissions`, если присутствует;
  - `default_agent`;
  - per-agent `permission` / `permissions` / `mode`;
  - file metadata/status;
- не сохраняет raw config text;
- не выводит provider/model/prompt/instructions;
- при parse error выдаёт только тип ошибки и line/column;
- при явном secret-like marker внутри permission view отказывается выдавать view;
- не читает `auth.json`, `.env`, logs или произвольный другой filename.

Raw source config agent/model напрямую не читает.

## 3. Preconditions

1. Работать из canonical local checkout `dilukhin/opencode_permissions`.
2. Прочитать `AGENTS.md` и local `../docs/workspace_layout_local.md`.
3. Проверить branch/HEAD/`git status`.
4. Получить актуальный `main` только через `git pull --ff-only`, если:
   - branch = `main`;
   - tracked tree clean;
   - canonical remote подтверждён;
   - операция является fast-forward.
5. Не использовать reset/clean/stash/rebase/force.
6. Убедиться, что committed extractor и tests присутствуют.

Untracked `__pycache__` или оставшийся ignored Stage 0 fixture не удалять ради чистоты.

## 4. Exact local action

Создать только sanitized evidence file вне repository:

```powershell
python tools/stage0_permission_config_extract.py --user-global-defaults --output ..\evidence\stage0\stage0_permission_config_view_20260818.json
```

Если фактическая дата другая, заменить только date suffix.

Не запускать extractor без `--output`, чтобы permission view не печатался в terminal transcript без необходимости.

После команды:

1. проверить exit code;
2. прочитать только созданный sanitized JSON;
3. не открывать исходные `opencode.json/opencode.jsonc` agent/native read tool;
4. проверить `raw_config_retained == false`;
5. для каждого source записать `status`;
6. если `status=ok`, вернуть его `permission_view`;
7. если `refused`, `parse_failed` или `read_failed` — остановить affected path и вернуть только sanitized status/reason; не применять другой parser и не читать raw config вручную.

## 5. Что вернуть ChatGPT Web

Передать файл:

```text
<workspace>/evidence/stage0/stage0_permission_config_view_<YYYYMMDD>.json
```

И краткий report:

```text
Environment
- repo / branch / HEAD
- OpenCode version (только если уже безопасно доступна обычным version check)

Extraction
- command exit code
- source statuses
- raw_config_retained

Permission view
- sanitized permission/default-agent fields ровно из output

Safety
- raw configs not displayed to agent
- no auth/log/.env reads
- no OpenCode debug/resolved-config call
- no config mutation
- no --auto/always

Git status
- tracked state
- существующие untracked/ignored residues перечислить, но не удалять

Decision needed from Web
- none | exact sanitized failure
```

## 6. Forbidden actions

Не:

- запускать `opencode debug config` / `--resolved-permissions`;
- читать или копировать `auth.json`;
- открывать raw global config через native read/editor ради проверки extractor;
- печатать raw config в PowerShell;
- использовать `Get-Content`, `type`, `cat`, Python/Node one-liner для обхода sanitizer;
- модифицировать global/project OpenCode config;
- удалять D04 fixture или `__pycache__` в рамках этого шага;
- менять permission policy;
- использовать `--auto` или `always`;
- делать remote/ssh probe.

Если sanitizer отказывается публиковать view — это корректный stop result, а не повод обходить его.

## 7. Acceptance

Шаг пригоден для final Stage 0 review, если:

- оба standard user-global candidates имеют явный sanitized status;
- при `ok` наружу вышли только permission-related поля;
- raw config не отображался агенту и не попал в evidence;
- `raw_config_retained=false`;
- config не изменён;
- tracked repository state не изменён;
- stop conditions не обходились.

После этого только ChatGPT Web определяет, достаточно ли evidence для закрытия Stage 0 и перехода к Native-policy gate.
