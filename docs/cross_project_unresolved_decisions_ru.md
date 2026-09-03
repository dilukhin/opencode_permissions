# Cross-project unresolved design decisions

Статус: **ACTIVE REGISTER**.  
Последняя reconciliation: 2026-09-03 после formal Gate B closure.

Этот документ содержит только те решения, которые ещё требуют evidence соответствующего owner/gate. Наличие записи не означает implementation gap текущего gate, если owner/gate указан как последующий.

| ID | Решение | Owner / Gate | Что должно быть доказано для closure | Статус / evidence |
|---|---|---|---|---|
| U1 | Конкретный trusted authorization handoff mechanism | `opencode_permissions` / B | model-controlled channel не может изготовить valid grant; exact binding и replay semantics проверяемы | **CLOSED (Gate B feasibility/contract)** — kernel peer identity + broker contract + B-P3 exact-binding/replay regressions; production startup/concurrency остаются integration work |
| U2 | Canonicalization и identity/hash `NormalizedOperation` | `opencode_permissions` / deterministic-classifier gate | semantic payload/target substitution меняет identity; platform quoting/path representation не создаёт unsafe equivalence; implementation имеет deterministic test vectors | **OPEN** — design и relation fixtures есть, но canonicalizer/cross-runtime vectors и trusted-boundary recomputation ещё не реализованы |
| U3 | Single-use vs short-lived scoped grant | `opencode_permissions` / B | минимальный scope/lifetime, защита от unintended replay, practical integration | **CLOSED (Gate B contract)** — broker-resident one-use grant; replay и broker/host generation invalidation покрыты regression |
| U4 | Canonical deployable permission artifact format/versioning | `opencode_permissions` / B | artifact достаточен `opencode_setup`, не требует semantic rewriting setup'ом | **CLOSED** — `opencode-permission-artifact/v1`, exact version/platform/profile/digest binding, Linux 1.18.26 artifact emitted |
| U5 | Native-policy representation wrapper/controlled path | `opencode_permissions` / B | generic wrapper не становится authorization tunnel; direct safe path сохраняет prompt reduction | **CLOSED at native-policy scope** — wrapper/relay/interpreter cases remain ASK/DENY; hard-dangerous nested payload dominates; unsafe auto-ALLOW = 0 |
| U6 | Integrated/standalone compatibility lifecycle `agent-safe` | `agent-safe` / C | standalone явно изолирован; integrated mode не принимает self-approval и не пишет competing policy | **OPEN** |
| U7 | `ExecutionPreflight` concrete API/schema | `agent-safe` / C | pre-ASK часть гарантированно read-only; post-authorization revalidation закрывает state drift | **OPEN** |
| U8 | `RemoteOutcome` correlation contract | `ssh_relay` / D | job/transfer identity связывается с execution evidence без authorization authority relay | **OPEN** |
| U9 | Transfer operations (`upload/download`) в controlled effects model | B + D | target/effect видимы authorization layer; transfer не скрывается за generic relay permission | **OPEN** — Gate B удерживает transfer в ASK и фиксирует identity requirements; runtime transport contract остаётся Gate D |
| U10 | Минимальный `ContextFacts` wire schema | `ScopedKB` / E | provenance/freshness/sensitivity достаточны policy consumer; stale/unknown fail-safe | **OPEN** |
| U11 | `opencode_permissions` managed checkout branch/version policy | `opencode_setup` + `opencode_permissions` / F | обновление воспроизводимо, non-destructive, соответствует artifact compatibility | **OPEN** |
| U12 | Semantic ownership format live OpenCode config | `opencode_setup` / F | permission section имеет canonical source owner; user settings сохраняются; conflict detectable | **OPEN** |
| U13 | Inventory всех effective permission layers целевой версии | B + F | global/project/environment/legacy sources учитываются без secret disclosure | **OPEN** — Stage 0/Gate B дали version evidence, но live reconciliation inventory остаётся Gate F |
| U14 | Legacy `agent-safe opencode-bootstrap` migration lifecycle | C + F | known exact artifacts мигрируются; modified/unknown preserve+conflict; competing writer исчезает | **OPEN** |
| U15 | Integration acceptance harness/fixture composition | G | все cross-project cases проверяются non-destructively и воспроизводимо | **OPEN** |

## Gate B reconciliation note

Formal Gate B closure для Linux/OpenCode 1.18.26 находится в:

```text
docs/gate_b_final_closure_ru.md
```

Gate B закрыл U1/U3/U4/U5 на уровне своих design/runtime-feasibility contracts. Это **не** означает реализацию downstream responsibilities `agent-safe`, `ssh_relay`, `ScopedKB` или `opencode_setup`.

U2 намеренно остаётся OPEN и становится foundational prerequisite внутреннего deterministic parser/effect-analysis gate: classifier не должен выдавать authorization для operation, identity которой нельзя детерминированно воспроизвести и повторно проверить на trusted boundary.

## Правила register

- Решение закрывается только evidence соответствующего project gate, а не roadmap entry.
- Новое version-sensitive утверждение про OpenCode требует проверки целевой версии до закрытия записи.
- Если решение меняет ownership/invariants Gate A, нужно вернуться к cross-project contract review, а не закрывать запись локальным workaround.
- Нельзя закрывать U1/U2/U5 prompt-only запретом агенту; требуется technical boundary.
- `CLOSED` design/feasibility decision не следует трактовать как production implementation соседнего проекта.