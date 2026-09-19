# План работ OpenCode Permissions

Принят в диалоге 2026-09-19. Проверка скорректировала предположение о незавершённом MP-2: текущий артефакт уже прошёл проверку метрик. [Состояние](STATUS.md), [доказательства](p0_readiness_review_2026-09-19_ru.md).

| Этап | Работа | Владелец / задача | Завершение |
|---|---|---|---|
| 1 | Актуализировать README/design, состояние и очередь | Этот документационный PR | Review и принятие; CI на точном PR head |
| 2А | Проверить P0 readiness по исходникам и CI logs | opencode_permissions | Выполнено: MP-2 + counters PASS, реальный gap — интерфейс MP-3 |
| 2Б | Сопоставить ProcessSpec/RemoteProcessSpec с NormalizedOperation | #34; agent-safe#25; ssh_relay#47 | Mapping, границы доверия, fixtures, решение о минимальном изменении |
| 3 | Закрыть пробелы MP-2 | agent-toolchain | Для текущего артефакта повтор не нужен. Новый runtime/installer diff требует релевантных gates |
| 4А | Подготовить explicit enable/disable/status/metrics | agent-toolchain#61 | Согласованный CLI/source/preflight contract; synthetic и runtime acceptance |
| 4Б | Применить P0 на конкретной Linux-среде и измерить | Отдельное согласованное применение | Фактическая exact версия поддержана; baseline и pilot workloads сопоставимы; disable проверен |
| 5 | Реализовать минимальный structured adapter, если нужен | #34 | После draft producer/consumer; no-change/API+fixtures допустимы |
| 6 | Улучшать native/deterministic coverage | opencode_permissions | Измеримый residual ASK, отрицательные cases, unsafe automatic allow = 0 |
| 6P1 | Trust-conditioned development scopes | После agent-toolchain#45 | Producer/integration acceptance и paired policy corpus |
| 7 | Решить вопрос auditor | После измерений | Только доказанная значимая semantic gray zone |

## Организация

- 2А → 4А → 4Б и 2Б → 5 — независимые направления, отдельные PR.
- Проектирование #34 начинается до окончательного утверждения соседних schemas. Реализация не должна опережать согласование input/source/consumer.
- Не дублировать installer в opencode_permissions; runtime recovery остаётся в agent-safe, transport — в ssh_relay.
- P0 не ждёт workspace trust, structured invocation или auditor.
- Перед следующим implementation slice проверять HEAD/issues/PR владельца; сохранять параллельные изменения.
- GitHub Connector — основной транспорт; после записи targeted read-back.
- Локальный исполнитель нужен только для действительно локальной проверки, с ограниченным заданием.

## Проверки и ограничения

Изменение только документов не требует новых runtime опытов. Проверки существующего exact артефакта переиспользуются как evidence; они не доказывают новую реализацию или изменённую среду.
Новое разрешение требует regression case и проверки отсутствия unsafe ALLOW.
Реальное включение pilot не является побочным эффектом обычного apply/update.

Auditor, kernel broker по умолчанию, общие schemas без producer/consumer, расширение P0 на writes/remote/build/test и смешение transitional YC с P0 отложены.

Ближайший результат: актуализированные документы и mapping #34. Для практического пилота следующий implementation owner — [agent-toolchain#61](https://github.com/dilukhin/agent-toolchain/issues/61).
