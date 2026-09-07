# Minimal Managed Pilot MP-0 — closure

Статус: **CLOSED / PASS** для production artifact/runtime bundle P0 на Linux и exact OpenCode 1.18.29.

Этот документ закрывает только implementation slice **MP-0 artifact/runtime bundle** из `docs/minimal_managed_pilot_design_ru.md`.

Он **не** означает managed deployment, изменение пользовательской OpenCode environment, PASS MP-1/MP-2, готовность MP-3, включение workspace trust, state-changing classifier или auditor.

## 1. Закрываемый gate

MP-0 должен предоставить минимальный production-shaped runtime без test/mock ownership:

- отдельный production bridge;
- content-bound pilot artifact;
- exact current compatibility target;
- минимальный P0 classifier ALLOW surface;
- отсутствие developer-checkout dependency;
- fail-closed/error paths;
- acceptance tests, связывающие committed artifact с canonical source bytes.

Результат MP-0: **PASS**.

## 2. Exact target

На момент closure rolling compatibility registry выбирает:

```text
OpenCode: 1.18.29
platform: linux
compatibility profile: opencode-1.18.29-gate-b
compatibility family: sha256:171d981f8853ca935d982899b15f3933964f8174e1a1d644f820d048fa07536f
platform status: RUNTIME_REVALIDATED
```

Exact native permission artifact:

```text
sha256:b38090e07008fb174607aa2a924cfef1dd26d03bdb339a379b1a770397a8ad84
```

Selection остаётся `exact_version_only`; nearest-version fallback запрещён.

## 3. Production bridge

Canonical production source:

```text
runtime/p0/opencode-permissions.js
```

Bridge использует только доказанный минимальный lifecycle:

```text
tool.execute.before
  -> bind sessionID + callID + command + cwd

permission.asked for native bash ASK
  -> deterministic P0 adapter
  -> ALLOW => reply once
  -> ASK_USER / unsupported / classifier failure => normal user ASK remains
  -> DENY => reject

shell.env after classifier ALLOW
  -> exact runtime/profile re-check
  -> actual cwd binding check
  -> no unexpected environment transform
  -> command/object/operation identity revalidation
  -> drift => block before spawn
```

Bridge не выполняет команду самостоятельно и не становится альтернативным execution runtime.

Production bundle разрешён только из каталога, имя которого совпадает с `artifact_path_segment` manifest.

## 4. P0 deterministic ALLOW surface

Единственная новая classifier ALLOW family:

```text
/usr/bin/grep <static-pattern> <one-existing-nonsecret-workspace-file>
```

Требования:

- Linux;
- managed shell `/bin/dash`;
- executable `/usr/bin/grep`;
- ровно три static token;
- без shell operators, quoting, expansion, glob syntax и redirection;
- без options;
- ровно один существующий regular file;
- target находится внутри workspace;
- workspace/cwd/target symlink ambiguity не допускается;
- target не совпадает с canonical native secret boundary;
- operation identity и filesystem object identity повторно проверяются перед execution.

Не входят в MP-0 classifier ALLOW:

- `find`;
- recursive search;
- pipelines и compound shell;
- Git;
- build/test/static-check;
- writes и другие state-changing actions;
- remote execution/transfer;
- workspace trust;
- auditor.

Native ALLOW/DENY остаются terminal и не расширяются classifier-ом.

## 5. Production P0 adapter

Canonical source:

```text
tools/opencode_p0_adapter.py
```

Adapter не является general shell parser. Он принимает только точную P0 shape и создаёт exact normalized operation для уже существующего deterministic classifier core/analyzer.

Unsupported, opaque, missing, external, symlink-ambiguous или otherwise unproven target возвращает `ASK_USER`; secret target не может стать classifier ALLOW.

Revalidation связывает как минимум:

- command;
- classifier profile;
- exact OpenCode version;
- compatibility profile;
- native policy artifact;
- shell identity;
- grep executable identity;
- cwd identity;
- target identity;
- operation identity.

## 6. Content-bound pilot artifact

Artifact ID:

```text
sha256:fe0587a7c2dea7756bc1e697aa17a79f0c52be45bd55ac145efd7b473badce42
```

Committed path:

```text
dist/pilot/sha256-fe0587a7c2dea7756bc1e697aa17a79f0c52be45bd55ac145efd7b473badce42/
```

Состав:

```text
manifest.json
bridge.js
profile.json
runtime/opencode_p0_adapter.py
runtime/classifier_analyzers.py
runtime/classifier_core.py
runtime/normalized_operation_identity.py
```

Manifest связывает SHA-256 каждого runtime file, exact OpenCode target, compatibility family/profile, exact native artifact, classifier profile и MP-0 constraints.

Runtime не импортирует code из mutable developer checkout.

## 7. Artifact verification

Canonical builder/validator:

```text
tools/build_p0_pilot_artifact.py
```

`validate_committed_artifact()` требует:

- exact artifact directory;
- manifest byte/semantic contract, совпадающий с deterministic current plan;
- presence, size и SHA-256 каждого runtime file;
- byte-for-byte equality committed artifact payloads и canonical source payloads.

Exact-byte materialization test выполняется на Linux, потому что сам P0 artifact Linux-only. Windows checkout может преобразовывать text line endings; это не используется для переопределения Linux artifact identity.

## 8. Acceptance evidence

Финальный pre-closure CI cycle: **CI #125 — PASS**.

Проверено:

- Ubuntu / Python 3.11 — PASS;
- Ubuntu / Python 3.14 — PASS;
- Windows / Python 3.11 — PASS для platform-neutral tests; Linux-only runtime/materialization tests корректно skipped;
- Windows / Python 3.14 — PASS для platform-neutral tests; Linux-only runtime/materialization tests корректно skipped;
- current exact OpenCode compatibility runtime proof — PASS.

Linux regression suite после materialization включает committed-artifact verification и проходит **180 tests**.

До final closure дополнительно перепроверено, что upstream latest release остаётся `v1.18.29`, а repository rolling `current_target` остаётся `1.18.29`.

## 9. Fail-closed acceptance

MP-0 подтверждает следующие invariants:

1. неизвестная/неподдержанная command shape не получает classifier ALLOW;
2. external, missing и symlink-ambiguous file target не получает classifier ALLOW;
3. canonical secret target не получает classifier ALLOW;
4. classifier internal failure не превращается в execution и оставляет normal ASK path;
5. native DENY не может быть переопределён;
6. classifier ALLOW выдаётся только `once`;
7. cwd drift после authorization блокирует execution;
8. executable/file/operation identity drift блокирует execution;
9. unexpected `shell.env` transform блокирует execution;
10. exact-version/profile mismatch отключает autonomous continuation;
11. bundle content/path substitution обнаруживается до использования runtime.

## 10. Что MP-0 ещё не доказывает

MP-0 намеренно не проверяет:

- установку artifact в managed OpenCode environment;
- effective read-back после installation;
- repeated apply/no-op reconciliation;
- disable/rollback;
- modified/unknown plugin ownership conflict;
- installed-version mismatch в setup layer;
- end-to-end P0 lifecycle через disposable exact OpenCode с production artifact placement.

Это gates следующих slices:

```text
MP-1 = synthetic managed deployment
MP-2 = disposable exact OpenCode integration
MP-3 = user opt-in pilot
```

## 11. Gate result

**MP-0: PASS.**

Следующий допустимый этап roadmap — MP-1. До его начала MP-0 считается самостоятельной закрытой опорной точкой.

Пробовать pilot в текущей пользовательской локальной OpenCode environment пока нельзя: по принятому design сначала должны получить explicit PASS MP-1 и MP-2. Первый реальный user opt-in начинается только на MP-3.
