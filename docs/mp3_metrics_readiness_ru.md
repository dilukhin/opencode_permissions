# MP-3 metrics readiness — измерительный контракт P0

Статус: **DESIGN + IMPLEMENTATION CANDIDATE / NO LIVE DEPLOYMENT**.

Этот документ уточняет раздел Metrics в `docs/minimal_managed_pilot_design_ru.md` для текущего exact target OpenCode 1.18.29. До отдельного user opt-in реальная пользовательская OpenCode environment не меняется.

## 1. Причина отдельного readiness slice

MP-3 нужен не только для включения classifier, но и для измерения реального эффекта pilot. Production bridge MP-0/MP-2 до этого не сохранял runtime counters, поэтому live pilot без дополнительного slice дал бы автоматизацию без доказуемого prompt-reduction dataset.

Измерение не должно:

- расширять authorization surface;
- становиться вторым native PDP;
- угадывать решения OpenCode по косвенным признакам;
- сохранять raw command, paths, file contents, env или session identifiers;
- превращать ошибку telemetry в classifier-controlled execution.

## 2. Наблюдаемость exact OpenCode 1.18.29

Для current target подтверждён следующий lifecycle native permission evaluation:

1. native `allow` завершается до `permission.asked`;
2. native `deny` завершается ошибкой до `permission.asked`;
3. `permission.asked` публикуется только когда native evaluation дошёл до ASK;
4. отсутствие `tool.execute.after` нельзя использовать как доказательство native DENY, потому что тот же признак возникает при обычной ошибке tool execution.

Следствие: production plugin для 1.18.29 не имеет однозначного event/hook, по которому можно честно считать live `native_allow` и `native_deny`.

P0 metrics v1 **не дублирует native evaluator** и **не выводит `native_allow/native_deny` эвристически**. Эти категории остаются проверяемыми в controlled MP-2 scenarios, но не входят в live counters v1.

Если будущая exact compatibility family предоставит однозначный hook/event, расширение counters требует отдельного version-sensitive решения и runtime proof.

## 3. Измеряемый ASK-path

Live P0 metrics v1 измеряет только точно наблюдаемый путь:

```text
native_ask
  -> classifier_allow
  -> classifier_deny
  -> residual_ask
  -> classifier_error/fail_closed
  -> binding_reject
```

Counters:

```text
native_ask
classifier_allow
classifier_deny
residual_ask
classifier_error/fail_closed
binding_reject
```

`classifier_error/fail_closed` является диагностическим подмножеством случаев, где classifier не смог безопасно завершить решение. Если после ошибки запрос остаётся пользователю, одновременно увеличивается `residual_ask`, чтобы основной prompt denominator оставался корректным.

`binding_reject` относится к post-approval revalidation/authorization binding failure. Он не считается classifier ALLOW и используется отдельно для operational-overhead оценки.

## 4. Основные метрики pilot

Для одного сопоставимого workload:

```text
prompt_reduction_ratio =
    (native_ask - residual_ask) / native_ask

residual_prompt_ratio =
    residual_ask / native_ask

classifier_allow_ratio =
    classifier_allow / native_ask
```

`prompt_reduction_ratio` нельзя интерпретировать отдельно от `binding_reject` и tool failures: удалённый prompt, после которого execution был fail-closed, не является operational success.

Baseline сравнивается с native-only workload того же класса, а не с искусственно подобранным classifier-friendly corpus.

## 5. Privacy contract

Snapshot содержит только:

- schema/scope;
- exact OpenCode version;
- compatibility profile id;
- native policy artifact id;
- pilot artifact id;
- classifier profile id;
- агрегированные counters;
- bounded reason-code buckets;
- bounded family buckets;
- timestamp последнего обновления.

Не сохраняются:

- raw command;
- argv;
- cwd/workspace path;
- target path;
- file contents;
- environment values;
- secrets;
- session ID;
- call ID;
- prompt/model text.

Reason/family key допускается только после строгой character/length validation. Число bucket keys ограничено 64; overflow агрегируется в `__other__`.

## 6. Storage contract

P0 Linux metrics v1 использует per-process aggregate snapshot:

```text
$HOME/.local/state/opencode_permissions/p0-metrics/<pilot-artifact-segment>/process-<pid>.json
```

Правила:

- storage остаётся внутри real home boundary;
- metrics artifact directory обязан быть реальным directory, не symlink;
- directory mode приводится к `0700`;
- snapshot mode — `0600`;
- запись выполняется через same-directory temporary file + `fsync` + atomic rename;
- разные OpenCode процессы не обновляют один snapshot;
- внутри процесса state разделяется между plugin instances через process-global registry.

P0 v1 намеренно не использует `XDG_STATE_HOME`: внешняя environment-controlled relocation не нужна для authorization telemetry и создала бы лишний путь записи за home boundary.

## 7. Fail-closed semantics

Telemetry не имеет права разрешать действие. Но для classifier ALLOW она является обязательной measurement dependency.

Порядок:

```text
permission.asked
  -> persist native_ask
  -> classifier prepare
  -> reply once only for classifier ALLOW
  -> shell.env authorization-binding revalidation
  -> persist classifier_allow
  -> execution
```

Если первичный `native_ask` denominator не удалось записать, bridge оставляет native ASK пользователю и classifier не пытается автоматически разрешить действие.

Если после успешной authorization revalidation не удалось записать `classifier_allow`, bridge выбрасывает `P0_METRICS_WRITE_FAILED`; classifier-controlled execution не происходит.

Ошибки metrics никогда не отменяют hard DENY. Для DENY/reject-path safety имеет приоритет над полнотой telemetry: отказ записать диагностический counter не превращает DENY в ASK/ALLOW.

## 8. Artifact contract

Metrics contract является частью content-bound classifier profile и поэтому входит в pilot artifact identity через SHA-256 `profile.json` и `bridge.js`.

Profile минимум фиксирует:

```json
{
  "schema": "opencode-permissions-p0-metrics/v1",
  "scope": "ask_path",
  "required_for_classifier_allow": true,
  "storage": "per_process_aggregate_snapshot",
  "state_resolution": "os_homedir_local_state",
  "raw_inputs": false,
  "max_reason_buckets": 64
}
```

Installer `agent-toolchain` не semantic-rewrite этот контракт.

## 9. Acceptance до MP-3 user opt-in

Metrics readiness считается PASS только если одновременно:

1. source profile и committed pilot artifact совпадают через существующий `build_p0_pilot_artifact.py --check`;
2. bridge проходит JavaScript syntax check;
3. repository unit tests подтверждают exact counters, privacy flags, bounded buckets и mandatory classifier-ALLOW write;
4. новый immutable artifact проходит полный `opencode_permissions` CI;
5. `agent-toolchain` disposable MP-2 повторно проходит на новом artifact;
6. MP-2 дополнительно подтверждает, что classifier ALLOW создаёт privacy-safe metrics snapshot и residual ASK увеличивает `residual_ask` без raw inputs;
7. user-facing enable/disable/status/metrics interface остаётся explicit opt-in и не вызывается обычным `toolchainctl apply`.

До выполнения пунктов 1–7 MP-3 live deployment не начинается.

## 10. Stop conditions

Остановить affected path и не включать pilot, если:

- metrics требуют raw command/path/env для основной статистики;
- classifier ALLOW может выполнить команду при failed required write;
- storage выходит за real home boundary или принимает symlinked metrics directory;
- counters требуют повторной реализации native OpenCode permission evaluator;
- MP-2 на новом artifact не воспроизводит предыдущие safety scenarios;
- установка metrics требует project-local authorization code;
- normal `toolchainctl apply` начинает автоматически активировать pilot.

## 11. Следующий gate

После merge этого slice semantic owner остаётся `opencode_permissions`. Затем `agent-toolchain` должен принять exact новый artifact, повторить disposable MP-2 с metrics assertions и только после PASS реализовать явный MP-3 user opt-in interface.
