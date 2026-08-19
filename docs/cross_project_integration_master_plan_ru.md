# Cross-project integration master plan

Статус: **ACCEPTED design plan**.  
Gate A закрывается отдельным `cross_project_gate_a_closure_ru.md`. Этот документ задаёт порядок дальнейшей работы и не доказывает наличие implementation.

## 1. Цель

Стыковка `opencode_permissions`, `agent-safe`, `ssh_relay`, `ScopedKB` и `opencode_setup` должна уменьшить дублирование safety/approval логики и исключить competing authorization writers.

Целевая модель:

```text
ScopedKB -> contextual facts
                |
                v
opencode_permissions -> ALLOW / ASK_USER / DENY
                |
                v
agent-safe -> preflight / execute / verify / recovery
                |
                v
ssh_relay -> transport / remote machine outcome

opencode_setup -> install/reconcile managed artifacts всех владельцев
```

## 2. Каноническое владение

| Project | Каноническая ответственность |
|---|---|
| `opencode_permissions` | authorization policy, `ALLOW/ASK_USER/DENY`, hard deny, approval semantics, normalized operation/effects |
| `agent-safe` | execution safety: target, expected state, preconditions, checkpoint, verify, recovery |
| `ssh_relay` | remote transport, jobs/transfers, remote machine outcome |
| `ScopedKB` | scoped contextual facts, provenance, freshness/sensitivity |
| `opencode_setup` | installation, repository ownership, live environment reconciliation, migration и verification |

`opencode_setup` обязан включить `dilukhin/opencode_permissions` как **first-class managed integration target/dependency**, аналогично другим managed source repositories. Он устанавливает/обновляет checkout и deploys canonical permission artifacts, но не меняет их authorization semantics.

## 3. Архитектурные invariants

1. **Single authorization owner.** Только `opencode_permissions` определяет `ALLOW / ASK_USER / DENY`.
2. **No self-approval.** Model-controlled input, включая CLI flag `--approved`, не является достаточным integrated proof approval.
3. **Exact binding.** Authorization связан с конкретной normalized operation/target/effects; payload substitution запрещён.
4. **Runtime may narrow, never broaden.** `agent-safe` может вернуть `RUNTIME_REJECT`, но не повысить authorization.
5. **Transport has no authority.** `ssh_relay` не принимает authorization decisions.
6. **Context has no authority.** ScopedKB поставляет facts, не permission decisions.
7. **Prompt text is not a security boundary.** `AGENTS.md`, skills и prompts не заменяют technical policy.
8. **Single live reconciler.** Shared OpenCode managed environment reconciles `opencode_setup`.
9. **Fail closed on ownership conflict.** Unknown/locally modified artifacts не удаляются и не перезаписываются blind action.
10. **Unknown effect != safe.** Неопределённость не может автоматически ослаблять решение.
11. **Hard DENY precedence.** Hard deny не отменяется auditor/runtime/context/transport layer.
12. **Generic wrapper != safe payload.** `safe`, `python -m agent_safe`, `ssh_relay`, interpreters и другие wrappers не получают blanket trust только по имени внешней команды.

## 4. Принятые design decisions Gate A

### 4.1 Канонический cross-project contract

Канонический контракт живёт в `opencode_permissions`. Соседние проекты фиксируют только свои локальные обязанности и ссылку/совместимость с контрактом, чтобы не создавать semantic drift.

### 4.2 Controlled execution path

Generic state-changing/wrapper operations должны проходить controlled path. Native direct path предназначен для детерминированно безопасных direct operations и hard-deny families.

### 4.3 Двухфазный preflight

До ASK допустим только гарантированно read-only preflight для target/reversibility/verify information. После authorization runtime-sensitive preconditions проверяются повторно непосредственно перед mutation.

### 4.4 Режимы `agent-safe`

Целевая модель различает:

- `integrated`: authorization приходит только от `opencode_permissions`; собственный permission writer и caller-controlled approval proof не используются;
- `standalone/manual`: compatibility mode возможен только как явно изолированный режим, не меняющий managed integrated environment.

### 4.5 Authorization handoff

Конкретный wire mechanism пока не выбран. Обязательное требование: authorization evidence должно быть non-forgeable через model-controlled command/payload channel и exact-bound к фактической operation.

## 5. Логические межпроектные contracts

До implementation должны быть стабилизированы:

- `ContextFacts`;
- `NormalizedOperation`;
- `AuthorizationDecision`;
- `AuthorizationGrant`;
- `ExecutionPreflight`;
- `ExecutionResult`;
- `RemoteOutcome`;
- `ManagedArtifactOwnership`.

Их normative semantics заданы в `cross_project_integration_contract_v1_ru.md`.

## 6. Этап A — Cross-project contract gate

Статус: **CLOSED** после фиксации closure document.

Deliverables:

- этот master plan;
- `cross_project_integration_contract_v1_ru.md`;
- `cross_project_permission_collision_matrix_ru.md`;
- `cross_project_unresolved_decisions_ru.md`;
- `cross_project_acceptance_matrix_ru.md`;
- `opencode_setup_opencode_permissions_target_ru.md`;
- `cross_project_gate_a_closure_ru.md`.

Gate A не меняет production permission policy/runtime.

## 7. Этап B — `opencode_permissions`

Отдельный диалог проекта.

Scope:

- Native-policy gate с учётом wrapper/cross-project boundaries;
- `NormalizedOperation`, `AuthorizationDecision`, `AuthorizationGrant` contract refinement;
- exact binding/lifetime/scope;
- исследование trusted controlled-operation integration primitives OpenCode 1.18.18;
- canonical deployable permission artifact/interface contract для будущего `opencode_setup`;
- расширение corpus wrapper/remote/approval-substitution cases;
- hard-deny invariants, deterministic native allow families, mandatory ASK zones, secret/external-directory boundaries;
- prompt-reduction metrics.

Не реализовывать deterministic classifier/auditor до явного закрытия Native-policy gate.

Обязательные families:

- `safe exec-risky ...`;
- `python -m agent_safe exec-risky ...`;
- caller-controlled `--approved`;
- interpreter/wrapper nested payload;
- `ssh_relay` remote payload и transfer effects;
- payload substitution/replay;
- unknown effect/context;
- hard deny внутри wrapper.

Проверки parser-only/mocks/synthetic fixtures; destructive validation запрещён.

## 8. Этап C — `agent-safe`

После стабилизации authorization contract B:

- отделить authorization от execution safety;
- убрать integrated reliance на caller-supplied approval Boolean;
- реализовать/поддержать agreed authorization handoff;
- развести `POLICY_DENY` и `RUNTIME_REJECT`;
- пересмотреть `risk-gate`/`safe-cli` как routing, не второй PDP;
- вывести independent production permission bootstrap из integrated ownership;
- сохранить checkpoint/verify/recovery/runtime blockers;
- изолировать standalone compatibility mode.

Gate C: `agent-safe` не способен повысить upstream authorization или выполнить mismatched operation по чужому grant.

## 9. Этап D — `ssh_relay`

- закрепить transport-only boundary;
- формализовать `RemoteOutcome`;
- `--risky` не является approval evidence;
- связать authorization/execution/job identity только для correlation;
- remote payload остаётся видимым upstream authorization;
- `unknown` не считается success и не вызывает blind retry.

## 10. Этап E — `ScopedKB`

- определить `ContextFacts`/provenance/freshness semantics;
- запретить generated authorization policy;
- определить sensitivity/redaction boundary;
- stale/missing/weaker context не должен ослаблять policy.

Implementation может быть deferred, если текущий ScopedKB ещё не производит соответствующий runtime context.

## 11. Этап F — `opencode_setup`

После стабилизации artifacts/contracts B–E:

1. добавить `opencode_permissions` в managed dependency/target model (`config_data.json` и orchestration);
2. установить/обновлять managed checkout по существующей non-destructive repository reconciliation policy;
3. определить branch/version policy и canonical checkout path;
4. получать deployable authorization artifacts только из `opencode_permissions`;
5. deploy/reconcile их без самостоятельной semantic modification;
6. inventory all version-relevant effective permission channels;
7. обнаруживать legacy `agent-safe` permission/bootstrap artifacts;
8. known exact legacy -> explicit migrate/remove;
9. modified/unknown/user-owned -> preserve + conflict;
10. verify фактический effective end state;
11. покрыть Windows/Linux validators и idempotent fixtures.

Acceptance fixtures:

```text
supported old A -> desired C
supported old B -> desired C
partial/mixed   -> desired C
C               -> C
```

Успешный exit code без end-state verification недостаточен.

## 12. Этап G — Cross-project integration acceptance

Проверяется система целиком на synthetic/non-destructive scenarios:

- direct deterministic-safe -> native ALLOW;
- hard-dangerous -> DENY до mutation;
- controlled mutation -> authorization -> agent-safe -> verify;
- forged approval marker -> no authorization;
- grant/payload mismatch -> reject;
- dangerous `safe`/`agent_safe` wrapper payload -> no blanket allow;
- dangerous `ssh_relay` payload -> no blanket allow;
- runtime preflight failure after ALLOW -> `RUNTIME_REJECT`;
- remote `unknown` -> diagnosis/recovery, no blind retry;
- stale ScopedKB fact -> no policy weakening;
- mixed legacy config -> reconciliation to desired managed state;
- unknown modified artifact -> preserve/conflict;
- hard deny cannot be overridden.

## 13. Зависимости

```text
A  Cross-project contract       CLOSED
|
v
B  opencode_permissions
|
v
C  agent-safe
|\
| +--> D ssh_relay
| +--> E ScopedKB
|      /
+-----+
   |
   v
F  opencode_setup
   |
   v
G  integration acceptance
```

D/E могут частично идти параллельно после стабилизации B/C interfaces, но implementation не должен опережать contract.

## 14. Организация диалогов

- текущий архитектурный диалог: Gate A/coordination;
- отдельный `opencode_permissions`: B;
- отдельный `agent-safe`: C;
- отдельный `ssh_relay`: D;
- отдельный `ScopedKB`: E;
- отдельный `opencode_setup`: F;
- свежий integration dialogue: G.

В каждом project dialogue сначала проверять актуальный default branch через GitHub Connector.

## 15. Stop/escalation conditions

Вернуться к cross-project contract, если обнаружено:

- второй live writer effective authorization policy;
- необходимость доверять model-controlled approval marker;
- wrapper, скрывающий payload от authorization;
- невозможность exact binding grant к operation;
- unknown ownership artifact, который требуется destructive изменить;
- неподтверждённое version-sensitive OpenCode behavior;
- prompt/instruction как единственная safety boundary;
- перенос runtime responsibility между проектами без отдельного решения.

## 16. Следующий шаг

Перейти в отдельный диалог этапа B. Starter: `next_dialog_stage_b_native_policy_integration_starter_ru.md`.
