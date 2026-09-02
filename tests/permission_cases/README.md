# Permission case corpus

Machine-readable conservative safety corpus. `expected_decision` is a safety expectation, not the final optimized policy.

Files:

- `manifest.json` — corpus metadata and file list;
- `safe_controlled.json` — read/secret/Git/build/test/write/delete/external-directory cases;
- `shell_system.json` — destructive Git, privilege/service, compound/pipeline/redirect/interpreter cases;
- `remote_unknown.json` — ssh_relay/remote and unknown CLI Stage 0 cases;
- `gate_b_integration.json` — Gate B wrapper/approval-substitution/remote job-transfer/grant mismatch-replay/unknown-effect cases.

Rules:

- `parser_only` cases must not execute on a working system;
- `temp_fixture` cases require a disposable fixture and version-specific probe design;
- `safe_real` cases may only be observed when naturally required in a trusted workflow;
- `optimization_candidate=true` marks a case that may reduce prompts only after the relevant native/controlled-path boundary is proven;
- wrapper name, `--approved`/equivalent, transport risk label and unknown effect never prove safety by themselves;
- dangerous Gate B cases are acceptance/parser/mock inputs, not destructive execution scenarios.
