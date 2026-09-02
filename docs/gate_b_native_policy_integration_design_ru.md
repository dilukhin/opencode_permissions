# Gate B — Native-policy integration design

Статус: **REVIEW PROPOSAL / implementation not started**  
Дата: 2026-09-02  
Проект: `dilukhin/opencode_permissions`

Этот документ фиксирует reviewable design Gate B. Он не является production permission policy, не закрывает Gate B и не разрешает переход к deterministic classifier или model auditor.

## 1. Версионная модель

Stage 0 закрыт по фактически исследованному OpenCode `1.18.18`. Это immutable baseline evidence, а не вечная целевая версия.

На 2026-09-02 upstream latest release — `v1.18.26` (`anomalyco/opencode` tag commit `774cc7c1914e4329eefde5a669f938b0cf566661`). Source revalidation показала, что ключевые V1 permission primitives, использованные Stage 0/Gate B, между baseline и `1.18.26` не изменились по проверенным blob identities/paths:

- `packages/opencode/src/permission/index.ts`;
- `packages/opencode/src/tool/tool.ts`;
- `packages/opencode/src/server/routes/instance/httpapi/groups/permission.ts`;
- `packages/opencode/src/server/routes/instance/httpapi/middleware/authorization.ts`.

Для `packages/opencode/src/tool/shell.ts` повторная проверка `v1.18.26` подтверждает ту же архитектуру shell scan/permission ask; GitHub path history после даты `1.18.18` не показала изменений этого файла.

Это **не** означает автоматическую совместимость будущих версий и не заменяет runtime observation установленной версии.

### 1.1 Инвариант обновления

`latest` никогда не является security-compatible только потому, что номер версии новее.

Для каждой фактически устанавливаемой версии требуется `OpenCodeCompatibilityProfile` со статусом evidence. Неизвестная версия не получает production policy автоматически.

Минимальные статусы:

```text
UNVALIDATED
SOURCE_EQUIVALENT
SOURCE_REVALIDATED
RUNTIME_REVALIDATED
DEPLOYABLE
```

`opencode_setup` в будущем должен определять установленную версию и deploy только artifact/profile, явно совместимый с ней. Он не должен самостоятельно выводить совместимость из semver.

Подробный lifecycle: `docs/gate_b_opencode_version_compatibility_ru.md`.

## 2. Два execution path

### 2.1 Direct native path

Только для операций, безопасность которых достаточно точно выражается native permission matcher целевой версии:

```text
deterministic safe -> native ALLOW -> execute
hard-dangerous      -> native DENY
otherwise           -> ASK / controlled path
```

### 2.2 Controlled path

Для state-changing, wrapper-mediated, remote/transfer, interpreter/unknown-effect операций:

```text
proposed operation
-> normalize target/payload/effects
-> authorization decision
-> trusted exact-bound handoff
-> runtime preflight/execution/verify
```

Generic wrapper name не является authorization proof.

## 3. Порядок native rules

Для target semantics с `last matching rule wins` logical order должен быть:

1. conservative broad `ASK` fallback;
2. narrow deterministic `ALLOW` families;
3. mandatory `ASK` exceptions/controlled-path routing;
4. hard `DENY` exceptions последними.

Exact JSON/JSONC artifact ещё не создаётся. Gate B сначала обязан доказать representability и regression behavior на corpus.

## 4. Proposed native families

### 4.1 Global deterministic ALLOW candidates

Кандидаты для auto-ALLOW после corpus verification:

- structured non-secret `read` внутри worktree;
- structured `glob` / `grep` / `list` внутри worktree;
- exact read-only Git families: `git status`, `git diff`, `git log`, `git show` и только отдельно проверенные read-only extensions;
- exact read-only transport/status operation `ssh_relay status`, если current CLI contract подтверждён;
- другие exact diagnostics только после positive + negative pair tests.

Нельзя превращать семейство в blanket executable allow (`git *`, `ssh_relay *`, `python *`).

### 4.2 Trusted-workspace ALLOW candidates

Build/test (`cmake --build`, `ctest`, exact `python -m pytest`) могут auto-ALLOW только если trust boundary workspace реализована технически и не выводится из model claim/purpose.

До определения ownership/project-profile mechanism они остаются design candidates, а не global production allow.

### 4.3 Mandatory ASK / controlled-path zones

До появления достаточного deterministic effect analysis обязательно сохраняются `ASK`/controlled routing для:

- `edit` / `write` / `apply_patch`, пока не определён доказуемый target scope для auto-ALLOW;
- external-directory access, кроме отдельно разрешённого exact scope;
- `bash -c`, `sh -c`, PowerShell `-Command`, `cmd /c`, `python -c`, `node -e` и прочих opaque interpreter payload;
- `find -exec/-execdir/-ok`, `xargs` и другие nested execution forms, если semantic payload не доказан native matcher;
- generic `safe`, `python -m agent_safe`, `ssh_relay exec/job/upload/download`;
- unknown/custom CLI;
- redirects/state-changing pipelines, которые не попали под hard deny;
- неизвестные effects/context dependencies.

Unknown effect != safe.

### 4.4 Hard DENY invariants

Native hard deny должен покрывать только те syntactic/effect families, которые matcher действительно способен гарантированно распознать. Минимальные accepted classes:

- destructive filesystem operations (`rm`, `Remove-Item`, `del`, destructive `find`, и exact equivalents);
- destructive Git (`reset --hard`, `clean -f/-fd`, destructive branch deletion, force push);
- privilege escalation/elevation;
- service/system lifecycle mutations;
- download-and-execute / dynamic evaluation families, где syntax recognizable;
- known secret/private-key/credential reads;
- direct mutation canonical live authorization-policy artifacts;
- caller/model-controlled approval markers (`--approved`/equivalent) в integrated wrapper path;
- known dangerous nested payload inside a recognized wrapper pattern.

Hard deny не претендует на semantic completeness произвольного CLI. Если dangerous effect не доказан syntactically, fallback остаётся `ASK`, а не `ALLOW`.

## 5. Wrapper / controlled-path decision table

| Operation family | Native Gate B result | Target path |
|---|---|---|
| `ssh_relay status` | narrow `ALLOW` candidate | direct native |
| `ssh_relay exec -- <payload>` | `ASK`, либо hard `DENY` для exact known-dangerous pattern | controlled |
| `ssh_relay job ...` | `ASK`, dangerous exact pattern -> `DENY` | controlled |
| `ssh_relay upload/download` | `ASK` | controlled transfer |
| `ssh_relay --risky ...` | label не даёт authorization; decision по operation | controlled |
| `safe exec-risky ...` | `ASK`, dangerous exact pattern -> `DENY` | controlled |
| `safe ... --approved ...` | `DENY` в integrated approval-substitution form | rejected/controlled redesign |
| `python -m agent_safe exec-risky ...` | `ASK`, dangerous exact pattern -> `DENY` | controlled |
| nested interpreter behind wrapper | `ASK`, dangerous exact pattern -> `DENY` | controlled |
| unknown wrapper/CLI | `ASK` | residual uncertainty |

## 6. `NormalizedOperation` refinement

Logical schema remains implementation-neutral, but Gate B requires the following semantics:

```yaml
schema: normalized-operation/v1
operation_id: opaque-correlation-id
channel: local|remote|transfer|other
execution_path: native|controlled
source_tool_call:
  session_id: ...
  message_id: ...
  call_id: ...
workspace:
  root_identity: ...
  platform: ...
targets:
  - kind: file|directory|repository|host|service|transfer_endpoint|other
    canonical_identity: ...
payload:
  kind: argv|structured_tool_args|remote_argv|transfer|other
  canonical_value: ...
expected_effects: [...]
context_dependencies: [...]
identity:
  canonicalization_version: ...
  digest: ...
```

Requirements:

1. `purpose`/model rationale не входит в authorization identity.
2. Payload, target, remote host, transfer direction или authorized effects substitution обязаны менять identity.
3. Canonicalization должна основываться на representation, максимально близком к фактически исполняемым structured data/argv, а не на косметической shell string.
4. Path case, separators, symlinks/reparse points, worktree identity и platform quoting требуют fixtures до закрытия U2.
5. `operation_id` — correlation, но не authorization secret.

## 7. `AuthorizationDecision`

Предлагаемый logical result:

```yaml
schema: authorization-decision/v1
decision: ALLOW|ASK_USER|DENY
operation_identity: ...
policy_artifact_id: ...
compatibility_profile: ...
rule_ids: [...]
hard_deny: false
reason_code: ...
approval_provenance: policy|user|none
```

Decision не является bearer capability и не разрешает downstream менять payload.

## 8. `AuthorizationGrant` и native approval primitive

### 8.1 Что подтверждено в OpenCode 1.18.18 и source-revalidated 1.18.26

Custom tool `Tool.Context` получает `sessionID`, `messageID`, `callID` и `ctx.ask(...)`. Session tool bridge дополняет permission request `tool: { messageID, callID }` и effective ruleset. Native `Permission.reply("once")` продолжает конкретный pending request; `always` добавляет tool-supplied patterns.

Это делает same-tool-call continuation полезным integration primitive: approval не обязан возвращаться модели как `--approved=true`.

### 8.2 Почему stock primitive пока не закрывает U1

Experimental permission HTTP surface имеет `list` и `reply` endpoint. TUI при выборе `Allow once` отправляет обычный `permission.reply` с `requestID`; отдельного cryptographic user assertion в этом path нет.

Server authentication включается только при `OPENCODE_SERVER_PASSWORD`. При отсутствии password middleware пропускает request. При обычной password configuration shell tool формирует child environment как `process.env + shell.env overrides`, то есть server password по умолчанию наследуется model-controlled shell process.

Следовательно:

- unauthenticated permission API не удовлетворяет non-forgeability;
- Basic auth secret, доступный model-controlled child environment, также не является достаточной isolation boundary;
- `ctx.ask()` можно использовать как UX/continuation primitive только вместе с отдельной технической защитой reply channel.

Evidence details: `docs/gate_b_authorization_handoff_research_ru.md`.

### 8.3 Requirements к acceptable handoff

Выбранный mechanism обязан обеспечить одновременно:

1. approval reply/capability недоступны model-controlled command/tool inputs;
2. credential/capability не наследуется model-controlled process environment;
3. grant exact-bound к `NormalizedOperation`;
4. payload/target substitution rejected before mutation;
5. replay ограничен single-use или эквивалентно узким lifecycle;
6. hard deny не может быть overridden reply/grant;
7. downstream `agent-safe` может только сузить authorization;
8. model не получает executable grant как обычную строку/flag.

Gate B пока **не выбирает** между hardened trusted custom-tool continuation, OS-protected IPC/broker или другим candidate. U1 остаётся OPEN до технического proof.

## 9. Canonical deployable artifact/interface proposal

Source semantics должны принадлежать `opencode_permissions`, а `opencode_setup` — только install/reconcile.

Предлагаемая структура после закрытия design:

```text
policy/
  native/
    rules.v1.json                 # ordered canonical logical rules
  compatibility/
    opencode-<exact-version>.json # evidence/profile

dist/
  opencode/
    <policy-artifact-id>/
      permission.jsonc            # generated deployable artifact
      manifest.json               # owner/version/compatibility/digest
```

Rules:

- `rules.v1.json` — canonical semantics, ordered explicitly;
- renderer живёт в `opencode_permissions`;
- `permission.jsonc` генерируется для совместимого OpenCode contract;
- `manifest.json` перечисляет exact compatibility profiles и artifact digest;
- `opencode_setup` не reorder/rewrite authorization semantics;
- setup определяет installed version, выбирает только compatible `DEPLOYABLE` profile, deploys artifact unchanged в semantic permission scope и выполняет effective-state read-back;
- неизвестная версия/competing effective layer -> conflict/fail closed, а не best-effort permissive merge.

## 10. Corpus и metrics

Stage 0 corpus: 49 cases (`11 allow / 15 ask / 23 deny` conservative expectations).

Gate B добавляет `tests/permission_cases/gate_b_integration.json` с wrapper, approval-substitution, remote job/transfer, nested payload, grant mismatch/replay и unknown-effect cases.

Acceptance metrics должны считаться отдельно:

```text
unsafe_auto_allow_count = 0
dangerous_false_safe_count = 0
unknown_false_safe_count = 0
wrapper_false_safe_count = 0
Stage0D D01-D07 prompt regression = 0
Stage0D D08 hard-deny regression = 0
```

Дополнительно:

- safe deterministic challenge subset: target permission-prompt reduction >= 50%;
- existing conservative ASK cases: reduction измеряется, но не является основанием ослабить unknown/wrapper invariants;
- wrapper cases публикуются отдельной строкой и не могут использоваться для улучшения prompt-reduction metric blanket trust'ом;
- build/test metrics разделяются на trusted-workspace и untrusted/unknown workspace.

## 11. Gate B closure criteria

Gate B можно закрыть только когда одновременно:

1. exact installed OpenCode version имеет compatibility profile с достаточным source/runtime evidence;
2. proposed native rules выражены canonical ordered artifact и simulator/corpus подтверждает expected decisions;
3. hard-deny dangerous cases не регрессировали;
4. unknown/wrapper cases не получили unsafe auto-ALLOW;
5. secret/external-directory boundaries проверены synthetic fixtures;
6. wrapper/remote/transfer corpus выполнен parser-only/mock;
7. `NormalizedOperation` canonicalization fixtures закрывают substitution/path/platform cases;
8. U1 authorization handoff имеет non-forgeability proof или Gate B явно ограничивает scope так, что controlled mutation не объявляется integrated-ready;
9. artifact/interface достаточно определён для будущего `opencode_setup`, без semantic rewriting setup'ом;
10. prompt-reduction acceptance достигнут без false-safe regressions;
11. применимые Gate-B строки cross-project acceptance matrix имеют evidence;
12. production permission policy всё ещё не меняется до отдельного явного решения closure/apply.

## 12. Gate state

```text
Gate A cross-project contract     CLOSED
Gate B design                     REVIEW PROPOSAL
Gate B native-policy verification NOT STARTED/IN PROGRESS BY SLICES
Deterministic classifier          NOT STARTED
Auditor                           NOT STARTED
Production permission policy      UNCHANGED
```

Следующие bounded slices:

1. finalize version compatibility profile schema + update lifecycle;
2. close/reject stock approval primitive candidate by threat-model tests/source proof;
3. implement policy simulator only for native-rule verification (не semantic classifier);
4. extend corpus and compute candidate metrics;
5. review Gate B closure readiness.
