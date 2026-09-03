# Gate B — canonical OpenCode permission artifact contract

Статус: **ACCEPTED / DEPLOYABLE LINUX ARTIFACT EMITTED**  
Дата актуализации: 2026-09-03

## Ownership

`opencode_permissions` owns ordered authorization semantics, renderer, compatibility binding and generated artifact. `opencode_setup` may install/reconcile an exact artifact but must not rewrite/reorder its ALLOW/ASK/DENY semantics.

## Canonical source and artifact

```text
policy/native/rules.v1.json
```

Linux/OpenCode 1.18.26 artifact:

```text
artifact_id = sha256:d983bb4d5f2b9f9be195267e89d16c27ce45e706a2afeb527d96142c535cc508
artifact_path_segment = sha256-d983bb4d5f2b9f9be195267e89d16c27ce45e706a2afeb527d96142c535cc508
```

Files:

```text
dist/opencode/<artifact_path_segment>/permission.jsonc
dist/opencode/<artifact_path_segment>/manifest.json
```

`artifact_path_segment` is colon-free for Windows-compatible repository checkout. `.gitattributes` enforces LF on byte-bound policy/artifact paths.

## Manifest contract

`opencode-permission-artifact/v1` binds:

- exact OpenCode version;
- exact platform;
- compatibility profile ID;
- canonical source SHA-256;
- renderer ID/version;
- generated output SHA-256;
- content-derived artifact ID.

Profile additionally pins the exact artifact ID per deployable platform.

Before any future mutation, setup must validate exact version/platform/profile/artifact/digests and all constraints. Drift fails closed.

Required constraints:

```text
exact_version_only = true
requires_deployable_profile = true
nearest_version_fallback = false
setup_semantic_rewrite = false
effective_readback_required = true
competing_effective_layer_result = CONFLICT
```

## Platform scope

Current artifact is deployable only for Linux OpenCode 1.18.26. Windows remains non-deployable until its OpenCode runtime profile receives sufficient evidence.

## Important distinction

Repository `status: deployable` means the artifact passed Gate B source/runtime/contract acceptance for its exact platform/version. It does not mean it has been installed into the user's OpenCode configuration. Installation/reconciliation/effective-state verification belongs to `opencode_setup` Gate F.

See `docs/gate_b_final_closure_ru.md`.
