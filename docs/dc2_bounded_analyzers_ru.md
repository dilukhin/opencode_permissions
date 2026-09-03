# DC-2 — bounded deterministic analyzers

Статус: **IMPLEMENTATION CANDIDATE / CI REQUIRED**  
Дата: 2026-09-03

## 1. Scope

DC-2 добавляет первые command/effect analyzers поверх DC-0/DC-1, но **не** парсит raw shell text.

Input contract:

```text
parsed-simple/v1
```

Он содержит exact argv boundaries, parser provenance и synthetic trusted-preflight identities executable/cwd/targets. Реальный OpenCode/Tree-sitter adapter и происхождение этих facts должны быть доказаны позже в DC-4.

## 2. Fail-closed вход

ALLOW невозможен, если:

- parser status не `exact`;
- executable/cwd object identity отсутствует;
- argv/executable mismatch;
- target boundary/sensitivity не доказаны для analyzer, который от них зависит;
- redirect semantics не полностью поддержаны;
- command shape выходит за bounded profile.

Opaque parser input -> `ASK_USER` с `syntax.opaque`.

## 3. Реализованные bounded analyzers

### `find`

ALLOW только exact read-only shape:

```text
find <workspace-root> -type f -name <pattern> -print
```

при exact workspace directory identity.

`-delete` -> DENY.  
`-exec/-execdir/-ok/-okdir` -> ASK с `unknown_code_execution`.

### `grep`

ALLOW только:

- exact single `workspace_file` с `sensitivity=nonsecret`; либо
- pipeline stdin, когда argv не содержит filesystem target.

Secret single file -> DENY.  
Recursive grep -> ASK, поскольку descendant secret boundary не доказана.

### Git read

`git diff` ALLOW только в hardened form:

```text
git diff --no-ext-diff --no-textconv -- <single-file>
```

с exact repository identity и single non-secret workspace-file identity, bound to requested path.

Plain `git diff` остаётся ASK с `git.diff.transforms_unconstrained`.

`git status` analyzer поддержан для composition/internal facts; native Gate B ALLOW остаётся terminal и classifier в обычном pipeline для него не вызывается.

Known `git reset --hard` / force-clean family -> DENY defensively, хотя production native hard DENY уже terminal.

### Writes / redirects

`touch <system_path>` -> DENY.  
Workspace touch -> ASK.

Output redirect:

- system target -> DENY;
- controlled workspace target -> ASK;
- unknown target -> ASK.

Input redirect пока ASK, кроме explicit secret target -> DENY.

### Build/test/interpreters

Следующие команды **не** повышаются до ALLOW только из-за familiar CLI или `trusted_workspace` label:

```text
cmake --build ...
ctest ...
python -m pytest ...
bash/sh/python/node/powershell/cmd payloads
```

Они получают `unknown_code_execution` / `nested_interpreter` и остаются ASK до отдельной technical execution boundary.

### Pure stdio / composition

Trusted external `printf` без redirects может ALLOW как stdout-only process.

DC-2 использует DC-1 для:

- compound operation composition;
- pipeline composition;
- parent identity binding;
- `DENY > ASK_USER > ALLOW` precedence.

## 4. Projection

Machine-readable projection:

```text
tests/classifier_cases/dc2_cases.json
```

Он содержит 27 cases с:

```text
native_decision
safety
expected_combined
exact argv/target descriptors
compound/pipeline child references
```

Projection intentionally включает both positive и paired negative/ambiguous cases.

Sound safe promotions из native ASK в этом synthetic projection:

- hardened single-file `git diff`;
- read-only `find -print`;
- single non-secret file grep;
- stdout-only printf;
- grep over pipe stdin;
- safe compound composition;
- safe pipeline composition.

Это **не** означает, что historical Gate B safe-capture автоматически вырос для production: DC-4 ещё должен доказать exact parser/preflight adapter. В частности original plain `git diff`, directory grep, build/test остаются ASK.

## 5. Safety metrics

Regression требует:

```text
unsafe_auto_allow = 0
dangerous_false_safe = 0
unknown_false_safe = 0
secret_false_safe = 0
native_deny_override = 0
unparsed_auto_allow = 0
identityless_auto_allow = 0
sound_safe_promotions >= 7   # synthetic DC-2 projection only
```

Каждый classifier ALLOW должен иметь valid `operation_identity` через DC-1 validation.

## 6. Deliberate non-claims

DC-2 не доказывает:

- production shell AST extraction;
- mapping OpenCode tool request -> `parsed-simple/v1`;
- actual runtime executable/path identity acquisition;
- filesystem race-free trusted-boundary revalidation;
- remote/wrapper recursive payload adapter (DC-3);
- live OpenCode deployment.

## 7. Acceptance

DC-2 candidate PASS только после Linux/Windows matrix, всех 27 projection cases, metrics above и сохранения Gate B/DC-0/DC-1 regressions.

После PASS следующий repository-only slice — DC-3 wrapper/remote recursive extraction. Реальный OpenCode parser adapter остаётся DC-4 и может потребовать bounded local-agent runtime probe.