# MP-0 — коррекция runtime version binding, найденная MP-2

Статус: **SOURCE CORRECTION / MP-2 BLOCKED UNTIL MERGE**.

## Причина

Первый disposable MP-2 run на официальном OpenCode 1.18.29 обнаружил, что native ASK возникает корректно, но production P0 bridge не отвечает `ALLOW` для разрешённой `grep.single_nonsecret_workspace_file` family.

Причина подтверждена по exact upstream source OpenCode 1.18.29:

- plugin получает v1 SDK client;
- у `client.global` в этом SDK есть `event()`, но нет `health()`;
- прежний bridge вызывал `client.global.health()`;
- исключение преобразовывалось в `null`, поэтому `exactRuntimeReady()` всегда возвращал `false`.

Старый pilot artifact:

`sha256:fe0587a7c2dea7756bc1e697aa17a79f0c52be45bd55ac145efd7b473badce42`

сохраняется как исторический immutable artifact, но **не должен использоваться для deployment**.

## Коррекция

Runtime version binding больше не зависит от отсутствующего SDK method.

Bridge один раз запускает текущий executable:

```text
process.execPath --version
```

и сравнивает stdout с `manifest.target.exact_version`.

Свойства:

- используется exact текущий executable процесса OpenCode;
- дочернему процессу передаётся пустой environment;
- сеть и HTTP authorization не требуются;
- никакие secret-like значения не читаются и не копируются;
- ошибка запуска, timeout, non-zero exit или version mismatch дают fail-closed и не превращаются в classifier ALLOW;
- native ALLOW/DENY semantics не меняются.

Exact OpenCode 1.18.29 CLI обрабатывает `--version` через встроенный `InstallationVersion`, поэтому эта проверка не требует запуска пользовательской команды или permission flow.

## Новый content-bound artifact

Текущий source plan после коррекции:

```text
pilot:
  sha256:ce1ae9aedcb65e2e62c4ee38f21d0d535b58338816bd273ad090bc76cc64a9d2
native:
  sha256:b38090e07008fb174607aa2a924cfef1dd26d03bdb339a379b1a770397a8ad84
OpenCode:
  1.18.29
```

Новый artifact создаётся как отдельный immutable directory. Старый artifact не переписывается.

## Regression guard

`tests/test_p0_pilot_artifact.py` теперь запрещает `client.global.health()` и требует:

- `spawnSync(process.execPath, ["--version"]`;
- пустой child environment;
- сравнение результата с exact version из manifest.

Полный runtime acceptance этой коррекции выполняется не synthetic assertion, а MP-2 disposable integration на официальном binary.

## Gate semantics

До source CI + merge этой коррекции MP-0 считается reopened для данного defect, а MP-2 — blocked.

После source merge MP-2 должен быть перезапущен с новым artifact. Только реальный PASS production bridge на официальном exact binary закрывает найденный integration gap.
