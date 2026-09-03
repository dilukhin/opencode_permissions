# DC-1 — classifier result schema и pure composition engine

Статус: **IMPLEMENTATION CANDIDATE / CI REQUIRED**  
Дата: 2026-09-03

## 1. Scope

DC-1 реализует только общий deterministic contract классификатора:

- `classifier-result/v1`;
- semantic completeness validation перед ALLOW;
- связь declared effects/targets с `NormalizedOperation` identity;
- terminal precedence native ALLOW/DENY;
- monotonic composition `DENY > ASK_USER > ALLOW`;
- requirement parent operation identity для composed ALLOW;
- fail-closed downgrade при incomplete parent effects/targets/identity.

DC-1 не содержит shell parser и command-specific analyzers.

## 2. Native precedence

Classifier используется только после native `ask`:

```text
native deny  -> DENY  (terminal)
native allow -> ALLOW (terminal)
native ask   -> classifier result or ASK_USER
```

Pure regression специально передаёт malformed/hypothetical classifier result вместе с terminal native decision и доказывает, что он не влияет на результат.

## 3. ALLOW invariant

`classifier-result/v1` с `decision=ALLOW` допустим только если одновременно:

```text
uncertainties = []
effects non-empty
unknown / unknown_code_execution absent
unknown_target absent
NormalizedOperation present
operation_identity valid and recomputes exactly
result effects == identity-core effects
result targets == identity-core targets
operation-kind semantic completeness passes
```

Наличие корректного hash без semantic completeness недостаточно.

## 4. Bounded operation completeness v1

DC-1 определяет minimum required shapes для уже типизированных operations:

- `process_exec / argv`;
- `shell_script / shell_script`;
- `remote_exec / remote_argv`;
- `transfer / transfer`;
- `file_create / structured_file_create`;
- `compound / compound`;
- `pipeline / pipeline`.

Unknown `operation_kind` не может поддержать ALLOW.

Это schema foundation для будущих analyzers; analyzer обязан построить один из поддержанных typed shapes либо оставить uncertainty.

## 5. Composition

Для child results:

```text
any DENY      -> DENY
else any ASK  -> ASK_USER
else all ALLOW:
  no parent operation identity -> ASK_USER
  invalid parent shape         -> ASK_USER
  missing child effect         -> ASK_USER
  missing child target         -> ASK_USER
  parent unknown effect/target -> ASK_USER
  otherwise                    -> ALLOW
```

Parent compound/pipeline identity включает ordered child operation identities и operators/pipes, поэтому перестановка/замена child operation меняет parent identity.

## 6. Deliberate non-claims

DC-1 не доказывает:

- parsing shell syntax;
- safety конкретного `find`, `git`, `grep`, build/test command;
- acquisition фактического filesystem/executable/remote object identity;
- runtime trusted-boundary recomputation;
- OpenCode adapter invocation ordering;
- live deployment.

Следующий slice DC-2 должен добавлять bounded analyzers поверх этого core без изменения composition invariants.

## 7. Regression acceptance

`tests/test_classifier_core.py` проверяет минимум:

- valid ALLOW имеет complete identity;
- unknown effect/target запрещает ALLOW;
- incomplete operation запрещает ALLOW;
- identity/effects mismatch rejected;
- native DENY/ALLOW terminal;
- native ASK routes to classifier;
- child DENY dominates ASK/ALLOW;
- child ASK dominates ALLOW;
- identityless composed ALLOW downgrades to ASK;
- complete parent compound permits ALLOW;
- incomplete parent effects/targets downgrades ASK;
- unknown parent effect downgrades ASK;
- malformed compound operator binding downgrades ASK.

DC-1 считается PASS только после Linux/Windows CI matrix и отсутствия Gate B/DC-0 regressions.