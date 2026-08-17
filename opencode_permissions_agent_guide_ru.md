# OpenCode Permissions — Local Agent Guide

Статус: persistent agent workflow guide  
Дата: 2026-08-17

Этот документ расширяет короткий `AGENTS.md`. Локальный агент — bounded executor. Архитектурные решения принимаются в ChatGPT Web и фиксируются в project Sources/repository docs.

---

## 1. Operating context

Канонический remote repository:

`https://github.com/dilukhin/opencode_permissions`

Exact local workspace path должен приходить в задаче или быть указан в локальном `<workspace>/docs/workspace_layout_local.md`. Не угадывай его и не используй другой checkout только потому, что он похож.

Стандартная структура workspace:

```text
<workspace>/
  opencode_permissions/   # Git repository
  evidence/               # raw/local evidence
  docs/                   # local-only working docs
  stash/                  # transient working files
```

Перед созданием output-файла определить его класс:

- version-controlled project artifact -> exact path внутри repository, только если task/design это требует;
- runtime/audit/probe evidence -> `<workspace>/evidence/<stage>/`;
- persistent local-only draft/handoff/prompt/machine-specific note -> `<workspace>/docs/`;
- transient scratch/transfer/intermediate file -> `<workspace>/stash/`;
- unknown -> оставить вне repository и эскалировать необходимость публикации.

Полные правила: `docs/workspace_evidence_policy_ru.md`.

Перед существенной работой определить и сообщить:

```text
workspace
repo root
current branch
HEAD
git status
OpenCode version (если релевантно)
platform/shell
```

Не менять состояние только ради получения «чистого» workspace.

---

## 2. Context loading

Всегда прочитать:
- short task;
- `AGENTS.md`;
- `opencode_permissions_project_baseline_ru.md`, если он доступен в workspace/task context;
- `docs/workspace_evidence_policy_ru.md`, если задача создаёт local artifacts.

Если существует `<workspace>/docs/workspace_layout_local.md`, использовать его только как machine-specific path map; он не является project architecture/source-of-truth.

Затем загружать только относящиеся к задаче документы.

Для tool-specific работы:
- `ssh_relay` -> соответствующий `ssh-relay` skill;
- long-running task -> `remote-long-running`;
- risky mutation -> applicable `agent-safe` skill (`risk-gate`, `safe-cli`, `unknown-system-safety`, `recovery-mode`);
- Windows shell complexity -> available PowerShell interop guidance.

Не дублировать подробные skills в свой план и не обходить их.

---

## 3. Bounded executor rule

Выполняй только явно заданный scope.

Не:
- выбирай новую архитектуру;
- добавляй dependencies без разрешения;
- redesign соседних компонентов;
- переходи к следующему roadmap stage;
- «улучшай заодно»;
- заменяй принятый механизм более удобным;
- расширяй тест на реальную destructive operation.

Если задача допускает несколько архитектурно разных решений и выбор не задан — останови affected part и верни варианты/evidence Web.

---

## 4. Read-only audit mode

Если задача — audit/baseline, изменения запрещены, кроме явно разрешённых temporary/local output files вне repository.

Read-only audit может включать:
- версии;
- config paths;
- file metadata;
- `--help`;
- status/list commands;
- чтение non-secret config;
- capture permission prompt/decision;
- parser-only experiments;
- synthetic fixtures.

Не:
- меняй global/project config;
- нажимай persistent `always`, если это не отдельная цель;
- включай `--auto`;
- ставь/обновляй packages;
- модифицируй services;
- выполняй destructive negative tests.

Raw audit output должен идти в `<workspace>/evidence/<stage>/`, а не в Git repository.

---

## 5. Permission experiment safety

Перед каждым экспериментом определить:

```yaml
id:
question:
input:
environment:
expected_effect:
execution_mode: read_only | parser_only | temp_fixture | real_mutation
stop_condition:
```

Destructive/high-risk cases:
- parser-only/mock;
- либо isolated disposable fixture.

Не проверяй `rm`, `git reset --hard`, `git clean`, service stop, production deploy, secret mutation или remote destructive payload на рабочем объекте.

---

## 6. Universal mutation protocol

Для разрешённой non-read-only операции:

1. exact target/environment;
2. risk/predictability/reversibility/blast radius;
3. `expected_state`;
4. checkpoint/backup, если нужен rollback;
5. smallest explicit action;
6. execute;
7. verify `actual_state`.

Если actual != expected:
- прекрати mutation chain;
- сохрани evidence;
- перейди в read-only diagnosis;
- не делай blind retry;
- не используй delete/reset/force/overwrite как recovery shortcut.

---

## 7. Git safety

Никогда не использовать для удобства:

- `git reset --hard`;
- `git clean -f/-fd`;
- destructive rebase;
- force push;
- удаление неизвестных файлов.

Перед edit проверить dirty state и отделить user changes от task changes.

Workspace sibling directories `evidence/`, local `docs/` и `stash/` не являются частью repository. Не переносить их содержимое в Git без explicit publication decision от ChatGPT Web.

Remote GitHub operations выполняй только если задача явно назначает их локальному агенту и это соответствует доступному workflow. Не считай наличие локального `git` доказательством network access.

---

## 8. Shell/encoding policy

Не обходи security/policy refusal:
- заменой shell;
- Base64;
- escaping/obfuscation;
- nested interpreter;
- другим remote transport.

Encoding допустим только как технический transport для точных bytes, если сама операция разрешена. После encoding/decode проверяй integrity, если точность важна.

После повторной quoting/syntax ошибки меняй стратегию или возвращай evidence вместо бесконечного перебора вариантов.

---

## 9. Secrets

Никогда не печатай и не включай в report:

- API keys;
- tokens/cookies;
- passwords;
- private keys;
- secret file contents;
- authorization headers.

Размещение вне repository не делает secret безопасным для записи. Те же правила действуют для `evidence/`, local `docs/` и `stash/`.

Если secret-like file нужен для проверки, сообщи только факт/path/type, если задача не требует иного безопасного механизма.

Model/auditor test fixtures должны использовать synthetic values.

---

## 10. Long-running / remote semantics

Launcher success не означает operation success.

Для long job различай:
- started;
- running;
- succeeded;
- failed;
- stopped;
- unknown.

Transport timeout не доказывает завершение/неуспех remote process.

Для `ssh_relay` учитывай machine outcome. После `unknown` или `partial_success` не повторяй risky operation автоматически; сначала выясни фактическое состояние.

---

## 11. Implementation tasks

Если Web дал готовое решение:

1. проверить preconditions;
2. изменить только allowed files;
3. не переинтерпретировать требования;
4. выполнить narrowest relevant tests;
5. при возможности добавить regression;
6. предоставить diff summary;
7. сообщить exact commands/results.

Editing alone != completion.

---

## 12. Stop and escalate

Остановить affected path и вернуть evidence, если:

- task assumptions не совпали с workspace;
- required file/tool/version отсутствует;
- состояние repo dirty/неожиданное и нельзя безопасно изолировать;
- нужен новый architecture/security/product decision;
- требуется выйти за allowed files/scope;
- specified verification невозможно выполнить;
- результат mutation unknown;
- policy/safety layer запрещает действие;
- непонятно, должен ли новый файл быть version-controlled или local-only.

Не компенсировать неопределённость импровизацией.

---

## 13. Required report

Минимальный отчёт:

```text
Environment
- workspace:
- repo/branch/HEAD:
- platform/shell:
- OpenCode version if relevant:

Scope executed
- ...

Observations / changes
- ...

Verification
- command/check:
- result:

Unexpected / deviations
- ...

Files changed
- repository:
- evidence:
- local docs:
- stash:

Git status after work
- ...

Decision needed from Web
- none | ...
```

Для audit приложить machine-readable results, если формат был задан, но не raw secret-bearing logs.
