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

## Границы проекта

- `opencode_permissions` — permission policy, command/effect classification, approval semantics и experiments;
- [`agent-safe`](https://github.com/dilukhin/agent-safe) — runtime-защита risky state-changing действий, verify/recovery;
- [`opencode_setup`](https://github.com/dilukhin/opencode_setup) — installation/reconciliation/integration;
- [`ssh_relay`](https://github.com/dilukhin/ssh_relay) — remote transport/machine contract.

Проект не должен дублировать runtime-функции этих компонентов без доказанной необходимости.

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

### Следующий gate

**Deterministic parser/effect analysis — NOT STARTED.**

Он должен добавляться только для gaps, которые доказанно не покрывает native layer, и обязан сохранять Gate B hard-deny/fail-closed invariants.

Model auditor остаётся `NOT STARTED` до отдельного gate.

## Актуальные документы

Persistent project sources:

- [`opencode_permissions_project_baseline_ru.md`](opencode_permissions_project_baseline_ru.md)
- [`opencode_permissions_chatgpt_web_guide_ru.md`](opencode_permissions_chatgpt_web_guide_ru.md)
- [`opencode_permissions_agent_guide_ru.md`](opencode_permissions_agent_guide_ru.md)
- [`github_project_bootstrap.md`](github_project_bootstrap.md)

Gate B:

- [`docs/gate_b_final_closure_ru.md`](docs/gate_b_final_closure_ru.md)
- [`docs/gate_b_native_policy_integration_design_ru.md`](docs/gate_b_native_policy_integration_design_ru.md)
- [`docs/gate_b_native_policy_candidate_metrics_ru.md`](docs/gate_b_native_policy_candidate_metrics_ru.md)
- [`docs/gate_b_compatibility_profiles_ru.md`](docs/gate_b_compatibility_profiles_ru.md)
- [`docs/gate_b_canonical_artifact_contract_ru.md`](docs/gate_b_canonical_artifact_contract_ru.md)
- [`docs/gate_b_authorization_broker_contract_ru.md`](docs/gate_b_authorization_broker_contract_ru.md)
- [`docs/gate_b_linux_opencode_broker_probe_ru.md`](docs/gate_b_linux_opencode_broker_probe_ru.md)
- [`docs/gate_b_windows_peer_identity_probe_ru.md`](docs/gate_b_windows_peer_identity_probe_ru.md)

Machine-readable evidence:

- [`tests/permission_cases/`](tests/permission_cases/) — 69-case corpus;
- [`tests/native_policy/`](tests/native_policy/) — native projection/matcher candidate evidence;
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

Документация и рабочее общение проекта ведутся преимущественно по-русски; code identifiers и machine-readable fields — преимущественно по-английски.
