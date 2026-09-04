# Deterministic classifier gate — closure

Статус: **CLOSED** для доказанного Linux / OpenCode 1.18.26 profile.

Этот документ фиксирует closure deterministic classifier stage после DC-0…DC-4. Он не означает запуск auditor stage, не означает production deployment permission policy и не переносит execution-safety функции `agent-safe` в `opencode_permissions`.

## 1. Закрываемый gate

Целевая последовательность проекта:

`native deterministic rules -> deterministic classifier/effect analysis -> optional auditor gray zone -> ASK_USER`

На этом этапе закрывается только deterministic classifier component между native `ASK` и последующим остаточным `ASK_USER`.

Сохраняются обязательные правила:

- native `DENY` терминален и не может быть переопределён;
- native `ALLOW` терминален и не требует classifier;
- classifier работает только с native `ASK`;
- unknown/opaque/unsupported не превращается в `ALLOW`;
- auditor отсутствует и не участвует в решениях;
- production permission configuration этим gate не изменяется.

## 2. Состав closure evidence

### DC-0 — NormalizedOperation identity

Закрыт deterministic identity contract:

- typed pre-normalization;
- canonical JSON representation;
- domain-separated SHA-256 operation identity;
- operation-kind-specific completeness;
- conservative path/object identity semantics;
- identity fixtures SAME / DIFFERENT / NON_COMPARABLE.

`ALLOW` без complete operation identity запрещён.

### DC-1 — classifier core

Закрыт deterministic result/composition core:

- `ALLOW | ASK_USER | DENY` result schema;
- native ALLOW/DENY terminal precedence;
- monotonic composition;
- child DENY доминирует;
- child ASK/uncertainty не может быть скрыт parent-ом;
- effects/targets/result identity должны совпадать с identity core;
- `ALLOW` с unknown effects/targets/uncertainty запрещён.

### DC-2 — bounded analyzers

Закрыты ограниченные deterministic analyzers для доказанных command families.

Ключевой safety result:

- dangerous / system-write / secret / unknown / opaque cases не auto-allow;
- build/test и unknown-code-execution families остаются `ASK_USER`;
- redirects и compound/pipeline effects не скрываются;
- разрешаются только конкретные доказанные read-only/simple families.

### DC-3 — wrappers и remote contract

Закрыты wrapper/remote invariants:

- wrapper label не является approval;
- `agent-safe` не получает права расширять classifier ALLOW;
- self-approval/forged approval semantics не принимаются;
- nested dangerous payload доминирует над wrapper envelope;
- remote host/transfer identity обязателен;
- remote benign payload без достаточной доказанности остаётся ASK;
- transfer/wrapper handling не становится blanket trust boundary.

### DC-4 — exact OpenCode adapter/runtime proof

Закрыта фактическая интеграция с OpenCode 1.18.26 ShellTool/native permission lifecycle.

Доказанный профиль описан в `docs/dc4_exact_opencode_adapter_ru.md`.

Runtime acceptance подтверждает:

- terminal native ALLOW без classifier;
- terminal native DENY без execution;
- real native ASK -> `permission.asked` -> deterministic classifier exact ALLOW -> one-shot reply -> authorization-binding revalidation -> execution;
- post-classification environment/identity drift -> authorization binding invalidated -> fail closed до spawn;
- exact call-ID/command binding;
- exact version-sensitive legacy permission reply path;
- отсутствие `--auto`, broad shell allow и destructive test execution.

## 3. Safety acceptance

Gate закрывается только при нулевых unsafe widening metrics.

Regression suite закрепляет:

- `unsafe_auto_allow = 0`;
- `dangerous_false_safe = 0`;
- `unknown_false_safe = 0`;
- `secret_false_safe = 0`;
- `native_deny_override = 0`;
- `unparsed_auto_allow = 0`;
- `identityless_auto_allow = 0`.

Дополнительно DC-3 tests подтверждают отсутствие blanket wrapper/remote widening и сохранение native DENY precedence.

Эти метрики имеют приоритет над prompt-reduction metric: рост auto-allow не принимается ценой любого safety regression.

## 4. Prompt-capture acceptance

Gate B historical native-policy baseline:

- safe prompts: 11;
- captured by native ALLOW: 6;
- capture rate: `6 / 11 = 54.5%`.

Classifier sound projection использует собственный зафиксированный набор; знаменатели не смешиваются с Gate B historical corpus:

- safe projection cases: 13;
- safe combined `ALLOW`: 9;
- capture rate: `9 / 13 = 69.2%`.

Следовательно:

`69.2% > 54.5%`.

Это не утверждение, что historical 11-case Gate B corpus был переписан. Это acceptance comparison двух явно разных фиксированных наборов с одинаковым смыслом метрики — долей безопасных случаев, для которых пользовательский prompt снимается без safety violation.

Regression test требует одновременно точного `(9, 13)` и строгого превышения `6/11`.

## 5. Runtime acceptance profile

Closure runtime evidence относится только к:

- Linux;
- OpenCode exact 1.18.26;
- official Linux x64 release artifact с pinned SHA-256;
- strict `/bin/dash` static adapter subset;
- фактически доказанному `/usr/bin/printf` execution family в DC-4 runtime fixture.

Classifier implementation шире этой одной runtime command family за счёт DC-0…DC-3 deterministic tests, однако production deployability любой дополнительной family должна следовать собственному version/profile/target contract и не выводится автоматически из DC-4 `printf` proof.

## 6. Граница ответственности с `agent-safe`

DC-4 выполняет pre-execution проверку только в той мере, в какой она необходима для **валидности authorization binding**:

> фактическая операция, которая сейчас продолжает execution path, должна совпадать с операцией, которой `opencode_permissions` разрешил выполнение.

Поэтому `opencode_permissions` может повторно проверить command, operation identity и те shell/executable/cwd/environment dependencies, которые входят в доказанный authorization contract. Если они изменились, прежний `ALLOW` инвалидируется.

Это не даёт `opencode_permissions` ownership над общим безопасным исполнением уже разрешённой mutation.

Owner `agent-safe` остаётся для:

- runtime execution-safety preconditions после authorization;
- temporary/normal/protected resource semantics;
- trash/retention/permanent-delete lifecycle;
- smallest safe mutation;
- журналирования фактического действия;
- post-mutation expected-state verification;
- runtime reject по safety preconditions;
- recovery/incident handling после partial, unexpected или unknown result.

Практическое правило разделения:

```text
opencode_permissions:
  «Это действие можно разрешить, и фактическая операция всё ещё совпадает с разрешённой?»

agent-safe:
  «Как выполнить уже разрешённое state-changing действие безопасно, проверить результат и восстановиться при проблеме?»
```

Ни DC-4 adapter, ни будущий auditor не должны реализовывать resource lifecycle или recovery вместо `agent-safe`.

## 7. Version-sensitive boundaries

Closure не переносится автоматически на другую OpenCode version.

При изменении runtime version требуется как минимум:

1. exact version selection без nearest-version fallback;
2. повторная проверка критических permission/ShellTool/plugin SDK fingerprints;
3. targeted source audit изменившихся primitives;
4. runtime revalidation соответствующего adapter profile;
5. fail closed при отсутствии доказанного profile.

Semver similarity сама по себе не является evidence.

## 8. Explicit non-claims

Closure deterministic classifier gate **не означает**:

- что production permission policy уже включает classifier adapter;
- что arbitrary shell command можно разрешать автоматически;
- что shell parser общего назначения доказан;
- что Windows classifier runtime path доказан;
- что OpenCode future versions совместимы;
- что model/auditor получает право исполнения;
- что auditor stage начат;
- что остаточные ASK-зоны должны автоматически исчезнуть;
- что temporary/trash/delete/verify/recovery semantics принадлежат `opencode_permissions`;
- что runtime responsibilities `agent-safe`, `opencode_setup` или `ssh_relay` переносятся в этот repository.

## 9. Gate checklist

| Criterion | Status |
|---|---|
| DC-0 identity implementation | PASS |
| Versioned deterministic parser/effect inputs for supported analyzers | PASS |
| Native -> classifier composition semantics | PASS |
| Unsafe auto-allow metrics = 0 | PASS |
| Every classifier ALLOW has complete effects/targets/operation identity | PASS |
| Compound/pipeline/nested danger cannot be hidden | PASS |
| Wrapper/remote handling does not create blanket trust | PASS |
| Unsupported/opaque input fails closed to ASK | PASS |
| Safe prompt capture exceeds Gate B 54.5% baseline | PASS — 69.2% |
| Exact Linux/OpenCode 1.18.26 non-destructive authorization-binding integration | PASS |
| `agent-safe` execution-safety ownership preserved | PASS |
| Auditor absent from execution/approval path | PASS |
| Production permission config unchanged | PASS |

## 10. Closure decision

**Deterministic classifier gate CLOSED for the proven Linux/OpenCode 1.18.26 profile.**

Следующий roadmap stage может проектировать optional auditor только для gray zone, сохраняя архитектуру:

`native deterministic rules -> deterministic classifier -> optional auditor -> ASK_USER`.

Auditor не может:

- отменять native/classifier hard DENY;
- создавать execution capability;
- превращать unknown в ALLOW без отдельного технически доказанного contract;
- подменять operation identity, target/effect binding или authorization-binding revalidation;
- брать на себя resource lifecycle, execution verification или recovery функции `agent-safe`.

До отдельного deployment gate production permission policy остаётся без изменений.
