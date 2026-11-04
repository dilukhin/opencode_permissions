# Длительные sudo-job: допуск OpenCode 2.0.23

Дата проверки: 07.10.2026. Связанные задачи: [#46](https://github.com/dilukhin/opencode_permissions/issues/46), [agent-safe#36](https://github.com/dilukhin/agent-safe/issues/36), [ssh_relay#52](https://github.com/dilukhin/ssh_relay/issues/52).

Статус: **исходный код проверен; совместимость и доверенный путь исполнения ещё не подтверждены**.

## 1. Результат

Готовый разбор CLI `sudo-job` нельзя считать готовым подключением к OpenCode 2.0.23. Транспорт ssh_relay 0.13.0 и совместный жизненный цикл agent-safe проверены отдельно. В этой работе проверен официальный исходный код OpenCode, а не работа установленного приложения.

Последняя версия, показанная пользователем 05.10.2026, — `opencode v2.0.23`. Это историческое наблюдение, не новое чтение с его компьютера. В текущем реестре проекта целевая версия остаётся 1.18.32; записи для 2.0.23 нет. Неизвестная версия должна сохранять `UNVALIDATED_OPENCODE_VERSION`, без подбора ближайшей.

Проверен тег `v2.0.23` репозитория `anomalyco/opencode`, указывающий на коммит `0fd7e2829449b052abf0078666669302923d77af`. В `packages/cli/package.json` указаны имя `@opencode/cli` и версия `2.0.23`.

## 2. Что изменилось относительно исследования 1.18.x

| Граница | Наблюдение на 2.0.23 | Следствие |
| --- | --- | --- |
| Контекст инструмента | `packages/schema/src/tool.ts`: `sessionID`, `agent`, `messageID`, `id`, `progress`; прежнего `ctx.ask` в этом интерфейсе нет | Старый пример подключения не переносится буквально |
| Контракт плагина | `packages/plugin/src/promise/tool.ts`: `ToolContext`, `signal`, `execute.before/after`, редактор инструментов | Требуется отдельная проверка нового интерфейса |
| Ожидание решения | `Permission.assert` в `packages/core/src/permission.ts` ждёт `Deferred`; `Permission.ask` только создаёт запрос и возвращает его ID/решение | Вызов `ask` сам по себе не подтверждает согласие и не разрешает запуск |
| Отказ | Сконфигурированный `deny` проверяется до сохранённых разрешений и события плагина; `assert` возвращает `BlockedError` | Жёсткий запрет нельзя отменять своим разрешением |
| Одноразовое решение | `reply` завершает ожидающий запрос; `always` при наличии `save` пишет сохранённые правила | Для root-операции нужен путь с пустым `save` и одной точной операцией |
| API решения | `POST /api/session/:sessionID/permission/:requestID/reply`; сервер сверяет принадлежность запроса сессии | Это проверка адресата запроса, не отдельное доказательство действия человека |
| Пароль сервера | `packages/server/src/process.ts` отказывает без пароля; штатный CLI выбирает введённый или случайный пароль | Старый вывод об отсутствии обязательного пароля нельзя без проверки переносить на штатный запуск 2.0.23 |
| Наследование пароля | В `packages/cli/src/server-process.ts` удаление `OPENCODE_PASSWORD` и `OPENCODE_SERVER_PASSWORD` выполняется **только при `options.mode === "stdio"`** | Это полезное ограничение одного режима, не доказательство изоляции всех способов запуска |
| Окружение команд | `Shell.create` использует `sessionEnvironment ?? process.env`, затем вызывает изменяемый обработчик `shell/create.before` | Проверить происхождение окружения сессии и расширения, а не только два удаляемых имени |
| Право плагина | `PluginHost` предоставляет `permission.list/get/reply` | Состав доверенных плагинов и запрет их подмены входят в границу доверия |

Уточнение: `ServerAuth.Config.layer` сам по себе допускает отсутствие пароля, а middleware тогда пропускает запрос. Наличие проверки в штатном `ServerProcess.start` не доказывает, что всякий встроенный или сторонний способ создания сервера использует именно этот путь.

Удаление переменных в режиме `stdio` устраняет прежнее прямое наследование этих имён в данном пути. Оно не доказывает недоступность учётных данных через родительский процесс, файлы службы/подключения, другой режим запуска, окружение сессии, MCP, терминалы или расширения. В этой работе эти возможности не испытаны и не объявлены уязвимостями.

## 3. Проверенная граница трёх компонентов

- ssh_relay PR #55 слит в `main@6d3973f453e0eb93807626914460d43c42510940`, версия 0.13.0.
- На точном HEAD `b9b68559c3ceff0a2a9a7762d54d0788a47f879a` успешны общий CI, установка пакета и четыре Ubuntu/Windows → Ubuntu испытания.
- agent-safe PR #37: `c896e8f658b55a70f77b242ecf4deb8e637d5112`; [совместный прогон 37629354123](https://github.com/dilukhin/agent-safe/actions/runs/37629354123) успешен с тем же точным ssh_relay.
- opencode_permissions PR #47: `0248ed931d7879e8721c26be5cbad4b531201639`; [CI 37530012018](https://github.com/dilukhin/opencode_permissions/actions/runs/37530012018) успешен.

В agent-safe кандидат `ssh_relay_sudo_job.start/stop` пока принимает библиотечный `approved: bool`. Успешный стенд использует этот библиотечный вход и не доказывает, что значение пришло из доверенного подтверждения OpenCode. `BrokerStateModel` остаётся имитацией. Локальный PreparedProcess из другого PR не выдаёт разрешение для удалённой root-операции.

## 4. Следующий проверяемый шаг

Сначала выполнить отдельную проверку **без удалённой мутации**, на точной сборке OpenCode 2.0.23:

1. Зафиксировать происхождение исполняемого файла и его SHA-256. Проверить точную версию; не менять пользовательскую установку или действующую конфигурацию.
2. В одноразовой среде установить новый доверенный испытательный инструмент. Сохранить внутри владельца неизменяемые параметры искусственного `start` или `stop`, включая локальный вызов, SSH-цель, UUID, hash команды, ожидаемый результат и роль. Модели не передавать объект разрешения.
3. Проверить реальный путь `Permission.assert → once/reject → продолжение того же вызова`. Ответ испытательной программы через API явно считать имитацией интерфейса человека. Он может доказать маршрутизацию и ожидание, но не происхождение настоящего согласия.
4. Отдельно доказать недоступность решения из дочернего процесса, недоверенного инструмента/плагина и другого вызова. Проверять только искусственные данные; не выводить пароль или содержимое окружения.
5. Проверить native `deny`, отмену, прерывание вызова и выход владельца. Во всех этих случаях исполнитель не вызывается.
6. Сопоставить точный запрос с отдельным разрешением на потребление непосредственно перед запуском. Дрейф любого существенного поля, повторное потребление, смена сессии/цели/поколения должны отказать. После допуска `start` нельзя допускать `stop` без отдельного решения.

Если штатная граница в выбранном режиме 2.0.23 выдержит проверку, уточнить минимальный вариант доверенного продолжения. Если нет — вернуться к защищённому местному посреднику из прежнего исследования, проверяя регистрацию живого процесса и недоступность интерфейса дочерним процессам. Само изменение версии не принимает ни один из вариантов.

Только после этой проверки подключать отдельный допуск `start/stop` к agent-safe и выполнять в GitHub Actions весь путь с одноразовым Ubuntu: разрешение → запуск → неизвестный исход/восстановление наблюдения → завершение → точная проверка результата. Производные разрешения и автоматический повтор после `unknown` недопустимы.

## 5. Источники для повторной проверки

Все ссылки закреплены за одним официальным коммитом:

- [packages/cli/package.json](https://github.com/anomalyco/opencode/blob/0fd7e2829449b052abf0078666669302923d77af/packages/cli/package.json) — Git blob `e8e0bf6bb9bb8b915915d82b826dd1a6d16550eb`.
- [packages/cli/src/server-process.ts](https://github.com/anomalyco/opencode/blob/0fd7e2829449b052abf0078666669302923d77af/packages/cli/src/server-process.ts) — Git blob `48c036c48bbb2e04d3a3ded26cd2a178b6f26da0`.
- [packages/server/src/process.ts](https://github.com/anomalyco/opencode/blob/0fd7e2829449b052abf0078666669302923d77af/packages/server/src/process.ts) — Git blob `1c11586d6308d3f79d1501fb653911bda74f7a8b`.
- [packages/server/src/auth.ts](https://github.com/anomalyco/opencode/blob/0fd7e2829449b052abf0078666669302923d77af/packages/server/src/auth.ts) — Git blob `2dc0a19daf84e8502ef27a8b3e6a75e9bbc42efa`.
- [packages/server/src/middleware/authorization.ts](https://github.com/anomalyco/opencode/blob/0fd7e2829449b052abf0078666669302923d77af/packages/server/src/middleware/authorization.ts) — Git blob `84906429d776a0c1062e78cee58fd5ea0d84e330`.
- [packages/core/src/permission.ts](https://github.com/anomalyco/opencode/blob/0fd7e2829449b052abf0078666669302923d77af/packages/core/src/permission.ts) — Git blob `2aecebb0ce347c9acfc7e8dbec0f6c1b7d5951b9`.
- [packages/schema/src/tool.ts](https://github.com/anomalyco/opencode/blob/0fd7e2829449b052abf0078666669302923d77af/packages/schema/src/tool.ts) — Git blob `06dec1c0c57c1a6c5809eae1bd61a89e1b9cd8c1`.
- [packages/plugin/src/promise/tool.ts](https://github.com/anomalyco/opencode/blob/0fd7e2829449b052abf0078666669302923d77af/packages/plugin/src/promise/tool.ts) — Git blob `5eb814e39807fa416dcfaed47e6213922c677113`.
- [packages/protocol/src/groups/permission.ts](https://github.com/anomalyco/opencode/blob/0fd7e2829449b052abf0078666669302923d77af/packages/protocol/src/groups/permission.ts) — Git blob `9085a51f9f892ebbab0e0bae332402c088e65d31`.
- [packages/server/src/handlers/permission.ts](https://github.com/anomalyco/opencode/blob/0fd7e2829449b052abf0078666669302923d77af/packages/server/src/handlers/permission.ts) — Git blob `72b61c0fbd7b19968a7934d6a641405d0f9ebb34`.
- [packages/core/src/shell.ts](https://github.com/anomalyco/opencode/blob/0fd7e2829449b052abf0078666669302923d77af/packages/core/src/shell.ts) — Git blob `393275517141031266f3c9819449fb5c78cc887f`.
- [packages/core/src/session/environment.ts](https://github.com/anomalyco/opencode/blob/0fd7e2829449b052abf0078666669302923d77af/packages/core/src/session/environment.ts) — Git blob `0991badb57db49e457a50ead40b47b52496569d7`.
- [packages/core/src/plugin/host.ts](https://github.com/anomalyco/opencode/blob/0fd7e2829449b052abf0078666669302923d77af/packages/core/src/plugin/host.ts) — Git blob `1f1e5b54bc53b99e64f31447274e3fdf9409601e`.

## 6. Граница доказательств

Проверены содержимое исходников, тип и точный SHA тега, реестр совместимости и результаты указанных CI. Новый OpenCode 2.0.23 здесь не запускался; его профиль не принят; действующие разрешения, поставка и установленный runtime не изменены. Чтение release API по тегу v2.0.23 дало 404 при существующем теге и исходном package.json; это не означает отсутствия установленной сборки и не позволяет подставить архив 1.18.x. Способ получения точной испытательной сборки нужно подтвердить отдельно.
