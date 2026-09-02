# Gate B — comparison of authorization handoff candidates

Статус: **DESIGN PREFERENCE FOR NEXT PROOF / not approved architecture**  
Дата: 2026-09-02

Этот документ сравнивает два оставшихся Gate B candidate после того, как stock `ctx.ask + ordinary Basic auth` признан недостаточным non-forgeability proof.

## 1. Candidate A — hardened native `ctx.ask()` continuation

### Flow

```text
trusted custom tool inside OpenCode
-> normalize operation
-> native ctx.ask()
-> user replies through OpenCode client
-> same tool call resumes
-> exact identity recheck
-> controlled runtime
```

### Плюсы

- native OpenCode permission UX;
- request уже связан с session/message/callID;
- same-call continuation не требует возвращать модели `--approved`/bearer token;
- меньше новых runtime components.

### Блокирующая проблема

Native user reply идёт через OpenCode permission API. Обычный `OPENCODE_SERVER_PASSWORD` не является isolated secret, потому что child execution по крайней мере shell по умолчанию наследует `process.env`.

Чтобы Candidate A стал приемлемым, требуется доказать техническую изоляцию privileged reply credential **от всех model-controlled executable surfaces**, а не только запретить печатать secret.

Это означает аудит/контроль как минимум:

- shell child environment;
- interpreter execution;
- plugin/custom executable paths;
- MCP child processes/capabilities;
- LSP/formatter/project executable hooks, если они способны использовать inherited credential;
- future new execution tools.

Такая граница существенно связана с внутренним process/runtime устройством OpenCode и чувствительна к версиям.

### Статус

`CANDIDATE / high version coupling / proof cost high`.

## 2. Candidate B — local authorization broker with kernel peer-process identity

### Идея

Не использовать model-visible bearer secret для подтверждения trusted caller.

Broker принимает authorization request только от зарегистрированного процесса OpenCode и проверяет peer process identity средствами ОС.

Linux предоставляет peer credentials для connected Unix-domain sockets (`SO_PEERCRED`); Windows named-pipe server может получить PID client process через `GetNamedPipeClientProcessId`.

### Proposed flow

```text
managed launcher/broker starts or registers OpenCode process
                     |
                     v
model -> trusted custom tool in OpenCode host process
                     |
                     | structured NormalizedOperation
                     v
          local authenticated IPC connection
          broker verifies kernel-reported peer process identity
                     |
                     v
              user approval UI
                     |
                 once/deny
                     |
                     v
same trusted tool call receives result
-> identity recheck
-> controlled runtime / agent-safe
```

### Security property

Model-controlled shell/interpreter process has a different PID/process identity from OpenCode host. It cannot become the accepted IPC peer merely by knowing pipe/socket name or by reading environment variables.

No approval token needs to exist in:

- model arguments;
- shell environment;
- filesystem config;
- prompt text.

### Required hardening

PID integer alone is insufficient because of lifecycle/reuse. Broker must bind authorization channel to a live process identity, for example registered process handle/start identity and connection peer credentials, and invalidate it when the OpenCode host exits/restarts.

Threats requiring explicit tests:

- shell child connects directly -> reject by peer identity;
- unrelated same-user process -> reject;
- stale/reused PID after restart -> reject;
- request A followed by execution B -> reject by operation identity;
- user approval reply replay -> reject;
- broker restart loses pending/grants safely;
- OpenCode restart requires new registration;
- hard-denied operation never reaches approval UI as approvable;
- broker/UI failure -> no mutation.

Process injection/debug privilege attacks are outside the normal model-controlled command threat boundary and remain protected by privilege/hard-deny/runtime controls; they must not be silently assumed available to the model.

## 3. Ownership

Broker is not a second PDP.

Canonical semantics remain:

```text
opencode_permissions -> ALLOW / ASK_USER / DENY
```

Broker would be a trusted **authorization transport/approval mechanism** owned by `opencode_permissions` (or a narrowly specified helper implementation), carrying an already normalized operation and returning user decision/evidence.

It must not invent policy rules from its own risk score.

`agent-safe` remains execution-safety PEP and may narrow authorization only.

## 4. Exact binding

Broker request must include canonical operation identity plus human-readable approval data:

```text
operation identity
target(s)
effects
environment/host
risk/reversibility evidence
source session/message/callID
policy decision/rule provenance
```

User approves the exact identity. Broker response is delivered only to the same registered host connection/call context or as a single-use capability that cannot be supplied through model CLI arguments.

Any downstream process boundary to `agent-safe` requires an exact-bound handoff inaccessible to model-controlled payload substitution.

## 5. UX trade-off

Candidate A has better native UX because prompt is OpenCode's own permission dialog.

Candidate B requires a small broker-owned approval surface (local dialog/TUI/notification; future remote client is a separate concern). This is additional UX/component cost, but it makes security independent of OpenCode's general HTTP permission-reply authentication and child environment behavior.

A broker UI can later display the canonical approval semantics already required by baseline:

```text
Цель
Среда
Target
Effects
Risk
Blast radius
Reversibility
Почему автоматика не решила
Recommendation
```

## 6. Version coupling

| Property | Candidate A | Candidate B |
|---|---|---|
| depends on `Tool.Context.ask` | yes | optional/no for security |
| depends on OpenCode permission HTTP reply | yes | no |
| depends on server auth implementation | yes | no |
| depends on child env isolation | strongly | no approval secret to inherit |
| custom tool host-process integration | yes | yes |
| OS-specific IPC code | minimal | yes |
| native OpenCode approval UX | yes | no/separate |
| future OpenCode version coupling | higher | lower, mainly custom-tool ABI/integration |

## 7. Current preference

For the **next bounded feasibility proof**, Candidate B is preferred.

Reason:

> It removes the authorization secret/reply capability from the model-controlled process environment entirely instead of requiring a growing blacklist of child-process inheritance paths inside frequently changing OpenCode.

This is a **preference**, not an approved architecture. Gate B must still prove practical Windows/Linux IPC peer identity, OpenCode host-process integration, failure semantics and exact operation binding before U1 can close.

Candidate A remains fallback only if a clean, auditable OpenCode-native credential-isolation mechanism is found (preferably upstream-supported rather than a brittle local patch).

## 8. Bounded proof plan

No destructive operations are needed.

### B-P1 Linux peer identity

Synthetic local Unix-domain socket:

- broker knows registered parent/OpenCode-like PID;
- same process connection accepted;
- child process connection rejected;
- restart/stale PID rejected.

Evidence: kernel `SO_PEERCRED`.

### B-P2 Windows peer identity

Synthetic named-pipe fixture:

- server obtains client PID using `GetNamedPipeClientProcessId`;
- registered host process accepted;
- child/unrelated process rejected;
- handle/PID lifecycle checked.

Evidence: Windows API + local isolated fixture when Windows executor is available.

### B-P3 exact operation binding

Pure unit/mock:

- approve A -> execute A allowed to continue;
- approve A -> B rejected;
- target substitution rejected;
- replay rejected;
- broker restart fails closed.

### B-P4 OpenCode integration feasibility

Trusted no-mutation custom tool:

- receives structured synthetic operation;
- broker sees peer as OpenCode host process, not shell child;
- user/mock approval returns to same call;
- tool only returns synthetic `AUTHORIZED/REJECTED`; no real mutation.

### B-P5 version portability

Repeat source/API compatibility check on installed/current OpenCode compatibility profile. New release must not silently invalidate trusted-tool host-process assumption.

## 9. Stop conditions

Return to design review if:

- custom tool executes out-of-process so peer identity is not OpenCode host as assumed;
- OpenCode architecture makes trusted and model-controlled requests indistinguishable at IPC peer level;
- cross-platform peer identity requires privileged/destructive mechanisms;
- broker would itself become a competing policy engine;
- user approval must be returned through model-visible data;
- exact operation binding cannot survive runtime handoff.
