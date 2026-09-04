# OpenCode Permissions

Проект по разработке и проверке практической модели разрешений OpenCode: меньше рутинных подтверждений без отказа от технических границ опасных действий.

## Целевая архитектура

```text
native deterministic rules
-> deterministic parser/effect analysis
-> optional auditor for gray zone
-> ASK_USER only for residual uncertainty
```

Жёсткий `DENY` имеет приоритет и не может быть отменён model auditor. Неизвестный эффект не считается безопасным.

## Практическая модель угроз

Default-режим проекта — технические **перила**, а не универсальная sandbox/host-integrity система.

Он защищает от ошибочных или слишком широких model-controlled операций, self-approval, скрытых nested effects, unknown/opaque payload, authorization substitution и несовместимого effective permission state.

Он не обязан по умолчанию защищать от уже скомпрометированного trusted plugin/host, malware того же OS-user, root/admin/kernel compromise или полного sandboxing пользовательского build/test code.

Канонический документ:
[`docs/default_threat_model_ru.md`](docs/default_threat_model_ru.md).

High-assurance механизмы допустимы как отдельный профиль, но не становятся default requirement без конкретной доказанной угрозы.

## Границы проекта

- `opencode_permissions` — permission policy, command/effect classification, approval semantics и experiments;
- [`agent-safe`](https://github.com/dilukhin/agent-safe) — runtime-защита risky state-changing действий, resource lifecycle, verify/recovery;
- [`opencode_setup`](https://github.com/dilukhin/opencode_setup) — installation/reconciliation/integration;
- [`ssh_relay`](https://github.com/dilukhin/ssh_relay) — remote transport/machine contract.

Проект не должен дублировать runtime-функции этих компонентов без доказанной необходимости.

Каноническая компактная граница `opencode_permissions` / `agent-safe`:
[`docs/opencode_permissions_agent_safe_boundary_ru.md`](docs/opencode_permissions_agent_safe_boundary_ru.md).

Коротко:

```text
opencode_permissions:
  можно ли разрешить именно эту операцию,
  и всё ли ещё фактическая операция совпадает с разрешённой?

agent-safe:
  как безопасно выполнить уже разрешённое изменение,
  проверить результат и восстановиться при проблеме?
```

Temporary/trash/delete/retention/verification/recovery semantics принадлежат `agent-safe`, а не `opencode_permissions`.

## Источники истины

Для фактического состояния реализации первым источником является текущий GitHub repository.

Для version-sensitive поведения OpenCode приоритет:

1. фактическая installed/target версия;
2. official docs и upstream source/tests этой exact версии;
3. [`opencode_permissions_project_baseline_ru.md`](opencode_permissions_project_baseline_ru.md);
4. остальные устойчивые project docs;
5. findings/reports/dialogs — только evidence.

Roadmap/design сам по себе не доказывает реализацию.

## Gate state

### Stage 0 / Gate A

**CLOSED** для исследованного OpenCode `1.18.18`.

Formal closure:
[`docs/stage0_gate_closure_ru.md`](docs/stage0_gate_closure_ru.md).

### Gate B / Native-policy integration

**CLOSED для Linux / exact OpenCode 1.18.26.**

Formal closure:
[`docs/gate_b_final_closure_ru.md`](docs/gate_b_final_closure_ru.md).

Ключевой результат:

```text
native corpus scope: 65 / 69 cases
ALLOW: 6
ASK:   30
DENY:  29
safe deterministic capture: 6 / 11 = 54.5%
unsafe_auto_allow:       0
dangerous_false_safe:    0
wrapper_false_safe:      0
unknown_false_safe:      0
secret_false_safe:       0
```

Canonical semantic source:

```text
policy/native/rules.v1.json
```

Deterministic renderer:

```text
tools/render_native_policy.py
```

Deployable repository artifact для Linux/OpenCode 1.18.26:

```text
sha256:d983bb4d5f2b9f9be195267e89d16c27ce45e706a2afeb527d96142c535cc508
```

Artifact **не установлен** автоматически в live OpenCode configuration. Installation/reconciliation/effective read-back принадлежат `opencode_setup`.

Windows B-P2 kernel peer/lifecycle primitive — `PASS`, но OpenCode 1.18.26 runtime на Windows не был runtime-revalidated, поэтому Windows отсутствует в `deployable_platforms`.

### Deterministic classifier gate

**CLOSED для доказанного Linux / exact OpenCode 1.18.26 profile.**

Formal closure:
[`docs/deterministic_classifier_gate_closure_ru.md`](docs/deterministic_classifier_gate_closure_ru.md).

DC-0…DC-4 закрыли:

- `NormalizedOperation` identity;
- deterministic result/composition core;
- bounded analyzers;
- wrapper/remote recursive analysis;
- exact OpenCode authorization-binding runtime proof.

Classifier sound projection:

```text
safe combined ALLOW: 9 / 13 = 69.2%
Gate B native baseline: 6 / 11 = 54.5%
```

Знаменатели относятся к разным фиксированным наборам и не смешиваются.

### Architecture-simplicity reconciliation

Аудит на переусложнение завершён на уровне архитектурных решений.

Принятые решения:

- kernel authorization broker — **optional high-assurance**, не обязательный default path;
- полный executable content hash — proof/high-assurance механизм, не default requirement;
- full `process.env` binding будет заменён explicit environment dependencies;
- trusted-workspace направление принято, но **не расширяет ALLOW до отдельного design/acceptance**;
- exact-version fail-closed сохраняется, evidence может переиспользовать capability/fingerprint contracts только после explicit revalidation;
- новые cross-project wire schemas — just-in-time;
- auditor отложен до managed pilot и реальных residual-ASK metrics.

Accepted decisions:
[`docs/architecture_simplicity_reconciliation_ru.md`](docs/architecture_simplicity_reconciliation_ru.md).

### Auditor

**NOT STARTED / DEFERRED BY POLICY.**

Auditor не проектируется только потому, что он следующий блок старой схемы. Сначала нужен ограниченный managed pilot уже готовых native + deterministic механизмов, реальные residual ASK и проверка более дешёвых deterministic улучшений.

Production permission configuration по-прежнему не изменена classifier-ом.

## Актуальные документы

Persistent project sources:

- [`opencode_permissions_project_baseline_ru.md`](opencode_permissions_project_baseline_ru.md)
- [`opencode_permissions_chatgpt_web_guide_ru.md`](opencode_permissions_chatgpt_web_guide_ru.md)
- [`opencode_permissions_agent_guide_ru.md`](opencode_permissions_agent_guide_ru.md)
- [`github_project_bootstrap.md`](github_project_bootstrap.md)

Current architecture/contracts:

- [`docs/default_threat_model_ru.md`](docs/default_threat_model_ru.md)
- [`docs/opencode_permissions_agent_safe_boundary_ru.md`](docs/opencode_permissions_agent_safe_boundary_ru.md)
- [`docs/architecture_simplicity_reconciliation_ru.md`](docs/architecture_simplicity_reconciliation_ru.md)
- [`docs/cross_project_integration_contract_v1_ru.md`](docs/cross_project_integration_contract_v1_ru.md)

Current implementation/closure:

- [`docs/gate_b_final_closure_ru.md`](docs/gate_b_final_closure_ru.md)
- [`docs/deterministic_classifier_gate_closure_ru.md`](docs/deterministic_classifier_gate_closure_ru.md)
- [`docs/dc4_exact_opencode_adapter_ru.md`](docs/dc4_exact_opencode_adapter_ru.md)

Review/history:

- [`docs/architecture_simplicity_audit_ru.md`](docs/architecture_simplicity_audit_ru.md) — review findings, resolved by reconciliation document above;
- broker/peer-identity documents — Gate B research/high-assurance evidence, not proof that a production broker is selected as default architecture.

Machine-readable evidence:

- [`tests/permission_cases/`](tests/permission_cases/) — 69-case corpus;
- [`tests/native_policy/`](tests/native_policy/) — native projection/matcher evidence;
- [`tests/normalized_operation/`](tests/normalized_operation/) — NormalizedOperation identity fixtures;
- [`tests/compatibility/`](tests/compatibility/) — exact-version/platform profiles;
- [`tests/artifact_contract/`](tests/artifact_contract/) — artifact validation contract.

## Safety invariants

- Никакого broad `bash: allow`, blanket auto-approval или prompt-only safety.
- Hard `DENY` имеет абсолютный приоритет.
- Unknown/opaque effect не становится `ALLOW`.
- Compound/nested/remote payload анализируется целиком.
- Dangerous negative cases проверяются parser-only/mock/temp/synthetic, а не destructive execution.
- Secrets не раскрываются ради анализа.
- Model auditor никогда не получает execution authority.
- Authorization layer не дублирует resource lifecycle, verification и recovery `agent-safe`.
- High-assurance research не превращается в default requirement без явного threat-model решения.

Документация и рабочее общение проекта ведутся преимущественно по-русски; code identifiers и machine-readable fields — преимущественно по-английски.
