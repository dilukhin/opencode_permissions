# Граница ответственности `opencode_permissions` и `agent-safe`

Статус: **ACCEPTED ARCHITECTURE BOUNDARY**.

Этот документ является компактным нормативным описанием границы между двумя проектами. Подробные межпроектные интерфейсы остаются в `cross_project_integration_contract_v1_ru.md`, но при расхождении трактовок правило ownership из этого документа имеет приоритет для разработки `opencode_permissions`.

## 1. Короткое правило

`opencode_permissions` отвечает на вопрос:

> **Можно ли разрешить именно эту предполагаемую операцию?**

`agent-safe` отвечает на вопрос:

> **Как безопасно выполнить уже разрешённое изменение состояния, проверить результат и восстановиться при проблеме?**

В форме pipeline:

```text
proposal
  -> opencode_permissions: ALLOW / ASK_USER / DENY
  -> authorization binding
  -> agent-safe: preconditions / smallest mutation / verify / recovery
  -> actual system
```

`agent-safe` может сузить разрешение runtime-отказом, но не может повысить `ASK_USER`/`DENY` до `ALLOW`.

## 2. Каноническая ответственность `opencode_permissions`

Проект владеет:

- native permission policy;
- `ALLOW / ASK_USER / DENY`;
- hard-deny rules;
- разбором command/payload structure в объёме, необходимом для authorization;
- определением предполагаемых target/effects;
- обнаружением nested/compound/wrapper/remote effects;
- secret/external-directory authorization boundaries;
- `NormalizedOperation` и authorization-relevant identity;
- формированием понятного approval context;
- проверкой того, что фактическая операция перед продолжением всё ещё совпадает с разрешённой операцией;
- измерением prompt reduction и unsafe automatic allow.

Последний пункт — **authorization-binding revalidation**, а не общий runtime safety.

## 3. Каноническая ответственность `agent-safe`

`agent-safe` владеет execution safety после authorization, включая:

- runtime-sensitive preconditions уже разрешённого state-changing действия;
- точную работу с фактическим target перед mutation;
- expected state;
- checkpoint/rollback, если применимо;
- smallest safe mutation;
- post-mutation verification;
- receipt/journal фактического действия;
- partial/unknown/unexpected result;
- recovery/incident handling;
- resource lifecycle;
- cleanup;
- trash/retention/permanent delete;
- классы ресурсов наподобие `temporary / normal / protected` и их будущие эквиваленты;
- состояния ресурсов наподобие `present / trashed / deleted` и их будущие эквиваленты.

Конкретные названия lifecycle-классов определяет `agent-safe`; `opencode_permissions` не должен заводить параллельную копию этой модели.

## 4. Что `opencode_permissions` не должен делать

Запрещено добавлять сюда как самостоятельную runtime-функцию:

- safe delete/trash/purge implementation;
- retention policy;
- temporary-data registry;
- resource tombstones;
- recovery journal;
- rollback engine;
- expected-state verification после mutation;
- generic filesystem safety wrapper;
- повторную реализацию `agent-safe` preflight/verify/recovery;
- собственную классификацию `temporary` по эвристике пути (`/tmp`, `build/`, имя файла и т. п.).

Если authorization layer нуждается в факте о lifecycle ресурса, он может **потреблять подтверждённый contextual fact**, но не владеть его lifecycle semantics.

Например:

```text
trusted fact:
  resource_id = R123
  resource_class = temporary
  target = /workspace/build/cache
```

может быть входом policy. Однако вывод:

```text
/path находится в /tmp -> значит temporary -> можно удалить
```

не является допустимым authorization proof.

## 5. Что `agent-safe` не должен делать

В integrated mode `agent-safe` не должен:

- становиться вторым источником `ALLOW / ASK_USER / DENY`;
- считать caller-controlled `--approved` доказательством authorization;
- отменять hard DENY;
- разрешать другую operation вместо разрешённой;
- расширять target/effects;
- писать competing production permission policy.

Standalone/manual compatibility mode может иметь собственный UX, но он должен быть явно отделён от managed integrated path.

## 6. Authorization binding не равно execution safety

`opencode_permissions` вправе перед execution повторно проверить только свойства, необходимые для ответа:

> **Это всё ещё та же операция, которую мы разрешили?**

К таким свойствам могут относиться, если они входят в доказанный профиль:

- exact tool call / call ID;
- command/payload representation;
- target/effects identity;
- cwd/host/channel;
- конкретные execution dependencies, без которых смысл разрешённой операции меняется.

Если эти свойства изменились, прежний authorization больше не применим.

Но вопрос:

> **Безопасно ли сейчас выполнять это уже разрешённое изменение и как проверить результат?**

принадлежит `agent-safe`.

Пример:

```text
opencode_permissions:
  operation = DELETE resource R123
  decision = ALLOW/approved once

agent-safe:
  R123 всё ещё тот же объект?
  допустим ли purge по lifecycle R123?
  какой минимальный action нужен?
  выполнено ли expected state после действия?
  нужен ли recovery?
```

## 7. Правило изменения target/effects

Если execution-safety layer вынужден изменить смысл операции, например:

```text
DELETE A -> DELETE B
UPLOAD host1:path -> host2:path
write file X -> write X and system config Y
```

старое authorization недействительно. Требуется новая нормализованная операция и новое решение `opencode_permissions`.

Без повторной authorization допустимы только внутренние execution-механизмы, которые сохраняют утверждённый target/effects contract, например более безопасная атомарная реализация той же mutation.

## 8. Минимальная межпроектная передача

Интерфейс между проектами должен быть настолько мал, насколько это возможно.

Authorization side передаёт только то, что нужно для безопасного исполнения конкретной разрешённой операции:

```text
operation identity
operation kind
exact target/effects
approval provenance/scope
correlation needed for this operation
```

Execution side возвращает только факты результата, необходимые upstream:

```text
DONE | RUNTIME_REJECT | UNEXPECTED | UNKNOWN
actual/verified state summary
correlation
recovery state, если есть
```

Не следует создавать общий "универсальный safety object", объединяющий policy, resource lifecycle, runtime state, recovery и transport semantics.

## 9. Связанные проекты

- `ssh_relay` владеет transport и remote machine outcome, но не authorization и не execution-safety policy;
- `opencode_setup` устанавливает и reconciles компоненты, но не меняет их semantics;
- contextual knowledge может поставлять facts/provenance, но не выдаёт authorization decisions.

## 10. Критерий нового функционала

Перед добавлением функции в `opencode_permissions` нужно ответить на вопрос:

> Если убрать эту функцию, можем ли мы всё ещё корректно решить `ALLOW / ASK_USER / DENY` и убедиться, что разрешение относится к фактической операции?

Если **да**, а функция нужна только для безопасного выполнения, проверки результата, очистки или восстановления — её owner, скорее всего, `agent-safe`.

Перед добавлением функции в `agent-safe` применяется обратный вопрос:

> Нужна ли эта функция для выбора `ALLOW / ASK_USER / DENY`, а не для выполнения уже разрешённого изменения?

Если **да**, её owner — `opencode_permissions`.

## 11. Инвариант против дублирования

Нельзя повышать надёжность системы созданием двух независимых реализаций одной и той же safety-семантики в соседних проектах.

Предпочтительная модель:

```text
один owner решения
+
минимальный проверяемый interface
+
downstream может только сузить
```

а не:

```text
несколько слоёв независимо пытаются решить одну и ту же задачу безопасности
```
