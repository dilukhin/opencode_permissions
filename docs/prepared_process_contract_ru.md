# Локальный PreparedProcess: проекция и одноразовое разрешение v1

Статус: **реализованный библиотечный контракт для подключения и совместной проверки**.
Связь: [#34](https://github.com/dilukhin/opencode_permissions/issues/34).
Это не включённый production-путь OpenCode и не подтверждённый межпроцессный транспорт.

## 1. Проверенные стороны и решение

Потребитель: [agent-safe#33](https://github.com/dilukhin/agent-safe/pull/33),
HEAD `2d29db8f7425aa12a2f934ea107b282f91e8f8b4`; прочитаны
`docs/PREPARED_PROCESS_HANDOFF.md`, `core/rollback.py`, `core/process_spec.py`
и `adapters/recover.py`. PR открыт, CI указанного HEAD успешен.
Исходная база opencode_permissions: `7922d612f244882aae3d843a64393b1363b593d9`.

Первый профиль — только локальные `process` (восстановление) и `verify` из сохранённого
комплекта. Публичные входы agent-safe#25A и удалённый SSH не нужны этому этапу.
Сохраняются NormalizedOperation v1, op-jcs-v1 и classifier core. Старые анализаторы,
P0, YC и policy-файлы не меняются. Второй исполнитель или обязательный broker не вводятся.

Выбран транспорт `local-inprocess/v1`: один доверенный Python-процесс, один владелец
состояния разрешений на сессию. Настоящие объектные ссылки передаются напрямую;
JSON, CLI-флаги, переменные окружения, файловые токены и IPC не являются транспортом v1.
Разрешение из другого экземпляра владельца или после перезапуска не принимается.

Это конкретное ограничение реализации, а не заявление, что OpenCode уже работает
в одном Python-процессе с agent-safe. Подключение к реальному native continuation
(продолжению после штатного подтверждения) ещё не реализовано. Проверять его должен
opencode_permissions в отдельном интеграционном изменении. Если фактическому размещению
нужен межпроцессный транспорт, его подлинность должна быть доказана отдельно; нельзя
сериализовать объект v1 или считать локальное имя канала доказательством доверия.

## 2. API проекции и доверенное получение данных

Модуль: [tools/prepared_process_adapter.py](../tools/prepared_process_adapter.py).

```python
project_prepared(prepared, *, platform, profile="agent-safe-local-prepared/v1") -> Projection
encode_object_identity(values, *, kind, platform) -> str
classify_prepared(projection, *, native_decision="ask") -> dict
```

Принимается frozen dataclass с **точным** набором полей PreparedProcess из agent-safe#33;
артефакты также frozen dataclass, коллекции — tuple. Лишние поля, другая версия, malformed
stat, неподдержанная платформа, argv или лимиты отклоняются. Прямого JSON-входа нет.
Поддержаны Linux и Windows; `.cmd/.bat`, UNC/ADS и неизвестные роли не поддержаны.

Проверка структуры не подтверждает происхождение объекта. Доверенный код подключения
обязан сам вызвать agent-safe `prepare_process` после `load_bundle`, обеспечить профиль
текущего Python `-I`, отсутствие секретов и фиксированный контекст исходной операции.
Нельзя принять объект, пути или функцию получения данных от модели как готовые факты.
Программа Python может исполнять произвольный код даже при правильных типах и хешах.

| Сведения | Представление v1 |
|---|---|
| program | execution.executable.invoked/resolved_path, подтверждённый абсолютный путь |
| argv без program | execution.argv = [program, *prepared.argv], без преобразования строк |
| cwd | requested/lexical/object_identity/follow_mode=target; отсутствие ссылок проверяет agent-safe |
| shell | execution.shell=false |
| timeout_seconds | execution.timeout_seconds, целое 1–3600 |
| stdin_utf8=None | execution.stdin = {mode: devnull} |
| stdin_utf8=str | execution.stdin: mode=pipe, encoding=utf-8, размер и SHA-256 точных UTF-8 bytes; без изменения LF/CRLF |
| artifacts | context_dependencies: kind=saved_artifact, artifact_id, path, size_bytes, sha256, object_identity для каждой сохранённой копии |
| Окружение | execution.environment=inherited-unproven; отсутствует полный снимок env, независимость скрипта от env не доказана |
| targets/effects | unknown_target, process/unknown_code_execution; целевой файл плана не доказывает полноты effects |
| manifest/source/attempt/role | Отдельная snapshot_identity, не новые верхнеуровневые поля NormalizedOperation |

Dependencies нормализуются как семантическое множество существующим identity core.
argv остаётся упорядоченным. Неиспользуемая переменная окружения не добавляется
автоматически в identity; это не разрешение игнорировать фактически значимые зависимости.
Непустой env_dependencies сейчас отвергается у потребителя; новый профиль нужен до его поддержки.

Projection содержит неизменяемые `operation_json`, `operation_identity`, `snapshot_identity`,
source_txn_id, attempt_txn_id и role. `operation()` возвращает новую копию словаря.
snapshot_identity — SHA-256 с префиксом `opencode_permissions.prepared-snapshot.v1\n`
над op-jcs-v1 объектом `{profile, operation_identity, manifest_sha256, source_txn_id,
attempt_txn_id, role}`. Manifest digest берётся из проверенного PreparedProcess.
Одинаковая операция в разных ролях может иметь одну operation_identity, но разные snapshot_identity.

Проекция не выполняет поиск секретов. Профиль допускает только заранее проверенные
несекретные планы, аргументы, stdin и артефакты. Хеш stdin не является обезличиванием
низкоэнтропийного секрета. Доверенный источник обязан отказать секретному/непроверенному
профилю; `non_secret:true` вызывающей стороны недостаточно. Сырые проекции не писать в журнал.

## 3. Файловая идентичность без потери точности

object_identity — строка `agent-safe-stat/v1:` плюс канонический op-jcs-v1 JSON:

```json
{"components":{"ctime_ns":"1790000000000000002","dev":"1","file_attributes":"0","ino":"9007199254740993","mode":"33152","mtime_ns":"1790000000000000001","reparse_tag":"0","size":"3"},"kind":"file","platform":"linux"}
```

Точный порядок tuple файла: dev, ino, mode, size, mtime_ns, ctime_ns,
file_attributes, reparse_tag. Каталога: dev, ino, mode, file_attributes, reparse_tag.
Имена соответствуют agent-safe#33. **Все** компоненты записываются десятичными строками,
включая mode; никаких float, repr, округления или платформенной нормализации путей.
Signed timestamps сохраняются. Bool не int для контракта. Каталог не получает
mtime/size, намеренно исключённые профилем agent-safe. Подмена содержимого артефакта
связывается дополнительным digest; обязательного полного хеша системного Python нет.

## 4. API владельца одноразовых разрешений

Модуль: [tools/prepared_process_authorization.py](../tools/prepared_process_authorization.py).

```python
host, execution = create_local_session(
    session_id=..., platform=..., acquire=..., native_check=...,
    ttl_seconds=60, capacity=1024,
)
binding = CallBinding(session_id, call_id, source_txn_id, attempt_txn_id, role)
pending = execution.request(binding)
# Только доверенный обработчик штатного approve-once:
host.approve_once(pending.continuation, binding,
                  snapshot_identity=pending.projection.snapshot_identity)
# Непосредственно перед единственным spawn:
projection = execution.consume(pending.continuation, binding)
```

Это последовательность отдельных доверенных событий, **не** инструкция автоматически
вызывать approve_once после request. У ExecutionPort нет метода подтверждения.

- `acquire(binding) -> PreparedProcess`: доверенная функция подключения. Проверяет
  исходный контекст, runtime preconditions и неизменность **первоначального** снимка,
  заново получает факты через prepare_process. Вызывается при request и consume.
  Конфигурация функции принадлежит установке/владельцу, не запросу инструмента.
- `native_check(binding, projection) -> "deny" | "ask" | "allow"`: доверенное чтение
  текущего native решения, также при request и consume. Подмена строковым параметром
  caller недопустима. Недоступность/ошибка источника останавливает вызов.
- `request`: возвращает DENY без continuation либо ASK_USER с непрозрачным объектом
  и точной проекцией для контекста подтверждения. Для непрозрачного скрипта даже
  native allow сужается до ASK_USER в этом новом профиле; глобальная terminal precedence
  classifier core и существующий P0 не меняются.
- `host.approve_once`: доступен только обработчику подлинного штатного подтверждения
  точного запроса. Привязывает утверждённый снимок к pending-вызову. Классификатор
  остаётся ASK_USER; результат — разрешение человека один раз, не автоматический ALLOW.
  Hard DENY не создаёт pending-объект и не может быть подтверждён этим методом.
- `consume`: сверяет session/transport/call/source/attempt/role, срок, состояние,
  повторно полученные факты и native veto. Атомарно переводит разрешение в CONSUMED.
  Возвращает исходную проекцию; agent-safe запускает именно свой исходный PreparedProcess.
- `host.cancel` отменяет pending/approved разрешение; отказ пользователя, отмена вызова
  и прекращение recovery должны вызвать cancel. `host.close` отзывает всю сессию.

Владелец HostPort — **opencode_permissions**, потребитель ExecutionPort — доверенный
код подключения agent-safe. agent-safe не создаёт собственный HostPort, не подтверждает
разрешение через --approved и не принимает continuation из внешнего ввода.
Внутренняя таблица регистрирует сам объект, его привязку и состояние; копия/строка/словарь
не пройдут проверку. Это подлинность относительно владельца в одном доверенном процессе,
а не криптографическая аттестация. Произвольный код в том же Python-процессе способен
обойти private-поля; такая защита здесь не заявляется.

TTL — 60 секунд от request, допустимо 1–300, часы монотонные; подтверждение срок
не продлевает. Новый request для уже использованного CallBinding запрещён. Состояния
потребления не вытесняются ради лимита: сессия отказывает при capacity, пока владелец
не завершит её. Не продлевать/переиздавать разрешение автоматически после отказа или timeout.
Две роли требуют двух call_id, двух pending-запросов и двух подтверждений. Можно
запрашивать verify непосредственно перед его запуском, но только для снимка, сохранённого
**до** восстановления. При его изменении требуется новый разбор всей попытки.

## 5. Ошибки, одноразовость и исходы

| Ошибка API | Смысл |
|---|---|
| CONTINUATION_UNKNOWN | Объект не выдан этим владельцем; в том числе чужая сессия/копия/подделка |
| CONTINUATION_NOT_APPROVED | Пользователь ещё не подтвердил; запуск запрещён |
| APPROVAL_SNAPSHOT_MISMATCH / CALL_BINDING_MISMATCH | Ошибка привязки; разрешение отозвано |
| PREPARED_DRIFT / ACQUISITION_OR_POLICY_FAILED / NATIVE_DENY | Подмена/недоступность фактов/новый запрет; разрешение отозвано |
| CONTINUATION_EXPIRED / REVOKED / CONSUMED | Истекло/отозвано/уже использовано; запуск запрещён |
| CALL_ALREADY_REQUESTED / SESSION_CAPACITY / SESSION_CLOSED | Повтор вызова либо завершённая/исчерпанная сессия; без автоматического нового запроса |

Если срок истёк во время повторной проверки, текущий consume возвращает EXPIRED,
разрешение отзывается, последующий consume возвращает REVOKED.
Разрешение потребляется **до** spawn и не восстанавливается даже при доказанном
not_started: нужна отдельная новая попытка и новое решение. Тайм-аут, потеря результата,
прерывание после возможного запуска — unknown; никакого retry.

Ошибка разрешения до первого дочернего процесса означает только not_started для
этого дочернего процесса. Если восстановление уже прошло, а разрешение verify не
получено, вся recovery не превращается в not_started: сохранить результат восстановления,
пометить verify как не запущенный, проверку как незавершённую, блокировку оставить.
Интеграция должна ловить AuthorizationError явно, не превращать её общий обработчик
исключений в ложное утверждение о запуске или отсутствии всей операции.

## 6. Охват служебных записей и граница запуска

Process-разрешение охватывает один дочерний процесс с данным снимком, не создание
комплекта, journal/ACTIVE/INCIDENT_BLOCKED и не последующее снятие блокировки.
Эти служебные записи выполняются agent-safe в рамках отдельно разрешённого входа
в recovery с известными служебными путями и исходной транзакцией. Доверенный код
подключения обязан проверять это исходное разрешение **до** служебных записей.
Если подтверждённого входа нет, управляемый режим не начинает подготовительные записи.
Ручной CLI сохраняет прежнюю семантику; его --approved не преобразуется в managed grant.

Порядок перед каждым spawn: проверка связанной блокировки/цели и original PreparedProcess;
consume с повторным acquire/native check; немедленный _run с исходными argv/cwd/stdin.
Если дополнительная runtime-проверка после consume не прошла, разрешение остаётся
израсходованным. Между проверкой пути и spawn остаётся обычная гонка stdlib; защита
от root/malware и враждебного кода внутри владельца не заявляется.

## 7. Приёмка и остаток

Автоматические проверки в `tests/test_prepared_process_contract.py` используют только
искусственные факты и имитацию событий host. Проверяются оба платформенных формата,
границы argv/stdin, большие числа, все привязки, срок, отмена, подделка, повтор,
дрейф, native veto и одновременное потребление — успешно только одно.
Существующий корпус classifier/identity проверяется без изменения его кода.

Это не end-to-end доказательство авторизации OpenCode. Для закрытия #34 нужны:
подключение agent-safe на точном API; проверка ошибок на реальной границе _run;
подлинный native host continuation в фактическом размещении и отдельное доказательство
его связи с HostPort; поддержанный способ поставки модулей. До этого никакой managed
режим не включать. Точное задание потребителю: [agent_safe_prepared_integration_task_ru.md](agent_safe_prepared_integration_task_ru.md).
