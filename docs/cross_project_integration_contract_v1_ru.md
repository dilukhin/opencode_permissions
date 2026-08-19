# Cross-project Integration Contract v1

Статус: **ACCEPTED architecture contract / implementation pending**.

Этот документ задаёт канонические границы ответственности и logical interfaces для integrated OpenCode environment. Он не утверждает, что interfaces уже реализованы, и не разрешает изменение production permission policy до соответствующих implementation gates.

## 1. Участники и роли

| Project | Role |
|---|---|
| `opencode_permissions` | PDP / authorization policy and decision |
| `agent-safe` | PEP + execution-safety runtime |
| `ssh_relay` | remote transport / machine outcome |
| `ScopedKB` | PIP / contextual facts and provenance |
| `opencode_setup` | installation / reconciliation plane |

`opencode_setup` обязан управлять `dilukhin/opencode_permissions` как first-class managed integration target/dependency, но не является владельцем authorization semantics.

## 2. Authorization ownership

### 2.1 Единственный PDP

Только `opencode_permissions` формирует:

- `ALLOW`;
- `ASK_USER`;
- `DENY`.

К authorization policy относятся любые effective artifacts, способные изменить это решение:

- native OpenCode `permission`;
- global/project/environment overlays;
- wrapper/custom-tool approval routing;
- agent-specific permission mechanisms;
- instructions/skills, если они нормативно требуют или обходят user approval.

### 2.2 Hard deny

Hard `DENY` имеет приоритет над:

- auditor/model decision;
- `agent-safe` runtime;
- ScopedKB context;
- transport metadata;
- user/model-supplied wrapper flags.

Обычный flow не может override hard deny.

### 2.3 Unknown effect

Unknown/ambiguous effect не считается безопасным по умолчанию и не может автоматически давать `ALLOW`.

## 3. `NormalizedOperation`

Authorization относится не к строковому имени wrapper, а к нормализованной операции.

Logical fields:

```yaml
schema: normalized-operation/v1
operation_id: ...
purpose: ...
channel: local|remote|transfer|other
target: ...
payload: ...            # canonical/normalized representation
expected_effects: [...]
context_dependencies: [...]
identity_hash: ...
```

Точная canonicalization/hash algorithm определяется этапом B.

Требования:

- operation identity должна меняться при semantic payload/target/effect substitution;
- generic wrapper name сам по себе не определяет безопасность;
- remote и transfer effects должны представляться как effects, даже если нет обычной shell-команды.

## 4. `ContextFacts`

ScopedKB может поставлять attributes вида:

```yaml
schema: context-facts/v1
facts:
  - id: ...
    value: ...
    scope: ...
    status: verified|observed|stale|unknown
    provenance: ...
    observed_at: ...
    sensitivity: ...
```

Факт не является authorization decision.

Fail-safe rule:

> missing, stale, weaker или unknown context не может сделать решение более permissive, если policy rule явно не разрешает использовать именно такой уровень evidence.

## 5. `AuthorizationDecision`

Logical result PDP:

```yaml
schema: authorization-decision/v1
decision: ALLOW|ASK_USER|DENY
operation_id: ...
policy_version: ...
rule_id: ...
reason: ...
hard_deny: false
context_dependencies: [...]
```

Decision не даёт execution layer права менять payload.

## 6. `AuthorizationGrant`

Grant нужен для controlled execution после `ALLOW` или подтверждённого `ASK_USER`.

Минимальные invariants:

1. non-forgeable через model-controlled command/payload channel;
2. exact-bound к `NormalizedOperation`;
3. scope ограничен конкретным target/effects;
4. provenance различает policy allow и подтверждённый user approval;
5. replay/substitution должны блокироваться согласно threat model;
6. grant не должен превращаться в обычный caller-controlled Boolean.

Конкретный mechanism — trusted bridge, capability handle, IPC/broker, custom OpenCode tool или иной вариант — решается этапом B после исследования фактических integration primitives OpenCode 1.18.18.

`--approved=true` или эквивалент, формируемый тем же агентом, не является достаточным integrated authorization proof.

## 7. `ExecutionPreflight`

Owner: `agent-safe`.

Принята двухфазная модель.

### До ASK

Разрешён только гарантированно read-only preflight, который может сообщить:

- resolved target;
- reversibility/checkpoint availability;
- verify method;
- recovery constraints;
- runtime blockers, обнаружимые без mutation.

Эти данные могут использоваться `opencode_permissions` для canonical approval prompt.

### После authorization

Непосредственно перед mutation `agent-safe` повторно проверяет runtime-sensitive preconditions для защиты от TOCTOU/state drift.

Preflight не формирует `ALLOW/ASK/DENY`.

## 8. `ExecutionResult`

Owner: `agent-safe`.

Минимальные terminal/non-terminal semantics:

- `DONE`;
- `RUNTIME_REJECT`;
- `UNEXPECTED`;
- observed actual state;
- verification result;
- recovery/incident state, если применимо.

`RUNTIME_REJECT` означает: upstream authorization существует, но runtime safety preconditions не позволяют безопасно выполнить действие.

Правило:

> runtime may narrow authorization, never broaden it.

## 9. `RemoteOutcome`

Owner: `ssh_relay`.

Минимальные состояния:

- `started`;
- `running`;
- `succeeded`;
- `failed`;
- `stopped`;
- `unknown`.

Transport возвращает correlation/job identity и observable evidence, но не `ALLOW/ASK/DENY`.

`unknown` не эквивалентен success и не является основанием для blind retry.

`--risky` и аналогичные transport labels не являются approval evidence.

## 10. Controlled execution flow

Целевой flow:

```text
1. Agent proposes operation
2. opencode_permissions normalizes operation/effects
3. optional ScopedKB ContextFacts enrichment
4. guaranteed read-only agent-safe preflight
5. hard-deny/native/authorization evaluation
6. ALLOW or ASK_USER or DENY
7. successful decision -> trusted exact-bound authorization handoff
8. agent-safe revalidates runtime-sensitive preconditions
9. smallest mutation
10. if remote: ssh_relay transports and returns RemoteOutcome
11. agent-safe verifies expected state
12. DONE / RUNTIME_REJECT / UNEXPECTED
```

Для hard deny execution path не начинается.

## 11. Direct native path и controlled path

### Direct native path

Предназначен для детерминированно безопасных direct operations и hard-deny families:

```text
safe direct operation -> native ALLOW -> execute
hard dangerous        -> native DENY
```

### Controlled path

Используется там, где operation является state-changing, wrapper-mediated или требует richer effect/target semantics:

```text
operation -> authorization -> grant -> agent-safe -> execute/verify
```

Generic wrappers (`safe`, `python -m agent_safe`, `ssh_relay`, interpreters, future generic executors) не получают blanket trust только из-за имени внешней команды.

## 12. `agent-safe` integration modes

### Integrated

- authorization приходит только от `opencode_permissions`;
- caller-controlled approval flag не считается proof;
- independent production permission writer не используется;
- runtime может reject, но не grant authorization.

### Standalone/manual

Compatibility mode может сохраниться, если он явно отделён и не меняет managed integrated environment. Его lifecycle и UX определяются этапом C.

## 13. `ScopedKB` boundary

ScopedKB может:

- хранить scoped facts;
- выдавать provenance/freshness/sensitivity;
- компилировать factual/routing context.

ScopedKB не должен генерировать normative authorization outputs:

```text
allow
deny
ask_user
approval_required
```

Если startup context содержит safety text, он не является technical security boundary и не может заменить PDP.

## 14. `ssh_relay` boundary

Relay владеет transport/lifecycle, но не authorization.

Remote shell payload, `sudo-exec`, jobs, upload/download и иные state-changing channels должны быть представлены upstream как semantic operation/effects; blanket allow relay wrapper запрещён как proof безопасности.

## 15. `ManagedArtifactOwnership`

Owner deployment plane: `opencode_setup`.

Logical fields:

```yaml
artifact: ...
semantic_section: ...
canonical_owner: ...
managed_scope: ...
source: ...
source_version: ...
legacy_signatures: [...]
conflict_policy: ...
```

Migration classes:

- `CURRENT_MANAGED`;
- `KNOWN_LEGACY_EXACT`;
- `KNOWN_LEGACY_MODIFIED`;
- `USER_OWNED`;
- `UNKNOWN`;
- `CONFLICTING_EFFECTIVE_LAYER`.

Rules:

- current managed -> reconcile + verify;
- known exact legacy -> explicit migrate/remove + verify;
- modified/user/unknown -> preserve + conflict unless отдельно доказано безопасное действие;
- successful deploy exit code не заменяет effective end-state verification.

## 16. `opencode_permissions` как managed target `opencode_setup`

Это обязательная часть integrated environment.

`opencode_setup` должен:

1. иметь managed dependency entry для `dilukhin/opencode_permissions`;
2. install/update checkout по non-destructive repository reconciliation policy;
3. конфликтовать на tracked changes/local commits вместо reset/clean/force;
4. получать canonical deployable policy artifacts из этого checkout;
5. deploy/reconcile их без собственной semantic modification;
6. inventory effective permission layers;
7. мигрировать known legacy `agent-safe` permission writers;
8. сохранять unknown/user-owned artifacts;
9. verify actual effective state.

Точный artifact format, branch/version policy и health check определяются B/F, а не настоящим контрактом преждевременно.

## 17. Prompt/skill boundary

Допустимые instructions/skills:

```text
use ssh-relay for remote transport
use recovery-mode after unexpected result
route risky/unknown operation to controlled execution path
```

Недопустимо считать security boundary правила вида:

```text
always ask user for X
auto-approve Y
risk=high means approval already required/obtained
```

Authorization semantics должны быть реализованы технически и принадлежать `opencode_permissions`.

## 18. Stop conditions

Cross-project design должен быть пересмотрен, если implementation требует:

- второго effective authorization writer;
- model-controlled self-approval;
- blanket trusted generic wrapper;
- grant без exact operation binding;
- destructive изменение unknown artifact;
- prompt-only safety boundary;
- переноса ownership между проектами без явного изменения контракта.

## 19. Отложенные implementation decisions

Контракт намеренно не фиксирует:

- конкретный authorization handoff transport;
- canonicalization/hash algorithm;
- single-use vs short-lived grant;
- final deployable policy artifact format;
- branch/version policy managed checkout;
- точный ContextFacts wire schema beyond required semantics.

Они перечислены в `cross_project_unresolved_decisions_ru.md` и закрываются соответствующими project gates.
