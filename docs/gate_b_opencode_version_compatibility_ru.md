# Gate B — OpenCode version compatibility contract

Статус: **REVIEW PROPOSAL**  
Дата: 2026-09-02

## 1. Проблема

OpenCode выпускается часто. Permission semantics, parser behavior, config precedence, approval lifecycle или server/tool integration primitives могут измениться между версиями. Поэтому нельзя строить production authorization policy на неявной предпосылке «последний patch совместим».

Stage 0 evidence для `1.18.18` сохраняется как baseline. Новые версии проверяются отдельно и не переписывают историческое evidence.

## 2. Три разных понятия версии

Всегда различать:

```text
baseline_runtime_version
installed_runtime_version
latest_upstream_version
```

На 2026-09-02:

```text
baseline_runtime_version = 1.18.18
latest_upstream_version  = 1.18.26
installed_runtime_version = MUST BE OBSERVED on target machine before deploy
```

`latest_upstream_version` не является автоматически deployment target.

## 3. `OpenCodeCompatibilityProfile`

Для каждой exact version/ref, которую планируется использовать с managed permission artifact, хранится machine-readable profile.

Минимальная logical schema:

```yaml
schema: opencode-compatibility/v1
opencode_version: 1.18.26
upstream_ref: 774cc7c1914e4329eefde5a669f938b0cf566661
status: SOURCE_REVALIDATED
policy_contract_version: native-policy/v1
platforms:
  windows: source_only
  linux: source_only
critical_evidence:
  permission_service:
    path: packages/opencode/src/permission/index.ts
    blob: 2e27ff2424dbb000ea9ed7f73471769716ba40a1
  tool_context:
    path: packages/opencode/src/tool/tool.ts
    blob: e5e7802858ca5cd2250f8f34c4725a25c7a3221d
  permission_http:
    path: packages/opencode/src/server/routes/instance/httpapi/groups/permission.ts
    blob: 79959db499bd12a359ac84a9a189faebc84c016e
  permission_http_auth:
    path: packages/opencode/src/server/routes/instance/httpapi/middleware/authorization.ts
    blob: 61ce39ad39e0643758861e82220953399bb6c824
  shell_tool:
    path: packages/opencode/src/tool/shell.ts
    blob: 1e4423e017740617bc6e0df36ad9dcdb0197bccb
verified_semantics:
  last_matching_rule_wins: true
  implicit_no_match: ask
  hard_deny_precedes_ask: true
  tool_context_ask: true
  permission_reply_once_current_request: true
  opaque_interpreter_payload_recursive_semantics: false
runtime_evidence: null
notes: ...
```

Blob list может расширяться, если policy начинает зависеть от нового upstream path.

## 4. Статусы evidence

### `UNVALIDATED`

Версия обнаружена, но compatibility audit не выполнен. Production deploy запрещён.

### `SOURCE_EQUIVALENT`

Critical source fingerprints и dependency/parser anchors совпадают с уже validated profile. Это позволяет сократить аудит, но само по себе не доказывает installed runtime.

### `SOURCE_REVALIDATED`

Exact upstream source/tests просмотрены, изменившиеся critical paths классифицированы, version-sensitive semantics подтверждены или bounded.

### `RUNTIME_REVALIDATED`

На фактически установленной версии выполнены безопасные version-specific probes/acceptance, необходимые для current policy contract.

### `DEPLOYABLE`

Source + необходимый runtime evidence + corpus acceptance совместимы с конкретным generated policy artifact. Только такой profile разрешает managed production deployment.

## 5. Fast path для нового patch release

Новый OpenCode release не должен автоматически запускать полный Stage 0 с нуля. Используется bounded compatibility gate:

```text
new version detected
-> resolve exact upstream tag/commit
-> compare critical source/dependency fingerprints
-> if unchanged: SOURCE_EQUIVALENT
-> run version-sensitive corpus/source assertions
-> if required: minimal safe runtime probes
-> promote profile to DEPLOYABLE
```

Если изменился любой critical permission/parser/config/integration primitive:

```text
stop fast path
-> targeted source/test audit of changed semantics
-> update cases/design if needed
-> runtime revalidation where material
-> only then DEPLOYABLE
```

Semver patch/minor alone не является evidence.

## 6. Critical change classes

Полный или targeted re-audit обязателен при изменениях как минимум в:

- permission matching/order/default action;
- `once` / `always` / `reject` lifecycle;
- saved/durable approval semantics;
- agent/subagent permission composition;
- shell parser/grammar versions or scanner logic;
- interpreter payload handling;
- external-directory detection;
- secret defaults;
- config merge/precedence/effective layers;
- `Tool.Context.ask`/custom tool bridge;
- permission event/list/reply API;
- server authentication/client separation;
- shell environment inheritance;
- new auto-approval/auto mode behavior;
- new tools whose default permission changes authorization surface.

## 7. Current revalidation: 1.18.18 -> 1.18.26

Confirmed source observations:

1. Upstream latest release on 2026-09-02 is `v1.18.26`.
2. `v1.18.26` tag resolves to commit `774cc7c1914e4329eefde5a669f938b0cf566661`.
3. `Permission.evaluate/ask/reply` critical blob equals the previously inspected 1.18.18 blob.
4. `Tool.Context.ask` critical blob equals the previously inspected 1.18.18 blob.
5. Experimental V1 permission HTTP route and its authorization middleware blobs are unchanged from the 1.18.18 evidence slice.
6. Current `shell.ts` retains Tree-sitter scan, `ctx.ask` and `process.env` child environment architecture; GitHub path history query since the 1.18.18 release timestamp returned no changes.

Therefore `1.18.26` can be recorded as **SOURCE_REVALIDATED for the Gate B primitives inspected here**, not yet `RUNTIME_REVALIDATED` and not yet production `DEPLOYABLE` because Gate B policy itself does not exist.

## 8. Managed update contract with `opencode_setup`

Future `opencode_setup` behavior must follow:

```text
detect installed OpenCode version
-> locate exact compatibility profile
-> require profile status allowed for requested operation
-> select referenced canonical artifact
-> deploy/reconcile without semantic rewrite
-> verify actual effective state/version
```

If installed version is absent from compatibility registry:

- do not silently use nearest/previous/latest artifact;
- do not infer compatibility from semver;
- report `UNVALIDATED_OPENCODE_VERSION` (exact naming to be defined in F);
- preserve current state and require compatibility work before changing authorization semantics.

## 9. Auto-update implication

A managed integrated environment cannot rely on uncontrolled OpenCode auto-update while simultaneously claiming version-locked permission guarantees.

Gate B does not choose the installation/update mechanism owned by `opencode_setup`, but imposes this invariant:

> The effective runtime version used with a managed authorization artifact must be observable and must have a compatible profile before that artifact is considered valid.

Gate F must decide whether this is achieved by pinning/managed updates, startup validation, or another technical mechanism. Silent version drift without validation is not acceptable.

## 10. Acceptance for version lifecycle

Before Gate B closure:

- profile schema is machine-readable;
- at least baseline `1.18.18` and current source-reviewed `1.18.26` profiles can be represented;
- a synthetic unknown future version fails compatibility selection;
- unchanged critical fingerprints take fast path but do not skip mandatory runtime probes;
- changed critical fingerprint triggers targeted re-audit;
- setup interface never selects «closest version»;
- no compatibility profile contains secrets or raw secret-bearing config.
