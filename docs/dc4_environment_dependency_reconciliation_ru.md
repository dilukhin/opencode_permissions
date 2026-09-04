# DC-4 environment dependency reconciliation

Статус: **PASS**.

Этот документ уточняет только environment-binding часть `docs/dc4_exact_opencode_adapter_ru.md` после принятия `docs/default_threat_model_ru.md` и `docs/architecture_simplicity_reconciliation_ru.md`.

Он не меняет native/classifier decisions и не расширяет production ALLOW surface.

## 1. Что признано избыточным

Исходный DC-4 proof сохранял полный snapshot `process.env` и требовал полного равенства перед ShellTool spawn.

Для default threat model это слишком широкий contract:

- большинство env variables не являются authorization input;
- окружение может содержать secret-like values;
- безобидная переменная не должна инвалидировать unrelated authorization;
- production adapter не должен читать всё окружение без доказанной необходимости.

Поэтому broad full-environment binding больше не является рекомендуемым default contract.

## 2. Новый contract

Environment включается в authorization binding только через **явно объявленные dependencies конкретного profile/analyzer**.

Логически:

```yaml
authorization_environment_dependencies:
  - name: ...
    representation: exact|derived|presence
```

Если dependency не объявлена, permission layer не должен читать её значение только ради generic snapshot.

Secret-like values не должны попадать в trace, logs, approval context или `NormalizedOperation` без отдельной необходимости и redaction contract.

## 3. Что проверяет DC-4 fixture

Runtime proof использует одну synthetic declared dependency:

```text
OPENCODE_PERMISSIONS_DC4_AUTHZ_DEP
```

Она нужна только для доказательства механизма:

1. `tool.execute.before` сохраняет значение только объявленной dependency;
2. classifier выдаёт exact ALLOW;
3. fixture изменяет declared dependency до spawn;
4. `shell.env` обнаруживает изменение;
5. authorization binding инвалидируется;
6. sentinel command не исполняется.

При этом plugin больше не перечисляет `Object.entries(process.env)` и не хранит full environment snapshot.

## 4. `shell.env` injection

В доказанном DC-4 profile сохраняется отдельное fail-closed правило:

> после classifier ALLOW proof plugin не допускает неожиданного `output.env` injection через `shell.env` hook.

Это не означает, что production default обязан сравнивать всё process environment.

Это защищает конкретный доказанный continuation path от изменения execution environment другим hook между authorization и spawn.

Если будущая production architecture допускает контролируемые env additions, они должны быть представлены как explicit profile dependencies/transform contract, а не приниматься молча.

## 5. Что остаётся неизменным

F3 reconciliation не ослабляет:

- native DENY precedence;
- native ALLOW passthrough;
- classifier только после native ASK;
- exact call-ID/command correlation;
- operation identity;
- shell/executable/cwd authorization binding;
- unsupported/opaque -> non-ALLOW;
- fail-closed identity drift;
- отсутствие `--auto`/blanket shell allow;
- границу с `agent-safe`.

## 6. Non-claims

Этот proof не утверждает, что synthetic dependency является реальной production dependency `/usr/bin/printf`.

Он доказывает только механизм:

```text
declared authorization dependency changed
-> old authorization invalid
```

Реальные environment dependencies будущих analyzers должны определяться отдельно и минимально.

## 7. Acceptance result

Подтверждено одновременно:

1. source regression запрещает full `process.env` enumeration;
2. declared dependency присутствует явно;
3. exact OpenCode 1.18.26 runtime `classifier_allow` остаётся PASS;
4. declared dependency drift блокирует до spawn;
5. все Linux/Windows regression jobs PASS;
6. production permission policy не меняется.

Этот документ supersedes только broad full-environment-snapshot interpretation DC-4; остальные DC-4 evidence остаются действующими.
