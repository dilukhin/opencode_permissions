# Minimal managed pilot — design и acceptance

Статус: **DESIGN / NO LIVE DEPLOYMENT**.

Pilot нужен до auditor stage. Его задача — подключить уже доказанные native + deterministic механизмы в ограниченном managed environment и измерить реальные остаточные `ASK_USER`.

Pilot не должен одновременно становиться тестом workspace trust, `agent-safe` controlled mutations, broker-а и auditor-а.

## 1. Цель

Проверить в обычной разработке:

1. сколько prompts снимает уже готовая deterministic архитектура;
2. какие реальные причины остаются у `ASK_USER`;
3. оправдан ли следующий сложный компонент вообще.

Главный результат pilot — **измерение**, а не максимальная автономность.

## 2. Version contract

P0 **не привязан навечно к конкретной patch-версии OpenCode**.

Он работает только с exact текущим Linux target, который в rolling compatibility registry имеет одновременно:

```text
exact profile
+ source/fingerprint validation
+ RUNTIME_REVALIDATED
+ exact-version permission artifact
+ deployable_platforms contains linux
```

Machine-readable owner target:

```text
tests/compatibility/registry.json -> current_target
```

Lifecycle обновлений:

```text
docs/rolling_opencode_compatibility_ru.md
```

Если установленный OpenCode обновился раньше validation новой версии, pilot не использует stale artifact и должен fail closed/disable classifier до revalidation. Откат OpenCode пользователю не требуется.

## 3. P0 scope

P0 ограничен:

- Linux;
- exact current runtime-revalidated OpenCode target;
- canonical native policy Gate B;
- deterministic classifier только для явно включённых P0 read-only families;
- hard DENY без изменений;
- unsupported/opaque -> ASK;
- никаких trust-conditioned build/test ALLOW;
- никаких classifier-controlled state-changing mutations;
- никакого auditor;
- никакого kernel broker;
- `agent-safe` runtime semantics не меняются.

P0 должен отключаться без восстановления project data: он меняет только managed OpenCode authorization artifacts/plugin.

## 4. Почему P0 идёт раньше workspace trust

Issue `agent-toolchain#45` реализует persistent workspace trust producer отдельно.

P0 не должен ждать его:

```text
P0 = current proven deterministic layer
P1 = P0 + trusted workspace development scopes
```

Build/test prompts в P0 являются полезной частью residual-ASK baseline.

## 5. Native component

Canonical semantic source:

```text
policy/native/rules.v1.json
```

P0 выбирает generated artifact **точно для current target/version/platform** через compatibility profile.

`agent-toolchain` deploy/reconcile не имеет права semantic-rewrite native policy. Effective read-back после installation обязателен.

## 6. Deterministic component

P0 требует production-shaped adapter bundle, но не новый classifier design.

Canonical modules остаются единственным источником classifier logic:

```text
tools/normalized_operation_identity.py
tools/classifier_core.py
tools/classifier_analyzers.py
tools/classifier_wrappers.py
tools/workspace_trust.py
```

DC-4 proof plugin не копируется как production plugin: mock/scenario/trace code является test fixture.

Минимальный production bridge:

```text
tool.execute.before
  -> bind callID + exact args

permission.asked after native ASK
  -> deterministic adapter
  -> ALLOW => reply once
  -> ASK_USER => оставить normal user decision path
  -> DENY => reject

shell.env / pre-execution hook
  -> authorization-binding revalidation only for classifier ALLOW
```

Bridge не исполняет mutation сам и не становится вторым PDP.

## 7. OpenCode plugin placement

Placement/plugin lifecycle считается version-sensitive contract и должен быть подтверждён current compatibility family.

Для доказанного family используется managed global local plugin, а не project-local `.opencode/plugins/`:

```text
~/.config/opencode/plugins/
```

Причины:

- project workspace не owner authorization plugin;
- model-controlled project edits не должны менять effective authorization implementation;
- одна managed installation должна работать одинаково в пилотных workspaces.

Ownership/deployment принадлежит `agent-toolchain`.

## 8. Bundle location

Runtime не зависит от developer checkout.

Предпочтительная схема:

```text
agent-toolchain managed data/runtime
  opencode_permissions/<artifact-id>/...

~/.config/opencode/plugins/
  opencode-permissions.js
```

Loader ссылается только на managed content-bound bundle.

Запрещены:

- import из mutable developer checkout;
- mutable `main` как production runtime;
- project-local authorization plugin;
- npm registry dependency только ради bridge.

## 9. Pilot artifact contract

Перед deployment выпускается content-bound pilot artifact, минимум:

```yaml
schema: opencode-permissions-pilot-artifact/v1
platform: linux
opencode_version: <exact current target>
native_policy_artifact_id: sha256:...
compatibility_profile_id: ...
classifier_profile: ...
files:
  bridge_js: <sha256>
  runtime_files: [...sha256...]
constraints:
  exact_version_only: true
  auditor_enabled: false
  workspace_trust_enabled: false
```

Artifact identity зависит от exact runtime content и exact compatibility profile. `agent-toolchain` только устанавливает artifact; semantic contents принадлежат `opencode_permissions`.

## 10. P0 ALLOW surface

P0 не обязан автоматически использовать весь synthetic classifier universe.

Для первой production-shaped итерации принят минимальный новый classifier family:

```text
single-file grep/search
  + static bounded command representation
  + one existing non-secret file inside workspace
  + read-only effect
```

Не входят в первый P0 classifier ALLOW:

- `find`;
- pipelines/compound shell;
- expanded Git inspection;
- build/test/static check;
- writes/state-changing actions.

Native-safe direct operations остаются native-owned.

Git расширяется только отдельным решением F5/P1 с техническим workspace/repository trust context; P0 не компенсирует Git config execution surface дополнительной кучей shell/env hacks.

## 11. Executable и environment binding

После simplicity audit P0 не повторяет high-assurance full-content hashing каждого системного executable по умолчанию.

Минимальный production profile использует только authorization-relevant dependencies конкретной family.

Для environment действует:

- никакого full `process.env` snapshot;
- только declared dependencies;
- secret-like values не логируются;
- unexpected execution transform invalidates classifier ALLOW.

## 12. Metrics

Pilot собирает минимальные privacy-safe counters/events:

```text
native_allow
native_deny
native_ask
classifier_allow
classifier_deny
residual_ask
classifier_error/fail_closed
reason_code / family
opencode_version
compatibility_profile
policy/pilot artifact profile
```

По умолчанию не собираются:

- raw command;
- file contents;
- secret values;
- environment dump;
- произвольные target paths, если reason/family можно посчитать без них.

Targeted redacted evidence включается отдельно только для диагностики конкретной проблемы.

## 13. Success criteria

P0 полезен, если одновременно:

- unsafe automatic allow = 0;
- hard DENY override = 0;
- classifier errors fail closed;
- получен measurable residual ASK dataset;
- routine prompts меньше native-only baseline;
- operational overhead не создаёт сопоставимого числа новых сбоев.

Искусственная цель вроде `90% ALLOW` заранее не задаётся.

## 14. Rollback / disable

Pilot имеет managed reversible switch:

```text
pilot enabled
  -> exact native artifact + exact classifier plugin active

pilot disabled
  -> classifier plugin removed/disabled owner-aware
  -> canonical native policy сохраняется либо восстанавливается
```

Unknown/modified user plugin/config не удаляется blind action.

Rollback не требует `git reset`, `clean`, удаления project files или `agent-safe` recovery.

## 15. `agent-safe` boundary

P0 не добавляет controlled mutation path.

State-changing operation остаётся ASK/DENY согласно текущей policy. P0 не execute/verify/recover её самостоятельно.

Будущий controlled mutation path интегрируется отдельно с `agent-safe`.

## 16. P1 workspace trust

После реализации/acceptance `agent-toolchain#45` P1 может добавить:

```text
trusted workspace fact
+ scope build/test/static_check/git_read
+ paired classifier policy
```

P1 измеряется отдельно от P0.

## 17. Auditor gate

Auditor остаётся **DEFERRED**.

После P0/P1 residual ASK классифицируются как:

```text
fixable native rule
fixable deterministic analyzer
trusted-workspace candidate
intent/context ambiguity
truly semantic gray zone
unsupported platform/version
```

Auditor проектируется только для реально значимой semantic gray zone.

## 18. Implementation slices

### MP-0 artifact/runtime bundle

- production bridge без test/mock code;
- content-bound artifact manifest;
- минимальный P0 family allowlist;
- no developer-checkout dependency;
- exact current compatibility target.

### MP-1 synthetic managed deployment

В `agent-toolchain` temp HOME/state/config fixture:

- install exact artifact;
- effective read-back;
- repeated apply no-op;
- disable/rollback;
- modified/unknown plugin conflict;
- installed-version mismatch fail closed.

### MP-2 disposable exact OpenCode integration

Используется **current runtime-revalidated official binary из compatibility registry**, а не навсегда закреплённый номер версии.

Проверяются:

- native ALLOW;
- native DENY;
- P0 classifier ALLOW family;
- residual ASK family;
- classifier failure fail-closed;
- no auditor.

### MP-3 user opt-in pilot

Только после MP-0..MP-2 PASS. Это первый этап, который меняет реальную пользовательскую managed OpenCode environment.

## 19. Stop conditions

Не переходить к live pilot, если:

- установленная версия не имеет exact deployable compatibility profile/artifact;
- нужен broad `bash: allow`;
- plugin доверяет project-local code/config;
- runtime требует developer checkout;
- setup semantic-rewrites classifier/policy;
- classifier error превращается в execution;
- unknown plugin ownership требует destructive overwrite;
- deployment требует broker/high-assurance machinery без evidence;
- state-changing execution дублирует `agent-safe`.

## 20. Следующий шаг

До помощи пользователя выполняются MP-0, MP-1 и MP-2 в GitHub/disposable fixtures.

Помощь пользователя нужна только перед MP-3 — реальным opt-in применением pilot к установленной, exact compatibility-validated версии OpenCode.
