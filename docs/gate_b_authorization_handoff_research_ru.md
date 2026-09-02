# Gate B — authorization handoff research for OpenCode 1.18.x

Статус: **EVIDENCE / candidate selection not closed**  
Дата: 2026-09-02

## 1. Вопрос

Можно ли использовать stock OpenCode permission/custom-tool primitives как non-forgeable exact-bound authorization handoff для controlled execution, не передавая модели caller-controlled `--approved`/token?

Исходные invariants Gate A:

- model-controlled input не является proof approval;
- authorization exact-bound к operation/target/effects;
- hard `DENY` не override-ится;
- generic wrapper не является trusted payload tunnel;
- runtime может narrow, never broaden.

## 2. Version evidence

Baseline runtime/source evidence: OpenCode `1.18.18`, upstream commit `31406ccc51b4bd2a4e1e086b2bcaa5f7f804f26d`.

Current upstream revalidation: release `v1.18.26`, tag commit `774cc7c1914e4329eefde5a669f938b0cf566661`.

Для ключевых primitives проверенные blobs на `1.18.26` совпадают с ранее исследованными 1.18.18 paths либо сохраняют ту же архитектуру:

- permission service: `2e27ff2424dbb000ea9ed7f73471769716ba40a1`;
- tool context: `e5e7802858ca5cd2250f8f34c4725a25c7a3221d`;
- permission HTTP group: `79959db499bd12a359ac84a9a189faebc84c016e`;
- HTTP auth middleware: `61ce39ad39e0643758861e82220953399bb6c824`;
- shell tool at 1.18.26: `1e4423e017740617bc6e0df36ad9dcdb0197bccb`.

Current official server documentation also describes `OPENCODE_SERVER_PASSWORD` as optional Basic-auth protection and states that normal TUI runs a server/client architecture.

## 3. `ctx.ask()` same-call continuation

`Tool.Context` includes:

```text
sessionID
messageID
callID
ask(...)
```

`SessionTools.resolve()` builds `ctx.ask` by calling the permission service with:

```text
sessionID = current session
tool.messageID = current assistant message
tool.callID = current tool call
ruleset = effective agent/session rules
```

This is a useful binding property: permission request is associated with the concrete tool invocation that produced it.

`Permission.ask()` stores a pending request and waits on a deferred result. `reply("once")` succeeds only that pending request and does not add a persistent allow rule. `reply("always")` succeeds the request and appends the tool-provided `always` patterns to instance-local approved state.

### Candidate benefit

A trusted controlled custom tool could theoretically:

```text
receive structured operation
-> normalize operation
-> ctx.ask(exact summary)
-> same tool execution resumes
-> execute controlled runtime path
```

The model would not need to receive `approved=true` or a bearer token.

## 4. `always` is not acceptable as authorization grant

For controlled mutation `always` is too broad as a generic grant primitive because tool-supplied patterns can authorize future requests.

A custom controlled tool could technically supply an empty `always` set, making an `always` reply add no future allow rules. This may reduce security scope, but stock TUI still presents the generic `Always allow` UX. It is therefore not selected as the authorization mechanism in this gate.

Gate B should prefer current-call/single-operation semantics and treat any broader saved approval as a separate policy concern.

## 5. Permission reply channel

OpenCode 1.18.26 experimental V1 HTTP API exposes:

- list pending permissions;
- reply to a permission request by `requestID`.

Both routes use the server authorization middleware.

The TUI user action is not accompanied by a separate cryptographic user assertion. For `Allow once`, TUI calls the SDK `permission.reply` with:

```text
reply = once
requestID = pending request id
workspace/directory routing context
```

Therefore the security of the reply channel is the security of access to the OpenCode server/API client credentials, not a distinct approval signature.

## 6. Server authentication boundary

Authorization middleware behavior:

```text
if OPENCODE_SERVER_PASSWORD is absent/empty:
    request proceeds without Basic-auth check
else:
    Basic credentials must match configured username/password
```

Thus default/optional server authentication cannot itself be assumed as a non-forgeability boundary.

## 7. Why ordinary `OPENCODE_SERVER_PASSWORD` is insufficient by itself

`ShellTool.shellEnv()` constructs child environment as:

```text
{
  ...process.env,
  ...shell_env_plugin_overrides
}
```

Therefore a password stored in the OpenCode process environment is, by default, inherited by model-controlled shell child processes.

This matters even if permission policy prevents casual secret display. Non-forgeability requires that the model-controlled execution channel cannot **use** the credential, not merely that the credential is not printed.

Consequently:

```text
OpenCode Basic auth enabled
+
password inherited by model-controlled child process
!=
trusted approval boundary
```

A technical environment-isolation layer could potentially remove the credential from child execution, but that layer would become part of the security boundary and must itself be audited across all model-controlled execution surfaces, not only shell.

## 8. Threat model cases that must fail

Any accepted handoff must reject or make impossible:

1. model-generated `--approved=true`;
2. model-generated/captured grant string;
3. permission reply from a model-controlled process;
4. listing pending permission IDs from a model-controlled process and replying to them;
5. grant for operation A used for operation B;
6. target A -> target B substitution;
7. local -> remote/other host substitution;
8. transfer direction/path substitution;
9. replay after successful consumption;
10. reuse in another session/tool call;
11. hard-denied operation after any apparent approval;
12. approval channel credential inherited by shell/interpreter/other executable tool.

Tests are mock/source/isolated only; no destructive payload execution is needed.

## 9. Current candidate assessment

| Candidate | Strength | Blocking gap | Status |
|---|---|---|---|
| caller Boolean/`--approved` | simple | fully model-forgeable | REJECTED |
| bearer token passed through model-visible CLI args | easy integration | token exposure/substitution/replay | REJECTED as default |
| stock custom tool + `ctx.ask` + unauthenticated server | same-call continuation | reply API forgeable by any reachable caller | REJECTED |
| stock custom tool + `ctx.ask` + ordinary env Basic auth | same-call continuation + auth | credential inherited by shell process by default | INSUFFICIENT |
| hardened custom tool + isolated reply credential | preserves native UX | must prove credential inaccessible to every model-controlled execution surface | CANDIDATE |
| OS-protected local broker/IPC + trusted tool | strong separation possible | extra component/protocol and integration evidence needed | CANDIDATE |
| patched/upstream capability-bound permission reply | potentially strongest native integration | not present/proven in current target release | FUTURE CANDIDATE |

No candidate is yet ACCEPTED.

## 10. Requirements for hardened custom-tool candidate

Before accepting this path, Gate B would need evidence that:

1. server/reply credential is mandatory;
2. credential is not present in model-visible tool arguments/output;
3. credential is removed from shell child environment;
4. interpreters/custom executable paths cannot access it through another inherited channel;
5. untrusted plugins/MCP processes do not inherit or obtain it;
6. only trusted UI/broker and trusted gate code can reply;
7. operation is re-normalized/checked after approval immediately before execution;
8. controlled tool cannot accept caller-supplied substitute grant;
9. approval is single-operation scoped;
10. failure/unknown state does not auto-retry mutation.

If achieving these requirements requires broad host patching or multiple brittle filters, prefer a dedicated OS-protected broker rather than pretending Basic auth is a sufficient boundary.

## 11. Exact-binding direction

The promising property of custom-tool continuation is that the structured operation can remain inside trusted code across the wait:

```text
immutable/validated tool args
-> NormalizedOperation identity
-> ASK display
-> reply unblocks same pending tool call
-> compare current normalized identity with approved identity
-> hand off directly to runtime
```

The model never needs a reusable authorization object.

If an explicit `AuthorizationGrant` object is still needed across process boundary to `agent-safe`, it should be created by trusted gate code after approval and passed over a channel inaccessible to model-controlled CLI input. The grant must contain/bind the operation identity and be consumed by `agent-safe` only after exact match.

## 12. Decision for this research slice

Confirmed:

- `ctx.ask` same-call continuation is technically useful;
- permission request has session/message/tool-call association;
- stock TUI reply is an API reply, not separate user-signed evidence;
- server auth is optional;
- ordinary server password environment is inherited by shell child processes;
- therefore stock OpenCode permission reply + ordinary environment Basic auth does **not** prove non-forgeability required by Gate A.

U1 remains OPEN, but one weak design branch is now eliminated. Next research should compare two bounded candidates:

```text
A. hardened custom-tool continuation with complete credential isolation
B. OS-protected local authorization broker/IPC
```

The comparison must include implementation complexity, Windows/Linux support, OpenCode-version coupling, failure modes, exact binding and testability. Deterministic classifier/auditor remains out of scope.
