# Stage 0 — Baseline / audit gate

Статус: design approved for execution after merge  
Проект: `dilukhin/opencode_permissions`  
Назначение: зафиксировать фактическую permission semantics исследуемой установки OpenCode до изменения policy или реализации classifier.

## 1. Gate objective

Stage 0 должен ответить на вопрос:

> Что фактически установлено, какие permission/config layers реально действуют, какие prompts возникают и где native permission layer уже достаточен или принципиально неоднозначен?

Stage 0 **не** реализует classifier, model auditor, custom approval UI или deployment через `opencode_setup`.

Gate закрывается только evidence, а не планом.

---

## 2. Важная развилка V1 / V2

Поведение OpenCode version-sensitive.

На момент проектирования официальная документация разделяет:

- стабильную линию V1, запускаемую как `opencode`, с `permission` и permission key `bash`;
- OpenCode 2.0 beta, устанавливаемый отдельно как `opencode2`, с новой rule schema `permissions` и action `shell`.

Это наблюдение необходимо **перепроверять в момент аудита**. Нельзя смешивать результаты V1 и V2.

По умолчанию Stage 0 исследует тот `opencode`, которым пользователь реально выполняет работу. Наличие `opencode2` фиксируется как inventory; отдельный V2 pilot не запускается без явного решения.

---

## 3. Stage 0 sub-gates

### 0A. Local inventory

Цель — получить безопасный машинный снимок без изменения рабочей конфигурации.

Нужно установить:

1. platform/shell;
2. путь и версию `opencode`;
3. наличие/версию `opencode2`;
4. path-based hint способа установки без попытки reconcile;
5. стандартные/global/custom/project config candidates;
6. наличие `OPENCODE_CONFIG`, `OPENCODE_CONFIG_DIR`, `OPENCODE_CONFIG_CONTENT` без раскрытия inline content;
7. доступность `--pure`/`debug`;
8. resolved permission view, только если её можно получить без загрузки внешних plugins;
9. agent-specific permission layers;
10. Git worktree для target directory.

Canonical tool: `tools/stage0_inventory.py`.

### 0B. Version-locked source audit

После 0A ChatGPT Web должен для **точной установленной версии** проверить:

- официальную документацию;
- upstream source/tests этой версии при недостатке или противоречии docs;
- config precedence;
- matcher semantics;
- default rules;
- `always/once/reject` semantics;
- external-directory enforcement;
- agent/subagent permission behavior;
- relevant plugin/custom-tool hooks.

Результат фиксируется как version-specific findings/report, а не в persistent baseline.

### 0C. Isolated native permission probes

После 0B формируется минимальный набор runtime probes только для вопросов, которые нельзя надёжно закрыть source audit.

Принципы:

- не менять активный global/project config;
- использовать `OPENCODE_CONFIG`/isolated config и disposable workspace, если версия это поддерживает;
- не использовать реальные destructive targets;
- dangerous command strings допускаются только при доказанном harmless shim/parser-only механизме;
- не использовать `--auto`;
- не выбирать `always`, пока сам механизм `always` не является предметом конкретного safe probe;
- фиксировать exact input, decision, suggested patterns и фактическое выполнение/неисполнение.

### 0D. Real workflow prompt baseline

На реальном development scenario собрать baseline обычного цикла:

- read/search;
- Git read;
- edit/write;
- build;
- unit tests;
- diagnostics;
- external directory, если реальный workflow его использует;
- `ssh_relay`, если он используется данным workflow.

Собирать только permission-level evidence. Не переносить в отчёт секреты, stdout с чувствительными данными или raw logs целиком.

---

## 4. Research questions

Stage 0 должен закрыть либо явно пометить `not_applicable` следующие вопросы.

### Environment/config

- Какая exact версия фактически запускается?
- Какой executable реально найден первым?
- Какой shell используется OpenCode на Windows?
- Какие config sources существуют и какие из них участвуют в effective config?
- Каков version-specific precedence/merge order?
- Есть ли agent-specific permission overrides?

### Native permission matching

- Что является resource/pattern для shell permission данной версии?
- Разбираются ли compound commands или match идёт по raw text?
- Как обрабатываются `&&`, `||`, `;`, pipelines и redirects?
- Что происходит с nested interpreters (`python -c`, PowerShell `-Command`, `cmd /c`, `bash -c`)?
- Как формируется suggested pattern для `always`?
- Last-match/override semantics совпадает ли с документацией установленной версии?

### Filesystem boundary

- Что именно считается project/worktree root?
- Какие tool paths вызывают `external_directory`?
- Применяется ли external-directory enforcement к shell side effects или только к структурированным path inputs/workdir?
- Как ведёт себя запуск из общего родителя нескольких repositories?

### Extensibility

- Может ли custom tool заменить/дополнить shell gate в исследуемой версии?
- Какие `tool.execute.before/after` и permission-related hooks реально существуют в target version?
- Может ли plugin инициировать native approval после собственного анализа, или только allow-by-continuation / hard failure?
- Можно ли изолировать auditor от execution tools?

Эти вопросы не являются утверждением, что соответствующая capability существует.

---

## 5. Evidence model

Для каждого утверждения использовать один из типов:

```text
runtime_observation
resolved_config
official_docs
upstream_source
upstream_test
isolated_probe
real_workflow_observation
```

Запись observation:

```yaml
id:
question:
opencode_version:
platform:
environment:
input:
observed_result:
evidence_type:
source_or_artifact:
confidence:
notes:
```

`confidence`:

- `high` — воспроизводимый runtime/source/test evidence;
- `medium` — official docs без version-locked source confirmation;
- `low` — inference/path hint/historical evidence.

---

## 6. Local inventory safety contract

`tools/stage0_inventory.py` обязан оставаться read-only.

Он не должен:

- читать `auth.json`;
- читать OpenCode logs;
- читать contents обычных config-файлов;
- печатать `OPENCODE_CONFIG_CONTENT`;
- запускать package upgrade/install;
- менять config;
- запускать agent/model requests;
- включать `--auto`;
- выполнять permission test commands.

Допустимо:

- `--version`;
- `--help`;
- path discovery;
- file existence/size/mtime metadata;
- `git rev-parse --show-toplevel`;
- `opencode --pure debug config` только если target CLI явно поддерживает `--pure`.

Даже при resolved-config probe сохраняются только:

- `permission` / `permissions`;
- `default_agent`;
- per-agent `permission` / `permissions` / `mode`.

Raw resolved config отбрасывается.

---

## 7. Permission corpus

Canonical corpus: `tests/permission_cases/` (manifest + machine-readable case files).

Его `expected_decision` в Stage 0 означает **консервативное safety expectation**, а не окончательную оптимизированную policy.

Поле `optimization_candidate=true` означает, что последующий Native-policy gate должен исследовать возможность безопасного перехода от `ask` к `allow` или более точной маршрутизации.

Dangerous cases с `execution_policy=parser_only` запрещено исполнять на рабочей машине.

---

## 8. Stage 0 artifacts

### В репозитории

- `docs/stage0_baseline_audit_ru.md` — этот design/gate contract;
- `tests/permission_cases/` — corpus manifest and case files;
- `tools/stage0_inventory.py` — read-only inventory;
- `tests/test_stage0_inventory.py` — regression tests inventory safety/extraction.

### Локальный evidence/report

Рекомендуемые имена вне normative docs:

```text
stage0_inventory_<date>.json
stage0_resolved_permissions_<date>.json
stage0_local_audit_report_<date>.md
```

Такие файлы не становятся source-of-truth автоматически. Перед публикацией в GitHub нужно проверить отсутствие sensitive data.

---

## 9. 0A execution

Из local checkout `opencode_permissions`:

```text
python tools/stage0_inventory.py --project-dir . --output stage0_inventory.json
python tools/stage0_inventory.py --project-dir . --resolved-permissions --output stage0_permissions_inventory.json
```

Вторая команда сама пропускает resolved-config probe, если CLI не рекламирует `--pure`.

После выполнения агент должен проверить JSON только на структурную корректность и отсутствие secret values; не дополнять недостающие данные чтением auth/log files.

---

## 10. Stop conditions

0A агент прекращает affected path и сообщает evidence, если:

- current directory не является ожидаемым repository;
- script отсутствует или отличается от committed version;
- `opencode --version` зависает/падает необычным образом;
- для получения данных требуется install/update/config mutation;
- `--pure debug config` недоступен;
- resolved output нельзя безопасно распарсить;
- обнаружена необходимость читать secret-like file;
- target state отличается от assumptions задания.

Пропущенный unsafe probe — корректный результат, а не причина обходить ограничение.

---

## 11. Gate acceptance

Stage 0 закрыт только если:

1. exact target binary/version/platform зафиксированы;
2. effective permission/config layers установлены с достаточным evidence;
3. version-locked native matcher semantics описаны;
4. corpus покрывает минимум safe read/Git/build/test, writes/deletes, destructive Git, privilege/services, secrets, compound/nested, external directory, remote и unknown CLI;
5. опасные cases не исполнялись разрушительно;
6. baseline реальных routine prompts собран;
7. вопросы, влияющие на Native-policy gate, имеют `confirmed`, `not_applicable` или явно сформулированный residual uncertainty;
8. `unsafe_test_allow_count = 0` для реально выполненных probes;
9. сформирован список native-policy gaps без начала classifier implementation.

После closure следующий этап — **Native-policy gate**. Parser/classifier до этого не реализуется.
