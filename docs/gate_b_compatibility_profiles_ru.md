# Gate B — exact-version compatibility profiles

Статус: **PROFILE REGISTRY ACCEPTED / NOT DEPLOYABLE**  
Дата: 2026-09-02  
Проект: `dilukhin/opencode_permissions`

## 1. Цель

Зафиксировать machine-readable compatibility gate для часто обновляемого OpenCode так, чтобы managed authorization artifact никогда не выбирался по принципу «ближайшая версия» или только по semver.

Этот slice не создаёт production policy и не делает OpenCode 1.18.26 `DEPLOYABLE`.

## 2. Registry

Test-only registry находится в:

```text
tests/compatibility/registry.json
```

Инварианты:

```text
selection = exact_version_only
nearest_version_fallback = false
unknown version -> UNVALIDATED_OPENCODE_VERSION
known but non-deployable version -> PROFILE_NOT_DEPLOYABLE
```

Profiles:

```text
1.18.18 -> tests/compatibility/profiles/opencode-1.18.18.json
1.18.26 -> tests/compatibility/profiles/opencode-1.18.26.json
```

## 3. Baseline profile 1.18.18

`1.18.18` остаётся immutable Stage 0 baseline:

```text
historical Stage 0 = CLOSED
Gate B overall status = SOURCE_REVALIDATED
Linux = SOURCE_REVALIDATED
Windows = SOURCE_REVALIDATED
deployable = false
```

Историческое runtime closure Stage 0 не переинтерпретируется как доказательство нового broker/custom-tool Gate B contract.

## 4. Current profile 1.18.26

На 2026-09-02 latest upstream release и фактически наблюдавшаяся версия на ILUKHIN совпадают: `1.18.26`.

Exact upstream tag:

```text
v1.18.26 -> 774cc7c1914e4329eefde5a669f938b0cf566661
```

Profile status:

```text
overall = SOURCE_REVALIDATED
linux   = RUNTIME_REVALIDATED
windows = SOURCE_REVALIDATED
deployable = false
```

Linux runtime status опирается только на фактически выполненный Gate B scope:

- project-local custom tool выполняется в registered OpenCode host process;
- trusted peer identity проверена через `SO_PEERCRED`;
- same-user child rejected;
- host lifecycle связан с `pidfd` и registration invalidates on exit;
- broker unavailable fails closed.

Это не означает production broker hardening и не расширяет runtime evidence на Windows.

## 5. Critical source fast path

Пять shared fingerprints между exact `v1.18.18` и `v1.18.26` совпадают byte-for-byte по Git blob identity:

```text
permission_service
  2e27ff2424dbb000ea9ed7f73471769716ba40a1

tool_context
  e5e7802858ca5cd2250f8f34c4725a25c7a3221d

shell_tool
  1e4423e017740617bc6e0df36ad9dcdb0197bccb

permission_http
  79959db499bd12a359ac84a9a189faebc84c016e

permission_http_auth
  61ce39ad39e0643758861e82220953399bb6c824
```

Поэтому `1.18.18 -> 1.18.26` удовлетворяет synthetic fast-path condition для этих shared primitives.

Но fast path означает только:

```text
SOURCE_EQUIVALENT_FAST_PATH_ELIGIBLE
```

Он не означает `DEPLOYABLE` и не позволяет пропустить required runtime/platform evidence.

Если хотя бы один fingerprint меняется:

```text
TARGETED_REAUDIT_REQUIRED
```

## 6. Additional 1.18.26 fingerprints

Current profile отдельно фиксирует version-sensitive paths, на которых теперь зависит Gate B design:

- wildcard matcher;
- shell permission ID;
- structured read/glob/grep/write/apply_patch;
- external-directory boundary;
- ToolRegistry custom-tool execution;
- `opencode run` in-process local path;
- plugin ToolResult contract.

Это делает drift нового release явным и reviewable вместо предположения о совместимости patch release.

## 7. Regression acceptance

`tests/test_gate_b_compatibility.py` проверяет:

1. exact `1.18.26` выбирает exact profile;
2. synthetic `1.18.27` возвращает `UNVALIDATED_OPENCODE_VERSION`;
3. nearest-version fallback запрещён;
4. current profile не может быть выбран с `require_deployable=true`;
5. Linux status = `RUNTIME_REVALIDATED`, Windows = `SOURCE_REVALIDATED`;
6. shared fingerprints 1.18.18/1.18.26 дают fast-path eligibility;
7. synthetic fingerprint drift требует targeted re-audit;
8. profiles не содержат policy artifact или secret material.

Test-only local verification перед публикацией:

```text
8 tests
OK
```

## 8. Remaining blockers

Current 1.18.26 profile остаётся non-deployable по трём явным причинам:

```text
WINDOWS_B_P2_PENDING
CANONICAL_DEPLOYABLE_ARTIFACT_NOT_BUILT
FINAL_GATE_B_CLOSURE_PENDING
```

После B-P2 Windows platform status может быть повышен только на основании reviewed runtime evidence, а не по аналогии с Linux.

## 9. Вывод

Version-lifecycle acceptance Gate B закрыт на уровне registry/profile semantics:

- baseline и current version представлены machine-readable;
- exact-only selection доказан тестом;
- unknown future version fail-closed;
- source fast path основан на fingerprints;
- fingerprint drift вызывает re-audit;
- deployability отделена от source/runtime status.

До production deployment этот registry остаётся test/design artifact. `opencode_setup` в будущем должен реализовать тот же exact-version contract, но не копировать или переопределять authorization semantics.
