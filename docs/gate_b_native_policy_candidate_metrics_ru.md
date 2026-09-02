# Gate B — native-policy candidate и corpus metrics

Статус: **DESIGN CANDIDATE ACCEPTED / NOT DEPLOYABLE**  
Дата: 2026-09-02  
Target semantics: OpenCode `1.18.26` V1 permissions

## 1. Назначение

Этот slice проверяет, насколько Gate B можно выразить штатным native matcher OpenCode до deterministic effect classifier.

Production `opencode.json/jsonc` не создаётся и не меняется. Candidate хранится только в `tests/native_policy/`.

## 2. Source facts, на которых основан harness

Для OpenCode `1.18.26` подтверждено:

- permission rule выбирается по **last matching rule wins**;
- если rule не matched, result = `ask`;
- Wildcard нормализует `\` в `/`, `*` охватывает любые символы, `?` — один символ, matching anchored на всю строку; Windows case-insensitive;
- pattern, заканчивающийся `" *"`, также совпадает с base command без аргументов;
- shell permission key остаётся `bash`;
- shell Tree-sitter scan добавляет source command node в permission patterns;
- redirected command pattern включает redirected statement;
- external-directory checks идут отдельным permission request;
- structured `read` спрашивает permission `read` по worktree-relative path;
- `write` и `apply_patch` используют permission `edit`;
- `apply_patch` использует тот же `edit` path permission для add/update/delete/move;
- `grep` permission pattern — search regex/pattern, а target path проверяется отдельно через `external_directory`.

Поэтому harness получает **already-extracted native requests** и не пытается заменить shell parser.

## 3. Candidate order

Логический порядок:

```text
1. broad fallback ASK
2. narrow ALLOW
3. mandatory ASK / controlled-path overrides
4. hard DENY
```

Candidate намеренно не использует blanket:

```text
bash: allow
git *
python *
grep: allow
edit: allow
ssh_relay *
safe *
```

## 4. ALLOW candidate

На текущем design slice auto-ALLOW ограничен:

- structured non-secret `read`, с secret-like ASK/DENY overrides;
- structured `glob`;
- exact/narrow shell diagnostics:
  - `pwd`;
  - `git status *`;
  - `git log -5 --oneline`;
  - `git show --stat HEAD`;
  - `git rev-parse HEAD`;
  - `git rev-parse --show-toplevel`;
  - `ssh_relay status`.

`git diff` content, build/test commands и `grep` пока не auto-ALLOW.

Причины:

- `grep` native permission не связывает allow с target path/secret boundary;
- `git diff` content оставлен conservative ASK вместо расширения read surface;
- build/test требует технически доказанной trusted-workspace boundary.

## 5. Mandatory ASK

ASK сохраняется для:

- redirects/input dependencies;
- opaque interpreters (`bash/sh -c`, `python -c`, PowerShell `-Command`, `cmd /c`, `node -e`);
- `find -exec`, `xargs`;
- generic `safe` / `python -m agent_safe`;
- `ssh_relay exec/job/upload/download` и risk labels;
- `grep`;
- ordinary `edit`/`write`/`apply_patch`;
- unknown CLI/effects;
- external-directory access без отдельного exact allow.

## 6. Hard DENY

Native hard deny применяется только к достаточно узнаваемым patterns:

- filesystem delete families;
- destructive Git;
- privilege/elevation;
- service lifecycle mutation;
- bare/dynamic shell/eval forms;
- environment dump;
- recognized destructive nested interpreter payloads;
- forged `--approved`;
- recognized destructive wrapper/relay payloads;
- direct edit protected `.opencode`, `opencode.json/jsonc`, `.git` control state;
- strong secret/private-key structured reads.

Это не претендует на semantic completeness arbitrary CLI.

## 7. Corpus projection

Исходный corpus: **69 cases**.

Из них:

```text
65 native-scope
4 broker-contract cases (B-P3), excluded from native metrics
```

Projection хранит explicit permission/pattern requests и не является shell parser.

## 8. Metrics

Одинаковый результат получен при POSIX и Windows-style Wildcard mode:

```text
candidate ALLOW = 6
candidate ASK   = 30
candidate DENY  = 29
native scope    = 65
```

Safety metrics:

```text
unsafe_auto_allow       = 0
dangerous_false_safe    = 0
wrapper_false_safe      = 0
unknown_false_safe      = 0
secret_false_safe       = 0
```

Safe optimization capture:

```text
6 / 11 existing safety-ALLOW cases = 54.5%
```

То есть native layer снимает prompt у шести уже признанных safe cases, не auto-allowing ни одного ASK/DENY case.

Пять safety-ALLOW cases сознательно остаются ASK:

```text
grep_source
git_diff
cmake_build
ctest
pytest_module
```

Два safety-DENY cases остаются native ASK, а не DENY:

```text
external_system_write
unknown_cli_delete_claim
```

Это **не false-safe**: native layer не выполняет их автоматически. Они показывают границу native matcher и являются входом будущего deterministic effect classifier. Gate B не должен расширять hard DENY wildcard до ложных совпадений только ради совпадения expected label.

## 9. Regression tests

`tests/test_gate_b_native_policy.py` проверяет:

- `" *"` base-command semantics;
- slash normalization;
- Windows/Posix case behavior;
- redirect override поверх `git status *`;
- secret read DENY;
- non-secret structured read ALLOW;
- `grep` remains ASK;
- wrapper/unknown remain ASK;
- destructive wrapper DENY;
- exact corpus metrics для POSIX и Windows matcher modes.

Локальный test-only прогон перед публикацией:

```text
10 tests
OK
```

## 10. Gate conclusion

Native-rule representability/corpus slice считается **закрытым на уровне design candidate**:

- unsafe auto-allow = 0;
- native boundary явно отделена от будущего classifier;
- prompt reduction измерен;
- known wrapper/secret/unknown cases не становятся false-safe;
- candidate остаётся fail-closed.

Это **не** делает candidate deployable.

До Gate B closure ещё нужны:

1. Windows B-P2;
2. exact installed-version compatibility profile/closure;
3. canonical deployable artifact contract/read-back;
4. final Gate B closure review.

Deterministic classifier и auditor до этого не начинаются.
