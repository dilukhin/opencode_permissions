# Gate B — `NormalizedOperation` exact identity / canonicalization contract

Статус: **REVIEW PROPOSAL / U2 design substantially specified, implementation pending**  
Дата: 2026-09-02

Этот документ определяет identity contract для exact-bound authorization. Он не классифицирует effects и не является deterministic classifier.

## 1. Цель

Authorization для operation A не должен быть применим к semantic/payload/target operation B.

При конфликте целей canonicalization приоритет такой:

```text
false non-equivalence -> лишний ASK / новое authorization
false equivalence     -> потенциальная authorization substitution
```

Поэтому canonicalization должна быть **консервативной**. Не требуется распознавать все семантически эквивалентные shell/path representations.

## 2. Разделение понятий

Нужно различать:

```text
NormalizedOperation          semantic/execution data to authorize
OperationIdentityCore        only fields affecting operation identity
operation_identity           digest of canonical identity core
source_binding               session/message/call scope; grant boundary, not operation semantics
AuthorizationDecision        decision + policy provenance
AuthorizationGrant           broker-resident single-use authorization state
```

`operation_id`/correlation ID не является `operation_identity`.

## 3. Canonical serialization

Для `OperationIdentityCore` предлагается:

```text
pre-normalize typed fields according to this contract
-> RFC 8785 JSON Canonicalization Scheme (JCS)
-> UTF-8 bytes
-> domain-separated SHA-256
```

Digest input:

```text
UTF8("opencode_permissions.normalized_operation.v1\n")
+
JCS(OperationIdentityCore)
```

Logical output:

```text
sha256:<lowercase-hex>
```

### 3.1 Почему JCS

RFC 8785 задаёт deterministic JSON property ordering/serialization для hashable representation. Он также явно не выполняет Unicode normalization; строки сохраняются как есть. Это соответствует консервативному принципу проекта.

### 3.2 Дополнительные schema restrictions

Identity schema должна быть уже JCS/I-JSON:

- duplicate object keys запрещены;
- `NaN`/Infinity запрещены;
- floating-point values в identity core не использовать;
- exact large numeric identifiers хранить как decimal strings;
- timestamps, если вообще нужны, не входят в operation semantics и остаются grant/audit metadata;
- Unicode strings не NFC/NFD-normalize автоматически;
- missing field и explicit `null` не считаются одинаковыми без schema rule.

## 4. Identity core — proposed fields

```yaml
schema: normalized-operation/v1
canonicalization: op-jcs-v1
platform: windows|linux|darwin|other
channel: local|remote|transfer|other
operation_kind: ...
execution:
  kind: argv|shell_script|structured|remote_argv|transfer|other
  executable: ...
  argv: [...]
  script: ...
  cwd: ...
remote: ...
targets: [...]
effects: [...]
context_dependencies: [...]
```

Fields absent when not applicable; schema defines allowed combinations.

Not in identity core:

```text
purpose
human-readable description
approval prompt prose
operation_id/correlation id
session_id/message_id/call_id
policy_artifact_id
rule_id
created_at/timestamps
AuthorizationDecision reason prose
```

These can affect grant validity/provenance but must not silently change what operation means.

## 5. Ordering rules

### Ordered data — preserve exact order

- `argv`;
- opaque script/interpreter payload text;
- ordered execution steps when operation type explicitly defines sequence;
- ordered transfer or patch elements if order affects result.

### Semantic sets — normalize to sorted unique representation

- `effects`;
- target collections only when each target has an explicit role/key and ordering is declared non-semantic by its operation schema;
- `context_dependencies` when represented as independent keyed dependencies.

Array/set status must be defined by schema, never guessed by generic canonicalizer.

## 6. Executable identity

For executable operations bind both invocation and resolved executor where available:

```yaml
executable:
  invoked: git
  resolved_path: C:/Tools/Git/bin/git.exe
  object_identity: win-file:...
```

or platform equivalent.

Required properties:

- different resolved executable -> different identity;
- same path now referencing a different filesystem object -> different identity when object identity is available;
- runtime must revalidate relevant executable identity immediately before mutation if operation risk requires it;
- `PATH` lookup string alone is not sufficient exact identity for controlled mutation.

For shell script execution bind:

```text
exact shell/executor identity
exact script string
cwd identity
```

Do not parse/rewrite/requote the script merely for identity equivalence. Effect analysis is a separate concern.

## 7. Path/resource identity

### 7.1 Conservative rule

Do **not** authorize solely by a cosmetically normalized path string.

Prefer a structure containing both:

```yaml
requested: exact model/tool-supplied path representation
resolved: platform-resolved absolute target representation
object_identity: filesystem object identity if object exists
follow_mode: link|target|operation-specific
```

Exact final field names are implementation detail; semantics are normative.

### 7.2 Do not over-normalize

For authorization identity v1:

- do not case-fold Windows paths;
- do not Unicode-normalize path strings;
- do not treat slash/backslash spelling as automatically identity-equivalent;
- do not collapse `.`/`..` spellings into authorization equivalence merely lexically;
- do not assume symlink/reparse behavior from path text.

This intentionally creates some false non-equivalence.

Reason: filesystem resolution can depend on symlink/reparse points, case-sensitive directories, mount/filesystem semantics and object replacement. Exact target proof is more important than reducing controlled-path prompts.

### 7.3 Existing target

Where safely available from read-only preflight, include platform object identity in addition to requested/resolved path.

Examples of possible implementation evidence (not fixed wire format):

- POSIX device/inode or stronger handle-derived identity;
- Windows volume/file identity obtained from a handle.

### 7.4 Non-existing write target

For create operations bind at least:

```text
resolved parent object identity
+
exact leaf name
+
requested/resolved destination representation
+
creation/overwrite semantics
```

Runtime preflight must revalidate parent/target state before mutation.

## 8. Remote identity

Remote operation identity must include stable target-machine identity supplied by trusted transport/context contract, not only a display hostname typed by the model.

At minimum:

```yaml
remote:
  transport: ssh_relay
  host_identity: machine:<stable-id>
```

Remote payload/path identity is scoped under that host identity.

Changing host A -> B always changes operation identity, even if command/path text is identical.

## 9. Transfer identity

Transfer is first-class operation, not shell decoration.

Identity includes at least:

```text
direction: upload|download
source identity
destination identity
remote host identity
overwrite/fail-if-exists semantics
transport operation kind
expected effects
```

Direction, host, local/remote path or overwrite-mode substitution changes identity.

## 10. Effects

`effects` is an explicit sorted unique semantic set.

Examples:

```text
read
write
delete
network
remote_execution
remote_state_change
transfer
privilege
unknown
```

Different authorized effect set -> different identity.

`unknown` must not canonicalize to absence of effects or to a known-safe set.

Hashing an opaque payload does **not** prove its effects safe. It only prevents post-approval payload substitution.

## 11. Context dependencies

Only context that the normalization/policy explicitly depends on belongs here.

Examples:

```yaml
- kind: resolved_variable
  name: BUILD_DIR
  value: C:/Repo/build
```

Rules:

- explicit dependency change -> different identity;
- do not dump whole environment;
- do not store raw secrets;
- do not store unsalted/ordinary hashes of low-entropy secrets as a substitute for secret handling;
- if operation semantics materially depend on secret/unknown context that cannot safely enter identity, represent residual uncertainty and require runtime revalidation/ASK rather than pretending exact context binding.

## 12. Source binding is separate

Two identical operations proposed by different tool calls may have the same `operation_identity`.

They do **not** share authorization because broker grant separately binds:

```text
session_id
message_id
call_id
host registration generation
broker generation
single-use state
```

Therefore:

```text
same operation identity != reusable approval
```

This separation keeps semantic identity stable while preserving exact approval scope.

## 13. Policy provenance is separate

`policy_artifact_id`, rule ID and decision reason are recorded in `AuthorizationDecision/Grant`, not mixed into operation digest.

A policy update must invalidate/re-evaluate pending authorizations through broker lifecycle/policy state, rather than changing the meaning of the underlying operation.

## 14. Runtime drift / TOCTOU

Identity is not a replacement for runtime safety.

Immediately before mutation:

- recompute/revalidate operation identity inputs that can drift;
- verify target/executable/object state where required;
- `agent-safe` checks runtime preconditions;
- if identity changed -> authorization mismatch, no mutation;
- if identity same but runtime safety precondition fails -> `RUNTIME_REJECT`;
- no automatic broaden/retry.

## 15. Identity relation fixture set

`tests/normalized_operation/identity_relations.json` defines 30 design fixtures.

Required SAME families are deliberately few:

- JSON object property ordering;
- explicitly declared semantic-set ordering/duplicates;
- excluded display/purpose/correlation metadata.

Required DIFFERENT includes:

- argv order/boundaries;
- opaque payload whitespace/text;
- channel/platform/operation kind;
- cwd/executable/object identity;
- effect set;
- unknown vs known effect;
- Windows path spelling/case variations under conservative v1;
- dot/parent path spelling;
- target object/follow mode;
- remote host;
- transfer direction/overwrite/path;
- non-existing target parent/leaf;
- explicit context dependency.

Different schema/canonicalization versions are `NON_COMPARABLE`, not silently equal/different under the same algorithm.

## 16. U2 closure criteria

U2 can close only after:

1. machine-readable identity schema/profile exists;
2. JCS-compatible canonicalizer has deterministic cross-runtime test vectors;
3. all relation fixtures pass on supported implementation runtimes;
4. path/object identity implementation has Windows + Linux safe fixtures;
5. remote/transfer identity uses actual accepted transport target semantics;
6. grant mismatch tests prove A cannot consume B;
7. no identity material/log artifact leaks secrets;
8. operation identity is recomputed/revalidated at trusted execution boundary;
9. schema/canonicalization version change is explicit and compatibility-managed.

Current state: **design specified; implementation/test-vector closure pending**.
