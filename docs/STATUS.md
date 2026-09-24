# Состояние OpenCode Permissions

Актуализация состояния workspace trust: 2026-09-24. Доказательства P0 от 2026-09-19: [подробный отчёт](p0_readiness_review_2026-09-19_ru.md).

| Направление | Состояние | Граница доказательства |
|---|---|---|
| Stage 0 / Gate A | CLOSED | Исследованный профиль, не все версии OpenCode |
| Native-policy / Gate B | CLOSED | Исторический Linux/exact profile; новые версии через compatibility registry |
| DC-0…DC-4 | CLOSED в доказанном scope | Core identity, composition, bounded analysis и конкретный runtime binding; не общий structured executor |
| P0 runtime artifact / MP-0 | Реализован | Linux, bounded single-file grep classifier family |
| MP-1 managed deployment | PASS в проверенном CI | Synthetic fixtures, не пользовательская установка |
| MP-2 с метриками | PASS | Официальный exact Linux binary, шесть сценариев, privacy-safe ASK-path counters |
| MP-3 пользовательский интерфейс | OPEN | [agent-toolchain#61](https://github.com/dilukhin/agent-toolchain/issues/61) |
| MP-3 применение и рабочие измерения | Не подтверждены; не выполнялись в этой итерации | После готовности интерфейса и согласования конкретного применения |
| Structured invocation | Проектирование [#34](https://github.com/dilukhin/opencode_permissions/issues/34) | Согласование с agent-safe#25 и ssh_relay#47, без расширения ALLOW |
| Workspace trust / P1 | Consumer и producer приняты; authorization integration ожидается | [agent-toolchain#45](https://github.com/dilukhin/agent-toolchain/issues/45) закрыта через PR #66; первый trust-conditioned ALLOW требует MP-3 baseline и отдельной integration acceptance |
| Auditor | DEFERRED BY POLICY | После реальных residual-ASK metrics |
| Transitional YC | Отдельные policy/classifier/artifact в main | Не расширяет P0; установка и состояние машин не проверялись здесь |

Windows имеет unit/synthetic проверки; это не Windows OpenCode runtime deployment proof. Registry на дату отчёта допускает deploy только Linux. Номер current_target не означает последнюю upstream-версию или версию на машине пользователя.

Следующая работа: [план](work_plan_ru.md). Main-код и пользовательская permission configuration данной документационной итерацией не меняются.
