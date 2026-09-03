# Gate B — formal closure

Статус: **CLOSED — Linux / OpenCode 1.18.26**  
Дата: 2026-09-03  
Проект: `dilukhin/opencode_permissions`

## 1. Решение

Gate B (Native-policy integration) закрыт для exact target:

```text
platform: linux
OpenCode: 1.18.26
upstream tag: v1.18.26
upstream commit: 774cc7c1914e4329eefde5a669f938b0cf566661
```

Closure означает, что `opencode_permissions` имеет проверенный canonical native-policy source, deterministic renderer, exact-version/platform compatibility profile и content-bound deployable artifact. Closure **не** означает, что artifact уже применён в live OpenCode environment.

Windows не входит в deployable scope этого closure: Windows B-P2 kernel peer/lifecycle primitive PASS, но OpenCode 1.18.26 runtime на Windows не выполнялся, поэтому Windows profile status остаётся `SOURCE_REVALIDATED`.

## 2. Canonical policy artifact

Canonical semantic source:

```text
policy/native/rules.v1.json
sha256: b7af96ecefd9fce341d128073f1bccae8b66c72e544bf0f47ccbb024232c3490
```

Renderer:

```text
tools/render_native_policy.py
id: opencode-v1-permission-renderer
version: 1
```

Deployable Linux artifact:

```text
artifact_id:
sha256:d983bb4d5f2b9f9be195267e89d16c27ce45e706a2afeb527d96142c535cc508

directory:
dist/opencode/sha256-d983bb4d5f2b9f9be195267e89d16c27ce45e706a2afeb527d96142c535cc508/

permission.jsonc sha256:
9d14d0697c88fc0b005d04d2f114da44bb58f5527f4646bd96afc981d3838ada
```

`artifact_path_segment` использует `sha256-<hex>`, а не `sha256:<hex>`, чтобы repository path был переносим на Windows.

`.gitattributes` фиксирует LF для byte-bound canonical policy/artifact paths, чтобы Git checkout не изменял bytes и digests на Windows runners.

## 3. Native-policy acceptance

Corpus:

```text
total cases:       69
native scope:       65
broker-contract:     4
```

Native candidate/canonical projection:

```text
ALLOW: 6
ASK:   30
DENY:  29
```

Safety metrics:

```text
unsafe_auto_allow       = 0
dangerous_false_safe    = 0
wrapper_false_safe      = 0
unknown_false_safe      = 0
secret_false_safe       = 0
```

Safe deterministic capture:

```text
6 / 11 = 54.5%
```

Five historically safe cases intentionally remain ASK because native matcher lacks sufficient boundary proof:

```text
grep_source
git_diff
cmake_build
ctest
pytest_module
```

Это deliberate conservative boundary, а не regression.

## 4. Renderer / representation proof

Exact OpenCode 1.18.26 source confirms:

- permission configuration preserves property order;
- `Permission.fromConfig()` iterates ordered permission/pattern properties;
- runtime evaluation uses last matching rule;
- user rules are applied after defaults.

Renderer is deliberately non-semantic: он только validates уже принятый ordered logical ruleset и переводит его в OpenCode V1 `permission` object representation.

Regression proves:

- canonical source is exact promotion of reviewed test candidate;
- rendered committed bytes equal deterministic renderer output;
- relative order внутри каждого permission сохраняется;
- duplicate `(permission, pattern)` и unrepresentable ordering fail closed;
- round-trip decisions совпадают для всего native projection в POSIX и Windows matcher modes.

## 5. Artifact / compatibility contract

Compatibility selection:

```text
exact_version_only = true
nearest_version_fallback = false
unknown version -> UNVALIDATED_OPENCODE_VERSION
deployability requires explicit platform
```

Current profile:

```text
overall: DEPLOYABLE
linux: RUNTIME_REVALIDATED
windows: SOURCE_REVALIDATED
deployable_platforms: [linux]
```

Profile pins exact Linux `artifact_id`.

Manifest pre-deploy validation fail-closes on:

- installed version mismatch;
- installed platform mismatch;
- profile/platform non-deployability;
- profile/artifact ID mismatch;
- source/output digest mismatch;
- artifact ID mismatch;
- artifact path-segment/directory mismatch;
- nearest-version fallback;
- setup semantic rewrite;
- missing effective read-back contract;
- competing effective permission layer (result `CONFLICT`).

## 6. Authorization handoff evidence

Linux:

```text
B-P1  SO_PEERCRED/pidfd feasibility         PASS
B-P4a OpenCode trusted host identity        PASS
B-P4b child rejection/lifecycle/failclose   PASS
```

Windows:

```text
B-P2 named-pipe peer PID/process HANDLE primitive PASS
```

Exact grant binding:

```text
B-P3 state model + executable A8–A11 regression PASS
```

Gate B proves feasibility/contracts only. Production broker concurrency/startup and trusted `agent-safe` PEP registration remain later integration ownership; Gate B does not claim them implemented.

## 7. Closure criteria

All Gate B closure criteria are satisfied for the Linux 1.18.26 scope:

1. exact installed version/profile evidence — PASS;
2. canonical ordered native rules + simulator/corpus — PASS;
3. dangerous hard-deny regressions — PASS;
4. unknown/wrapper unsafe auto-allow — zero;
5. secret/external-directory boundary — PASS at Gate-B native scope;
6. wrapper/remote/transfer mock/parser corpus — PASS;
7. NormalizedOperation identity fixtures — PASS;
8. authorization non-forgeability feasibility/exact binding — PASS at Gate-B scope;
9. artifact/interface contract for `opencode_setup` — PASS;
10. prompt reduction >= 50% without false-safe — PASS (54.5%);
11. applicable Gate-B cross-project matrix rows — evidence complete;
12. live production OpenCode permission state — unchanged.

## 8. Explicit non-claims / deferred ownership

Not implemented by this closure:

- deterministic effect classifier — `NOT STARTED`;
- model auditor — `NOT STARTED`;
- live deployment/reconciliation — Gate F / `opencode_setup`;
- production `agent-safe` PEP integration — Gate C;
- `ssh_relay` runtime outcome integration — Gate D;
- ScopedKB context integration — Gate E;
- Windows OpenCode deployability — not validated.

A deployable repository artifact is **not** equivalent to an installed/effective live policy.

## 9. Next gate

Native-policy Gate B is closed. The next architectural stage may begin with deterministic parser/effect analysis only for the gaps demonstrated by the native layer. It must preserve all Gate B hard-deny/fail-closed invariants and may not broaden this artifact implicitly.
