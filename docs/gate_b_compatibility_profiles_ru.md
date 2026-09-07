# Gate B — exact-version compatibility profiles

Статус: **ACCEPTED / ROLLING EXACT-VERSION LIFECYCLE**.

Machine-readable registry: `tests/compatibility/registry.json`.

Основной lifecycle частых обновлений описан в:

```text
docs/rolling_opencode_compatibility_ru.md
```

## Contract

```text
selection = exact_version_only
nearest_version_fallback = false
unknown version -> UNVALIDATED_OPENCODE_VERSION
deployable selection requires explicit platform
```

Новая версия OpenCode не получает старый deployment artifact по semver или по принципу "ближайшей версии".

## Compatibility family

Чтобы частые patch-релизы не требовали полного повторного аудита, exact profiles сравниваются по полному набору authorization-relevant critical fingerprints.

Если все fingerprints совпадают с runtime-revalidated baseline family:

```text
SOURCE_EQUIVALENT
```

и разрешён короткий путь к runtime revalidation.

Если хотя бы один fingerprint изменился или отсутствует:

```text
TARGETED_REAUDIT_REQUIRED
```

с точным списком изменившихся компонентов.

## Current target

`registry.json` содержит exact `current_target` для normal CI.

CI автоматически читает из его профиля:

- exact version;
- official Linux x64 release asset name;
- official release SHA-256.

Номер версии не hardcode-ится в runtime workflow.

## Profiles

### OpenCode 1.18.18

Historical Stage 0 baseline. Сохраняется как source/fingerprint evidence.

### OpenCode 1.18.26

Historical runtime-revalidated Linux baseline и первый deployable Gate B profile.

### OpenCode 1.18.29

Current target.

Source comparison с 1.18.26:

```text
critical fingerprints: 16 / 16 identical
result: SOURCE_EQUIVALENT
```

После exact official Linux x64 runtime proof:

```text
linux: RUNTIME_REVALIDATED
windows: SOURCE_REVALIDATED
overall: DEPLOYABLE
deployable_platforms: [linux]
```

Для 1.18.29 выпущен отдельный exact-version Linux permission artifact. Он semantic-equivalent 1.18.26 native policy output, но имеет отдельную artifact identity, потому что target exact version/profile являются частью binding.

## Regression acceptance

Tests обязаны доказывать:

- exact profile selection;
- unknown future version fail-closed;
- nearest fallback forbidden;
- полный critical fingerprint family comparison;
- changed/missing fingerprint -> targeted re-audit;
- current target Linux runtime proof на official exact binary;
- current target exact artifact contract;
- historical profiles не становятся обязательными runtime jobs каждого PR;
- profiles не содержат secret material.

## Maintenance rule

При новом OpenCode release сначала выполняется rolling compatibility path, а не полный Stage 0:

```text
exact version/tag/commit
-> critical fingerprint comparison
-> SOURCE_EQUIVALENT или TARGETED_REAUDIT_REQUIRED
-> exact runtime proof
-> exact artifact/profile promotion
```

Полный/расширенный source audit возвращается только при фактическом drift критического contract.
