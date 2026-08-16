# Permission case corpus

Stage 0 machine-readable corpus. `expected_decision` is a conservative safety expectation, not the final optimized policy.

Files:

- `manifest.json` — corpus metadata and file list;
- `safe_controlled.json` — read/secret/Git/build/test/write/delete/external-directory cases;
- `shell_system.json` — destructive Git, privilege/service, compound/pipeline/redirect/interpreter cases;
- `remote_unknown.json` — ssh_relay/remote and unknown CLI cases.

Rules:

- `parser_only` cases must not execute on a working system;
- `temp_fixture` cases require a disposable fixture and version-specific probe design;
- `safe_real` cases may only be observed when naturally required in a trusted workflow;
- `optimization_candidate=true` marks a case for the later Native-policy gate.
