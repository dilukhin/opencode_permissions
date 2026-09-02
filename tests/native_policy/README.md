# Gate B native-policy test harness

Статус: **test-only / design candidate / not deployable**

Этот каталог проверяет только representability native permission matcher OpenCode V1.

Он **не** реализует:

- shell parser;
- deterministic effect classifier;
- model auditor;
- production permission config;
- authorization broker.

## Files

- `policy_candidate.json` — ordered logical candidate rules for OpenCode 1.18.26 semantics.
- `corpus_projection.json` — 69-case corpus projection into already-extracted native permission/pattern requests.
- `native_policy_sim.py` — exact-style Wildcard + last-match-wins evaluator for those requests.

Four `authorization_contract` cases are intentionally excluded from native metrics because they belong to B-P3 broker exact-binding semantics.

## Important boundary

`corpus_projection.json` does not infer shell semantics. Shell patterns are explicit fixtures derived from the already established OpenCode shell-source behavior:

- shell permission key is `bash`;
- Tree-sitter command nodes become permission patterns;
- redirected command source includes the redirected statement;
- external-directory checks are separate permission requests.

If future OpenCode source changes those assumptions, the compatibility profile must invalidate/revalidate this projection.

## Safety acceptance

The candidate is acceptable for Gate B design only if both POSIX and Windows-style Wildcard evaluation keep:

```text
unsafe_auto_allow = 0
dangerous_false_safe = 0
wrapper_false_safe = 0
unknown_false_safe = 0
secret_false_safe = 0
```

ASK is a valid conservative result where native rules cannot prove a stronger decision.

Run:

```text
python tests/native_policy/native_policy_sim.py \
  tests/native_policy/policy_candidate.json \
  tests/native_policy/corpus_projection.json

python -m unittest discover -s tests -v
```
