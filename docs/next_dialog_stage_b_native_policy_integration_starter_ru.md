# Starter следующего диалога — Gate B / Native-policy integration design

Продолжаем проект `dilukhin/opencode_permissions`.

Gate A cross-project integration contract закрыт. Используй действующие Project Instructions и актуальный GitHub repository как source of truth.

Сначала через GitHub Connector проверь актуальный `main` и прочитай:

- `README.md`;
- `docs/stage0_gate_closure_ru.md`;
- `docs/stage0_v1_18_18_source_audit_ru.md`;
- `docs/stage0c_interpreter_parser_closure_ru.md`;
- `docs/cross_project_gate_a_closure_ru.md`;
- `docs/cross_project_integration_master_plan_ru.md`;
- `docs/cross_project_integration_contract_v1_ru.md`;
- `docs/cross_project_permission_collision_matrix_ru.md`;
- `docs/cross_project_unresolved_decisions_ru.md`;
- `docs/cross_project_acceptance_matrix_ru.md`;
- `docs/opencode_setup_opencode_permissions_target_ru.md`;
- `tests/permission_cases/`.

Текущий target OpenCode — `1.18.18`; version-sensitive behavior перепроверять по фактической версии/официальному upstream evidence, а не по старым findings.

## Цель Gate B

Разработать и закрыть **Native-policy integration design** до deterministic classifier/auditor implementation.

Нужно:

1. определить hard-deny invariants;
2. определить безопасные deterministic native allow families;
3. определить обязательные ASK/controlled-path zones;
4. сохранить secret/external-directory boundaries;
5. учесть generic wrappers (`safe`, `python -m agent_safe`, `ssh_relay`, interpreters) и не допустить blanket trust внешней команды;
6. уточнить logical `NormalizedOperation`, `AuthorizationDecision`, `AuthorizationGrant` requirements;
7. исследовать фактические integration primitives OpenCode 1.18.18 для non-forgeable exact-bound authorization handoff, но не выбирать механизм без evidence;
8. определить canonical deployable permission artifact/interface contract, который позже сможет установить `opencode_setup` как единственный reconciler;
9. расширить `tests/permission_cases/`/acceptance plan wrapper, approval-substitution, remote payload/transfer, unknown-effect cases;
10. посчитать baseline vs proposed policy prompt-reduction metrics, отдельно показывая wrapper cases и требуя zero false-safe regressions для dangerous/unknown invariants.

## Архитектурные invariants Gate A

Обязательны:

- только `opencode_permissions` определяет `ALLOW / ASK_USER / DENY`;
- model-controlled `--approved`/эквивалент не является integrated proof approval;
- authorization exact-bound к operation/target/effects;
- `agent-safe` может вернуть `RUNTIME_REJECT`, но не повысить authorization;
- `ssh_relay` — transport, не PDP;
- ScopedKB — facts/PIP, не PDP;
- prompt/skills не являются technical security boundary;
- hard `DENY` не может быть отменён auditor/runtime/context/transport;
- generic wrapper name не доказывает безопасность nested payload;
- shared live environment в конечной архитектуре reconciles `opencode_setup`;
- `opencode_permissions` должен стать first-class managed target/dependency `opencode_setup`, но setup не меняет semantics canonical policy artifact.

## Ограничения

- deterministic classifier и model auditor пока **NOT STARTED**;
- actual production permission policy не менять до reviewable design/acceptance plan;
- опасные cases не исполнять разрушительно: parser-only, mocks, temp dirs, synthetic fixtures;
- unknown effect != safe;
- roadmap/design text не доказывает implementation;
- если выбранное решение требует второго permission writer, blanket `bash: allow`, prompt-only boundary или model self-approval — остановить affected path и вернуть к cross-project contract.

## Ожидаемый первый результат нового диалога

Сначала подготовь concrete Gate B design review:

- proposed native policy families;
- wrapper/controlled-path decision table;
- hard deny/ASK/ALLOW matrix;
- artifact/interface proposal для `opencode_setup`;
- unresolved OpenCode 1.18.18 integration questions;
- corpus changes;
- quantitative prompt-reduction acceptance;
- explicit Gate B closure criteria.

Не переходи к classifier/auditor до явного подтверждения closure Native-policy gate.
