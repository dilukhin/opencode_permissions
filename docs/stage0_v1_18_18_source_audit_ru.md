# Stage 0B — version-locked source audit OpenCode 1.18.18

Статус: 0B closed; residual runtime questions routed to 0C  
Дата: 2026-08-17  
Проект: `dilukhin/opencode_permissions`  
Target runtime: OpenCode `1.18.18`  
Exact upstream ref: `anomalyco/opencode` tag/version source at commit `31406ccc51b4bd2a4e1e086b2bcaa5f7f804f26d`

## 1. Назначение

Документ фиксирует version-specific результаты Stage 0B после локального 0A.1. Это findings/evidence для исследуемой версии, а не persistent architecture baseline.

Source priority для этого аудита:

1. runtime observation 0A.1;
2. upstream source/tests exact commit;
3. documentation из того же exact commit;
4. current docs/issues только как дополнительный контекст.

При конфликте exact docs и exact runtime source/tests приоритет имеет source/tests.

## 2. Решение по 0A.2 resolved-config probe

### Решение

`opencode --pure debug config` для OpenCode 1.18.18 **не разрешён** как read-only 0A.2 mechanism.

`--pure` означает `run without external plugins`; это не режим без побочных эффектов.

`debug config` использует обычный `effectCmd` с instance bootstrap. В exact source bootstrap включает загрузку config, plugin initialization и другие instance services.

Config loading в этой версии может:

- читать auth state;
- получать remote/well-known config;
- переписывать config для добавления `$schema`;
- создавать config/default files при соответствующем состоянии;
- создавать служебный `.gitignore`;
- запускать dependency/plugin installation для config directories;
- выполнять migration старых config files.

Следовательно, команда не соответствует Stage 0 read-only acceptance даже с `--pure` и `OPENCODE_DISABLE_AUTOUPDATE=true`.

### Следствие

- `tools/stage0_inventory.py --resolved-permissions` не запускать для target 1.18.18.
- Не пытаться компенсировать это чтением `auth.json`, raw logs или secret-bearing config.
- Effective permissions устанавливать из metadata + exact source semantics + минимальных isolated runtime probes, где они действительно нужны.

Evidence:

- `packages/opencode/src/index.ts` — semantics `--pure`;
- `packages/opencode/src/cli/effect-cmd.ts` — default instance bootstrap;
- `packages/opencode/src/cli/cmd/debug/config.ts` — `debug config` не отключает instance;
- `packages/opencode/src/project/bootstrap.ts`;
- `packages/opencode/src/project/instance-store.ts`;
- `packages/opencode/src/config/config.ts`.

Confidence: **high / upstream_source**.

## 3. Config loading / precedence

Exact source подтверждает deep-merge config layers. Later layers override conflicting earlier values; non-conflicting values сохраняются.

Основная последовательность для target version:

1. remote/well-known configuration, если она доступна через auth/provider context;
2. global config;
3. file from `OPENCODE_CONFIG`;
4. project config files, если project config не отключён;
5. config directories (`.opencode`/configured directories) и найденные commands/agents/modes/plugins/tools;
6. `OPENCODE_CONFIG_CONTENT`;
7. active organization/account remote config;
8. managed config files;
9. macOS managed preferences;
10. `OPENCODE_PERMISSION` дополнительно merge-ится в final permission config.

Внутри config location JSON/JSONC variants также merge-ятся по source order. Legacy `tools` booleans переводятся в permission defaults; explicit `permission` имеет преимущество над этим legacy mapping.

Exact documentation того же commit подтверждает общий принцип merge и порядок remote -> global -> custom -> project -> `.opencode` -> inline -> managed.

Evidence:

- `packages/opencode/src/config/config.ts`;
- `packages/web/src/content/docs/config.mdx`.

Confidence: **high / upstream_source + exact_docs**.

## 4. Native permission schema

Exact V1 schema использует `permission`, а shell permission key остаётся `bash`, включая PowerShell/cmd compatibility path.

Actions:

```text
allow
ask
deny
```

Поддерживаются granular pattern maps. Runtime parser сохраняет order rules, так как порядок влияет на precedence.

Основные permission keys target version включают:

```text
read
edit
glob
grep
list
bash
task
external_directory
todowrite
question
webfetch
websearch
lsp
doom_loop
skill
```

Schema допускает также дополнительные string permission keys.

Evidence:

- `packages/core/src/v1/config/permission.ts`;
- `packages/opencode/src/tool/shell/id.ts`.

Confidence: **high / upstream_source**.

## 5. Matcher semantics

Runtime `Permission.evaluate()`:

- flatten-ит rulesets;
- выбирает **last matching rule** по permission и pattern;
- если подходящей rule нет, результат implicit `ask`;
- wildcard matching используется и для permission name, и для resource pattern.

Это совпадает с exact documentation: last matching rule wins.

### `once / always / reject`

- `once` разрешает только текущий pending request и не создаёт in-memory allow rule;
- `always` добавляет в instance-local approved state allow rules для `always` patterns, предложенных самим tool;
- такие approvals не переписывают config;
- `reject` отклоняет request и другие pending requests той же session;
- approved state непостоянный и живёт в instance/session runtime, а не в config file.

Evidence:

- `packages/opencode/src/permission/index.ts`;
- `packages/web/src/content/docs/permissions.mdx`.

Confidence: **high / upstream_source + exact_docs**.

## 6. Default permissions и конфликт docs/source

Exact runtime source формирует базовый ruleset примерно так:

```text
*                  allow
doom_loop          ask
external_directory ask
question           deny
plan_enter         deny
plan_exit          deny
read *             allow
read *.env         ask
read *.env.*       ask
read *.env.example allow
```

Важно: exact documentation из того же upstream commit утверждает, что `.env` default — `deny`, но exact runtime source задаёт `ask`.

Для target OpenCode 1.18.18 project policy должна считать runtime source авторитетным: **`.env` default = ask**, пока runtime probe не покажет обратное.

Это version-locked evidence of documentation drift и причина не переносить docs semantics без проверки source/tests.

Evidence:

- `packages/opencode/src/agent/agent.ts`;
- `packages/web/src/content/docs/permissions.mdx`.

Confidence: **high / upstream_source**, conflict recorded.

## 7. Shell permission parsing

Shell tool target version использует Tree-sitter AST до исполнения shell command.

Для parsed tree он собирает descendant `command` nodes и формирует отдельные `bash` permission patterns. Поэтому native layer не ограничивается match по первой executable/raw command string.

Exact upstream tests подтверждают:

- `echo foo && echo bar` -> separate patterns `echo foo`, `echo bar`;
- PowerShell conditional/`;` constructs -> separate command patterns;
- Bash command substitution `echo $(cat ...)` -> nested `cat ...` pattern;
- PowerShell command substitution -> nested command pattern;
- redirect `echo test > output.txt` -> redirect входит в permission pattern;
- external paths у известных file-oriented commands обнаруживаются до execution;
- external workdir вызывает `external_directory` request.

### Suggested `always` patterns

Tool использует `BashArity.prefix(tokens)` и добавляет ` *`.

Примеры exact semantics:

```text
ls -la                    -> ls *
git log --oneline -5      -> git log *
Remove-Item -Recurse tmp  -> Remove-Item *
npm run dev               -> npm run dev *
```

Arity dictionary определяет human-understandable command/subcommand prefix; unknown command по default использует первый token.

Evidence:

- `packages/opencode/src/tool/shell.ts`;
- `packages/opencode/src/permission/arity.ts`;
- `packages/opencode/test/tool/shell.test.ts`.

Confidence: **high / upstream_source + upstream_test**.

## 8. Residual uncertainty: interpreter payload

Upstream source/tests не дают достаточного подтверждения рекурсивного анализа строкового payload для:

```text
bash -c "..."
sh -c "..."
powershell -Command "..."
pwsh -Command "..."
cmd /c "..."
python -c "..."
node -e "..."
```

AST traversal подтверждён для shell syntax/command substitution, но строковый argument interpreter может остаться частью outer command pattern, а не быть повторно разобран как отдельная program semantics.

В exact `shell.test.ts` нет regression tests для `bash -c`, `python -c` и `cmd /c` payload parsing.

Статус: **residual uncertainty -> Stage 0C**.

До 0C эти конструкции нельзя считать безопасно разобранными native layer и нельзя auto-allow широким interpreter prefix rule.

## 9. `external_directory`

Structured helper:

- no-op для path внутри instance;
- для path снаружи формирует canonical parent-directory glob `<dir>/*`;
- отдельный permission key `external_directory`;
- tool supplies тот же glob как `always` pattern.

Exact tests подтверждают нормализацию Windows path variants, drive root paths и directory/file target semantics.

Shell дополнительно анализирует cwd и аргументы набора известных filesystem commands. Это полезная защита, но она не является общим effect analyzer любого CLI.

Следствие: unknown/custom CLI, который сам интерпретирует path argument, нельзя считать покрытым `external_directory` только потому, что shell tool имеет эту проверку.

Evidence:

- `packages/opencode/src/tool/external-directory.ts`;
- `packages/opencode/test/tool/external-directory.test.ts`;
- `packages/opencode/src/tool/shell.ts`;
- `packages/opencode/test/tool/shell.test.ts`.

Confidence: **high / upstream_source + upstream_test**.

## 10. Agent / subagent semantics

Built-in agent permissions создаются как defaults + user/global rules + agent-specific rules. Agent-specific rules merge-ятся после inherited set и поэтому могут override предыдущие matches.

Task/subagent session наследует от parent session:

- все parent `deny` rules;
- parent `external_directory` rules;
- default `task`/`todowrite` denies, если subagent сам не объявляет соответствующую capability.

Parent ALLOW/ASK rules в общем случае не копируются в child session. Собственный permissions ruleset subagent остаётся основным набором его capabilities.

Следствие: hard deny policy, которую требуется гарантировать и для subagents, должна попадать в наследуемый deny layer, а не существовать только как permissive primary-agent convention.

Evidence:

- `packages/opencode/src/agent/agent.ts`;
- `packages/opencode/src/agent/subagent-permissions.ts`;
- `packages/opencode/src/tool/task.ts`.

Confidence: **high / upstream_source**.

## 11. Plugin / custom-tool extensibility

### Ordinary plugin hooks

Exact plugin API объявляет:

- `permission.ask`;
- `tool.execute.before`;
- `tool.execute.after`;
- `command.execute.before`;
- `shell.env`;
- custom tools.

Но exact `Permission.Service` не вызывает `Plugin.trigger("permission.ask", ...)`; native permission path публикует permission events, но typed `permission.ask` hook не является работающим dynamic approval interception point в проверенном source path.

`tool.execute.before` вызывается перед tool execution, затем host без отдельного skip/result contract вызывает сам tool. Поэтому этот hook сам по себе не является native approval gate.

### Custom tool

Plugin-defined custom tool получает `ToolContext.ask(...)`. Registry мостит этот Promise API в native `Tool.Context.ask`, а он — в `Permission.ask` с effective agent/session ruleset.

Следовательно, custom tool **может явно инициировать native approval request**.

Но обычный plugin runtime не удовлетворяет требованию auditor isolation: PluginInput предоставляет executable capabilities, включая shell helper `$`, а plugin code исполняется в host process.

Следствие для будущего design:

- custom tool — candidate integration point для controlled gate;
- model auditor нельзя просто реализовать как unrestricted plugin и считать его execution-isolated;
- auditor isolation должна быть отдельной технической границей.

Evidence:

- `packages/plugin/src/index.ts`;
- `packages/plugin/src/tool.ts`;
- `packages/opencode/src/plugin/index.ts`;
- `packages/opencode/src/tool/registry.ts`;
- `packages/opencode/src/session/tools.ts`;
- `packages/opencode/src/tool/tool.ts`;
- `packages/opencode/src/permission/index.ts`.

Confidence: **high / upstream_source**.

## 12. Auto-update flag

Exact runtime flag schema содержит `OPENCODE_DISABLE_AUTOUPDATE` и `OPENCODE_PURE`.

Для Stage 0 inventory `OPENCODE_DISABLE_AUTOUPDATE=true` остаётся корректной defense-in-depth мерой против automatic updater path, но она **не** делает config/bootstrap read-only и не запрещает отдельные dependency/plugin installation paths config loader.

Поэтому этот flag не меняет решение по 0A.2.

Evidence:

- `packages/core/src/flag/flag.ts`;
- `packages/opencode/src/config/config.ts`.

Confidence: **high для наличия/границы flag; medium для полной карты всех auto-update call paths**.

## 13. 0B gate decision

Stage 0B считается **CLOSED** для target OpenCode 1.18.18.

Закрыты source/tests evidence:

- exact V1 schema;
- config merge/precedence;
- last-match semantics;
- defaults и docs/source discrepancy;
- once/always/reject;
- shell AST handling для compound commands/redirects/command substitutions;
- external-directory behavior;
- agent/subagent permission composition;
- plugin/custom-tool integration points;
- safety decision по resolved-config mechanism.

0A.2 через `opencode --pure debug config` — **UNAVAILABLE/UNSAFE FOR READ-ONLY AUDIT** и не выполняется.

## 14. Bounded Stage 0C scope

0C не должен повторять подтверждённые upstream tests. Минимальный residual scope:

1. harmless isolated runtime observation для `bash -c` / `sh -c` там, где shell доступен;
2. harmless isolated runtime observation для PowerShell `-Command` на Windows;
3. harmless isolated runtime observation для `cmd /c` на Windows;
4. harmless isolated runtime observation для `python -c`;
5. harmless isolated runtime observation для `node -e`, если Node runtime реально присутствует и этот case нужен target workflow;
6. при необходимости один control case compound command, чтобы доказать корректность capture method.

Probe payload должен быть только harmless marker/read-only operation. Нельзя использовать `rm`, deletion, destructive Git, services, privilege, secret access или remote mutation даже если цель — проверить DENY.

Нужно фиксировать:

```text
input
permission key
exact requested patterns
suggested always patterns
external_directory request if any
whether execution occurred
```

Если capture method требует реальной risky execution либо изменения active user config — affected probe пропускается как unsafe и возвращается evidence.

## 15. Gate state после 0B

```text
0A.1 Minimal inventory        CLOSED
0A.2 Resolved permissions     UNAVAILABLE via debug config for 1.18.18
0B   Version-locked audit     CLOSED
0C   Isolated probes          READY
0D   Real workflow baseline   NOT STARTED

Stage 0                      NOT CLOSED
Native-policy gate           NOT STARTED
Classifier                   NOT STARTED
```
