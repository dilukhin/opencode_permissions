# OpenCode Permissions — Agent Seed

Project: `dilukhin/opencode_permissions`.

Read `opencode_permissions_agent_guide_ru.md` before substantial local work and follow the exact task scope.

## Workspace boundary

Standard local layout:

```text
<workspace>/
  opencode_permissions/   # Git repository
  evidence/               # raw/local evidence
  docs/                   # local-only working documents
  stash/                  # transient working files
```

- Treat the repository root as a **version-controlled project area**, not a scratch/output directory.
- If `<workspace>/docs/workspace_layout_local.md` exists, read it for the exact machine-specific paths. Do not copy those absolute paths into repository docs unless explicitly required.
- Put raw audit output, inventory JSON, prompt captures, transient reports and other machine-specific evidence under `<workspace>/evidence/<stage>/`.
- Put local-only drafts, handoffs, prompts and working notes that are useful across iterations but are not repository artifacts under `<workspace>/docs/`.
- Put disposable/intermediate working files, transfer artifacts, temporary patches and other non-authoritative scratch material under `<workspace>/stash/`.
- Never `git add`, commit, copy or move files from `evidence/`, local `docs/` or `stash/` into the repository merely to make them available to ChatGPT Web.
- A local artifact becomes a repository artifact only after ChatGPT Web explicitly selects/reviews it for publication and gives an exact repository path.
- If classification is uncertain, keep the file outside the repository and escalate rather than placing it in Git.
- See `docs/workspace_evidence_policy_ru.md` for the full routing and publication rules.

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
