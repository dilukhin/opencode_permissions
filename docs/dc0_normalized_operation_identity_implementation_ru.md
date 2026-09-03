# DC-0 — NormalizedOperation identity implementation

Статус: **IMPLEMENTATION CANDIDATE / CI REQUIRED**  
Дата: 2026-09-03

## 1. Scope

Этот slice реализует U2 foundation для deterministic-classifier gate:

- restricted JCS-compatible canonicalization `op-jcs-v1`;
- typed validation identity core;
- domain-separated SHA-256 `operation_identity`;
- executable regression поверх существующих `tests/normalized_operation/identity_relations.json`;
- strict JSON duplicate-key/number/unicode handling.

Это **не** classifier и не runtime authorization integration.

## 2. Identity implementation

Implementation:

```text
tools/normalized_operation_identity.py
```

Domain separator:

```text
opencode_permissions.normalized_operation.v1\n
```

Output:

```text
sha256:<lowercase-hex>
```

## 3. Restricted JCS domain

Identity v1 намеренно ограничен I-JSON-like subset:

- objects with string keys;
- arrays;
- strings without unpaired surrogates;
- booleans/null;
- integers only inside IEEE-754 safe integer range;
- floats/NaN/Infinity rejected.

Object keys sort by UTF-16 code units, как требует RFC 8785 property ordering.

Duplicate JSON object keys rejected during strict load.

## 4. Explicit semantic-set normalization

Set semantics применяются только к заранее объявленным identity fields:

```text
effects
targets
context_dependencies
```

Для них выполняется deterministic sort + exact duplicate elimination.

`argv`, opaque payload strings и execution structure не reordered/requoted.

## 5. Fail-closed validation

Unknown top-level identity fields rejected, если они не входят в explicit excluded metadata set.

Excluded metadata не влияет на operation identity:

```text
purpose
description
display
operation_id/correlation_id
session/message/call IDs
policy/rule provenance
created_at/reason prose
```

Sensitive context dependency explicitly marked `sensitive=true` или `value_kind=secret` rejected instead of hashing raw secret material.

Schema/canonicalization version mismatch возвращает relation `NON_COMPARABLE`.

## 6. Regression

`tests/test_normalized_operation_identity.py` проверяет:

- JCS object order;
- UTF-16 key order edge case;
- control/quote/backslash string escaping;
- duplicate-key rejection;
- float/non-finite/unsafe-integer rejection;
- unpaired-surrogate rejection;
- fixed digest vector for existing `local_git_status` operation;
- excluded metadata invariance;
- unknown field fail-closed;
- sensitive context dependency rejection;
- schema/canonicalization `NON_COMPARABLE`;
- все 30 existing relation fixtures executable end-to-end.

## 7. Deliberate non-claims

Этот slice пока не доказывает:

- actual filesystem object identity acquisition;
- Windows HANDLE/POSIX inode preflight implementation for arbitrary targets;
- remote host identity provider;
- trusted execution-boundary recomputation before mutation;
- classifier parser/effect semantics;
- live OpenCode integration.

Эти responsibilities остаются последующими slices/gates. Но после PASS этого slice classifier сможет выпускать reproducible identity для уже trusted/preflighted typed operation data.

## 8. Acceptance

DC-0 implementation candidate считается PASS только если Linux/Windows CI matrix подтверждает:

```text
all existing relation fixtures pass
fixed identity vector stable
invalid JSON/numeric/unicode forms fail closed
no secret-like sensitive dependency accepted
no existing Gate B regression fails
```

После PASS можно начинать DC-1 classifier schema/composition engine. U2 register может быть повышен только до статуса `IMPLEMENTED CORE / trusted-boundary recomputation deferred`, а не безусловно CLOSED.