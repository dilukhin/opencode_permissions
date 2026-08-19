# `opencode_permissions` как managed target `opencode_setup`

Статус: **ACCEPTED design requirement / implementation pending**.

Этот документ дополняет cross-project integration master plan. Он фиксирует обязательное направление интеграции, но не утверждает наличие реализации в `opencode_setup` и не определяет преждевременно формат production permission artifact.

## 1. Решение

`dilukhin/opencode_permissions` должен стать **first-class managed integration target/dependency** проекта `dilukhin/opencode_setup`.

`opencode_setup` должен в целевой integrated environment:

1. обнаруживать наличие checkout `opencode_permissions`;
2. безопасно устанавливать отсутствующий checkout;
3. обновлять принадлежащий setup checkout только по принятой non-destructive repository reconciliation policy;
4. обнаруживать tracked/local modifications, local commits и иные ownership conflicts без `reset/clean/force`;
5. использовать `opencode_permissions` как canonical source authorization-policy artifacts/contracts;
6. разворачивать и reconciliate такие artifacts в live OpenCode environment после того, как их конкретный формат и ownership будут определены этапом B;
7. проверять фактическое effective permission state после deployment/reconciliation;
8. обнаруживать и мигрировать известные legacy/conflicting permission writers, прежде всего старые artifacts `agent-safe`, не удаляя unknown/user-owned state вслепую.

Таким образом, `opencode_setup` владеет **установкой и reconciliation**, но не смыслом permission policy.

## 2. Текущее состояние

На момент принятия решения `opencode_setup` уже имеет managed dependency/repository model для `ssh_relay` и `agent_safe`, но `opencode_permissions` в `managed_environment.dependencies` ещё отсутствует.

Это считается implementation gap этапа F, а не причиной менять `opencode_setup` до стабилизации cross-project contract и authorization artifact contract.

## 3. Целевая зависимость

Концептуально `opencode_setup` должен прийти к модели:

```text
managed dependencies / authoritative sources

ssh_relay
agent-safe
opencode_permissions
[ScopedKB integration — только если/когда она станет runtime dependency]
```

Для `opencode_permissions` должны быть определены как минимум:

- repository URL: `https://github.com/dilukhin/opencode_permissions.git`;
- canonical branch/version policy — определяется перед implementation, не предполагается автоматически;
- canonical checkout directory под `projects_dir`;
- deployable artifact(s) и их ownership — определяются этапом B;
- health/version/read-back checks;
- legacy signatures и migration rules, если они нужны.

## 4. Разделение ответственности

### `opencode_permissions`

Определяет:

- `ALLOW / ASK_USER / DENY` semantics;
- hard-deny invariants;
- native policy rules;
- schemas/contracts authorization layer;
- canonical deployable permission artifacts и их version semantics.

### `opencode_setup`

Определяет:

- где и как checkout устанавливается;
- repository ownership/reconciliation;
- как canonical artifacts доставляются в live environment;
- conflict/legacy detection;
- backup/migration mechanics;
- end-state verification.

`opencode_setup` не редактирует semantic contents policy по собственным эвристикам и не добавляет собственные `ALLOW/ASK/DENY` rules.

## 5. Требование к порядку работ

Implementation в `opencode_setup` начинается только после того, как этап B `opencode_permissions` определит минимальный стабильный artifact/contract, необходимый для installation.

Порядок:

```text
Gate A: cross-project ownership/contract
        ↓
Gate B: opencode_permissions artifact/interface contract
        ↓
Gate C–E: соседние runtime/context boundaries
        ↓
Gate F: opencode_setup добавляет opencode_permissions target и reconciliation
        ↓
Gate G: cross-project acceptance
```

Это не запрещает заранее подготовить read-only inventory/design в `opencode_setup`, но production writer не должен опережать владельца policy.

## 6. Обязательные deliverables этапа F

При реализации в отдельном диалоге `opencode_setup` должны быть рассмотрены как минимум:

- `config_data.json`: добавить `opencode_permissions` в managed dependency/target model;
- README/operational docs: добавить checkout и managed policy source в перечень управляемых компонентов;
- orchestration: clone/update/check dependency по тем же safe repository rules, что применимы к другим managed repos;
- reconciliation: получать canonical policy artifact только из согласованного source;
- effective-layer inventory: обнаруживать old/global/project/environment conflicts;
- legacy migration: известный точный legacy artifact можно мигрировать по explicit rule; modified/unknown — preserve + conflict;
- tests: missing/current/outdated/local-modified checkout, mixed legacy permission state, repeated idempotent deploy;
- Windows/Linux validators;
- targeted end-state read-back после apply.

## 7. Acceptance

Эта часть Gate F считается закрытой только если доказано, что:

1. fresh environment получает managed `opencode_permissions` checkout и согласованный permission artifact без ручной сборки частей из разных repos;
2. existing current checkout является no-op;
3. outdated clean managed checkout безопасно обновляется согласно принятой version policy;
4. local changes/local commits вызывают conflict, а не destructive repair;
5. повторный reconcile идемпотентен;
6. `opencode_setup` не изменяет смысл canonical permission artifact;
7. legacy `agent-safe` permission artifacts не остаются незаметным competing effective writer;
8. unknown/user-owned permission-related artifacts не удаляются вслепую;
9. effective end state проверяется, а успешный exit code сам по себе недостаточен.

## 8. Связь с master plan

Это требование является обязательным уточнением **этапа F — `opencode_setup`** и должно быть включено в итоговую редакцию `cross_project_integration_master_plan_ru.md` и `cross_project_integration_contract_v1_ru.md` перед формальным закрытием Gate A.
