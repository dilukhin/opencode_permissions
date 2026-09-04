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
| F3 full process environment snapshot | **ACCEPT + IMPLEMENT NEXT** | default binding должен учитывать только явно объявленные authorization-relevant environment dependencies; чтение всего env не является default requirement |
| F4 build/test слишком недоверенные | **ACCEPT DIRECTION / DESIGN REQUIRED** | нужен technical trusted-workspace fact; до его доказательства текущий ASK не ослаблять |
| F5 read-only Git overly hardened | **ACCEPT DIRECTION / DEPENDS ON F4** | в trusted repository/workspace можно рассмотреть обычные read-only Git families; в untrusted profile сохранить hardened/ASK |
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

Новый logical contract:

```yaml
authorization_environment_dependencies:
  - name: ...
    representation: exact|derived|presence
```

Если analyzer/profile не декларирует environment dependency, environment не входит в authorization binding.

Secret-like values не должны автоматически копироваться в operation identity, trace или approval context.

DC-4 fixture будет изменена отдельно так, чтобы проверять declared dependency drift без snapshot всего окружения.

## 4. F4 — trusted workspace

Направление принято, но blanket `trusted_workspace=true` запрещён.

До изменения build/test policy нужен отдельный design/acceptance slice, который определит:

- кто создаёт trust fact;
- где он хранится;
- почему модель не может сама его выставить;
- к какому exact workspace/repository identity он относится;
- как trust инвалидируется при смене target/workspace;
- какие command families получает право упростить;
- какие hard-deny/secrets boundaries trust никогда не ослабляет.

Предпочтительный owner факта — managed setup/user configuration plane, а не classifier input от модели.

Пока этот contract не доказан:

```text
cmake --build / ctest / pytest -> текущая conservative policy сохраняется
```

## 5. F5 — read-only Git

Не реализуется отдельно от F4.

После появления trusted repository/workspace fact можно проверить две политики:

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

Принята последовательность:

```text
1. threat-model/document reconciliation
2. убрать full-env binding из DC-4 proof, заменить declared dependency
3. design trusted-workspace fact (без policy widening до acceptance)
4. подготовить minimal managed pilot contract для opencode_setup
5. pilot + residual ASK metrics
6. deterministic/native tuning
7. auditor только при доказанной необходимости
```

Параллельная работа `agent-safe` по resource lifecycle/execution safety не переносится сюда и не должна ждать auditor.
