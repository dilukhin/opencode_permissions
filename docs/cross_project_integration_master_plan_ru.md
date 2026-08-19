# Cross-project integration master plan

Статус: **DRAFT / reviewable plan**.

Этот документ не доказывает наличие реализации и не закрывает ни один implementation gate. Он фиксирует порядок проектирования и проверки стыковки `opencode_permissions`, `agent-safe`, `ssh_relay`, `ScopedKB` и `opencode_setup` до изменения production permission policy.

## 1. Причина и цель

Текущий аудит показал, что несколько проектов потенциально влияют на один и тот же effective OpenCode environment: native permissions, global/project instructions, skills, wrappers и runtime approval semantics. Наиболее существенный текущий конфликт — `agent-safe` способен устанавливать собственные OpenCode permission defaults и принимать caller-supplied `--approved`, тогда как `opencode_permissions` должен стать каноническим владельцем authorization semantics.

Цель интеграции — получить систему, где каждый проект имеет один явно ограниченный класс ответственности и не может незаметно расширить полномочия соседнего проекта.

Целевая логика:

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

### 2.1 `opencode_permissions`

Единственный канонический владелец:

- `ALLOW / ASK_USER / DENY`;
- hard-deny invariants;
- safe auto-allow families;
- обязательных ASK-зон;
- interpretation command/effect semantics для authorization;
- approval context и approval semantics;
- scope/lifetime authorization;
- policy version и decision evidence.

### 2.2 `agent-safe`

Владелец execution safety уже авторизованной state-changing operation:

- target;
- expected state;
- checkpoint/recovery feasibility;
- execution preconditions;
- smallest mutation;
- verify;
- recovery/incident handling.

`agent-safe` может сузить разрешённое действие через `RUNTIME_REJECT`, но не может повысить authorization или самостоятельно заменить `ASK_USER` на `ALLOW`.

### 2.3 `ssh_relay`

Владелец transport и remote machine outcome:

- delivery/session identity;
- job lifecycle;
- transfer semantics;
- reconnect/status;
- `started/running/succeeded/failed/stopped/unknown`.

Transport metadata вроде `--risky` не является authorization decision.

### 2.4 `ScopedKB`

Владелец scoped contextual facts и provenance. Он может поставлять проверенные attributes, но не `allow`, `deny`, `ask_user`, `approval_required` и другие authorization decisions.

### 2.5 `opencode_setup`

Единственный reconciler shared live OpenCode environment. Он устанавливает артефакты их канонических владельцев, обнаруживает legacy/conflicting writers и не создаёт собственную permission policy.

## 3. Обязательные архитектурные invariants

1. **Single authorization owner.** Только `opencode_permissions` определяет `ALLOW / ASK_USER / DENY`.
2. **No self-approval.** Model-controlled input не может сам служить достаточным доказательством пользовательского approval.
3. **Exact binding.** Authorization должен быть связан с конкретной нормализованной operation/target/effects; замена payload после approval недопустима.
4. **Runtime may narrow, never broaden.** `agent-safe` может остановить разрешённое действие, но не разрешить запрещённое.
5. **Transport has no authority.** `ssh_relay` не принимает authorization decisions.
6. **Context has no authority.** ScopedKB предоставляет facts, а не policy decisions.
7. **Prompt text is not a security boundary.** `AGENTS.md`, skills и model instructions не заменяют технический permission layer.
8. **Single live reconciler.** Shared OpenCode environment изменяет `opencode_setup`; другие проекты публикуют собственные source artifacts/contracts.
9. **Fail closed on ownership conflict.** Unknown или локально модифицированный conflicting artifact не удаляется/перезаписывается blind action.
10. **Unknown effect != safe.** Неопределённость в effects/context не может автоматически ослабить решение.
11. **Hard DENY precedence.** Hard policy deny не отменяется runtime layer, auditor, ScopedKB fact или transport metadata.

## 4. Межпроектные контракты v1

До реализации необходимо спроектировать reviewable schemas/semantics следующих logical contracts. Конкретный wire format пока не фиксируется.

### 4.1 `ContextFacts`

Минимально должны быть определены:

- fact/value;
- scope;
- provenance;
- freshness/observed_at;
- confidence/status (`verified`, `observed`, `stale`, `unknown` или согласованный эквивалент);
- sensitivity classification, если требуется.

Критерий: missing/stale/weaker fact не делает authorization более permissive без явного policy rule, допускающего именно такой уровень evidence.

### 4.2 `NormalizedOperation`

Должен описывать именно действие, которое будет авторизовано:

- semantic operation/purpose;
- target;
- channel (`local`, `remote`, etc.);
- normalized payload/arguments либо их canonical representation;
- expected effects;
- operation identity/hash для binding.

### 4.3 `AuthorizationDecision`

Минимум:

- `ALLOW | ASK_USER | DENY`;
- rule/reason;
- policy version;
- normalized operation identity;
- evidence/context dependencies;
- hard-deny marker там, где применимо.

### 4.4 `AuthorizationGrant`

Нужен только для перехода от decision к controlled execution. Требования:

- non-forgeability через model-controlled command channel;
- exact binding к operation/target/effects;
- ограниченный scope;
- lifetime/expiry или single-use semantics;
- provenance (`policy` или подтверждённый `user`);
- защита от payload substitution/replay согласно принятой threat model.

Обычный caller-supplied Boolean вроде `--approved` не считается достаточным integrated authorization proof.

Конкретная реализация — capability handle, trusted bridge, IPC, broker token, custom OpenCode tool или другой механизм — отдельное решение следующего design slice.

### 4.5 `ExecutionPreflight`

`agent-safe` должен иметь возможность до mutation вернуть read-only результат:

- executable/not executable;
- target resolution;
- reversibility/checkpoint capability;
- verify method;
- recovery constraints;
- runtime safety blockers.

Preflight не принимает authorization decision.

### 4.6 `ExecutionResult`

Минимальные результаты:

- `DONE`;
- `RUNTIME_REJECT`;
- `UNEXPECTED`;
- фактический observed state/evidence;
- verify result;
- recovery status, если применимо.

### 4.7 `RemoteOutcome`

`ssh_relay` возвращает machine/transport outcome без authorization semantics:

- correlation/job identity;
- `started/running/succeeded/failed/stopped/unknown`;
- observable transport evidence;
- terminal/non-terminal semantics.

### 4.8 `ManagedArtifactOwnership`

Для reconciliation должны быть определены:

- artifact/path/semantic section;
- canonical owner;
- managed scope;
- expected source/version;
- legacy signatures;
- modification/conflict detection;
- migration/removal policy.

## 5. Этап A — Cross-project contract gate

Работа ведётся в архитектурном диалоге `opencode_permissions`.

### Deliverables

- этот master plan;
- отдельный `cross_project_integration_contract_v1_ru.md` после review;
- collision matrix по effective permission channels;
- unresolved design decisions register;
- acceptance matrix для последующих project gates.

### Решения, которые должны быть приняты

- точная граница PDP/PEP между `opencode_permissions` и `agent-safe`;
- требования к authorization handoff/non-forgeability;
- preflight до/после ASK и какие поля preflight разрешено показывать пользователю;
- ownership model для live config;
- migration compatibility policy для standalone `agent-safe`.

### Gate A acceptance

Gate закрыт только если:

- каждый authorization-sensitive artifact имеет одного канонического владельца;
- ни один интерфейс не требует model-controlled self-approval;
- wrapper/remote paths не могут считаться безопасными только по имени внешней команды;
- unresolved implementation choices явно отделены от обязательных invariants;
- не требуется изменение production policy для доказательства design closure.

## 6. Этап B — `opencode_permissions`

Отдельный диалог и отдельный project gate.

### Scope

- закрепить ownership authorization semantics;
- спроектировать `NormalizedOperation`, `AuthorizationDecision`, `AuthorizationGrant`;
- определить exact binding и lifetime/scope;
- определить trusted controlled-operation integration point;
- расширить Native-policy acceptance wrapper/transport cases;
- определить native rules для direct safe path с учётом wrapper collision;
- не реализовывать deterministic classifier/auditor до закрытия Native-policy gate.

### Обязательные regression/corpus families

- `safe exec-risky ...`;
- `python -m agent_safe exec-risky ...`;
- variants с caller-provided `--approved`;
- nested interpreter/wrapper payload;
- `ssh_relay` remote payload;
- argument/payload substitution после approval;
- unknown effect/context;
- hard DENY внутри wrapper.

Проверки только parser-only/mocks/synthetic fixtures; destructive validation запрещён.

### Gate B acceptance

- native/direct policy не использует blanket wrapper allow как доказательство безопасности payload;
- authorization contract reviewable и технически предполагает non-forgeable handoff;
- hard-deny semantics сохраняются на nested/controlled paths;
- corpus и метрики prompt reduction учитывают wrappers;
- classifier/auditor остаются `NOT STARTED`, если Native-policy gate ещё не закрыт.

## 7. Этап C — `agent-safe`

Отдельный диалог проекта после Gate B design closure.

### Scope

- отделить authorization от execution safety;
- заменить integrated reliance на caller-supplied `--approved` на согласованный authorization handoff;
- сохранить standalone/manual compatibility только как явно отделённый режим, если он нужен;
- пересмотреть `risk-gate`/`safe-cli`: routing в controlled execution path не должен означать самостоятельный `ASK_USER`;
- убрать ownership production OpenCode permission policy из integrated bootstrap;
- определить `ExecutionPreflight`/`ExecutionResult`;
- сохранить checkpoint/verify/recovery/hard runtime blockers.

### Gate C acceptance

- `agent-safe` не может повысить upstream authorization;
- подделка CLI flag не создаёт integrated authorization;
- mismatch между grant и фактической operation блокируется;
- runtime preflight может reject разрешённую operation;
- standalone mode, если сохранён, явно изолирован и не конфликтует с managed integrated mode;
- tests покрывают authorization mismatch без destructive execution.

## 8. Этап D — `ssh_relay`

Отдельный короткий диалог после определения controlled execution contract.

### Scope

- закрепить transport-only ownership;
- формализовать `RemoteOutcome`;
- проверить `--risky`/прочие labels на отсутствие approval semantics;
- определить correlation между authorization/execution/job identity без передачи transport'у права authorization;
- regression: dangerous remote payload нельзя скрыть за blanket allowance relay wrapper.

### Gate D acceptance

- relay не возвращает и не трактует `ALLOW/ASK/DENY`;
- `unknown` outcome не считается success и не вызывает blind retry;
- remote payload остаётся видимым upstream semantic analysis/controlled path;
- transport metadata не ослабляет policy.

## 9. Этап E — `ScopedKB`

Отдельный диалог. Реализация может быть отложена, если текущий код ещё не производит такой context.

### Scope

- определить `ContextFacts` и provenance/freshness semantics;
- запретить будущим adapters/startup-context generators создавать authorization policy;
- определить sensitivity/redaction boundary;
- определить fail-safe consumption stale/unknown context.

### Gate E acceptance

- ScopedKB является PIP/context provider, не PDP;
- generated context не содержит нормативных permission decisions;
- stale/missing facts не ослабляют policy;
- provenance достаточен для policy rules, которые на него ссылаются.

## 10. Этап F — `opencode_setup`

Отдельный диалог после стабилизации артефактов B–E.

### Scope

- стать единственным reconciler shared live OpenCode environment;
- определить `ManagedArtifactOwnership` manifest/registry;
- устанавливать policy artifact от `opencode_permissions` без самостоятельного изменения смысла;
- устанавливать skills/runtime artifacts `agent-safe` и `ssh_relay`;
- обнаруживать legacy permission writers, включая старый `agent-safe` bootstrap config;
- учитывать одновременно возможные `opencode.json` и `opencode.jsonc`, project/global layers и другие version-relevant effective channels;
- known exact legacy -> migrate/remove;
- locally modified/unknown -> preserve + conflict, без blind delete;
- verify actual effective state после reconciliation.

### Gate F acceptance

На synthetic fixtures:

```text
old supported state A -> desired C
old supported state B -> desired C
partial/mixed state -> desired C
C -> C
```

при этом:

- unknown/user-owned artifacts сохраняются;
- известные obsolete managed artifacts не продолжают влиять на effective permission policy;
- повторный deploy идемпотентен в managed scope;
- успешный exit code без end-state verification недостаточен.

## 11. Этап G — Cross-project integration acceptance

После project-specific gates проводится отдельный integration dialogue/run.

### Обязательная acceptance matrix

1. Direct deterministic-safe operation -> native `ALLOW` -> execute.
2. Controlled risky operation -> decision/grant -> `agent-safe` -> verify.
3. Hard-dangerous operation -> `DENY` до mutation.
4. Forged/caller-supplied approval marker -> не создаёт authorization.
5. Grant/payload mismatch -> reject.
6. Dangerous nested command за `safe` wrapper -> не получает blanket allow.
7. Dangerous remote payload за `ssh_relay` -> не получает blanket allow.
8. Runtime preflight failure после upstream ALLOW -> `RUNTIME_REJECT`.
9. Remote outcome `unknown` -> read-only diagnosis/recovery flow, не blind retry.
10. Stale/unknown ScopedKB fact -> не ослабляет authorization.
11. Mixed legacy OpenCode config -> `opencode_setup` приводит managed scope к одному desired state.
12. Unknown locally modified artifact -> preserve/conflict, не blind overwrite/delete.
13. Hard DENY не отменяется auditor/runtime/context/transport layer.
14. Approval относится только к согласованной normalized operation и не переносится на подменённый payload.

### Gate G closure

Integration gate закрывается только при наличии evidence по всем применимым строкам matrix и явном списке deferred/non-applicable cases.

## 12. Зависимости и рекомендуемый порядок

```text
A  Cross-project contract
|
v
B  opencode_permissions authorization/native design
|
v
C  agent-safe execution integration
|
+------> D  ssh_relay transport boundary
|
+------> E  ScopedKB context boundary
|          (может быть design-only/deferred)
\----------/
     |
     v
F  opencode_setup reconciliation
     |
     v
G  integration acceptance
```

`D` и `E` могут частично выполняться параллельно после стабилизации интерфейсов B/C, но implementation changes не должны опережать согласованный contract.

## 13. Организация диалогов

- текущий архитектурный диалог: A и coordination;
- отдельный диалог `opencode_permissions`: B;
- отдельный диалог `agent-safe`: C;
- отдельный диалог `ssh_relay`: D;
- отдельный диалог `ScopedKB`: E;
- отдельный диалог `opencode_setup`: F;
- свежий integration dialogue: G.

В каждом project dialogue сначала проверяется актуальный default branch/implementation через GitHub Connector; cross-project plan является design input, но не заменяет source of truth конкретного репозитория.

## 14. Stop/escalation conditions

Работа по affected path останавливается и возвращается к архитектурному контракту, если обнаружено хотя бы одно:

- второй live writer effective authorization policy;
- необходимость доверять model-controlled `--approved`/эквиваленту;
- wrapper, скрывающий payload от semantic authorization;
- невозможность связать grant с фактической operation;
- неизвестный ownership live artifact, который требуется удалить/переписать для продолжения;
- version-sensitive OpenCode behavior, не подтверждённый для целевой версии;
- proposal, при котором prompt/instruction становится единственной safety boundary;
- изменение одного проекта требует переноса runtime responsibility другого проекта без отдельного архитектурного решения.

## 15. Нерешённые design decisions

До implementation должны быть отдельно решены, но сейчас не фиксируются как факт:

1. Конкретная форма authorization handoff: trusted in-process bridge, custom OpenCode tool, capability handle, IPC/broker или другой механизм.
2. Нужно ли выполнять read-only `agent-safe` preflight до ASK, чтобы показать пользователю reversibility/verification, и какие поля являются trustworthy.
3. Single-use против short-lived scoped authorization grants.
4. Формат ownership manifest для `opencode_setup`.
5. Compatibility lifecycle старого `agent-safe opencode-bootstrap`.
6. Способ versioning/correlation `NormalizedOperation` между permission layer и execution layer.
7. Минимальный `ContextFacts` schema и требования к provenance/freshness.
8. Где физически живёт canonical cross-project contract после стабилизации и какие части дублируются только ссылками в соседних repos.

## 16. Ближайшее действие

До перехода в отдельный project dialogue закрыть **Gate A design review**:

1. проверить этот master plan;
2. принять/исправить ownership и invariants;
3. разработать concrete `cross_project_integration_contract_v1_ru.md` с logical schemas/state transitions/threat boundaries;
4. составить collision matrix текущих и legacy effective permission channels;
5. подготовить starter/handoff для этапа B (`opencode_permissions` Native-policy integration design).

До этого production permission policy, deterministic classifier, auditor и runtime approval mechanisms не изменять.
