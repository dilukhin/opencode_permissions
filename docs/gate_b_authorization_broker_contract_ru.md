# Gate B — authorization broker contract and B-P3 exact-binding state model

Статус: **REVIEW PROPOSAL + B-P3 PURE MODEL PASS**  
Дата: 2026-09-02

Этот документ уточняет Candidate B из `gate_b_handoff_candidate_comparison_ru.md`. Он не реализует production broker и не является deterministic effect classifier.

## 1. Ключевое решение design-level

`AuthorizationGrant` для integrated controlled path не должен быть model-visible bearer token.

Предпочтительная logical representation — **broker-resident single-use authorization record**. Идентификатор записи является correlation data, а не секретом и сам по себе не даёт права исполнения.

Право продолжить mutation возникает только при сочетании:

```text
valid broker-resident authorization record
AND exact operation identity match
AND registered/living trusted execution peer
AND current broker/registration generation
AND not previously consumed
AND source tool call still active
```

Таким образом, знание `authorization_id`, `operation_id` или digest моделью не является authorization proof.

## 2. Roles

```text
OpenCode trusted gate/custom tool host
    proposes normalized operation

opencode_permissions broker
    stores canonical policy/user authorization state
    verifies trusted IPC peers
    owns local approval interaction/transport
    does NOT execute mutation

agent-safe integrated runtime / PEP
    asks broker to consume exact authorization
    performs runtime preflight/execute/verify
    can narrow, never broaden
```

`ssh_relay` остаётся downstream transport, а не authorization peer.

## 3. Trusted process registrations

Broker хранит как минимум две role-scoped registrations:

```yaml
host_registration:
  role: OPENCODE_GATE_HOST
  process_identity: kernel-bound-live-process-reference
  generation: ...

pep_registration:
  role: AGENT_SAFE_PEP
  process_identity: kernel-bound-live-process-reference
  generation: ...
```

Registration creation itself должна происходить через managed trusted startup/integration path; model-controlled process не может объявить себя trusted role.

Gate B не определяет lifecycle installation — это стык с будущими Gate C/F — но требует non-model-controlled registration mechanism.

## 4. Broker-resident `AuthorizationGrant`

Logical schema:

```yaml
schema: authorization-grant/v1
authorization_id: opaque-correlation-id
operation_identity: sha256:...
source_binding:
  session_id: ...
  message_id: ...
  call_id: ...
policy_artifact_id: ...
compatibility_profile: ...
provenance: policy_allow|user_once
broker_generation: ...
host_registration_generation: ...
state: PENDING|APPROVED|REJECTED|CONSUMED|CANCELLED
created_at: ...
```

Не включать reusable secret/token field.

`authorization_id` может быть unpredictable для robustness, но security acceptance не должна зависеть от его secrecy.

## 5. Lifetime semantics — proposal to close U3 design

Для controlled mutation предлагается:

```text
single-use
+
source-tool-call-bound
+
host-process-liveness-bound
+
broker-generation-bound
```

Grant invalidates on first successful consumption or earlier when:

- source tool call aborts/completes without consumption;
- host registration/process exits;
- broker restarts/generation changes;
- explicit user reject/cancel;
- policy/compatibility state changes in a way that invalidates pending request;
- operation identity no longer matches execution request.

Arbitrary reusable «valid N minutes» bearer semantics не нужны. Optional maximum wall-clock timeout может быть defense-in-depth later, but is not the primary authorization boundary.

## 6. Request flow

### 6.1 Authorization request

Accepted only from kernel-verified `OPENCODE_GATE_HOST` peer:

```text
AUTH_REQUEST(
  NormalizedOperation,
  source_binding,
  policy context/version
)
```

Broker validates caller role/process registration, recomputes/verifies operation identity where applicable and evaluates the applicable authorization path.

For Gate B controlled cases that are mandatory ASK, broker creates `PENDING` record and shows the exact canonical approval context. Hard DENY creates no approvable grant.

### 6.2 User decision

```text
DENY/REJECT -> REJECTED
ALLOW ONCE  -> APPROVED
```

Integrated controlled path does not expose `always` as a generic grant semantic.

### 6.3 Execution consumption

Accepted only from kernel-verified `AGENT_SAFE_PEP` peer:

```text
CONSUME(
  authorization_id,
  operation_identity
)
```

Broker checks atomically:

```text
record exists
state == APPROVED
broker generation matches
registered host still live/current
source binding still active
PEP peer is current registered PEP
operation identity matches exactly
```

Success atomically transitions:

```text
APPROVED -> CONSUMED
```

and returns only an execution-continuation result to trusted PEP.

No second consumption is possible.

## 7. Why model-known IDs are insufficient to attack

A model-controlled shell/interpreter may learn or guess:

```text
authorization_id
operation_id
operation digest
socket/pipe endpoint name
```

but cannot consume authorization because broker also requires kernel-observed peer identity of the registered `AGENT_SAFE_PEP` process.

Likewise it cannot create/approve a trusted request because authorization-request and user-decision surfaces are not authenticated by those IDs.

This property is explicitly preferable to a CLI bearer flag/token.

## 8. B-P3 pure state-machine probe

Environment:

```text
Python in isolated ChatGPT execution environment
no network
no filesystem mutation required
no real OpenCode/agent-safe execution
```

Minimal reference state modeled:

```text
PENDING -> APPROVED -> CONSUMED
PENDING -> REJECTED
```

Checks performed:

| Case | Expected | Observed |
|---|---|---|
| trusted host requests A | `PENDING` | PASS |
| user approves A | `APPROVED` | PASS |
| registered PEP consumes A | allow once + `CONSUMED` | PASS |
| same PEP replays A | reject consumed state | PASS |
| approved A, PEP requests B | reject digest mismatch | PASS |
| model-child tries to consume A | reject untrusted PEP | PASS |
| model-child tries to create trusted request | reject untrusted host | PASS |
| broker restarts before consume | old grant absent/invalid | PASS |

This proves internal contract consistency, not OS peer verification or production race-safety.

## 9. Exact binding dependency on U2

B-P3 treats `operation_identity` as an opaque exact digest. Security depends on U2 ensuring that all authorization-relevant substitutions change that identity.

Therefore U1/U3 cannot be declared implementation-closed until `NormalizedOperation` canonicalization covers at least:

- channel/local/remote/transfer;
- workspace/cwd/execution environment identity needed by semantics;
- local/remote host identity;
- target path/resource identities;
- payload/argv/transfer representation;
- direction/overwrite semantics for transfer;
- expected authorized effects;
- executor/operation kind.

`purpose`, user-facing prose and correlation IDs must not create semantic equivalence or authorization scope.

## 10. TOCTOU rule

Authorization identity describes the approved operation, but runtime state can drift between approval and execution.

Therefore:

```text
broker exact-binding check
!=
runtime safety precondition proof
```

After consumption, `agent-safe` still performs its Gate C runtime-sensitive preflight. If actual state no longer satisfies safety preconditions, it returns `RUNTIME_REJECT`; it cannot ask broker to broaden authorization automatically.

If operation identity itself changed, consumption must fail before mutation rather than treating it as runtime drift.

## 11. Crash/restart semantics

Fail closed:

- broker restart: all pending/approved unconsumed records invalid unless future persistence is explicitly designed and proven (not proposed now);
- trusted host exit: grants bound to it cancel;
- PEP exit/restart: old PEP registration invalidates; replacement must re-register through trusted startup path;
- IPC disconnect before atomic consume result: caller treats execution authorization as unknown/not obtained and must query broker state read-only or abort; no blind mutation retry;
- successful consume followed by PEP crash before mutation: grant remains consumed; a retry requires a new authorization request unless a future transaction protocol proves safe recovery.

This deliberately prefers duplicate approval over duplicate mutation.

## 12. Gate state impact

B-P3: **PASS as pure contract model**.

U3 design recommendation can now be narrowed to:

> broker-resident, single-use, source-call/liveness/generation-bound authorization; no reusable short-lived bearer grant.

Still OPEN before Gate B closure:

- B-P2 Windows kernel peer/lifecycle fixture;
- B-P4 real no-mutation OpenCode host integration;
- trusted registration startup mechanism;
- U2 canonicalization/identity fixtures;
- exact agent-safe integrated PEP registration/handoff to be accepted with Gate C ownership.
