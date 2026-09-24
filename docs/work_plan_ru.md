# План работ OpenCode Permissions

Принят в диалоге 2026-09-19. Проверка скорректировала предположение о незавершённом MP-2: текущий артефакт уже прошёл проверку метрик. [Состояние](STATUS.md), [доказательства](p0_readiness_review_2026-09-19_ru.md).

| Этап | Работа | Владелец / задача | Завершение |
|---|---|---|---|
| 1 | Актуализировать README/design, состояние и очередь | Этот документационный PR | Review и принятие; CI на точном PR head |
| 2А | Проверить P0 readiness по исходникам и CI logs | opencode_permissions | Выполнено: MP-2 + counters PASS, реальный gap — интерфейс MP-3 |
| 2Б | Сопоставить ProcessSpec/RemoteProcessSpec с NormalizedOperation | #34; agent-safe#25; ssh_relay#47 | Mapping, границы доверия, fixtures, решение о минимальном изменении |
| 3 | Закрыть пробелы MP-2 | agent-toolchain | Для текущего артефакта повтор не нужен. Новый runtime/installer diff требует релевантных gates |
| 4А | Подготовить explicit enable/disable/status/metrics | agent-toolchain#61 | Согласованный CLI/source/preflight contract; synthetic и runtime acceptance |
| 4Б | Провести MP-3 baseline на конкретной Linux-среде | Отдельное согласованное применение после #61 | Фактическая exact версия повторно проверена, включая 1.18.30 при использовании ILUKHIN; baseline и pilot workloads сопоставимы; disable проверен |
| 5 | Реализовать минимальный structured adapter, если нужен | #34 | После draft producer/consumer; no-change/API+fixtures допустимы |
| 6 | Улучшать native/deterministic coverage | opencode_permissions | Измеримый residual ASK, отрицательные cases, unsafe automatic allow = 0 |
| 6P1 | Подключить trust-conditioned development scope | Consumer готов; producer принят в agent-toolchain#45 / PR #66 | После MP-3 baseline: отдельная issue и приёмка self-trust boundary, provider integration и одной измеренно полезной family; P0 artifact не расширять |
| 7 | Решить вопрос auditor | После измерений | Только доказанная значимая semantic gray zone |

## Организация

- 2А → 4А → 4Б и 2Б → 5 — независимые направления, отдельные PR.
- Проектирование #34 начинается до окончательного утверждения соседних schemas. Реализация не должна опережать согласование input/source/consumer.
- Не дублировать installer в opencode_permissions; runtime recovery остаётся в agent-safe, transport — в ssh_relay.
- P0 не ждёт workspace trust, structured invocation или auditor.
- Producer workspace trust принят; следующим барьером первого P1 ALLOW служат MP-3 baseline и отдельная integration acceptance, а не доработка producer. Self-trust boundary готовить до нового ALLOW. Не смешивать эту работу с #34.
- Перед следующим implementation slice проверять HEAD/issues/PR владельца; сохранять параллельные изменения.
- GitHub Connector — основной транспорт; после записи targeted read-back.
- Локальный исполнитель нужен только для действительно локальной проверки, с ограниченным заданием.

## Проверки и ограничения

Изменение только документов не требует новых runtime опытов. Проверки существующего exact артефакта переиспользуются как evidence; они не доказывают новую реализацию или изменённую среду.
Новое разрешение требует regression case и проверки отсутствия unsafe ALLOW.
Реальное включение pilot не является побочным эффектом обычного apply/update.

Auditor, kernel broker по умолчанию, общие schemas без producer/consumer, расширение P0 на writes/remote/build/test и смешение transitional YC с P0 отложены.

Ближайший результат: актуализированные документы и mapping #34. Для практического пилота следующий implementation owner — [agent-toolchain#61](https://github.com/dilukhin/agent-toolchain/issues/61).
