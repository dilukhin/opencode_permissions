# Minimal managed pilot — design и acceptance

Статус: **DESIGN / NO LIVE DEPLOYMENT**.

Этот pilot нужен до auditor stage. Его задача — подключить уже доказанные native + deterministic механизмы в ограниченном managed environment и измерить реальные остаточные `ASK_USER`.

Pilot не должен одновременно становиться тестом workspace trust, `agent-safe` controlled mutations, broker-а и auditor-а.

## 1. Цель

Проверить в обычной разработке три практических вопроса:

1. сколько prompts снимает уже готовая deterministic архитектура;
2. какие реальные причины остаются у `ASK_USER`;
3. оправдан ли следующий сложный компонент вообще.

Главный результат pilot — **измерение**, а не максимальная автономность.

## 2. P0 scope

P0 ограничен:

- Linux;
- exact OpenCode 1.18.26;
- canonical native policy Gate B;
- deterministic classifier только для уже доказанных safe/read-only families;
- hard DENY без изменений;
- unsupported/opaque -> ASK;
- никаких trust-conditioned build/test ALLOW;
- никаких classifier-controlled state-changing mutations;
- никакого auditor;
- никакого kernel broker;
- `agent-safe` runtime semantics не меняются.

P0 должен быть пригоден для отключения без восстановления данных: он меняет только managed OpenCode authorization artifacts/plugin, а не пользовательские project files.

## 3. Почему P0 идёт раньше workspace trust

Issue `agent-toolchain#45` реализует persistent workspace trust producer отдельно.

P0 не должен ждать его, потому что:

- текущий deterministic classifier уже закрыт и даёт измеримый prompt reduction;
- build/test prompts — как раз полезная часть residual-ASK baseline;
- после P0 можно измерить реальную цену отсутствия trusted-workspace policy;
- P1 сможет показать incremental benefit workspace trust отдельно.

Таким образом:

```text
P0 = current proven deterministic layer
P1 = P0 + trusted workspace development scopes
```

## 4. Native component

P0 использует уже существующий canonical semantic source:

```text
policy/native/rules.v1.json
```

и platform-scoped generated artifact для Linux/OpenCode 1.18.26.

`agent-toolchain` deploy/reconcile не имеет права semantic-rewrite native policy.

Effective read-back после installation обязателен.

## 5. Deterministic component

P0 требует production-shaped adapter bundle, но не новый classifier design.

Bundle должен использовать существующие canonical modules:

```text
tools/normalized_operation_identity.py
tools/classifier_core.py
tools/classifier_analyzers.py
tools/classifier_wrappers.py
tools/workspace_trust.py   # available to consumer, P0 trust lookup disabled/no fact
```

DC-4 proof plugin **не копируется как production plugin без review**: его mock/scenario/trace code является test fixture.

Нужен минимальный production bridge, который делает только:

```text
tool.execute.before
  -> bind callID + exact args

permission.asked for native ASK
  -> deterministic adapter
  -> ALLOW => reply once
  -> ASK_USER => не подменять user decision / оставить normal ASK path
  -> DENY => reject

shell.env / pre-execution hook
  -> authorization-binding revalidation only when classifier issued ALLOW
```

Bridge не исполняет mutation сам и не становится вторым PDP.

## 6. OpenCode plugin placement

Exact OpenCode 1.18.26 официально поддерживает global local plugins в:

```text
~/.config/opencode/plugins/
```

и загружает их автоматически.

P0 использует **managed global plugin**, а не project-local `.opencode/plugins/`, потому что:

- project workspace не должен быть owner authorization plugin;
- model-controlled project edits не должны менять effective authorization implementation;
- один managed installation должен работать одинаково в пилотных workspaces.

Ownership/deployment plugin-файла принадлежит `agent-toolchain`.

## 7. Bundle location

Runtime code не должен зависеть от developer checkout `~/projects/...`.

Предпочтительная схема:

```text
agent-toolchain managed data/runtime
  opencode_permissions/<artifact-id>/...

~/.config/opencode/plugins/
  opencode-permissions.js   # small managed bridge/loader
```

Loader ссылается только на managed immutable/pinned bundle.

Конкретный absolute data root определяет `agent-toolchain`.

P0 запрещает:

- importing classifier из текущего developer checkout;
- mutable `main` checkout как production runtime;
- npm registry dependency только ради plugin;
- project-local copy plugin-а.

## 8. Pilot artifact contract

Перед deployment `opencode_permissions` должен выпустить content-bound pilot artifact, минимум:

```yaml
schema: opencode-permissions-pilot-artifact/v1
platform: linux
opencode_version: 1.18.26
native_policy_artifact_id: sha256:...
classifier_profile: ...
files:
  bridge_js: <sha256>
  runtime_files: [...sha256...]
constraints:
  exact_version_only: true
  auditor_enabled: false
  workspace_trust_enabled: false
```

Artifact identity зависит от exact content всех runtime файлов и relevant profile contract.

`agent-toolchain` только устанавливает artifact; semantic contents принадлежат `opencode_permissions`.

## 9. P0 ALLOW surface

Pilot не должен автоматически использовать весь synthetic classifier universe.

В P0 входят только families, для которых есть одновременно:

1. deterministic analyzer regression;
2. paired dangerous/unknown negatives;
3. production adapter representation;
4. exact runtime binding, достаточный для family;
5. отсутствие state-changing effects.

Initial target families:

- narrow read-only `find ... -print`;
- single-file non-secret grep/search;
- hardened read-only Git inspection;
- pure compound/pipeline только из P0-proven children;
- уже native-safe direct operations остаются native-owned.

Build/test остаются ASK в P0.

## 10. Executable identity после simplicity audit

P0 не обязан повторять high-assurance DC-4 full-content hashing для каждого системного executable.

Минимальный production profile должен доказать достаточную substitution protection, но exact choice фиксируется отдельным P0 implementation review.

Default direction:

- absolute/resolved executable from known system boundary;
- basic object identity where needed;
- no repeated full content hash unless family/profile requires it.

Это не меняет DC-4 proof; оно определяет production pilot contract.

## 11. Environment dependencies

P0 следует `dc4_environment_dependency_reconciliation_ru.md`:

- никакого full `process.env` snapshot;
- только declared authorization-relevant dependencies;
- unexpected plugin-provided execution transform, не входящий в profile contract, invalidates classifier ALLOW.

Secret-like env values не логируются.

## 12. Metrics

Pilot собирает только минимальные privacy-safe counters/events.

Нужно знать:

```text
native_allow
native_deny
native_ask
classifier_allow
classifier_deny
residual_ask
classifier_error/fail_closed
reason_code / family
opencode version
policy/artifact profile
```

Не собирать по умолчанию:

- raw command;
- file contents;
- secret values;
- environment dump;
- arbitrary target paths, если family/reason можно посчитать без них.

Для диагностики конкретного false block пользователь может отдельно включить targeted evidence capture с redaction.

## 13. Pilot success metrics

P0 считается полезным, если одновременно:

- unsafe automatic allow = 0;
- hard DENY override = 0;
- classifier errors fail closed;
- measurable residual ASK dataset получен;
- фактическая доля routine prompts ниже native-only pilot baseline;
- нет регулярной необходимости открывать raw command только для понимания prompt;
- operational overhead plugin/runtime не создаёт сопоставимого числа новых сбоев.

Не задавать заранее искусственную цель вроде «90% ALLOW». Решение auditor/trusted-workspace должно исходить из наблюдаемой структуры residual ASK.

## 14. Rollback / disable

Pilot должен иметь managed reversible switch:

```text
pilot enabled
  -> native artifact + classifier plugin active

pilot disabled
  -> classifier plugin removed/disabled by owner-aware reconciliation
  -> canonical native policy остаётся либо восстанавливается
```

Unknown/modified user plugin/config не удаляется blind action.

Rollback не должен требовать `git reset`, `clean`, ручного удаления project files или `agent-safe` recovery.

## 15. `agent-safe` boundary

P0 не добавляет controlled mutation path.

Если operation state-changing:

- current native/classifier policy остаётся ASK/DENY согласно существующим rules;
- P0 не пытается самостоятельно execute/verify/recover;
- будущий controlled path интегрируется отдельно с `agent-safe`.

Это сознательно уменьшает scope первого pilot.

## 16. P1 workspace trust

После реализации/acceptance `agent-toolchain#45` P1 может добавить:

```text
trusted workspace fact
+ scope build/test/static_check/git_read
+ paired classifier policy
```

P1 должен измеряться отдельно от P0, чтобы видеть реальный incremental prompt reduction.

## 17. Auditor gate

Auditor остаётся **DEFERRED**.

После P0/P1 анализируются residual ASK categories:

```text
fixable native rule
fixable deterministic analyzer
trusted-workspace candidate
intent/context ambiguity
truly semantic gray zone
unsupported platform/version
```

Auditor проектируется только для последней значимой категории, если она действительно остаётся существенной.

## 18. Implementation slices

### MP-0 artifact/runtime bundle

- production bridge без test/mock code;
- content-bound artifact manifest;
- P0 family allowlist;
- no developer-checkout dependency.

### MP-1 synthetic managed deployment

В `agent-toolchain` temp HOME/state/config fixture:

- install artifact;
- effective read-back;
- repeated apply no-op;
- disable/rollback;
- modified/unknown plugin conflict.

### MP-2 disposable exact OpenCode integration

Exact 1.18.26 official binary:

- native ALLOW;
- native DENY;
- P0 classifier ALLOW family;
- residual ASK family;
- classifier failure fail-closed;
- no auditor.

### MP-3 user opt-in pilot

Только после MP-0..MP-2 PASS.

Это первый этап, который меняет реальную пользовательскую managed OpenCode environment.

## 19. Stop conditions

Не переходить к live pilot, если:

- нужен broad `bash: allow`;
- plugin должен доверять project-local code/config;
- runtime требует developer checkout;
- setup semantic-rewrites classifier/policy;
- fail-closed classifier error превращается в execution;
- unknown plugin ownership нужно destructive overwrite;
- deployment требует broker/high-assurance machinery без нового evidence;
- state-changing execution начинает дублировать `agent-safe`.

## 20. Следующий шаг

До помощи пользователя можно выполнить MP-0 и MP-1 design/implementation в GitHub.

Помощь пользователя потребуется только перед MP-3 — реальным opt-in применением pilot к его OpenCode environment.
