# Gate B — B-P3 executable broker state-model regression

Статус: **PURE CONTRACT REGRESSION PASS / NOT PRODUCTION BROKER**  
Дата: 2026-09-02

## 1. Назначение

Ранее `docs/gate_b_authorization_broker_contract_ru.md` зафиксировал B-P3 как pure state-model PASS. Этот slice превращает соответствующие свойства в executable regression tests без реализации production IPC/broker.

Test-only model:

```text
tests/authorization_broker/state_model.py
```

Regression:

```text
tests/test_gate_b_broker_state_model.py
```

## 2. Проверяемая модель

State model хранит broker-resident authorization record:

```text
PENDING -> APPROVED -> CONSUMED
```

Security не зависит от secrecy `authorization_id`.

Consume требует одновременно:

```text
trusted PEP role
record exists
state == APPROVED
broker generation current
host registration generation current
host live
source binding exact and active
operation identity exact
```

Успех атомарно моделируется как:

```text
APPROVED -> CONSUMED
ALLOW_EXECUTION_ONCE
```

## 3. Cross-project acceptance A8–A11

В executable tests закреплено:

| Matrix row | Scenario | Result |
|---|---|---|
| A8 | exact grant + exact operation | PASS, consume once |
| A9 | operation/payload substitution | REJECT |
| A10 | target substitution changes operation identity | REJECT |
| A11 | replay consumed authorization | REJECT |

## 4. Дополнительные fail-closed regressions

Также проверяются:

- model/same-user child, знающий `authorization_id`, не является trusted PEP;
- model child не может создать trusted authorization request;
- source-call substitution rejected;
- aborted source call cannot consume;
- host exit blocks consumption;
- broker restart invalidates old grant;
- hard DENY creates no approvable grant.

## 5. Scope boundary

Этот model намеренно **не** реализует:

- OS peer credential lookup;
- production concurrency/storage;
- approval UI;
- `agent-safe` runtime;
- filesystem/system mutation;
- deterministic effect classifier.

OS peer non-forgeability отдельно доказана Linux B-P1/B-P4 и остаётся pending для Windows B-P2.

PEP registration/startup implementation относится к Gate C/F ownership. Поэтому Gate B не объявляет full controlled mutation integrated-ready только на основании этого state model.

## 6. Verification

Локальный pure test run перед публикацией:

```text
11 tests
OK
```

Dangerous operations не выполнялись; operation identities в tests synthetic.

## 7. Вывод

B-P3 и применимые строки A8–A11 теперь имеют executable repository regression, а не только narrative/past execution evidence.

Это закрывает внутреннюю exact-binding/lifecycle часть Gate B; cross-platform trusted-peer proof всё ещё требует B-P2 Windows.
