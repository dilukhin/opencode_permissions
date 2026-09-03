# Gate B — exact-version compatibility profiles

Статус: **ACCEPTED / Linux 1.18.26 DEPLOYABLE**  
Дата актуализации: 2026-09-03

Machine-readable registry: `tests/compatibility/registry.json`.

## Contract

```text
selection = exact_version_only
nearest_version_fallback = false
unknown version -> UNVALIDATED_OPENCODE_VERSION
deployable selection requires explicit platform
```

No nearest/semver-compatible profile may be selected implicitly.

## Profiles

### OpenCode 1.18.18

Historical Stage 0 baseline. It remains non-deployable for the Gate B artifact contract and is retained as source/fingerprint comparison evidence.

### OpenCode 1.18.26

Exact upstream:

```text
v1.18.26 -> 774cc7c1914e4329eefde5a669f938b0cf566661
```

Current profile:

```text
overall_status: DEPLOYABLE
linux: RUNTIME_REVALIDATED
windows: SOURCE_REVALIDATED
deployable_platforms: [linux]
```

Linux is bound to:

```text
sha256:d983bb4d5f2b9f9be195267e89d16c27ce45e706a2afeb527d96142c535cc508
```

Windows B-P2 proves the named-pipe/process-handle kernel primitive, but OpenCode 1.18.26 was not executed on Windows. Therefore Windows is deliberately absent from `deployable_platforms`.

## Fast path

Shared critical fingerprints between 1.18.18 and 1.18.26 remain explicit. Unchanged fingerprints may use `SOURCE_EQUIVALENT_FAST_PATH_ELIGIBLE`; any changed critical fingerprint returns `TARGETED_REAUDIT_REQUIRED`. Fast path never bypasses required platform/runtime evidence.

## Regression acceptance

Tests prove:

- exact current profile selection;
- unknown future version fail-closed;
- nearest fallback forbidden;
- platform required for deployable selection;
- Linux 1.18.26 selects successfully;
- Windows 1.18.26 deployable selection fails closed;
- fingerprint drift triggers targeted re-audit;
- profiles contain no secret material.

See `docs/gate_b_final_closure_ru.md` for formal Gate B closure.
