# Cross-project unresolved design decisions

Статус: **ACTIVE REGISTER**.

Этот документ содержит только те решения, которые намеренно не фиксировались Gate A. Наличие записи не означает implementation gap текущего gate, если owner/gate указан как последующий.

| ID | Решение | Owner / Gate | Что должно быть доказано для closure | Статус |
|---|---|---|---|---|
| U1 | Конкретный trusted authorization handoff mechanism | `opencode_permissions` / B | model-controlled channel не может изготовить valid grant; exact binding и replay semantics проверяемы | OPEN |
| U2 | Canonicalization и identity/hash `NormalizedOperation` | `opencode_permissions` / B | semantic payload/target substitution меняет identity; platform quoting не создаёт ложных equivalence | OPEN |
| U3 | Single-use vs short-lived scoped grant | `opencode_permissions` / B | минимальный scope/lifetime, защита от unintended replay, practical integration | OPEN |
| U4 | Canonical deployable permission artifact format/versioning | `opencode_permissions` / B | artifact достаточен `opencode_setup`, не требует semantic rewriting setup'ом | OPEN |
| U5 | Native-policy representation wrapper/controlled path | `opencode_permissions` / B | generic wrapper не становится authorization tunnel; direct safe path сохраняет prompt reduction | OPEN |
| U6 | Integrated/standalone compatibility lifecycle `agent-safe` | `agent-safe` / C | standalone явно изолирован; integrated mode не принимает self-approval и не пишет competing policy | OPEN |
| U7 | `ExecutionPreflight` concrete API/schema | `agent-safe` / C | pre-ASK часть гарантированно read-only; post-authorization revalidation закрывает state drift | OPEN |
| U8 | `RemoteOutcome` correlation contract | `ssh_relay` / D | job/transfer identity связывается с execution evidence без authorization authority relay | OPEN |
| U9 | Transfer operations (`upload/download`) в controlled effects model | B + D | target/effect видимы authorization layer; transfer не скрывается за generic relay permission | OPEN |
| U10 | Минимальный `ContextFacts` wire schema | `ScopedKB` / E | provenance/freshness/sensitivity достаточны policy consumer; stale/unknown fail-safe | OPEN |
| U11 | `opencode_permissions` managed checkout branch/version policy | `opencode_setup` + `opencode_permissions` / F | обновление воспроизводимо, non-destructive, соответствует artifact compatibility | OPEN |
| U12 | Semantic ownership format live OpenCode config | `opencode_setup` / F | permission section имеет canonical source owner; user settings сохраняются; conflict detectable | OPEN |
| U13 | Inventory всех effective permission layers целевой версии | B + F | global/project/environment/legacy sources учитываются без secret disclosure | OPEN |
| U14 | Legacy `agent-safe opencode-bootstrap` migration lifecycle | C + F | known exact artifacts мигрируются; modified/unknown preserve+conflict; competing writer исчезает | OPEN |
| U15 | Integration acceptance harness/fixture composition | G | все cross-project cases проверяются non-destructively и воспроизводимо | OPEN |

## Правила register

- Решение закрывается только evidence соответствующего project gate, а не roadmap entry.
- Новое version-sensitive утверждение про OpenCode требует проверки целевой версии до закрытия записи.
- Если решение меняет ownership/invariants Gate A, нужно вернуться к cross-project contract review, а не закрывать запись локальным workaround.
- Нельзя закрывать U1/U2/U5 prompt-only запретом агенту; требуется technical boundary.
