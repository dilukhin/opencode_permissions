# Stage 0C — parser-only closure для nested interpreter payload

Статус: CLOSED  
Дата: 2026-08-17  
Проект: `dilukhin/opencode_permissions`  
Target runtime: OpenCode `1.18.18`  
Exact OpenCode upstream commit: `31406ccc51b4bd2a4e1e086b2bcaa5f7f804f26d`

## 1. Цель

Stage 0B оставил один существенный residual question: разбирает ли native shell permission layer строковый payload вложенных interpreters как отдельные commands/effects.

Проверяемые формы:

```text
bash -c "..."
sh -c "..."
powershell -Command "..."
pwsh -Command "..."
cmd /c "..."
python -c "..."
node -e "..."
```

Задача 0C — снять эту неопределённость безопасно, не исполняя payload и не расширяя доступ к auth/secrets.

## 2. Почему выбран parser-only source/grammar analysis

OpenCode 1.18.18 `ShellTool`:

1. выбирает Tree-sitter parser по фактическому shell;
2. парсит всю shell command line;
3. собирает `root.descendantsOfType("command")`;
4. для каждого найденного command node создаёт native `bash` permission pattern из source text;
5. only after permission checks запускает process.

Следовательно, вопрос о nested interpreter payload сводится к детерминированному вопросу grammar: становится ли строка после `-c`, `-Command`, `/c` или `-e` вложенным `command` node.

Exact dependency versions OpenCode 1.18.18:

```text
web-tree-sitter          0.25.10
tree-sitter-bash        0.25.0
tree-sitter-powershell  0.25.10
```

Это позволяет закрыть вопрос parser-only по exact source и exact grammar, без LLM/model/auth/runtime mutation.

Попытка дополнительно поднять эти exact NPM packages в isolated ChatGPT execution `/tmp` была остановлена network timeout до появления dependencies. Это не меняет вывод: project/user files не затрагивались, а authoritative grammar source доступен по exact tags.

## 3. Bash / POSIX grammar

OpenCode 1.18.18 использует `tree-sitter-bash 0.25.0`, exact tag commit:

`tree-sitter/tree-sitter-bash@56b54c61fb48bce0c63e3dfa2240b5d274384763`.

Grammar определяет shell command как:

```text
command name + literal arguments/redirections
```

Double-quoted argument — `string`; обычный текст внутри него — `string_content`.

Внутри string grammar отдельно распознаёт только реальные shell constructs языка, например:

- variable expansion;
- command substitution `$(...)`;
- arithmetic expansion.

Обычный текст вроде `echo ok; rm x` внутри кавычек не превращается во второй `command` node текущего shell parse.

### Следствие

Для:

```text
bash -c "echo ok; <payload>"
sh -c "echo ok; <payload>"
python -c "<python payload>"
node -e "<javascript payload>"
```

native outer-shell AST видит outer command (`bash`, `sh`, `python`, `node`) и его string argument. Он **не выполняет recursive parse payload на языке вложенного interpreter**.

Если внутри quoted string присутствует настоящий syntax-level command substitution текущего Bash, например `$(...)`, Tree-sitter Bash может увидеть его как вложенный shell construct. Это отдельный случай и не означает recursive parsing `-c/-e` payload.

Confidence: **high / exact upstream source + exact dependency grammar**.

## 4. PowerShell grammar на Windows

OpenCode 1.18.18 использует `tree-sitter-powershell 0.25.10`, exact tag commit:

`airbus-cert/tree-sitter-powershell@7212f47716ced384ac012b2cc428fd9f52f7c5d4`.

PowerShell grammar различает:

- outer `command`;
- command parameters;
- command arguments / generic tokens;
- string literals;
- настоящие PowerShell expressions/subexpressions/script blocks.

Quoted string literal может содержать PowerShell subexpression, но простой текст внутри строки сам по себе не становится новым statement/command list.

OpenCode при этом по-прежнему собирает только descendant nodes типа `command` из **одного** PowerShell parse дерева.

### Следствие для target Windows environment

Типовые формы:

```text
powershell -Command "<payload>"
pwsh -Command "<payload>"
cmd /c "<payload>"
python -c "<payload>"
node -e "<payload>"
```

дают native permission visibility outer command + raw argument text, но не semantic recursive parsing языка, который затем интерпретирует payload.

Отдельно: PowerShell syntax-level constructs, которые grammar действительно моделирует как script block/subexpression/pipeline, могут содержать nested `command` nodes и покрываются лучше. Это не распространяется автоматически на opaque quoted payload другого interpreter.

Confidence: **high / exact upstream source + exact dependency grammar**.

## 5. Что native permission всё же видит

`opaque payload` не означает, что строка исчезает из approval pattern.

Для outer command native `bash` permission pattern строится из source text command node. Поэтому строковый payload присутствует как **raw text части outer pattern**.

Проблема состоит в другом:

- native matcher не классифицирует effects этого payload;
- он не знает, что `python -c` содержит file delete, network call или subprocess, если это выражено только кодом в строке;
- broad allow rule на interpreter prefix может автоматически разрешить семантически опасный payload.

Следовательно, native rules могут безопасно использовать exact/узкие patterns, но не должны считать `bash *`, `python *`, `node *`, `cmd *`, `powershell *` безопасными по имени interpreter.

## 6. Подтверждённая граница native layer

Native parser хорошо покрывает syntax текущего shell:

```text
&&
||
;
pipelines
redirects
command substitutions
PowerShell pipelines/conditionals/subexpressions
```

Но он **не является recursive multi-language effect parser**.

Граница формулируется так:

```text
current-shell syntax tree        -> parsed into multiple command nodes where grammar exposes them
opaque interpreter string payload -> retained as raw outer-command text, not semantically decomposed
```

Это доказанный gap native layer и будущий input для deterministic classifier gate — но classifier пока не начинается.

## 7. Решение по installed-runtime probe

Installed-runtime `opencode run` может отображать requested permission patterns и при отсутствии `--auto` reject-ить request до execution. Это потенциально полезный control mechanism.

Однако для текущего 0C он не требуется:

- unresolved question уже однозначно закрыт exact parser source/grammar;
- `opencode run` добавляет model selection/auth/network behavior, не относящиеся к parser question;
- полная XDG isolation уводит OpenCode `auth.json`, а перенос/чтение secret auth material только ради probe нарушил бы минимальность эксперимента;
- normal OpenCode bootstrap создаёт global data/config/state/cache directories, поэтому runtime experiment требует дополнительной isolation machinery.

Решение: **не выполнять installed-runtime probe только ради дублирования parser fact**.

Если позднее 0D real-workflow observation естественным образом покажет такой request, его можно сохранить как дополнительное runtime evidence без расширения scope.

## 8. Safety result

В 0C:

- destructive payload не исполнялся;
- `--auto` не использовался;
- active user config не изменялся;
- `auth.json`/secret contents не читались и не копировались;
- remote mutation не выполнялась;
- project/runtime logic не менялась.

`unsafe_test_allow_count = 0`.

## 9. Gate decision

Stage 0C — **CLOSED**.

Подтверждено:

1. current-shell compound syntax разбирается native AST;
2. quoted nested-interpreter payload не получает recursive semantic parse;
3. raw payload остаётся видимым в outer permission pattern;
4. broad interpreter allow rules технически опасны и не должны использоваться;
5. этот gap относится к будущему deterministic effect-classifier analysis, а не является основанием немедленно реализовывать classifier до закрытия Stage 0.

## 10. Gate state после 0C

```text
0A.1 Minimal inventory        CLOSED
0A.2 Resolved permissions     UNAVAILABLE via debug config for 1.18.18
0B   Version-locked audit     CLOSED
0C   Parser-only probes       CLOSED
0D   Real workflow baseline   READY

Stage 0                      NOT CLOSED
Native-policy gate           NOT STARTED
Classifier                   NOT STARTED
```

Следующая bounded задача: спроектировать и выполнить 0D real-workflow prompt baseline на target OpenCode 1.18.18 без изменения permission policy.
