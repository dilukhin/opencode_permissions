# Rolling compatibility для часто обновляемого OpenCode

Статус: **IMPLEMENTED / 1.18.29 LINUX RUNTIME_REVALIDATED**.

## 1. Проблема

OpenCode выпускает patch-релизы часто. Проект не должен требовать полного ручного повторения Stage 0/Gate B/DC-4 после каждого обновления, если permission/runtime contract фактически не изменился.

Одновременно нельзя считать новую версию совместимой только по semver (`1.18.x`) или выбирать ближайший старый профиль.

Поэтому используются два разных понятия:

```text
exact version
  -> определяет, какой artifact можно запускать

compatibility family
  -> определяет, можно ли быстро переиспользовать уже доказанный source contract
```

## 2. Инвариант deployment

Для реального запуска всегда действует:

```text
installed exact version
== profile exact version
== artifact exact version
```

Новая неизвестная версия не получает старый artifact автоматически.

```text
unknown version -> UNVALIDATED_OPENCODE_VERSION
nearest-version fallback -> forbidden
semver-only trust -> forbidden
```

## 3. Critical fingerprint family

Compatibility family задаётся полным набором authorization-relevant upstream файлов.

Текущий набор содержит 16 fingerprints:

- permission service;
- tool context;
- ShellTool;
- permission HTTP и authorization middleware;
- wildcard matcher;
- shell permission id;
- read/glob/grep/write/apply_patch/external-directory tools;
- tool registry;
- run command;
- plugin tool contract.

Machine-readable source списка:

```text
tests/compatibility/registry.json -> critical_fingerprint_keys
```

Family ID вычисляется детерминированно из ordered `(key, path, blob)` rows и не содержит номер версии OpenCode.

## 4. Fast path новой версии

Для нового exact release:

```text
1. определить exact version/tag/commit
2. собрать все critical fingerprints
3. сравнить с последним runtime-revalidated baseline family

all identical
  -> SOURCE_EQUIVALENT
  -> полный source re-audit не нужен

changed/missing fingerprint
  -> TARGETED_REAUDIT_REQUIRED
  -> вывести exact changed/missing component list
  -> пересмотреть только затронутые contracts
```

Missing fingerprint также fail-closed и не считается совместимостью.

## 5. Runtime promotion

`SOURCE_EQUIVALENT` недостаточно для production deployment.

Новый exact binary обязан пройти фиксированный non-destructive runtime proof:

- exact binary version check;
- native ALLOW terminal path;
- native DENY terminal path;
- native ASK -> deterministic continuation;
- authorization-binding revalidation;
- fail-closed drift case.

Только после PASS версия может получить:

```text
linux: RUNTIME_REVALIDATED
overall: DEPLOYABLE
```

и exact-version permission artifact.

Исторический DC-4 proof остаётся pinned к версии, на которой был закрыт. Rolling wrapper переиспользует его non-destructive scenario contract на exact current target и сам проверяет ожидаемую версию.

## 6. Current target

Registry содержит `current_target` — exact версию, на которой normal CI выполняет runtime proof.

`.github/workflows/ci.yml` не содержит вручную закреплённый номер OpenCode. Он читает:

```text
current_target
release asset name
official release SHA-256
```

из machine-readable compatibility profile.

При частом обновлении OpenCode меняется target/profile, а runtime workflow остаётся тем же.

## 7. Исторические версии

Исторические runtime-revalidated profiles остаются evidence и regression data, но normal CI не обязан скачивать и запускать все прошлые версии на каждом PR.

Их contract проверяется статическими unit tests.

Это предотвращает рост CI стоимости пропорционально числу релизов.

## 8. Drift path

Если новая версия меняет один или несколько fingerprints:

```text
changed_fingerprints = [shell_tool, ...]
```

это не означает автоматически несовместимость всей версии.

Нужно:

1. прочитать exact diff/source только этих компонентов и связанных tests;
2. определить, изменился ли наш permission contract;
3. если contract эквивалентен — принять новый family fingerprint set;
4. если contract изменился — обновить соответствующий adapter/policy/test;
5. прогнать runtime proof.

Таким образом новый release не переоткрывает закрытые архитектурные решения без конкретной причины.

## 9. Installed-version behavior

Managed integration (`agent-toolchain`) должна перед использованием permission/classifier artifact определить фактический `opencode --version`.

Если exact profile отсутствует или не deployable:

```text
classifier pilot -> disabled / compatibility conflict
stale exact-version artifact -> not installed/activated
```

Нельзя тихо продолжать работу со старым classifier artifact после обновления OpenCode.

Это operational fail-closed, а не требование откатывать OpenCode.

## 10. Частота обновлений

Обычный happy path для нового patch release должен состоять из:

```text
fingerprint collection
+ family comparison
+ official asset digest binding
+ one fixed runtime proof
+ exact profile/artifact promotion
```

а не из повторения всего исследования проекта.

Целевой результат: если authorization-relevant source не менялся, переход на новую patch-версию является короткой maintenance operation.

## 11. Что намеренно не добавляется

Rolling compatibility не требует:

- semver ranges;
- nearest fallback;
- подписей собственной инфраструктуры;
- daemon/broker;
- запуска всех исторических binaries на каждом CI;
- блокировки обновлений OpenCode пользователю;
- отдельной semantic policy для каждого patch, если semantic source одинаков.

Exact profiles/artifacts остаются отдельными, compatibility family позволяет только переиспользовать доказательства.

## 12. Текущий пример: 1.18.29

OpenCode 1.18.29 сравнен с runtime-revalidated baseline 1.18.26.

Source comparison:

```text
critical fingerprints matched: 16 / 16
changed: 0
result: SOURCE_EQUIVALENT
```

Exact official Linux x64 release artifact затем прошёл rolling runtime proof:

```text
native ALLOW terminal                 PASS
native DENY terminal                  PASS
ASK -> classifier -> once             PASS
authorization-binding revalidation    PASS
declared environment drift fail-close PASS
```

После этого выпущен отдельный exact-version Linux permission artifact и профиль 1.18.29 получил `RUNTIME_REVALIDATED / DEPLOYABLE` для Linux.

Windows для 1.18.29 остаётся source-revalidated only и не входит в `deployable_platforms`.
