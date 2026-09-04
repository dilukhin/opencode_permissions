# DC-4: exact OpenCode 1.18.26 adapter и runtime proof

Статус: **PASS** для ограниченного Linux-профиля, описанного ниже.

Этот документ фиксирует доказанный runtime-path DC-4. Он не является production deployment guide и не расширяет native permission policy.

## 1. Цель

DC-4 закрывает разрыв между детерминированным classifier core/analyzers и фактическим OpenCode permission lifecycle:

`native ASK -> trusted adapter -> deterministic classifier -> exact ALLOW -> reply once -> pre-spawn revalidation -> ShellTool execution`

При этом сохраняются инварианты проекта:

- native `DENY` терминален;
- native `ALLOW` не переоценивается classifier-ом;
- classifier вызывается только из native `ASK`;
- classifier не получает право исполнения как отдельную capability;
- unsupported/opaque input не становится `ALLOW`;
- изменение среды или identity после classifier result блокирует выполнение до spawn;
- `--auto`, `--yolo`, `dangerously-skip-permissions` и blanket `bash: allow` не используются.

## 2. Exact runtime profile

Доказанный профиль:

- OpenCode: **1.18.26**;
- platform: Linux;
- shell: exact `/bin/dash`;
- adapter profile: `dc4-opencode-1.18.26-dash-static-v1`;
- доказанный executable family: exact `/usr/bin/printf`;
- официальный Linux x64 release artifact проверяется до запуска по SHA-256:
  `7c20c1ffa91bcca0ac903752260bcc36307dff656833baead2f5ef3b224b16c6`.

CI дополнительно требует, чтобы скачанный binary сообщил ровно `1.18.26`.

Совпадение по semver или ближайшей версии не считается совместимостью.

## 3. Strict adapter

Реализация: `tools/opencode_dc4_adapter.py`.

Adapter намеренно не является general shell parser. Для `ALLOW` принимается только узкий статический command shape:

- одна simple command;
- executable задан абсолютным POSIX path;
- нет redirect, pipeline, compound operators, command substitution, variable expansion, quoting, wildcard/glob и других dynamic shell constructs;
- executable находится в явном allowlist adapter profile;
- shell находится в явном allowlist adapter profile;
- cwd находится внутри workspace boundary.

Все остальные формы fail closed в `ASK_USER`.

### 3.1 Executable identity

Перед classifier `ALLOW` adapter проверяет executable и связывает результат с фактическим объектом:

- regular executable file;
- owner UID = 0;
- нет group/world write;
- executable path в текущем профиле не должен быть symlink;
- фиксируются `resolved_path` и object identity;
- object identity включает file metadata и SHA-256 содержимого.

Semantic analyzer получает доказанное имя команды только после этой проверки. Затем semantic result заново связывается с фактическим absolute executable и exact argv в `NormalizedOperation`.

Таким образом basename сам по себе не является основанием для `ALLOW`.

### 3.2 Shell и cwd identity

Guard также связывает:

- requested/resolved shell и его object identity;
- cwd lexical path и object identity;
- workspace boundary;
- итоговый `operation_identity`.

### 3.3 Runtime guard

После classifier `ALLOW` adapter сохраняет guard, содержащий exact command, shell, executable, cwd и `operation_identity`.

Непосредственно перед ShellTool spawn выполняется повторная `prepare()`-проверка. Для продолжения требуется полное равенство нового guard исходному. Любой identity drift переводит path в fail-closed error до выполнения команды.

Кроме этого, adapter-path связывает process environment snapshot. Изменение environment между classifier result и spawn также блокирует выполнение.

## 4. Интеграция с фактическим OpenCode permission lifecycle

Runtime fixture использует обычный OpenCode ShellTool `bash` permission path, а не direct `SessionPrompt.shell`.

Project-local proof plugin:

1. перехватывает `tool.execute.before` для `bash`;
2. сохраняет exact command, cwd, session ID и call ID;
3. слушает фактическое событие `permission.asked`;
4. принимает ASK только если `request.tool.callID` совпадает с ранее зарегистрированным call ID и `metadata.command` совпадает с exact command;
5. запускает deterministic adapter;
6. при результате, отличном от exact `ALLOW`, отвечает `reject`;
7. при exact `ALLOW` отвечает только `once`;
8. на `shell.env` выполняет pre-spawn revalidation;
9. при drift бросает fail-closed error до spawn.

### 4.1 Exact legacy SDK reply

OpenCode 1.18.26 передаёт project plugin legacy `@opencode-ai/sdk` client. В этом client нет v2-style `client.permission.reply`.

Доказанный reply path использует generated legacy method:

`postSessionIdPermissionsPermissionId`

с привязкой:

- session path ID = permission request `sessionID`;
- permission path ID = permission request `id`;
- body response = `once` или `reject`;
- directory query = текущий instance directory.

Это version-sensitive часть adapter contract.

## 5. Runtime acceptance scenarios

Fixture выполняет только non-destructive `/usr/bin/printf` cases с synthetic sentinel output.

### 5.1 Native ALLOW

Native rule для exact command = `allow`.

Ожидается и подтверждено:

- `tool.execute.before` наблюдается;
- `permission.asked` отсутствует;
- classifier не вызывается;
- `shell.env` проходит native passthrough;
- команда реально выполняется;
- exact sentinel присутствует в tool output;
- `tool.execute.after` наблюдается.

Это доказывает, что classifier не перехватывает terminal native ALLOW.

### 5.2 Native DENY

Native rule для exact command = `deny`.

Ожидается и подтверждено:

- `tool.execute.before` наблюдается;
- tool заканчивается error;
- `permission.asked` отсутствует;
- classifier не вызывается;
- `shell.env` не достигается;
- `tool.execute.after` отсутствует;
- sentinel не выполняется.

Это доказывает terminal precedence native DENY.

### 5.3 Native ASK -> classifier ALLOW

Native rule для exact command = `ask`.

Ожидается и подтверждено:

- `tool.execute.before`;
- фактический `permission.asked`;
- exact call-ID/command correlation;
- deterministic classifier возвращает `ALLOW` с валидным `sha256:` operation identity;
- legacy SDK reply `once`;
- `shell.env` guard успешно повторно подтверждает operation identity и environment;
- команда реально выполняется;
- exact sentinel присутствует;
- `tool.execute.after` наблюдается.

В trace `shell_env_guard_pass` может появиться раньше post-`await` marker `permission_reply_once`: продолжение permission deferred способно начать ShellTool continuation до возврата HTTP/SDK call в plugin handler. Acceptance поэтому проверяет наличие обеих стадий и terminal execution result, а не ошибочно трактует порядок trace-записей как порядок authorization transition.

### 5.4 ASK -> classifier ALLOW -> environment drift

После exact classifier `ALLOW` fixture намеренно меняет environment до spawn.

Ожидается и подтверждено:

- `tool.execute.before`;
- `permission.asked`;
- classifier exact `ALLOW` с operation identity;
- reply `once` инициирует continuation;
- `shell.env` фиксирует `environment_drift`;
- tool заканчивается error;
- guard pass отсутствует;
- `tool.execute.after` отсутствует;
- sentinel не выполняется.

Это доказывает fail-closed TOCTOU guard для доказанного environment dependency.

## 6. Изоляция runtime fixture

Первые варианты fixture выявили скрытую network dependency OpenCode instance bootstrap.

В exact 1.18.26 `Config` запускает background `Npm.install` для config directories, добавляя `@opencode-ai/plugin`. При наличии project-local plugin `plugin.init()` вызывает `config.waitForDependencies()` до загрузки plugin. На чистом temporary HOME это могло ожидать npm registry и блокировать первый directory-scoped request.

Финальная fixture не подделывает lockfile или installed package state. Вместо этого она использует штатную ветку exact `Npm.install`:

- заранее создаёт необходимые temporary config directories и `.gitignore`;
- делает global OpenCode config directory и project `.opencode` readable, но non-writable на время процесса;
- exact `Npm.install` при `canWrite == false` возвращает без `reify`/network;
- после завершения OpenCode права восстанавливаются для cleanup.

Loopback HTTP controller также явно не использует proxy environment.

Таким образом после скачивания и проверки exact OpenCode release artifact runtime proof не зависит от npm registry или внешнего LLM provider.

## 7. Что DC-4 не доказывает

DC-4 **не** означает:

- поддержку arbitrary shell syntax;
- blanket trust к `/bin/dash` или `bash`;
- разрешение arbitrary absolute executable;
- Windows runtime deployability classifier adapter;
- совместимость с OpenCode новее или старше 1.18.26;
- production deployment permission policy;
- безопасность direct `SessionPrompt.shell` как model-tool authorization path;
- право auditor/model самостоятельно разрешать выполнение;
- возможность обходить native DENY.

Неподдерживаемая форма остаётся `ASK_USER`.

## 8. Acceptance contract

DC-4 считается PASS только если одновременно выполняются условия:

1. exact OpenCode 1.18.26 artifact checksum и version check проходят;
2. native ALLOW выполняет sentinel без classifier path;
3. native DENY блокирует до execution;
4. native ASK проходит через real `permission.asked` и exact call-ID/command correlation;
5. classifier `ALLOW` имеет complete normalized operation и `operation_identity`;
6. reply ограничен `once`;
7. pre-spawn shell/executable/cwd/environment revalidation проходит для неизменённой операции;
8. environment drift блокирует до spawn;
9. unsupported adapter input остаётся non-ALLOW;
10. общий regression suite остаётся зелёным на поддерживаемой CI matrix.

При выполнении этих условий DC-4 закрывает runtime-integration criterion deterministic classifier gate для exact Linux/OpenCode 1.18.26 profile.
