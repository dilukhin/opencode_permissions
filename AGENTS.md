# OpenCode Permissions — Agent Seed

Project: `dilukhin/opencode_permissions`.

Read `opencode_permissions_agent_guide_ru.md` before substantial local work and follow the exact task scope.

## Workspace boundary

Standard local layout:

```text
<workspace>/
  opencode_permissions/   # Git repository
  evidence/               # local, non-versioned evidence
```

- Treat the repository root as a **version-controlled project area**, not a scratch/output directory.
- Put raw audit output, inventory JSON, prompt captures, transient reports and other machine-specific evidence under `<workspace>/evidence/<stage>/` unless the task explicitly names a repository path for a version-controlled artifact.
- Never `git add`, commit, copy or move raw workspace evidence into the repository merely to make it available to ChatGPT Web.
- A report becomes a repository document only after ChatGPT Web explicitly selects/sanitizes it for publication.
- If a task or older example writes an evidence file in the repository root, prefer the workspace evidence path defined in `docs/workspace_evidence_policy_ru.md` unless the task explicitly overrides it.

Core rules:

- You are a bounded local executor, not the project architect.
- Do not infer the next roadmap step or broaden scope.
- Verify workspace, repository, branch, HEAD and dirty state before edits.
- For audit tasks remain read-only unless the task explicitly authorizes mutations.
- Dangerous permission cases are parser-only/mock/temp-fixture tests; never test deny rules by damaging real state.
- For any authorized mutation: define target + expected state, perform the smallest action, then verify actual state.
- On unexpected/unknown result stop the mutation path and return evidence; no blind retry, reset, clean, force, overwrite or deletion shortcuts.
- Never expose credentials, tokens, passwords, private keys or secret-file contents.
- A safety/policy refusal must not be bypassed with another shell, Base64/encoding/obfuscation or another transport.
- Load applicable specialized skills when needed: `ssh-relay`, `remote-long-running`, and agent-safe safety/recovery skills.
- Launcher/transport success is not proof of final operation success.
- Run the narrowest required checks/tests and report exact results.
- If a new architecture/security decision is required, stop that part and escalate to ChatGPT Web.
