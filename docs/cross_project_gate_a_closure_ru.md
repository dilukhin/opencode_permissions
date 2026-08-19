# Closure Gate A — Cross-project integration contract

Статус: **CLOSED**.

Gate A закрывает только архитектурное проектирование стыковки проектов. Production permission policy, deterministic classifier, model auditor и runtime authorization mechanisms этим решением не реализованы и не считаются закрытыми.

## 1. Scope closure

Рассмотрены:

- `opencode_permissions`;
- `agent-safe`;
- `ssh_relay`;
- `ScopedKB`;
- `opencode_setup`;
- effective OpenCode permission/config/instruction/wrapper channels, способные создать cross-project collision.

## 2. Принятые boundaries

1. `opencode_permissions` — единственный canonical owner `ALLOW / ASK_USER / DENY` и approval semantics.
2. `agent-safe` — execution safety; runtime может сузить authorization, но не повысить его.
3. `ssh_relay` — transport/machine outcome; transport metadata не является authorization.
4. `ScopedKB` — contextual facts/provenance; context не является policy decision.
5. `opencode_setup` — единственный reconciler shared live OpenCode managed environment.
6. `opencode_permissions` должен стать first-class managed target/dependency `opencode_setup`.
7. Generic wrapper name не является proof безопасности nested payload.
8. Model-controlled self-approval запрещён как integrated authorization proof.
9. Authorization должен быть exact-bound к normalized operation/target/effects.
10. Prompt/instructions/skills не являются security boundary.
11. Hard `DENY` имеет абсолютный приоритет в normal flow.

## 3. Evidence artifacts

Normative/reviewable design artifacts:

- `cross_project_integration_master_plan_ru.md` — accepted master plan;
- `cross_project_integration_contract_v1_ru.md` — accepted architecture contract;
- `cross_project_permission_collision_matrix_ru.md` — collision audit/design input;
- `cross_project_unresolved_decisions_ru.md` — implementation decisions register;
- `cross_project_acceptance_matrix_ru.md` — evidence matrix B–G;
- `opencode_setup_opencode_permissions_target_ru.md` — accepted requirement добавить `opencode_permissions` в managed targets setup.

Current-code audit, выполненный перед closure, подтвердил как минимум:

- `agent-safe` содержит собственные OpenCode permission defaults с blanket `safe *` / `python -m agent_safe *` allow;
- `agent-safe exec-risky` принимает caller-supplied approval Boolean;
- `opencode_setup` уже имеет managed dependency/reconciliation model для `ssh_relay` и `agent-safe`, но `opencode_permissions` пока не является managed dependency;
- `ssh_relay` текущим skill в основном задаёт transport/lifecycle semantics;
- ScopedKB текущим bootstrap не меняет system settings, а specification содержит provenance/status primitives для будущего factual context.

Эти observations являются входом следующих gates; closure Gate A не утверждает, что collisions уже исправлены.

## 4. Acceptance Gate A

| Criterion | Result |
|---|---|
| Каждый authorization-sensitive class имеет canonical owner | PASS |
| Model-controlled self-approval запрещён как architecture invariant | PASS |
| Wrapper/remote paths не считаются безопасными только по имени wrapper | PASS |
| PDP/PEP/PIP/transport/reconciliation boundaries определены | PASS |
| `opencode_permissions` включён в целевую dependency model `opencode_setup` | PASS |
| Unresolved implementation choices отделены от invariants | PASS |
| Cross-project acceptance scenarios определены | PASS |
| Gate closure не требует production mutation | PASS |

## 5. Deferred decisions

Gate A намеренно не выбирает:

- конкретный authorization grant transport/capability mechanism;
- exact canonicalization/hash implementation `NormalizedOperation`;
- single-use vs short-lived grant semantics;
- final deployable permission artifact format;
- concrete `agent-safe` API migration;
- final `ContextFacts` wire schema;
- final `opencode_setup` branch/version policy для `opencode_permissions` checkout.

Они принадлежат gates B–F и зарегистрированы в `cross_project_unresolved_decisions_ru.md`.

## 6. Следующий gate

Следующий этап — **B: `opencode_permissions` Native-policy integration design**.

Обязательная последовательность:

1. проверить актуальный `main` и version-sensitive OpenCode 1.18.18 evidence;
2. спроектировать Native-policy rules с учётом wrapper collision;
3. уточнить `NormalizedOperation`/authorization handoff requirements;
4. определить canonical deployable policy artifact/interface contract для будущего `opencode_setup`;
5. расширить corpus/acceptance cases;
6. измерить ожидаемое снижение prompts без false-safe regressions;
7. только после явного closure Native-policy gate рассматривать deterministic classifier.

Starter: `next_dialog_stage_b_native_policy_integration_starter_ru.md`.
