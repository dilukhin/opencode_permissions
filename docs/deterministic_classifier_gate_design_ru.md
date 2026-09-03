# Deterministic classifier gate — design и acceptance

Статус: **DESIGN / IMPLEMENTATION NOT STARTED**  
Дата: 2026-09-03  
Проект: `dilukhin/opencode_permissions`

## 1. Контекст и naming

Gate B / Native-policy integration закрыт для Linux + exact OpenCode 1.18.26.

Следующий внутренний этап `opencode_permissions` — deterministic parser/effect analysis. В этом документе он называется **Deterministic classifier gate**.

Это **не** cross-project Gate C: в `docs/cross_project_integration_master_plan_ru.md` Gate C принадлежит `agent-safe`.

Model auditor остаётся `NOT STARTED` и не входит в этот gate.

## 2. Источники факта

Design основан на актуальном `main` после Gate B closure:

- `docs/gate_b_final_closure_ru.md`;
- `docs/gate_b_native_policy_candidate_metrics_ru.md`;
- `docs/gate_b_normalized_operation_identity_ru.md`;
- `docs/cross_project_integration_contract_v1_ru.md`;
- `docs/cross_project_integration_master_plan_ru.md`;
- `tests/permission_cases/*.json`;
- `tests/normalized_operation/identity_relations.json`;
- canonical Gate B policy `policy/native/rules.v1.json`.

Gate B evidence фиксирует 65 native-scope cases:

```text
ALLOW 6
ASK   30
DENY  29
```

Safety-ALLOW cases, сознательно оставшиеся native ASK:

```text
grep_source
git_diff
cmake_build
ctest
pytest_module
```

Safety-DENY cases, сознательно оставшиеся native ASK:

```text
external_system_write
unknown_cli_delete_claim
```

Эти gaps являются входом classifier, но их historical `expected_decision` не является лицензией автоматически повысить их до ALLOW/DENY без дополнительного proof.

## 3. Цель gate

Добавить deterministic слой между native permissions и будущим auditor/user approval:

```text
native deterministic rules
        |
        +-- DENY  -> terminal DENY
        +-- ALLOW -> terminal ALLOW
        +-- ASK   -> deterministic classifier
                         |
                         +-- proven safe       -> ALLOW
                         +-- proven dangerous  -> DENY
                         +-- residual unknown  -> ASK_USER
```

Classifier должен анализировать **operation/effects/targets**, а не имя внешней команды или prose purpose.

## 4. Главные invariants

### 4.1 Native hard DENY абсолютен

Classifier никогда не вызывается для terminal native DENY и не может его отменить.

### 4.2 Unknown blocks ALLOW

Если operation содержит неподдержанный syntax, opaque payload, unknown executable semantics, unresolved target/effect dependency или непроверяемый context dependency, result не может быть ALLOW.

### 4.3 Composition monotonicity

Для compound/nested operation:

```text
DENY > ASK_USER > ALLOW
```

ALLOW допустим только если **каждый** executable/redirect/transfer/nested payload полностью классифицирован как safe и их composition не добавляет state-changing/unknown effect.

### 4.4 Outer wrapper не даёт trust inner payload

Имена:

```text
safe
python -m agent_safe
ssh_relay
bash/sh/python/node/powershell/cmd
```

не дают blanket ALLOW.

Known dangerous inner payload -> DENY.  
Opaque/unknown inner payload -> ASK_USER.

### 4.5 Purpose не является security input

`purpose`, prompt prose и model explanation не могут понизить risk или удалить effects.

### 4.6 Environment labels не являются proof

Строки corpus вроде `trusted_workspace` — test metadata, не trusted runtime fact.

ALLOW, зависящий от workspace/target/executable boundary, требует trusted preflight identity, а не caller/model label.

## 5. Важная граница build/test

Gate B исторически помечает следующие операции как safety-ALLOW optimization candidates:

```text
cmake --build build
ctest --test-dir build --output-on-failure
python -m pytest -q
```

Но command shape не доказывает effects: build scripts, test code, compiler/linker hooks и imported project code способны выполнять arbitrary process/network/filesystem actions.

Поэтому classifier v1 **не** auto-ALLOW build/test только по CLI + `trusted_workspace`.

До отдельной technical boundary они классифицируются как минимум с effect:

```text
unknown_code_execution
```

и остаются ASK_USER.

Допустимые будущие способы снять uncertainty:

- sandbox/runtime confinement с доказанным effect boundary;
- trusted immutable build/test plan с exact identity;
- другой отдельно reviewable deterministic contract.

Prompt-only утверждение «workspace trusted» недостаточно.

## 6. Parser architecture

Classifier не должен строиться на regex/shlex как полном shell parser.

Целевая граница:

```text
raw tool request
  -> trusted parser adapter
       -> ParsedOperationV1 / command graph
            -> deterministic effect classifier
                 -> NormalizedOperation
                 -> decision
```

### 6.1 Trusted parser adapter

Для shell target OpenCode 1.18.26 основной reference grammar — тот же Tree-sitter bash family, на котором основано native shell scanning OpenCode.

Parser adapter обязан явно отмечать unsupported/opaque nodes. Ошибка parsing -> ASK_USER, а не best-effort ALLOW.

### 6.2 Parsed command graph

Минимальные node kinds:

```text
simple_command
compound
pipeline
redirect
wrapper_payload
remote_payload
transfer
opaque
```

Каждый node содержит только deterministic syntax facts:

- argv boundaries;
- operator kind (`&&`, `||`, `;`, pipeline);
- redirects and destinations;
- nested payload boundaries;
- parser/version provenance;
- unsupported syntax flags.

Effect semantics вычисляются следующим слоем.

## 7. Effect model v1

Минимальный sorted unique vocabulary:

```text
read
search
write
delete
process
git_read
git_destructive
network
transfer
local_write
remote_write
remote_execution
remote_state_change
privilege
process_control
system_service
nested_execution
nested_interpreter
unknown_code_execution
external_directory
system
secrets
unknown
```

`unknown` или `unknown_code_execution` исключают ALLOW.

## 8. Target model v1

Classifier должен различать минимум:

```text
workspace_path
external_path
system_path
repository
local_process
remote_host
remote_path
transfer_source
transfer_destination
unknown_target
```

Target должен иметь trusted identity representation, совместимую с `NormalizedOperation`:

- exact requested representation;
- resolved representation;
- object identity where safely available;
- follow mode;
- parent identity + leaf for nonexistent create target;
- stable remote host identity for remote operations.

## 9. U2 / NormalizedOperation prerequisite

`docs/cross_project_unresolved_decisions_ru.md` оставляет U2 OPEN.

До первого classifier ALLOW, зависящего от deterministic analysis, требуется implementation slice:

1. typed validation `OperationIdentityCore`;
2. deterministic `op-jcs-v1` canonicalization;
3. domain-separated SHA-256 identity;
4. relation fixtures executable, а не только declarative;
5. no float/NaN/Infinity/duplicate-key ambiguity;
6. set fields (`effects`, declared semantic target sets, context dependencies) normalize explicitly, never generically guessed;
7. Windows/Linux path spelling remains conservative;
8. identity material does not include secrets/prose/correlation metadata.

Trusted-boundary recomputation during actual mutation remains downstream integration responsibility, but classifier-generated identity must already be reproducible and exact.

## 10. Initial deterministic analyzers

### 10.1 Structured read/search

`read`/`glob` remain primarily native-owned.

`grep` may become ALLOW only when target scope is deterministic and proven non-secret/non-external. Directory-wide grep is **not** automatically safe merely because the root path name looks like `src`; descendants may contain secret-like files.

Initial safe promotion candidate should therefore use a single trusted non-secret file target or another boundary whose descendants are deterministically constrained.

### 10.2 Git read

`git diff` is not blanket safe: external diff/textconv configuration can execute commands.

Initial classifier may ALLOW only a hardened invocation whose semantics explicitly disable executable diff transforms, with trusted Git executable/repository identity. Existing corpus sample `git diff -- src/example.cpp` remains ASK until such proof exists.

### 10.3 `find`

Narrow allow-list analyzer is feasible for read-only forms such as:

```text
find <trusted subtree> -type f -name <literal/pattern> -print
```

Any `-delete`, `-exec`, `-execdir`, `-ok`, `-okdir`, output-to-file action or unsupported predicate prevents ALLOW; destructive variants DENY where semantics are certain.

### 10.4 Compound operations

Compound may ALLOW only if every child ALLOW and operator adds no unknown/state-changing effect.

Example promotion fixture should use already-proven pure children, e.g.:

```text
pwd && git status --short
```

not a child whose safety is itself unresolved.

### 10.5 Pipelines

Pipeline may ALLOW only when every stage is pure/read-only, stdin/stdout topology is explicit, no file redirects exist, and executable identities/arguments are supported.

Unsupported stage -> ASK_USER.  
Dangerous downstream stage -> DENY.

### 10.6 Interpreters

`bash/sh -c`, `python -c`, PowerShell `-Command`, `cmd /c`, `node -e` stay ASK by default.

Known destructive payload recognized with high-confidence deterministic semantics may DENY, but benign sample does not justify interpreter-wide ALLOW.

### 10.7 Unknown CLI

Unknown executable never ALLOW.

Explicit destructive verb may produce DENY only from a narrowly specified syntactic rule with false-positive regression coverage; otherwise ASK_USER.

### 10.8 Remote / transfer

`ssh_relay` remains transport-only.

Classifier extracts remote payload/transfer effects and target identity. Generic remote exec/job/upload/download remains ASK unless a later exact remote-safe contract exists.

Known privilege/destructive payload -> DENY.

## 11. Classifier result contract

Logical result:

```yaml
schema: classifier-result/v1
decision: ALLOW|ASK_USER|DENY
reason_codes: [...]
parsed_operation: ...
effects: [...]
targets: [...]
uncertainties: [...]
normalized_operation: ... | null
operation_identity: sha256:... | null
policy_provenance:
  native_artifact_id: ...
  classifier_profile_id: ...
```

Rules:

- ALLOW requires `uncertainties=[]` and valid operation identity;
- ASK_USER may carry partial effects/targets + explicit uncertainties;
- DENY records deterministic deny reason and effects/targets when known;
- no secret values in output/logging.

## 12. Initial corpus strategy

Не менять historical safety labels существующих 69 cases.

Добавить classifier projection с отдельными expected fields:

```text
native_decision
classifier_decision_if_invoked
combined_decision
required_effects
required_uncertainties
```

Это позволяет сохранить исходный intent corpus и одновременно честно оставить historical safe candidate в ASK, если deterministic proof отсутствует.

Добавить новые hardened promotion fixtures, минимум:

```text
find_print_trusted_subtree
compound_pwd_git_status
git_diff_no_ext_diff_no_textconv
single_file_grep_nonsecret
```

Каждый ALLOW fixture должен иметь paired negative/mutation cases.

## 13. Safety acceptance metrics

Для classifier gate обязательно:

```text
unsafe_auto_allow = 0
dangerous_false_safe = 0
wrapper_false_safe = 0
unknown_false_safe = 0
secret_false_safe = 0
native_deny_override = 0
unparsed_auto_allow = 0
identityless_auto_allow = 0
```

Дополнительно:

- every combined ALLOW has valid `operation_identity`;
- every expected DENY is DENY or conservative ASK, never ALLOW;
- classifier resolves both known native-DENY gaps where deterministic semantics are implemented, либо явно оставляет ASK with reason;
- safe prompt capture должен быть **строго больше Gate B 54.5%** только после появления sound new ALLOW fixtures; metric нельзя улучшать ослаблением corpus.

## 14. Implementation slices

### DC-0 — U2 identity implementation

- restricted JCS-compatible canonicalizer;
- typed identity-core validation;
- identity digest;
- executable relation fixtures/tests.

### DC-1 — classifier schema + pure composition engine

- `ClassifierResult`;
- effect/target vocab;
- monotonic composition;
- unknown/opaque fail-closed.

### DC-2 — bounded analyzers

- narrow `find`;
- hardened Git read;
- pure compound/pipeline;
- structured single-file grep boundary;
- explicit external-system write DENY;
- unknown destructive verb conservative rule.

### DC-3 — wrapper/remote recursive extraction

- `safe` / `agent_safe` payload visibility;
- `ssh_relay` exec/job/transfer facts;
- no blanket trust;
- dangerous nested payload dominance.

### DC-4 — exact OpenCode adapter proof

- target exact OpenCode version profile;
- parser adapter provenance;
- synthetic/disposable integration only;
- classifier invoked only after native ASK;
- native DENY/ALLOW paths remain unchanged.

## 15. Stop conditions

Остановить affected path, если:

- parser требует heuristic reconstruction raw shell вместо exact AST boundaries;
- ALLOW зависит от model/caller `trusted` label;
- build/test arbitrary code предлагается считать safe без confinement/provenance proof;
- analyzer должен читать/логировать secrets;
- unknown syntax предлагается считать harmless;
- classifier меняет Gate B hard-DENY precedence;
- implementation требует second authorization writer или execution authority;
- exact target OpenCode semantics изменились без revalidation.

## 16. Gate closure criteria

Deterministic classifier gate закрывается только когда:

1. DC-0 identity implementation/tests PASS;
2. parser/effect schemas versioned и deterministic;
3. combined native→classifier harness воспроизводим;
4. all safety counters = 0;
5. every classifier ALLOW has complete effects/targets and valid identity;
6. compound/pipeline/nested dangerous cases cannot hide behind safe prefix;
7. wrappers/remote payload remain visible and no blanket trust exists;
8. unsupported/opaque syntax fails to ASK_USER;
9. prompt capture > Gate B baseline на sound new fixtures;
10. Linux exact-version parser adapter has non-destructive runtime proof;
11. model auditor remains absent from authorization path;
12. live production permission configuration is unchanged unless a later explicit integration gate authorizes deployment.

До выполнения этих criteria classifier artifact не считается production-deployable.