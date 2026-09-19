# ProcessSpec → NormalizedOperation: предварительное сопоставление

Статус: **DESIGN CANDIDATE / РЕАЛИЗАЦИЯ НЕ НАЧАТА**.  
Задача: [#34](https://github.com/dilukhin/opencode_permissions/issues/34). Дата: 2026-09-19.

Первый результат #34: сопоставление существующего API, границ доверия и минимального следующего изменения. Это не утверждённая новая wire schema и не разрешение расширить ALLOW.

## 1. Основание и решение

Изучены main@7922d612f244882aae3d843a64393b1363b593d9:

- [identity core](../tools/normalized_operation_identity.py);
- [classifier core](../tools/classifier_core.py);
- [bounded analyzers](../tools/classifier_analyzers.py);
- [wrapper/remote analyzers](../tools/classifier_wrappers.py);
- [P0 adapter](../tools/opencode_p0_adapter.py);
- [declared environment dependencies](dc4_environment_dependency_reconciliation_ru.md);
- [граница agent-safe](opencode_permissions_agent_safe_boundary_ru.md).

Задачи producer/consumer ещё требуют design: [agent-safe#25](https://github.com/dilukhin/agent-safe/issues/25) и [ssh_relay#47](https://github.com/dilukhin/ssh_relay/issues/47). Их постановки перечитаны; окончательные schemas из них не следуют.

Предварительное решение: **переиспользовать NormalizedOperation и существующий classifier core; не создавать новый PDP, authorization schema или универсальный исполнитель**. После конкретного draft выбрать: существующий API + fixtures либо узкий trusted adapter. Утверждать сейчас, что адаптер не нужен или что общий adapter уже готов, нельзя.

## 2. Что действительно реализовано

| Механизм | Есть | Чего это не доказывает |
|---|---|---|
| operation_identity | Строгий JSON subset, domain-separated SHA-256, консервативная сериализация | Достоверность переданных facts или безопасность effects |
| Ordered argv | Вложенные массивы сохраняют порядок, границы и пустые строки | Что producer и executor одинаково понимают argv[0] |
| process_exec | Core требует executable, argv и cwd identity | Проверку произвольного ProcessSpec и его дополнительных полей |
| remote_exec | Core знает remote_argv, host identity и host target | Реальную передачу/выполнение удалённого argv и получение доверенной host identity |
| DC-3 | Bounded wrapper analysis; известный child DENY доминирует; прочее ASK | Автоматическое разрешение любого JSON или shell=false |
| DC-4/P0 | Конкретные acquisition/revalidation paths | Общую защиту всех shells, помощников и платформ |
| Environment | Core умеет context_dependencies; DC-4 проверяет declared dependency | Автоматическое извлечение dependencies из произвольного env |

Существенная граница: `classifier_analyzers._process_operation()` сейчас строит execution из executable/argv/cwd, а context_dependencies устанавливает в пустой список. Нельзя передать ему произвольный ProcessSpec с env/stdin/helper и считать, что эти поля автоматически попали в identity. Это ограничение существующего bounded profile, а не доказанный обход текущего P0.

Identity core допускает вложенные JSON-поля execution, но generic hash/validation не заменяют profile-specific проверку поддерживаемых полей. Новые execution-relevant поля нельзя молча отбросить.

## 3. Сопоставление полей

Имена слева логические: окончательные имена и wire representation принадлежат producer. «Нужно уточнить» означает открытое решение, а не готовое поле публичного API.

| Вход / факт | NormalizedOperation или отдельное связывание | Кто подтверждает / что проверить |
|---|---|---|
| Версия ProcessSpec | Versioned adapter profile; при неподдерживаемом входе отказ | Producer объявляет, consumer проверяет; не nearest fallback |
| Платформа исполнения | platform | Trusted adapter определяет фактическую целевую ОС; для remote Windows client не подменяет Linux target |
| Локальный/удалённый вызов | channel | Trusted adapter + transport; не модельный флаг |
| program | execution.executable: invoked/resolved_path/object_identity | Resolver исполнения; выбранный executable проверяется до spawn, PATH name недостаточен |
| argv / args | execution.argv — точный упорядоченный вектор | До реализации договориться, содержит ли source argv executable. Existing local core требует argv[0] == executable.invoked; избежать двойной вставки или потери argv[0] |
| cwd | execution.cwd и релевантный target | Trusted acquisition: requested/resolved/object/follow semantics; не косметическая нормализация пути |
| env | Только объявленные context_dependencies | Profile определяет влияние, adapter получает подтверждённые значения/факты. Не копировать весь environment |
| stdin | Execution-relevant dependency/descriptor; точное представление нужно согласовать | Producer + trusted executor: mode, границы bytes, immutable/read-back binding при необходимости. Отсутствие stdin и пустой input не приравнивать без контракта |
| script/interpreter/helper payload | exact execution payload или bound dependency принятого profile | Анализатор + executor; digest предотвращает подмену, но не доказывает безопасность |
| Удалённый узел и transport | remote.host_identity, transport и согласованный host target | ssh_relay предоставляет подтверждённую связь endpoint → identity. Display hostname/пользовательская строка не proof |
| Конкретный remote route/channel/helper version | Согласованный profile-specific remote/execution dependency | Transport и trusted consumer; смена значимого маршрута/помощника инвалидирует старое разрешение |
| targets/effects | targets/effects | Вычисляет/подтверждает trusted analyzer, а не копирует model claims |
| timeout / лимиты | Runtime contract; в identity/binding, если меняют разрешённые effects или условия | agent-safe/ssh_relay владеют прекращением/исходом; policy определяет значимость. Не добавлять float в op-jcs-v1 |
| purpose/description | Вне identity | Только объяснение, не доказательство разрешения |
| call/session/transaction/receipt IDs | Отдельная correlation/source binding | Владелец authorization + transport; одинаковая identity не разрешает повтор другой операции |
| approved=true / trusted=true | Не является authority | Не признавать caller input доказательством; embedded agent-safe может только сузить решение |

Для stdin/helper/route/timeout текущий документ задаёт требование, но не придумывает обязательную новую wire schema. Если поле существенно и его невозможно точно связать с исполнением, результат остаётся non-ALLOW.

## 4. Граница доверия

1. Producer передаёт структурированный запрос как данные; это не готовое разрешение.
2. Trusted adapter валидирует supported schema/profile и подтверждает executable/cwd/host/context.
3. Существующий analyzer определяет whole-operation effects/targets; непрозрачный nested payload остаётся неизвестным.
4. Native hard DENY сохраняется. Новый adapter не меняет действующий P0 и не переинтерпретирует исходный запрос ради обхода native решения.
5. Decision связывается с точной операцией и конкретным вызовом через принятый continuation/handoff. Digest сам по себе не grant.
6. Перед spawn consumer проверяет значимые inputs и payload. Drift ведёт к остановке этого исполнения/новому разрешению, не к silent rewrite/retry.
7. agent-safe выполняет runtime preconditions/verify/recovery, ssh_relay — transport/outcome. Они не повышают ASK/DENY до ALLOW.

Raw ProcessSpec нельзя просто переименовать в parsed-simple/v1 и присвоить parser.status=exact. Даже корректная schema не подтверждает происхождение facts.

Не требуется full executable content hash для каждого процесса, полный process.env snapshot или новый broker. Степень object/content binding выбирается по реальному profile и принятой модели угроз.

## 5. Вложенное исполнение и secrets

- shell=false не исключает bash -c, PowerShell -Command, Python -c, Node -e или .cmd/.bat. Нужен известный bounded analyzer; неизвестное не ALLOW.
- Для Windows отдельно проверить способ запуска .cmd/.bat, quoting и literal $. Нельзя молча заменить неподдерживаемый executable строковым shell execution.
- Если исполнение действительно требует shell, его exact executor/script остаются явным workload.
- Secrets не копируются в identity/log/fixtures. Обычный hash низкоэнтропийного секрета не является безопасной заменой secret handling.
- argv и stdin также могут содержать secrets: нельзя ограничить проверку только context_dependencies.sensitive. Если безопасный binding для конкретного secret-bearing profile не определён, он остаётся неподдерживаемым/non-ALLOW.
- Revalidation не означает абсолютное устранение всех гонок с malware/root. Граница — принятая guardrails threat model.
- Transitional YC не включается в общий adapter автоматически; его canonical classifier остаётся единственным semantic owner своего пути.

## 6. Матрица будущей приёмки

Это план parser/mock fixtures, **не отчёт о новых пройденных тестах**.

| Сценарий | Ожидание |
|---|---|
| Одинаковые facts, разный порядок JSON keys | SAME identity |
| Порядок/число/пустые элементы argv, пробелы, Unicode, literal $ изменены | DIFFERENT; bytes/строки не переписываются оболочкой |
| Один argv имеет две трактовки argv[0] | Adapter contract reject, не угадывание |
| Сменились executable/cwd object или значимый follow mode | Binding reject до spawn |
| Добавлена неиспользуемая env variable | SAME при неизменных declared dependencies |
| Изменилась declared execution-relevant dependency | DIFFERENT/binding reject |
| Существенные env/stdin/helper поля отброшены проекцией | Тест должен запретить ALLOW |
| Существенный stdin/script заменён после decision | Старое разрешение непригодно |
| Поменялись remote host/значимый channel/helper | Binding reject |
| Remote host claim поступил только от caller | Non-ALLOW |
| Helper отсутствует или версия неизвестна | Fail closed без fallback в shell string |
| Вложенный destructive/secret payload | Не ALLOW; подтверждённый hard DENY доминирует |
| Caller approved=true/trusted=true | Не создаёт grant/trust и не повышает решение |
| Тот же digest в другом call/replayed continuation | Старое разрешение не переиспользуется |
| Известный текущий P0/native DENY | Поведение без расширения |
| Windows/Linux и unsupported OpenCode version | Отдельные fixtures; runtime deployability только exact supported profile |
| Разрыв транспорта после возможной доставки | unknown остаётся unknown; не повторять удалённую команду |

## 7. Минимальный следующий PR и условия начала

Для реализации получить конкретные ответы от draft producer/consumer:

1. agent-safe#25: schema/version, executable и argv[0], cwd, stdin/env limits, entrypoint и место post-authorization revalidation; особенно verify/rollback/receipt.
2. ssh_relay#47: выбран ли helper вообще; точный payload boundary, host identity source, route/version binding, stdin/sudo framing, outcomes. Допустимо отложить remote slice.
3. На этой основе выбрать самый узкий adapter API и allowlist поддержанных полей. Не расширять текущий analyzer общим permissive forwarding.
4. Отдельный PR добавляет только выбранную проекцию, fixtures и нужную revalidation; schema/compatibility изменение явно версионируется. Canonicalizer меняется лишь при доказанной невозможности выразить нужные facts в действующем контракте.
5. При достаточности API — добавить только подтверждающие integration fixtures и зафиксировать no-change решение.

До этих ответов данное сопоставление можно рецензировать и использовать в соседнем design, но #34 целиком не закрывается. Связанный практический P0 pilot продолжает собственный путь независимо.
