# Cross-project Integration Contract v1

Статус: **DRAFT / architecture contract**.  
Этот документ задаёт целевые границы ответственности и logical interfaces. Он не утверждает, что интерфейсы уже реализованы, и не разрешает изменение production permission policy до закрытия соответствующих gates.

## 1. Область контракта

Участники:

- `opencode_permissions` — authorization policy/decision;
- `agent-safe` — execution safety;
- `ssh_relay` — remote transport/outcome;
- `ScopedKB` — contextual facts/provenance;
- `opencode_setup` — installation/reconciliation.

Контракт действует для integrated OpenCode environment. Standalone/legacy modes отдельных проектов допускаются только если они явно изолированы и не меняют effective authorization semantics managed environment.

## 2. Термины

### Authorization

Решение, можно ли выполнять конкретную operation:

- `ALLOW`;
- `ASK_USER`;
- `DENY`.

### Execution safety

Проверка возможности безопасно выполнить уже авторизованное действие: preconditions, target, expected state, reversibility, checkpoint, verify, recovery.

### Runtime reject

Отказ execution layer выполнить operation из-за технических safety preconditions. `RUNTIME_REJECT` не является новым authorization decision.

### Context fact

Наблюдение/знание с scope, provenance и freshness, которое policy может использовать как attribute. Сам fact не является authorization decision.

### Transport outcome

Фактическое состояние доставки/удалённой execution: `started`, `running`, `succeeded`, `failed`, `stopped`, `unknown`.

## 3. Роли в access-control модели

Приближённое соответствие:

```text
ScopedKB              = PIP / contextual attributes
opencode_permissions  = PDP / authorization decision
agent-safe            = PEP + execution-safety runtime
ssh_relay             = transport/execution channel
opencode_setup        = deployment/reconciliation plane
```

Это соответствие логическое, а не требование использовать конкретный стандарт access control.

## 4. Authorization ownership

### 4.1 Единственный PDP

Только `opencode_permissions` имеет право формировать `ALLOW`, `ASK_USER` или `DENY` в integrated environment.

К authorization policy относятся не только native OpenCode `permission`, но и любой artifact, который способен изменить фактическое решение:

- `permission` config;
- environment permission overlays;
- project/global permission config;
- wrapper allow/deny semantics;
- custom-tool approval routing;
- agent-specific permission mechanisms;
- instructions/skills, если они нормативно предписывают требовать либо обходить user approval.

### 4.2 Hard deny

Hard `DENY` имеет приоритет над:

- model auditor;
- `agent-safe` runtime;
- ScopedKB context;
- ssh_relay metadata;
- user-facing convenience rules.

Никакой downstream component не может превратить hard `DENY` в executable operation.

### 4.3 Unknown

Unknown command/effect/context не интерпретируется как safe автоматически.

## 5. Controlled execution flow

Целевая logical sequence:

```text
1. Agent proposes operation.
2. Operation is normalized.
3. Optional ContextFacts are resolved.
4. Optional read-only execution preflight is collected.
5. opencode_permissions evaluates policy.
6. DENY -> stop.
7. ASK_USER -> canonical approval request -> user decision.
8. ALLOW/user-approved -> trusted authorization handoff.
9. agent-safe validates authorization binding + runtime preconditions.
10. Execute smallest mutation.
11. ssh_relay transports remote operation when needed.
12. agent-safe verifies expected state.
13. DONE / RUNTIME_REJECT / UNEXPECTED.
14. On UNEXPECTED: recovery/read-only diagnosis according to agent-safe policy.
```

Пункты 3–4 не должны сами принимать authorization decision.

## 6. `NormalizedOperation`

Logical contract должен содержать достаточную информацию, чтобы decision и execution относились к одному действию.

Минимальная модель:

```yaml
schema: opencode.normalized-operation/v1
operation_id: <canonical identity>
purpose: <human-readable purpose>
channel: local | remote | other
target: <structured target>
payload: <canonical semantic representation>
effects:
  - <effect>
context_requirements: []
```

Конкретный canonicalization/hash algorithm определяется отдельно.

Обязательное свойство: изменение authorization-relevant target/payload/effects создаёт другую operation identity.

## 7. `ContextFacts`

Минимальная модель:

```yaml
schema: opencode.context-facts/v1
facts:
  - id: <fact id>
    value: <value>
    scope: <scope>
    status: verified | observed | stale | unknown
    provenance: <source/provenance>
    observed_at: <timestamp or explicit unknown>
    sensitivity: <classification if applicable>
```

Правила:

1. ScopedKB поставляет facts, но не authorization fields.
2. `allow`, `deny`, `ask_user`, `approval_required` и эквиваленты не являются допустимыми decision fields ContextFacts.
3. Policy rule, использующий fact для ослабления decision, обязан указать требуемый evidence level.
4. Missing/stale/weaker evidence не может неявно удовлетворить более сильное условие.
5. Filtering context не считается самостоятельной security boundary.

## 8. `AuthorizationDecision`

Минимальная модель:

```yaml
schema: opencode.authorization-decision/v1
operation_id: <same normalized operation>
decision: ALLOW | ASK_USER | DENY
policy_version: <version>
rule_id: <rule>
reason: <human-readable reason>
hard_deny: false
context_dependencies: []
```

`ASK_USER` означает, что решение ещё не является executable grant.

## 9. Canonical user approval

User approval semantics принадлежат `opencode_permissions`.

Approval request должен по возможности включать:

- purpose;
- target;
- expected effects;
- risk/reason for ASK;
- reversibility/checkpoint status, если trustworthy preflight доступен;
- verification method;
- remote host/session identity, если применимо;
- существенную residual uncertainty.

Другие проекты могут поставлять поля/evidence, но не определяют, требуется ли пользователь.

## 10. `AuthorizationGrant`

Logical contract между authorization и execution layer.

Минимальные свойства:

```yaml
schema: opencode.authorization-grant/v1
grant_id: <opaque identity>
operation_id: <exact normalized operation>
source: policy | user
policy_version: <version>
scope: <single-use/exact scope>
issued_at: <time>
expires_at: <optional>
```

### 10.1 Security requirements

Grant должен быть:

- non-forgeable через model-controlled command/payload channel;
- связан с exact operation;
- непригоден для произвольной payload substitution;
- ограничен scope/lifetime;
- защищён от replay в пределах принятой threat model.

Caller-controlled `--approved=true`, текстовое поле `approved`, строка в prompt или произвольный JSON, который может изготовить модель, сами по себе grant не образуют.

### 10.2 Implementation status

Механизм не выбран. Кандидаты:

- trusted in-process bridge;
- custom OpenCode tool;
- capability handle;
- private IPC;
- short-lived broker token;
- другой механизм с доказанной non-forgeability.

Выбор требует отдельного version-sensitive design исследования.

## 11. `ExecutionPreflight`

Владелец: `agent-safe`.

Logical result:

```yaml
schema: agent-safe.execution-preflight/v1
operation_id: <operation>
runtime_ready: true | false
target_resolution: <result>
checkpoint:
  available: true | false | unknown
reversibility: <classification>
verification: <method/capability>
blockers: []
```

Правила:

- preflight read-only;
- preflight не выдаёт `ALLOW/ASK/DENY`;
- `runtime_ready=true` не является authorization;
- downstream runtime может вернуть reject даже после ALLOW.

## 12. `ExecutionResult`

Владелец: `agent-safe`.

```yaml
schema: agent-safe.execution-result/v1
operation_id: <operation>
status: DONE | RUNTIME_REJECT | UNEXPECTED
actual_state: <sanitized observed state>
verification: <result>
recovery: <status if applicable>
remote_outcome_ref: <optional>
```

`RUNTIME_REJECT` и `UNEXPECTED` не должны автоматически вызывать повтор mutation.

## 13. `RemoteOutcome`

Владелец: `ssh_relay`.

```yaml
schema: ssh-relay.remote-outcome/v1
operation_id: <correlation only>
session: <remote identity>
job_id: <optional>
state: started | running | succeeded | failed | stopped | unknown
evidence: <sanitized transport evidence>
```

Правила:

1. Relay не принимает `ALLOW/ASK/DENY`.
2. `--risky` или аналогичный transport label не доказывает authorization.
3. `unknown` не равен success/failure и требует diagnosis/status before retry.
4. Remote payload должен оставаться связанным с upstream authorization operation.

## 14. Wrapper boundary

Наличие разрешённого внешнего wrapper не доказывает безопасность вложенной operation.

Запрещённый design pattern:

```text
safe * -> native ALLOW
safe exec-risky --approved -- <arbitrary payload>
```

если вложенный payload не проходит эквивалентный authorization flow.

То же правило действует для:

- `python -m agent_safe ...`;
- `ssh_relay exec ...`;
- interpreter wrappers;
- shell helpers;
- future generic executor tools.

## 15. `agent-safe` boundary

В integrated mode `agent-safe`:

- потребляет upstream authorization evidence;
- проверяет exact binding;
- выполняет runtime preconditions;
- execute/verify/recovery;
- не генерирует user approval самостоятельно;
- не трактует caller-supplied Boolean как достаточное authorization evidence.

Standalone/manual compatibility, если сохраняется, должна иметь явно отдельный mode/contract и не влиять на managed integrated environment.

## 16. `ssh_relay` boundary

`ssh_relay` может реализовывать технические ограничения transport и mutating-operation labels, но не определяет необходимость user approval.

Remote operation authorization должна существовать upstream независимо от того, выполняется payload локально, через `exec`, `sudo-exec`, `job`, upload/download или будущий transport primitive.

## 17. `ScopedKB` boundary

ScopedKB может:

- идентифицировать runtime/host/project/repository;
- поставлять verified observations;
- хранить provenance/freshness;
- компилировать ограниченный context.

ScopedKB не должен:

- создавать authorization decisions;
- генерировать startup instructions, которые фактически становятся вторым permission engine;
- считать filtering единственной security boundary;
- автоматически повышать inferred/observed fact до verified.

## 18. `opencode_setup` boundary

Только `opencode_setup` выполняет reconciliation shared live environment.

Другие проекты публикуют canonical artifacts/source templates, но integrated install path не должен позволять им независимо модифицировать shared OpenCode config/AGENTS/skills таким образом, чтобы возникал второй writer authorization semantics.

### 18.1 `ManagedArtifactOwnership`

Logical model:

```yaml
schema: opencode-setup.managed-ownership/v1
artifacts:
  - id: opencode.permission-policy
    owner: opencode_permissions
    managed_by: opencode_setup
    target: <semantic/path target>
    source: <canonical artifact>
    legacy_signatures: []
    conflict_policy: preserve-and-report
```

### 18.2 Reconciliation rules

- known exact legacy owned artifact -> migrate/remove according to explicit rule;
- current managed artifact -> reconcile;
- managed but locally modified -> conflict/preserve unless explicit approved recovery path;
- unknown artifact -> preserve/conflict;
- successful deploy command without effective-state verification is insufficient.

Reconciliation must account for all relevant effective config channels of the target OpenCode version rather than assuming one filename is authoritative.

## 19. Skills and instructions

Skills/AGENTS may describe workflow and routing, например:

```text
Use agent-safe controlled execution for state-changing operation.
Use ssh-relay for remote transport.
```

Они не должны быть единственной реализацией правил:

```text
always ask the user for X
never ask the user for Y
this wrapper is pre-approved
```

Если такое правило влияет на фактическую authorization semantics, оно принадлежит `opencode_permissions` и должно иметь техническое enforcement.

## 20. State precedence

Для одной operation применяется следующий принцип:

```text
POLICY_DENY        -> terminal authorization stop
ASK_USER           -> no execution until trusted approval
ALLOW              -> may proceed to runtime checks
RUNTIME_REJECT     -> terminal for current attempt
UNEXPECTED         -> recovery/read-only diagnosis
REMOTE_UNKNOWN     -> no blind retry
DONE               -> verified completion
```

`ALLOW` не гарантирует, что operation будет выполнена; он только разрешает переход к execution safety.

## 21. Threat boundaries для acceptance

Обязательно проверяются без destructive execution:

- model forges `--approved`;
- wrapper hides hard-denied payload;
- grant created for A but execution requests B;
- replay of expired/single-use grant;
- remote payload differs from approved payload;
- stale ScopedKB fact пытается ослабить decision;
- legacy config continues to supply blanket wrapper allow after new deploy;
- locally modified unknown config is silently overwritten;
- auditor proposes allow over hard deny;
- runtime preflight reports safe but authorization is absent.

## 22. Версионирование

Каждый machine-readable contract должен иметь schema version. Breaking semantic changes требуют новой major contract version либо явно совместимого migration layer.

OpenCode-version-sensitive implementation details не должны считаться постоянными invariants этого документа; они фиксируются в version-specific design/evidence docs.

## 23. Acceptance для Contract v1

Contract может перейти из DRAFT в accepted design только если:

- ownership границы согласованы;
- collision matrix не содержит неразрешённого второго authorization owner;
- определён trustworthy authorization handoff requirement;
- wrapper boundary покрыт acceptance cases;
- live reconciliation ownership согласован с `opencode_setup`;
- standalone compatibility не создаёт скрытый integrated writer;
- unresolved implementation choices перечислены явно и не подменены предположениями.
