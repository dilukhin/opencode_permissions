# Проверка готовности P0 — 2026-09-19

Статус: **MP-2 + METRICS PASS; MP-3 INTERFACE OPEN; NO LIVE DEPLOYMENT В ЭТОЙ ИТЕРАЦИИ**.

## Точные источники

- opencode_permissions main: `7922d612f244882aae3d843a64393b1363b593d9`.
- agent-toolchain main: `d612c2cc187ea926ecbcd39cb4f243d0850005cd`.
- [opencode_permissions CI 34567122150](https://github.com/dilukhin/opencode_permissions/actions/runs/34567122150): success на указанном main.
- [agent-toolchain MP-1 35432826248](https://github.com/dilukhin/agent-toolchain/actions/runs/35432826248): success.
- [agent-toolchain MP-2 35432826165](https://github.com/dilukhin/agent-toolchain/actions/runs/35432826165), [job 105870315416](https://github.com/dilukhin/agent-toolchain/actions/runs/35432826165/job/105870315416): success; прочитан журнал с SHA обоих checkout и результатами.
- Exact OpenCode target: `1.18.29`, Linux; `opencode-1.18.29-gate-b`.
- Pilot: `sha256:21582d375823f499a2792824993a7a7510301c8fce2711cd01a25caececdaf88`.
- Native policy: `sha256:b38090e07008fb174607aa2a924cfef1dd26d03bdb339a379b1a770397a8ad84`.

Это подтверждённый registry target, не утверждение о последней upstream или установленной версии. Новый runtime-прогон в текущем диалоге не запускался.

## Матрица

| Требование | Evidence | Вывод |
|---|---|---|
| Текущий content-bound artifact | build_plan/manifest, CI и MP-2 log показывают 21582d37… | PASS |
| Native ALLOW terminal | native_allow: completed, pending=false; metrics=null | PASS; не live counter |
| Native DENY terminal | native_deny: error, pending=false; fake executable marker не достигнут по harness assertion | PASS |
| Classifier ALLOW | completed; native_ask=1, classifier_allow=1, residual_ask=0 | PASS |
| Остаточный ASK | pending=true; native_ask=1, residual_ask=1, classifier_allow=0 | PASS |
| Отказ classifier | pending=true; residual_ask=1, classifier_error/fail_closed=1, classifier_allow=0 | PASS |
| Auditor отсутствует | pilot_constraint=false, profile_constraint=false | PASS |
| Privacy-safe metrics | aggregate_metrics проверяет exact keys, version/artifact, mode 0600, отсутствие command/workspace/session/fixture text; job success | PASS в tested scope |
| Интерфейс для пользователя | Python facade существует; toolchainctl.py не содержит P0 CLI | OPEN: agent-toolchain#61 |
| Пользовательская установка | В проверенном evidence только disposable среды | Не доказана этой проверкой |
| Windows runtime deployment | SOURCE_REVALIDATED_ONLY, deployable_platforms=[linux] | Не разрешён текущим profile |

Во всех трёх измеряемых сценариях binding_reject=0. Это не отдельная проверка всех отказов metrics storage или всех вариантов binding drift; их coverage нельзя выводить из нулевого counter. Runtime binding proof существует в отдельном compatibility gate.

[Исходник harness](https://github.com/dilukhin/agent-toolchain/blob/d612c2cc187ea926ecbcd39cb4f243d0850005cd/tests/run_opencode_permissions_mp2_disposable.py).

## Коррекция инвентаризации

Исторический closure-документ agent-toolchain ссылался на ce1ae9ae…; metrics slice — на c6b33341…. Эти ссылки не определяют текущий artifact. Текущий build_plan и фактический run используют 21582d37….

Предположение «MP-2 нового artifact ещё может отсутствовать» снято чтением кода и журналов. Повторять успешный прогон без изменения входов не нужно. Историческое closure верно для своей даты, но не заменяет current evidence.

## Следующий gate

[agent-toolchain#61](https://github.com/dilukhin/agent-toolchain/issues/61): explicit user interface, проверка применимых effective layers, безопасное отключение при version drift и read-only metrics. Пункты Acceptance 1–6 metrics readiness подтверждены существующими CI/исходниками в их scope; пункт 7 интерфейса не закрыт.

Перед live opt-in определить фактическую среду и exact установленную версию. При несовпадении требуется compatibility revalidation, без отката и nearest-version fallback.
Параллельная #34 не является предпосылкой P0.
