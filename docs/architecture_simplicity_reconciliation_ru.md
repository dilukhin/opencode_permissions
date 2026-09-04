# Reconciliation аудита архитектурной минимальности

Статус: **ACCEPTED DECISIONS**.

Источник review findings:

`docs/architecture_simplicity_audit_ru.md`

Этот документ переводит brainstorm F1–F9 в принятые решения. Он не означает немедленную реализацию всех предложений.

## Решения

| Finding | Решение | Что это значит |
|---|---|---|
| F1 broker как default | **ACCEPT** | kernel-authenticated broker остаётся high-assurance research/option; default production path не обязан его иметь |
| F2 полный content hash executable | **ACCEPT** | сохранить как доказательный/high-assurance механизм; не считать обязательным default contract |
| F3 full process environment snapshot | **ACCEPT / IMPLEMENTED IN DC-4 PROOF** | default binding учитывает только явно объявленные authorization-relevant environment dependencies; full env enumeration удалён из proof fixture |
| F4 build/test слишком недоверенные | **CONSUMER CONTRACT PASS / PRODUCER PENDING** | WorkspaceTrustFact schema/exact matcher реализованы без policy widening; первый trust-conditioned ALLOW запрещён до trusted producer/integration proof |
| F5 read-only Git overly hardened | **ACCEPT DIRECTION / DEPENDS ON F4 PRODUCER** | в trusted repository/workspace можно рассмотреть обычные read-only Git families; в untrusted profile сохранить hardened/ASK |
| F6 exact-version profile explosion | **ACCEPT** | exact version selection сохраняется, но evidence/fingerprint contracts можно переиспользовать между версиями после explicit revalidation; nearest-version fallback запрещён |
| F7 auditor преждевременен | **ACCEPT** | auditor откладывается до managed pilot и измерения residual ASK |
| F8 speculative wire contracts | **ACCEPT** | новые межпроектные schemas проектируются just-in-time для реального producer/consumer |
| F9 research смешан с current architecture | **ACCEPT** | candidate/broker docs остаются evidence, но явно маркируются как research/high-assurance, не default requirement |

## 1. F1 — broker

Принято:

```text
DEFAULT:
OpenCode-native proven authorization continuation / minimal trusted adapter

OPTIONAL HIGH-ASSURANCE:
kernel-authenticated broker
```

Broker research не удаляется. Его proofs остаются полезными для сценариев с более сильным local-adversary threat model.

Возврат broker в default возможен только при:

- воспроизводимом bypass более простого path;
- внешнем high-assurance requirement;
- доказанной необходимости отделить trusted authorization channel от OpenCode host runtime.

## 2. F2 — executable identity

DC-4 полный SHA-256 системного executable сохраняется как сильный proof того, что exact object binding вообще реализуем.

Но future default production adapter не обязан повторно hash-ить содержимое каждого executable.

Минимальный default contract будет определён при pilot implementation. Допустимые составляющие:

- resolved path из trusted installation/search boundary;
- basic object identity, если требуется для substitution protection;
- content digest только там, где он действительно является частью chosen immutable/high-assurance profile.

До pilot никакой существующий safety check не удаляется.

## 3. F3 — environment dependencies

Принято более узкое правило:

> Authorization связывается не со всем `process.env`, а только с теми environment facts, от которых реально зависит смысл/исполнение доказанного operation profile.

Логический contract:

```yaml
authorization_environment_dependencies:
  - name: ...
    representation: exact|derived|presence
```

Если analyzer/profile не декларирует environment dependency, environment не входит в authorization binding.

Secret-like values не должны автоматически копироваться в operation identity, trace или approval context.

F3 реализован в DC-4 proof:

- full `process.env` enumeration удалён;
- synthetic declared dependency проверяет механизм drift invalidation;
- неожиданный `shell.env` injection остаётся fail-closed;
- source regression запрещает возврат broad snapshot;
- exact OpenCode runtime proof и Linux/Windows regression matrix остаются PASS.

Durable evidence:

`docs/dc4_environment_dependency_reconciliation_ru.md`.

## 4. F4 — trusted workspace

Consumer-contract часть завершена без изменения policy.

Реализовано:

```text
tools/workspace_trust.py
tests/test_workspace_trust.py
docs/trusted_workspace_fact_design_ru.md
```

Закреплено:

- `trusted=true` из caller/model input не является proof;
- fact validity не равна provider authenticity;
- exact match требует platform/requested root/resolved root/object identity;
- content hash всего репозитория не требуется;
- scopes ограничены `build/test/static_check/git_read`;
- wildcard/all/delete/system scopes запрещены;
- TTL/generation/broker не добавляются без evidence необходимости;
- Windows path matching остаётся conservative, без case folding.

Текущая build/test policy **не изменена**:

```text
cmake --build / ctest / pytest -> ASK_USER
```

До первого trust-conditioned ALLOW остаётся отдельный producer/integration gate:

- кто создаёт/revokes trust;
- где/как хранится authoritative state;
- почему model-controlled path не может автоматически выдать себе trust;
- runtime acquisition observed workspace identity;
- paired build/test policy corpus;
- managed setup integration.

## 5. F5 — read-only Git

Не реализуется отдельно от F4 producer/integration boundary.

После появления authenticated trusted repository/workspace fact можно проверить две политики:

```text
trusted repository:
  common read-only git -> candidate ALLOW

untrusted repository:
  hardened invocation or ASK
```

Изменение `.git/config`, hooks и других execution-affecting repository controls остаётся отдельно защищённым.

## 6. F6 — OpenCode version evidence

Сохраняется fail-closed exact-version selection.

Упрощается организация evidence:

```text
exact version
  -> capability/fingerprint set
  -> source equivalence/revalidation
  -> targeted runtime proof where required
```

Две patch-версии могут ссылаться на один и тот же semantic capability contract только после explicit проверки каждой версии.

Запрещено:

- nearest-version fallback;
- semver-only compatibility;
- автоматическое наследование deployability.

## 7. F7 — auditor

Auditor **DEFERRED BY POLICY** до практического pilot.

До его проектирования требуется:

1. подключить уже доказанный native + deterministic path в ограниченном managed environment;
2. собрать реальные residual ASK;
3. разбить их по причинам;
4. проверить, сколько снимается более простыми native/deterministic rules;
5. оценить оставшийся объём/цену human prompts.

Auditor разрешено начинать только если остаётся значимая gray zone, для которой deterministic решение непропорционально дорого или невозможно.

## 8. F8 — contracts just-in-time

Существующая cross-project vocabulary сохраняется.

Но новые wire schemas не считаются обязательными deliverables сами по себе.

Правило:

> schema стабилизируется, когда существует конкретный producer + consumer и acceptance case.

Например, `ContextFacts` не детализируется дальше до фактической необходимости `opencode_permissions` потреблять такие facts.

## 9. F9 — documentation classes

Документы трактуются тремя классами:

### Current contracts

Нормативные границы и действующие решения.

### Current implementation / closure evidence

Что фактически реализовано и доказано.

### Research / alternatives / historical design

Исследования, rejected/optional candidates, bounded proofs и старые plans.

Research не удаляется, но не задаёт default architecture без отдельного accepted decision.

## 10. Что не меняется

Аудит не ослабляет следующие инварианты:

- hard DENY absolute;
- unknown/opaque не ALLOW;
- whole-operation/nested analysis;
- secret boundary;
- target/effects binding;
- caller-controlled self-approval запрещён;
- один authorization owner;
- `agent-safe` может только сузить upstream authorization;
- production changes только через explicit integration/deployment gate.

## 11. Следующая последовательность

Текущее состояние последовательности:

```text
1. threat-model/document reconciliation                         DONE
2. убрать full-env binding, заменить declared dependency        DONE
3a. trusted-workspace consumer contract                         DONE
3b. trusted-workspace producer/integration boundary             NEXT
4. minimal managed pilot contract
5. pilot + residual ASK metrics
6. deterministic/native tuning
7. auditor только при доказанной необходимости
```

Параллельная работа `agent-safe` по resource lifecycle/execution safety не переносится сюда и не должна ждать auditor.
