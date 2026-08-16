# OpenCode Permissions — Project Baseline

Статус: persistent project baseline  
Дата актуализации: 2026-08-16  
Канонический репозиторий: `https://github.com/dilukhin/opencode_permissions`  
Назначение: устойчивые границы, архитектурные инварианты и критерии проекта.

Этот документ не фиксирует текущий SHA, активную ветку разработки, текущий CI status или установленную версию OpenCode. Эти данные проверяются в момент задачи.

---

## 1. Проблема

OpenCode может останавливаться на большом количестве безопасных и повторяемых действий. Частые prompts ухудшают не только скорость, но и качество контроля: человек привыкает подтверждать длинные команды автоматически.

Проект должен заменить модель:

```text
неизвестная команда -> человек читает shell
```

на:

```text
очевидно безопасно -> ALLOW
очевидно опасно -> DENY
неоднозначно -> автоматический анализ effects
остаточная неопределённость -> ASK_USER
```

Главная цель — не минимизировать prompts любой ценой, а убрать бессмысленные prompts при сохранении технических защитных границ.

---

## 2. Scope

Проект отвечает за:

- исследование реальной семантики OpenCode permissions;
- policy для `allow / ask / deny`;
- классификацию команд и их эффектов;
- parsing составных shell/PowerShell/interpreter операций;
- обработку local и remote command intent/effects;
- формирование осмысленного approval context;
- тестовый корпус permission cases;
- измерение autonomy/safety;
- прототипы custom tool/plugin/gate, если native permissions недостаточны.

Проект не должен по умолчанию становиться:

- установщиком OpenCode;
- универсальным package manager;
- заменой `agent-safe`;
- заменой `ssh_relay`;
- отдельной оболочкой общего назначения;
- production approval UI до подтверждения необходимости.

---

## 3. Границы связанных проектов

### `opencode_permissions`

Владеет вопросом:

> Можно ли автоматически разрешить предполагаемую операцию, нужно ли её заблокировать или привлечь человека?

### `agent-safe`

Владеет вопросом:

> Как безопасно выполнить уже классифицированное рискованное изменение внешнего состояния и доказать его результат?

Используются принципы target, expected state, checkpoint, atomic action, verify, recovery.

### `opencode_setup`

Владеет установкой и reconciliation:

- конфигурации OpenCode;
- managed instructions;
- skills/tools;
- runtime dependencies;
- последующей интеграции итогового permission layer.

`opencode_setup` не должен становиться источником permission policy.

### `ssh_relay`

Владеет remote transport/machine outcome contract. Permission layer должен анализировать смысл remote payload до исполнения и не считать локальный вызов `ssh_relay` автоматически безопасным.

---

## 4. Source-of-truth hierarchy

### Фактическое состояние реализации

```text
1. Current canonical GitHub state
2. Stable project Sources
3. Roadmap / design plans
4. Findings / reports / conversations / memory
```

### Version-sensitive поведение OpenCode

```text
1. Installed/target OpenCode version and observed behavior
2. Official docs for that version
3. Upstream source/tests when docs are insufficient or contradictory
4. Project baseline
5. Historical findings
```

Нельзя переносить старую permission semantics по памяти.

---

## 5. Decision model

Базовая модель:

```text
OpenCode tool request
        |
        v
native deterministic permission
        |
        +-- obvious ALLOW
        +-- hard DENY
        |
        v
deterministic command/effect classifier
        |
        +-- ALLOW
        +-- DENY
        +-- uncertain
                 |
                 v
optional auditor
        |
        +-- confident safe/ask recommendation
        +-- uncertain
                 |
                 v
ASK_USER
```

Инварианты:

1. Hard `DENY` срабатывает до model auditor.
2. Auditor не может отменять hard `DENY`.
3. Auditor не имеет execution tools.
4. Low confidence не превращается в `ALLOW`.
5. Неизвестный эффект не считается безопасным.
6. Permission decision должен относиться ко всей операции, а не только к первому executable.

---

## 6. Native-first principle

Перед созданием parser/custom tool/plugin нужно доказать, что требуемую политику нельзя достаточно точно выразить штатным OpenCode config.

Целевая последовательность разработки:

```text
native rules
-> measurement
-> gap analysis
-> minimal deterministic classifier
-> measurement
-> only then consider auditor/plugin/UI
```

Широкие shortcuts (`bash: allow`, blanket auto-approval) не являются приемлемой архитектурой.

---

## 7. Effect analysis

Classifier должен оценивать не имя программы, а возможные эффекты.

Минимальные признаки:

```yaml
execution:
  shell:
  command_structure:
  nested_interpreter:
  remote:
target:
  paths:
  repository:
  host:
effects:
  read:
  write:
  delete:
  process_control:
  privilege:
  network:
  secrets:
  remote_state_change:
risk:
  predictability:
  reversibility:
  blast_radius:
```

Нужно учитывать как минимум:

- `&&`, `||`, `;`;
- pipelines;
- redirects;
- `xargs`;
- `find -delete/-exec/-execdir/-ok`;
- `bash -c`, `sh -c`;
- PowerShell `-Command`, `Invoke-Expression`;
- `cmd /c`;
- Python/Node/other interpreter one-liners;
- shell download-and-execute patterns;
- remote payload через `ssh_relay`/SSH;
- path traversal и external directories.

---

## 8. Базовые классы решения

### Safe read

Примеры: чтение не-secret файлов, grep/glob, read-only inspection.

Цель: максимально native `ALLOW`.

### Safe deterministic development operation

Сборка, unit tests, static checks, повторяемая read-only диагностика.

Они не должны автоматически становиться risky только из-за длительности. Long-running lifecycle — отдельный operational concern.

### Controlled write

Изменение файлов репозитория или generated output требует оценки target/scope. Не должно смешиваться с system-level risk.

### High-risk mutation

Deletion, destructive Git, privilege escalation, services, production deploy, secret mutation, unknown remote state change.

Default — `DENY` или отдельный контролируемый protocol, а не широкий shell allow.

### Unknown

Неизвестный CLI, неразобранный nested payload, неясный target/effect.

Default — не `ALLOW`.

---

## 9. Secrets boundary

Permission layer не должен расширять чтение secrets ради удобства анализа.

Нужно защищать:

- `.env*`;
- key/certificate files;
- credential/config files с secret data;
- environment dumps;
- auth headers/tokens;
- private remote material.

Model auditor не получает реальные secrets.

Logs, fixtures, reports и GitHub artifacts не должны содержать secret values.

---

## 10. Approval semantics

Если требуется человек, основной текст должен объяснять:

```text
Цель
Среда
Target
Фактические effects
Что изменится
Risk
Blast radius
Reversibility
Почему автоматика не решила
Рекомендация
```

Raw command доступна как техническая деталь, но не является единственным объяснением.

Если compound command нельзя уверенно объяснить, предпочтительно потребовать декомпозицию на атомарные операции.

---

## 11. Stage/gate model

Проект развивается этапами. Точный порядок хранится в roadmap/implementation plan, но устойчивый принцип такой:

### Baseline / audit gate

До реализации classifier необходимо подтвердить фактическую OpenCode semantics и собрать baseline prompts/cases.

### Native-policy gate

Сначала измеряется максимально точная native policy.

### Deterministic-classifier gate

Parser/classifier добавляется только для доказанных gaps native layer.

### Auditor gate

Model auditor рассматривается только если deterministic approach оставляет значимую gray zone.

### Integration gate

Только проверенная policy интегрируется через `opencode_setup`.

Переход к следующему gate должен быть явным.

---

## 12. Test strategy

Нужен machine-readable corpus. Минимальные классы:

```text
safe_read
secret_read
safe_git_read
safe_build
safe_test
file_write
file_delete
git_destructive
system_service
privilege
nested_shell
pipeline
redirect
interpreter
remote_safe
remote_destructive
unknown_cli
purpose_mismatch
external_directory
```

Каждый case должен задавать:

```yaml
id:
platform:
input:
purpose:
environment:
expected_decision:
expected_effects:
expected_summary:
execution_policy:
```

`execution_policy` определяет, можно ли:
- выполнить реально;
- выполнять только в temp fixture;
- parser-only/mock only.

Опасные negative cases не исполняются на рабочей системе.

---

## 13. Metrics

Минимум:

```text
permission_prompt_count
human_approval_count
auto_allow_count
hard_deny_count
classifier_count
auditor_count
false_block_count
unsafe_test_allow_count
unknown_count
```

Дополнительно:
- latency;
- raw-command-open rate;
- decision stability;
- platform/version coverage.

Ключевой acceptance-инвариант тестового корпуса:

```text
unsafe automatic allow = 0
```

при заметном сокращении routine human prompts.

---

## 14. Verification discipline

Изменение policy считается завершённым только если:

1. задан ожидаемый decision;
2. добавлен/обновлён regression case;
3. тест выполнен в допустимой безопасной среде;
4. фактический decision подтверждён;
5. не ослаблены соседние hard-deny cases.

Успешный запуск одной команды не является доказательством безопасности policy.

---

## 15. Research safety

Перед экспериментом классифицировать его как:

```text
read-only
parser-only
isolated mutation
real mutation
```

Предпочтение:
`read-only/parser-only > isolated fixture > real mutation`.

Не использовать production/stateful system changes для проверки deny rules.

После unexpected result:
- остановить исходный mutation path;
- сохранить evidence;
- провести read-only diagnosis;
- не повторять operation вслепую;
- не использовать destructive cleanup.

---

## 16. Documentation lifecycle

### Persistent Sources

Рекомендуемое ядро:

1. `opencode_permissions_project_baseline_ru.md`;
2. `opencode_permissions_chatgpt_web_guide_ru.md`;
3. при активной координации локального агента — `opencode_permissions_agent_guide_ru.md`;
4. `github_project_bootstrap.md` для GitHub workflow.

### Repository documents

Кодовые contracts, schemas, test corpus, README и implementation docs живут в GitHub и проверяются по актуальному состоянию.

### Findings

`opencode_permissions_findings_ru.md` — evidence/historical handoff. Его утверждения, зависящие от версии OpenCode, перепроверяются.

Не держать две нормативные копии одной policy.

---

## 17. Критерий успешного проекта

Успешный результат позволяет обычному циклу разработки выполнять чтение, поиск, сборку, тесты и безопасную диагностику практически без участия пользователя, при этом:

- опасные операции технически блокируются или маршрутизируются в контролируемый runtime;
- compound/nested/remote effects не скрываются за безопасным префиксом;
- неизвестное не становится автоматическим allow;
- approval редок и понятен;
- policy воспроизводимо проверяется тестовым корпусом;
- deployment/integration выполняется отдельным `opencode_setup`.
