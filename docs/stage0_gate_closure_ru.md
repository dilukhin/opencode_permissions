# Stage 0 — gate closure

Статус: **CLOSED**  
Дата: 2026-08-18  
Проект: `dilukhin/opencode_permissions`  
Target runtime: OpenCode `1.18.18`

## 1. Решение

Stage 0 закрыт. Acceptance contract из `docs/stage0_baseline_audit_ru.md` выполнен с достаточным evidence для перехода к **Native-policy gate**.

Это не означает, что permission policy уже оптимизирована или что deterministic classifier реализован. Следующий разрешённый этап — только Native-policy gate. Classifier implementation остаётся `NOT STARTED` до явного закрытия Native-policy gate.

## 2. Acceptance matrix

### 1. Exact target binary/version/platform — CLOSED

Локальный runtime зафиксирован как OpenCode `1.18.18` на Windows. Version-sensitive source audit выполнен по exact upstream commit `31406ccc51b4bd2a4e1e086b2bcaa5f7f804f26d`.

Evidence: Stage 0A.1 local inventory/report; `docs/stage0_v1_18_18_source_audit_ru.md`.

### 2. Effective permission/config layers — CLOSED

Локально проверяемые layers установлены sanitized mechanisms без raw resolved-config bootstrap:

- legacy global `config.json`: отсутствует;
- user global `opencode.json`: содержит active permission policy;
- user global `opencode.jsonc`: permission-related overrides отсутствуют;
- project config candidates / `OPENCODE_CONFIG*`: ранее не обнаружены; final presence checks также не показали relevant overrides;
- managed Windows `opencode.json` / `opencode.jsonc`: отсутствуют;
- `OPENCODE_PERMISSION`: отсутствует;
- `OPENCODE_AUTH_CONTENT`: отсутствует;
- well-known auth activation: отсутствует;
- active account organization activation: отсутствует;
- remote permission layer activation: не наблюдается, result fully determined.

`opencode --pure debug config` не использовался: для 1.18.18 exact source audit доказал, что это не read-only mechanism.

### 3. Native matcher semantics — CLOSED

Version-locked source/tests подтвердили:

- last matching rule wins;
- no match -> implicit `ask`;
- `once` не сохраняет allow rule;
- `always` добавляет session/instance-local allow rule для tool-provided patterns;
- `reject` отклоняет pending request;
- shell tool использует Tree-sitter и выделяет shell `command` nodes;
- compound commands, redirects и syntax-level substitutions анализируются на уровне текущего shell grammar;
- quoted nested-interpreter payload не получает рекурсивный multi-language semantic analysis.

Evidence: `docs/stage0_v1_18_18_source_audit_ru.md`, `docs/stage0c_interpreter_parser_closure_ru.md`.

### 4. Permission corpus — CLOSED

Canonical corpus содержит 49 unique cases и покрывает safe read/Git/test, controlled writes/deletes, destructive Git, privilege/services, secrets, compound/nested commands, external directory, remote и unknown CLI. Dangerous cases имеют parser-only/temp-fixture boundaries.

Evidence: `tests/permission_cases/`.

### 5. Dangerous cases not destructively executed — CLOSED

Destructive cases не исполнялись на рабочей машине. Исследование использовало source/tests, parser-only reasoning, synthetic fixtures и bounded safe observations.

### 6. Real routine prompt baseline — CLOSED

Stage 0D baseline собран. Routine measured actions D01-D07 завершились без permission prompts в текущей policy. D08 exact cleanup через `Remove-Item` был корректно заблокирован existing hard deny до исполнения; policy bypass не применялся.

### 7. Material questions — CLOSED / bounded residuals recorded

Вопросы, влияющие на Native-policy gate, либо подтверждены exact source/tests/runtime evidence, либо сформулированы ниже как bounded design limitations. Не осталось residual uncertainty, требующего unsafe resolved-config, destructive probe или secret disclosure для начала Native-policy gate.

### 8. Unsafe test allow count — CLOSED

`unsafe_test_allow_count = 0` для реально выполненных probes/baseline.

### 9. Native-policy gaps — CLOSED as inventory

Список сформирован в разделе 3. Он является входом в следующий gate и не является classifier implementation.

## 3. Native-policy gaps для следующего gate

### NP-G01 — routine shell prompts остаются coarse-grained

Current shell fallback остаётся `ask`; безопасные routine команды разрешаются только отдельными syntactic patterns. Нужно определить минимальный deterministic native allowlist/ask policy, которая снижает prompts без broad `bash: allow`.

### NP-G02 — interpreter prefixes нельзя широко разрешать

`bash -c`, `sh -c`, PowerShell `-Command`, `cmd /c`, `python -c`, `node -e` и аналогичные конструкции не получают общий рекурсивный effect analysis вложенного языка. Broad allow для interpreter prefix небезопасен.

Следствие: Native-policy gate должен сохранять `ask/deny` там, где native matcher не способен доказать harmless payload.

### NP-G03 — shell AST не является general CLI effect analyzer

Tree-sitter хорошо покрывает syntax текущего shell, но не знает semantics произвольного executable. Unknown/custom CLI может менять filesystem, network, service или remote state, даже если command shape выглядит простой.

Следствие: native rules могут безопасно auto-allow только deterministically understood command families/patterns.

### NP-G04 — `external_directory` не покрывает любой side effect

Native external-directory checks работают для structured path inputs/workdir и части известных filesystem commands. Они не доказывают отсутствие внешнего side effect для arbitrary CLI/interpreter payload.

Следствие: нельзя считать `external_directory` универсальной sandbox boundary.

### NP-G05 — syntactic hard-deny coverage конечна

Current policy содержит явные destructive deny patterns (`rm`, `Remove-Item`, destructive Git, shutdown, download-pipe-execute и др.), но эквивалентный effect может выражаться другим executable, subcommand, interpreter payload или custom tool.

Следствие: Native-policy gate должен определить, какие hard denies реально можно гарантировать native matcher, не создавая ложное ощущение полного effect coverage.

### NP-G06 — subagent inheritance требует deny-first discipline

Exact source показывает: child/subagent наследует parent deny rules и `external_directory`, но не все parent allow/ask rules. Собственный ruleset subagent остаётся существенным.

Следствие: safety-critical hard deny должен находиться в реально наследуемом deny layer; permissive convention primary-agent недостаточна.

### NP-G07 — native `always` suggestions могут быть шире конкретного действия

Shell tool строит `always` patterns по command/subcommand prefix. Для некоторых commands такой pattern существенно шире текущего invocation.

Следствие: проект не должен использовать `always` как способ автономизации по умолчанию; approval semantics должны оценивать scope предложенного pattern отдельно.

### NP-G08 — plugin hooks не дают готового isolated auditor gate

В target 1.18.18 typed `permission.ask` hook не является подтверждённым working interception point native permission path, а ordinary plugin/custom-tool runtime обладает executable capabilities.

Следствие: auditor isolation нельзя считать решённой native/plugin configuration. Этот gap остаётся для более позднего Auditor gate и не должен подталкивать Native-policy gate к unrestricted plugin execution.

### NP-G09 — secret-read deny patterns требуют явной policy границы

Current local policy запрещает ряд известных secret-like filename patterns и разрешает обычный read. Filename-based native matching не является semantic secret detector.

Следствие: Native-policy gate должен определить conservative deny/ask patterns для secret-bearing paths, не полагаясь на model judgment или prompt convention.

## 4. Bounded residuals, не блокирующие Native-policy gate

- Stage 0 не получает raw resolved config через OpenCode runtime; вместо этого effective locally relevant layers установлены отдельными sanitized extractors.
- Remote config contents не запрашивались. Exact activation conditions были проверены presence-only и оказались inactive; поэтому remote contents не входят в effective policy текущего baseline environment.
- Build и `ssh_relay` были `not_applicable` для measured workflow и не имитировались искусственно.
- D04 ignored fixture и local `__pycache__` residues не являются tracked project state и не удалялись через policy bypass.

Эти residuals не разрешают делать выводы о другой машине, другой OpenCode version или будущем изменении auth/config/account state. При смене target runtime/environment соответствующий baseline должен быть revalidated.

## 5. Gate state

```text
Stage 0             CLOSED
Native-policy gate  READY
Classifier gate     NOT STARTED
Auditor gate        NOT STARTED
Integration gate    NOT STARTED
```

## 6. Следующий шаг

Начать Native-policy gate с проектирования version-locked native rules поверх подтверждённой baseline policy и corpus. Сначала определить:

1. hard-deny invariants, которые native matcher способен гарантировать;
2. exact safe deterministic command families для auto-allow;
3. operations, которые обязаны оставаться `ask` из-за interpreter/unknown-effect ambiguity;
4. external-directory и secret boundaries;
5. expected prompt-reduction metrics против Stage 0D baseline.

Не реализовывать deterministic classifier до явного закрытия Native-policy gate.
