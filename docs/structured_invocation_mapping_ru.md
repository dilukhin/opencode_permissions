# ProcessSpec → NormalizedOperation: предварительное сопоставление

Статус: **ЛОКАЛЬНЫЙ DRAFT СОПОСТАВЛЕН / БИБЛИОТЕЧНАЯ СТОРОНА В PR #37 / ПОДКЛЮЧЕНИЕ НЕ ЗАВЕРШЕНО**.  
Задача: [#34](https://github.com/dilukhin/opencode_permissions/issues/34). Дата: 2026-09-19.

Первый результат #34: сопоставление существующего API, границ доверия и минимального следующего изменения. Это не утверждённая новая wire schema и не разрешение расширить ALLOW.

**Продолжение по agent-safe#33:** прочитаны новый комментарий #34, PREPARED_PROCESS_HANDOFF.md и код HEAD `2d29db8f7425aa12a2f934ea107b282f91e8f8b4`; CI этого HEAD успешен. Точный stdin и неизменяемые подготовленные вызовы реализованы в открытом PR #33. В [нашем PR #37](https://github.com/dilukhin/opencode_permissions/pull/37) опубликованы [конкретный контракт](https://github.com/dilukhin/opencode_permissions/blob/d33eac7567a47e56f15066a6eb68dba75c7b47ca/docs/prepared_process_contract_ru.md), библиотечная реализация и [задание подключения agent-safe](https://github.com/dilukhin/opencode_permissions/blob/d33eac7567a47e56f15066a6eb68dba75c7b47ca/docs/agent_safe_prepared_integration_task_ru.md). Они уточняют открытые вопросы исторического сопоставления ниже. Формат — один доверенный Python-процесс; действующий OpenCode host bridge/IPC этим не объявляется реализованным.

## 1. Основание и решение

Изучены main@7922d612f244882aae3d843a64393b1363b593d9:

- [identity core](../tools/normalized_operation_identity.py);
- [classifier core](../tools/classifier_core.py);
- [bounded analyzers](../tools/classifier_analyzers.py);
- [wrapper/remote analyzers](../tools/classifier_wrappers.py);
- [P0 adapter](../tools/opencode_p0_adapter.py);
- [declared environment dependencies](dc4_environment_dependency_reconciliation_ru.md);
- [граница agent-safe](opencode_permissions_agent_safe_boundary_ru.md).

Повторная проверка 2026-09-19: конкретный **локальный** draft появился. Удалённый structured-контракт намеренно отложен.

| Источник | Проверенный HEAD | Готовность |
|---|---|---|
| [agent-safe#28](https://github.com/dilukhin/agent-safe/pull/28), PROCESS_RECOVERY_DESIGN.md | `4c6d28a6c06e53c6b178dcad55c39ae59b0c7d37` | Локальный вариант принят; PR слит, коммит слияния `fab10264c519db3c09540160de3fe885bf0c1aab` |
| [agent-safe#31](https://github.com/dilukhin/agent-safe/pull/31), ProcessSpec/RollbackPlan/recover | `40a1fdf3d9f25f84608a3c9c9b0c1f5d8f6086f9` | Первый внутренний потребитель восстановления и его verify слит; коммит слияния `889366c52fb63b34fe06249604dc9864b6e5d492` |
| [agent-safe#25](https://github.com/dilukhin/agent-safe/issues/25), часть A | Исходная проверка: `9f92c3953d061882aba5c5545465c5490bfbb110` | На исходной версии публичные verify/receipt/main-spec отсутствовали; продолжающаяся работа agent-safe проверяется отдельно при интеграции |
| [ssh_relay#49](https://github.com/dilukhin/ssh_relay/pull/49), исследование #47 | `eb06ed7f21cc286b31c115d0a44b701525e8d6d0` | Архитектурный обзор завершён; сохранить строковый API, отложить RemoteProcessSpec/helper. PR открыт, готов к рассмотрению, не слит |

Повторно прочитаны [документ ssh_relay#49](https://github.com/dilukhin/ssh_relay/blob/eb06ed7f21cc286b31c115d0a44b701525e8d6d0/docs/structured_exec_review_ru.md), описание PR и issue #47. Состояния слияния agent-safe#28/#31 подтверждены метаданными GitHub. Проверки CI и Package install для указанного HEAD #49 завершились успешно. Технические наблюдения о локальном исполнителе ниже относятся к явно указанному HEAD #31; готовность текущих доработок agent-safe этим чтением не утверждается.

**Заключение со стороны opencode_permissions:** сведений от ssh_relay достаточно для текущего локального этапа. Дополнительный интерфейс, помощник, запуск на сервере или слияние #49 для продолжения #34 не требуются. Раздел 6.2 документа relay корректно оставляет точную локальную схему за agent-safe/opencode_permissions; его предложения не становятся утверждённым контрактом автоматически. Существующий строковый SSH API не объявляется реализацией remote_argv.

Возврат к удалённому проектированию требует совокупности четырёх условий из §8.1 документа relay: конкретный удалённый потребитель и сценарий; воспроизведённая недостаточность API либо необходимая отсутствующая семантика; обоснование недостаточности существующих минимальных средств; владельцы и отдельная ограниченная задача проектирования. Готовность локального ProcessSpec сама по себе отсрочку не снимает. Закрытие #47 после принятия #49 означает завершение исследования, не реализацию удалённого исполнения.

Решение: **продолжить локальный mapping сейчас; переиспользовать NormalizedOperation и classifier core**. Не требуется ждать SSH или реализации всех публичных входов #25A. Для связи первого потребителя с authorization нужна узкая доверенная граница подготовки facts/проекции и проверки перед spawn; обычного forwarding ProcessSpec в существующий bounded analyzer недостаточно. Необходимость изменения canonicalizer не обнаружена. Production adapter ещё не готов: точный handoff и представления дополнительных dependencies требуют решений из раздела 7.

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

Для локального ProcessSpec имена и семантика ниже проверены по agent-safe#28/#31. Удалённые поля остаются логическими требованиями, не существующим RemoteProcessSpec API.

| Вход / факт | NormalizedOperation или отдельное связывание | Кто подтверждает / что проверить |
|---|---|---|
| Версия ProcessSpec | Versioned adapter profile; при неподдерживаемом входе отказ | Producer объявляет, consumer проверяет; не nearest fallback |
| Платформа исполнения | platform | Trusted adapter определяет фактическую целевую ОС; для remote Windows client не подменяет Linux target |
| Локальный/удалённый вызов | channel | Trusted adapter + transport; не модельный флаг |
| program | execution.executable: invoked/resolved_path/object_identity | Resolver исполнения; выбранный executable проверяется до spawn, PATH name недостаточен |
| argv | execution.argv = [program, *resolved_argv] | agent-safe argv **не включает program**; после раскрытия artifact-ссылок добавить program ровно один раз. Core требует argv[0] == executable.invoked |
| cwd | execution.cwd и релевантный target | Trusted acquisition: requested/resolved/object/follow semantics; не косметическая нормализация пути |
| env_dependencies | Только подтверждённые context_dependencies | В #31 допустимы отсутствие или []; непустой список отклоняется, окружение наследуется. Это не доказательство независимости скрипта от env и не основание ALLOW |
| stdin_utf8 | Связать mode и точное исполненное содержимое; представление adapter ещё согласовать | До 64 КиБ UTF-8; отсутствие → DEVNULL, пустая строка → PIPE с пустым вводом. Для обещания exact bytes проверить text-mode executor на Windows |
| script/interpreter/helper payload | exact execution payload или bound dependency принятого profile | Анализатор + executor; digest предотвращает подмену, но не доказывает безопасность |
| Удалённый узел и transport | remote.host_identity, transport и согласованный host target | ssh_relay предоставляет подтверждённую связь endpoint → identity. Display hostname/пользовательская строка не proof |
| Конкретный remote route/channel/helper version | Согласованный profile-specific remote/execution dependency | Transport и trusted consumer; смена значимого маршрута/помощника инвалидирует старое разрешение |
| targets/effects | targets/effects | Вычисляет/подтверждает trusted analyzer, а не копирует model claims |
| timeout_seconds / лимиты | Runtime contract; для этого локального adapter связывать timeout как условие исполнения | В #31 целое 1–3600. Timeout после spawn даёт unknown, не rollback/retry; остальные лимиты проверяются до запуска. Не добавлять float в op-jcs-v1 |
| purpose/description | Вне identity | Только объяснение, не доказательство разрешения |
| call/session/transaction/receipt IDs | Отдельная correlation/source binding | Владелец authorization + transport; одинаковая identity не разрешает повтор другой операции |
| approved=true / trusted=true | Не является authority | Не признавать caller input доказательством; embedded agent-safe может только сузить решение |

Для stdin/helper/route/timeout текущий документ задаёт требование, но не придумывает обязательную новую wire schema. Если поле существенно и его невозможно точно связать с исполнением, результат остаётся non-ALLOW.

### 3.1. Конкретный локальный потребитель #31

Проверены [process_spec.py](https://github.com/dilukhin/agent-safe/blob/40a1fdf3d9f25f84608a3c9c9b0c1f5d8f6086f9/src/agent_safe/core/process_spec.py), [rollback.py](https://github.com/dilukhin/agent-safe/blob/40a1fdf3d9f25f84608a3c9c9b0c1f5d8f6086f9/src/agent_safe/core/rollback.py), [recover.py](https://github.com/dilukhin/agent-safe/blob/40a1fdf3d9f25f84608a3c9c9b0c1f5d8f6086f9/src/agent_safe/adapters/recover.py) и [_run](https://github.com/dilukhin/agent-safe/blob/40a1fdf3d9f25f84608a3c9c9b0c1f5d8f6086f9/src/agent_safe/adapters/exec_adapter.py).

- Это внутренний процесс восстановления и его отдельный verify. Основное действие, его verify/receipt остаются на прежнем входе. Комплект rollback не связывает зависимости основного действия.
- ProcessSpec v1: обязательны schema_version/program/argv/cwd/shell/timeout_seconds; optional stdin_utf8/env_dependencies. shell только false; неизвестные поля отклоняются. В RollbackPlan допустимы целые аргументы `{"artifact":"id"}`; resolved_spec заменяет их абсолютными путями сохранённых копий. Identity строится **после раскрытия**, до authorization; никакой shell-пересборки.
- Первый профиль: текущий канонический Python, `-I`, сохранённый script; одна обычная файловая цель до 8 МиБ либо отсутствующая. Manifest фиксирует SHA-256/размеры артефактов, контекст program/cwd и target. Один manifest digest не заменяет анализ effects/targets и не даёт разрешения произвольному Python-коду.
- load_bundle повторно проверяет план, артефакты, program/cwd перед исполнением. recover сверяет target, создаёт отдельную транзакцию и сохраняет исходный recovery block. Это полезная consumer-side revalidation, но вызова opencode_permissions и проверки его continuation в #31 нет. Локальный `--approved` не является таким handoff.
- Восстановление и verify — разные вызовы. Нужны отдельные operation/call bindings либо явно согласованная композиция с проверкой каждого запуска; разрешение исходной mutation не наследуется. Служебные записи/барьеры остаются под управлением agent-safe, но граница разрешаемого действия должна быть названа явно.

### 3.2. Найденные несовместимости и открытые детали

**Object identity.** agent-safe хранит stat identity массивом, включая mtime_ns/ctime_ns; classifier core ожидает непустую строку object_identity. Вложить исходный stat-массив как JSON dependency тоже нельзя без преобразования: типичные наносекундные timestamps превышают MAX_SAFE_INTEGER op-jcs-v1. Нужна документированная versioned lossless кодировка от доверенного resolver (например, десятичные строки компонентов с явными именами/профилем). Нельзя округлять числа, брать Python repr или принимать готовую identity от caller. Конкретная кодировка теперь определена библиотечным контрактом PR #37: `agent-safe-stat/v1:` и канонический JSON с platform/kind/именованными десятичными строками всех компонентов.

В отдельной синтетической проверке на исходном identity core main@7922d612 проверены два случая: число `1790000000000000000` отвергнуто с `INTEGER_OUTSIDE_IJSON_SAFE_RANGE`; его десятичная строка сохраняется без потери. Это проверка выразимости, не тест готового adapter и не интеграционный runtime-прогон.

**stdin: исправлено в agent-safe#33.** Исторический #31 использовал text-mode; #33 кодирует ввод до spawn и передаёт bytes бинарным каналом. Прочитаны исправление _run и тест дочернего процесса с LF/CRLF/Unicode/empty/DEVNULL; CI Windows/Ubuntu успешен. В нашем PR #37 identity различает mode и связывает размер/SHA-256 точных UTF-8 bytes. Это закрывает прежний вопрос преобразования переводов строк; подключение разрешений остаётся отдельным.

**Dependencies и timeout.** Согласовать точные versioned поля для stdin mode/content, artifact ID/path/size/digest и timeout; связывать реально используемые сохранённые копии, не только исходные пути. Integer timeout и несекретные descriptors выразимы текущим identity core, но generic core не валидирует их профильную семантику. До такой проверки нельзя объявить adapter готовым.

**Effects.** Файл-цель из RollbackPlan, non_secret:true и Python -I — ограничения/заявления профиля, не доказательство полного поведения скрипта. Неизвестный script workload остаётся non-ALLOW; подтверждённый hard DENY сохраняется.

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

## 7. Порядок продолжения и критерии готовности

1. **Библиотечная сторона opencode_permissions — PR #37.** Модули prepared_process_adapter.py и prepared_process_authorization.py задают строгую проекцию, lossless stat, stdin/artifacts/timeout, отдельные snapshot/call/role bindings, TTL, отзыв, native veto и одноразовое потребление. Неизвестный скрипт остаётся ASK_USER; разрешение человека не становится автоматическим ALLOW. 24 новых теста и 81 локальная проверка совместно с существующим корпусом classifier/identity прошли.
2. **Потребитель agent-safe — отдельное подключение после #33.** Использовать опубликованное задание PR #37: настоящий prepare/revalidate, две роли, исходные снимки, ExecutionPort перед каждым _run, сохранение результатов и блокировки при отказе verify. Не копировать issuer/policy, не принимать --approved/JSON как grant, не включать публичный managed CLI.
3. **Реальный штатный host — ответственность opencode_permissions.** Библиотечный транспорт local-inprocess/v1 работает лишь в одном доверенном Python-процессе. Нужны подлинное native approve-once событие, доказанная связь с HostPort и разрешение служебных записей до recovery. Если выбранное размещение требует IPC, его аутентичность и привязка доказываются отдельно; файл-токен или сериализация object reference не являются обходным решением. Этот интеграционный этап пока не выполнен.
4. **Совместная приёмка.** Подмена данных/роли/вызова, чужой/истёкший/повторный grant должны остановить настоящий consumer до spawn; одновременное consume допускает один успех. P0/native DENY/ASK и правила unknown остаются без расширения. Подключение потребителя с имитацией host не заменяет runtime proof штатного подтверждения.
5. **ssh_relay — результат достаточен.** #49 не блокирует локальную работу. RemoteProcessSpec/helper отложены по четырём условиям раздела 1. Публичные agent-safe#25A входы также не требуются первому внутреннему потребителю.

#34 остаётся открытой до совместной приёмки и подключения подлинного native continuation. PR #36 сохраняет архитектурный контекст, PR #37 — конкретный контракт и нашу реализацию. Слияния, развёртывание, включение managed-пути и расширение ALLOW в эту итерацию не входят. Практический P0 pilot независим.
