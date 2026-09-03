# Gate B — closure readiness review

Статус: **NOT CLOSED / ONE INTERNAL BLOCKER REMAINS**  
Дата: 2026-09-03  
Проект: `dilukhin/opencode_permissions`

## 1. Решение review

После reviewed Linux OpenCode broker probes, Windows B-P2, native-policy corpus/metrics, compatibility registry, artifact contract и B-P3 executable state-model Gate B ещё **не закрывается**.

Остался один внутренний blocker:

```text
CANONICAL_DEPLOYABLE_ARTIFACT_NOT_BUILT
```

Текущие rules существуют только как test/design candidate:

```text
tests/native_policy/policy_candidate.json
```

Closure criterion требует canonical ordered semantic source и generated artifact, принадлежащие `opencode_permissions`, без изменения live OpenCode config.

## 2. Windows B-P2 result

Reviewed B-P2: **PASS**.

Evidence:

```text
docs/gate_b_windows_peer_identity_probe_ru.md
```

Подтверждены:

- named-pipe peer PID через kernel API;
- trusted host ACCEPT;
- same-user child получает distinct PID и REJECT;
- retained process HANDLE non-inheritable;
- host lifecycle/exit observable через retained HANDLE;
- registration invalidates after host exit;
- bearer approval secret не требуется;
- elevation/destructive/system mutation не использовались.

Scope ограничен Windows kernel primitive. OpenCode 1.18.26 на Windows в B-P2 не запускался; Windows compatibility platform status поэтому остаётся `SOURCE_REVALIDATED`.

## 3. Closure criteria review

Исходные criteria: `docs/gate_b_native_policy_integration_design_ru.md`, section `Gate B closure criteria`.

| # | Criterion | Status | Evidence / note |
|---|---|---|---|
| 1 | exact installed OpenCode compatibility profile | PASS for current installed Linux target | `tests/compatibility/profiles/opencode-1.18.26.json`; Linux `RUNTIME_REVALIDATED`; source exact tag/fingerprints |
| 2 | canonical ordered native rules + simulator/corpus | **BLOCKED** | simulator/corpus PASS, но rules пока test-only; `policy/native/rules.v1.json` и generated artifact ещё не созданы |
| 3 | hard-deny dangerous cases no regression | PASS | native metrics: `dangerous_false_safe=0`; explicit DENY regressions |
| 4 | unknown/wrapper no unsafe auto-ALLOW | PASS | `unknown_false_safe=0`, `wrapper_false_safe=0` |
| 5 | secret/external-directory boundaries | PASS at Gate-B design/test scope | secret path overrides + external-directory conservative ASK/source semantics; no unsafe auto-ALLOW |
| 6 | wrapper/remote/transfer parser-only/mock corpus | PASS | `tests/permission_cases/gate_b_integration.json` + projection/metrics |
| 7 | NormalizedOperation substitution/path/platform fixtures | PASS | `tests/normalized_operation/identity_relations.json` |
| 8 | U1 non-forgeability proof or explicit scope limitation | PASS at Gate-B scope | Linux B-P4a/b PASS; Windows B-P2 PASS; B-P3 state model; production PEP/startup integration explicitly deferred |
| 9 | artifact/interface defined for `opencode_setup` | PASS | `docs/gate_b_canonical_artifact_contract_ru.md`; semantic rewrite forbidden |
| 10 | prompt reduction without false-safe | PASS | 6/11 = 54.5%; all false-safe safety counters = 0 |
| 11 | applicable Gate-B cross-project matrix rows have evidence | PASS / ownership-deferred where appropriate | A1–A11 and B-side A16–A18 covered; ScopedKB execution remains Gate E; setup execution remains Gate F |
| 12 | production permission policy unchanged | PASS | no live OpenCode permission config was modified |

## 4. Cross-project matrix interpretation

### Gate B evidence complete

At Gate-B scope evidence exists for:

```text
A1  deterministic safe native allow
A2  hard-dangerous deny
A3  unknown/ambiguous non-allow
A4  secret-like read boundary
A5  external-directory conservative boundary
A6  safe wrapper forged approval rejected/non-allow
A7  python -m agent_safe forged approval rejected/non-allow
A8  exact grant/operation consume
A9  operation/payload substitution reject
A10 target substitution reject
A11 replay reject
A16 relay dangerous payload non-allow/deny
A17 relay job payload explicit ASK
A18 transfer explicit ASK/effects
A32 B-side requirement: competing effective layer -> CONFLICT
```

### Correctly deferred ownership

Not Gate-B implementation blockers:

- A12–A15: `agent-safe` Gate C runtime preflight/execute/verify;
- A19–A20: `ssh_relay` Gate D runtime/transport outcomes;
- A21–A23: ScopedKB Gate E context implementation (Gate B invariant already says context cannot broaden policy implicitly);
- A24–A34: `opencode_setup` Gate F installation/reconciliation/effective read-back;
- A35–A38: later auditor/full integration Gate G.

Deferred означает ownership boundary, а не доказательство реализации.

## 5. Native-policy acceptance state

Current test-only candidate:

```text
native scope:       65 / 69 corpus cases
ALLOW:              6
ASK:                30
DENY:               29
safe capture:       6 / 11 = 54.5%
unsafe_auto_allow:  0
dangerous_false_safe: 0
wrapper_false_safe: 0
unknown_false_safe: 0
secret_false_safe:  0
```

Five existing safety-ALLOW cases остаются conservative ASK:

```text
grep_source
git_diff
cmake_build
ctest
pytest_module
```

Это сознательная граница native matcher, а не regression.

## 6. Authorization handoff state

### Linux

```text
B-P1 kernel peer/lifecycle       PASS
B-P4a OpenCode host identity     PASS
B-P4b child/lifecycle/failclose  PASS
```

### Windows

```text
B-P2 named-pipe peer/lifecycle primitive  PASS
```

### Exact binding

```text
B-P3 pure state model + executable regression  PASS
```

Gate B не объявляет production broker/PEP implementation готовой. Trusted PEP registration, runtime preflight/execute/verify и setup lifecycle остаются соответствующим Gate C/F ownership.

## 7. Compatibility state

Current exact profile:

```text
OpenCode: 1.18.26
upstream tag: v1.18.26
overall: SOURCE_REVALIDATED
Linux: RUNTIME_REVALIDATED
Windows: SOURCE_REVALIDATED + B-P2 OS primitive PASS
deployable: false
```

Current blockers в profile должны оставаться только:

```text
CANONICAL_DEPLOYABLE_ARTIFACT_NOT_BUILT
FINAL_GATE_B_CLOSURE_PENDING
```

Unknown future OpenCode version остаётся fail-closed; nearest-version fallback запрещён.

## 8. Last required Gate-B implementation slice

Перед formal closure выполнить один bounded repository-only slice:

1. промотировать reviewed ordered native rules из test candidate в canonical semantic source:

```text
policy/native/rules.v1.json
```

2. реализовать renderer, принадлежащий `opencode_permissions`, для exact OpenCode V1 permission artifact;
3. generated bytes положить под content-bound artifact directory:

```text
dist/opencode/<artifact-id>/permission.jsonc
dist/opencode/<artifact-id>/manifest.json
```

4. manifest должен удовлетворять `opencode-permission-artifact/v1` contract;
5. regression должен доказать round-trip semantic equivalence canonical rules -> rendered permission rules;
6. digest/artifact-id validation должна пройти;
7. никаких live/user/project OpenCode config mutations;
8. после CI выполнить final closure review.

Renderer не должен становиться classifier: он только детерминированно переводит уже принятый ordered logical ruleset в exact OpenCode V1 config representation.

## 9. Stop conditions для promotion slice

Остановить promotion и не объявлять artifact deployable, если:

- exact OpenCode V1 config representation не сохраняет required rule order;
- round-trip меняет решение хотя бы для одного corpus/projection case;
- renderer требует semantic guess/reclassification;
- artifact manifest/digest не связывает exact source/output/profile;
- CI regression не зелёный;
- current exact compatibility assumptions изменились.

## 10. Gate state

```text
Gate A                               CLOSED
Gate B Windows B-P2                  PASS
Gate B native policy metrics         PASS
Gate B compatibility registry        PASS
Gate B artifact interface contract   PASS
Gate B B-P3 exact binding            PASS
Gate B canonical artifact promotion  PENDING  <-- only internal blocker
Gate B final closure                 PENDING
Deterministic classifier             NOT STARTED
Auditor                              NOT STARTED
Production live permission policy    UNCHANGED
```

Gate B нельзя формально закрыть до successful canonical artifact promotion + final read-back/CI.
