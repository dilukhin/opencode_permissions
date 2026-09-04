# Trusted workspace producer/integration contract

Статус: **ACCEPTED DESIGN / IMPLEMENTATION OWNER: agent-toolchain / NO POLICY WIDENING YET**.

Этот документ закрывает F4 producer-boundary design после `trusted_workspace_fact_design_ru.md`.

## 1. Цель

Нужен простой способ один раз явно доверить конкретный workspace для ограниченных development scopes, чтобы обычные build/test/static-check операции не требовали отдельного подтверждения каждый раз.

При этом модель не должна иметь возможность тихо выдать доверие самой себе.

Default threat model не требует криптографической защиты от malware того же пользователя или root/admin compromise.

## 2. Выбранная модель

Authoritative state хранит managed setup plane (`agent-toolchain`) вне project workspace.

Логически:

```text
agent-toolchain state
  / workspace-trust.json
```

Конкретный absolute path определяется установленным `agent-toolchain` state directory, а не model/caller input.

`opencode_permissions`:

- определяет schema/semantics `WorkspaceTrustFact`;
- читает fact только через trusted provider integration;
- exact-match фактического workspace;
- решает, как scope влияет на authorization.

`agent-toolchain`:

- хранит registry;
- создаёт/revokes entries;
- использует atomic write;
- не кладёт registry в project-local directory;
- предоставляет read-only provider/reader для authorization integration.

## 3. Создание trust — отдельная authorization operation

Модель может **предложить** доверить workspace, но не может сама подтвердить это решение.

Операция логически представляется как:

```yaml
operation_kind: workspace_trust_change
action: add
workspace: <exact observed identity>
scopes: [build, test, ...]
```

Если она инициирована из OpenCode/model-controlled path:

```text
native/classifier result = ASK_USER
```

Она никогда не является automatic ALLOW.

Пользовательский prompt должен явно показывать:

- exact workspace root;
- scopes, которые станут trusted;
- что последующие распознанные операции этих families могут выполняться без повторного prompt;
- что hard DENY/secrets/destructive/system rules сохраняются;
- что это persistent state до revoke.

One-off approval build/test **не превращается автоматически** в persistent workspace trust.

## 4. Manual user path

Пользователь может выполнить соответствующую `agent-toolchain` команду вручную вне model-controlled OpenCode path.

Это считается явным user action и не требует дополнительной broker/capability архитектуры.

Будущий CLI shape выбирает `agent-toolchain`, например концептуально:

```text
toolchainctl workspace-trust add <path> --scope build --scope test
toolchainctl workspace-trust remove <path>
toolchainctl workspace-trust list
```

Точные названия CLI не являются нормативной частью этого contract.

## 5. Почему model self-trust блокируется без broker

Default path опирается на три простых границы:

1. classifier не принимает `trusted=true`/fact из model/tool input;
2. единственная штатная mutation authoritative registry — отдельная `workspace_trust_change`, которая из OpenCode всегда ASK_USER;
3. direct known writes в authoritative trust registry должны быть запрещены managed permission policy.

Opaque/unsupported способ записи не становится ALLOW и остаётся ASK_USER.

Следовательно модель не получает **тихого автоматического** пути к выдаче trust.

Это соответствует default threat model. Защита от malware, который уже может произвольно писать user state вне permission system, относится к optional high-assurance profile.

## 6. Registry protection

Authoritative registry не является secret.

Но write semantics должны быть защищены:

- structured edit/write/apply-patch к registry -> DENY в integrated managed policy;
- известный shell redirect/write к registry -> DENY;
- unknown/opaque write mechanism -> не ALLOW;
- dedicated setup-owned trust mutation -> ASK_USER;
- read/list operation может быть ALLOW, если не содержит sensitive metadata.

Не требуется:

- signature каждого entry;
- kernel broker;
- separate daemon;
- root-owned file;
- TTL;
- generation counters;
- repository content hashes.

## 7. Registry format

Минимальный registry:

```json
{
  "schema": "workspace-trust-registry/v1",
  "entries": [
    {
      "schema": "workspace-trust-fact/v1",
      "trust_class": "development",
      "workspace": {
        "platform": "linux",
        "requested_root": "/path/project",
        "resolved_root": "/path/project",
        "object_identity": "..."
      },
      "scopes": ["build", "test"]
    }
  ]
}
```

Registry не хранит secrets, tokens, authorization grants или model prose.

Ordering entries не должен менять semantics.

Duplicate exact workspace entry — conflict/error, не last-wins.

## 8. Create/revoke semantics

### Add

- runtime получает actual workspace identity;
- scopes валидируются;
- existing exact entry с теми же scopes -> no-op;
- existing exact entry с другими scopes -> explicit update requiring same user-confirmation semantics when model-initiated;
- path exists but object identity не совпадает with stale entry -> stale entry не применяется; add creates/replaces only via explicit trust action.

### Remove

Revoke только сужает future authorization.

Manual revoke разрешён напрямую.

Model-initiated revoke может быть ASK или ALLOW по UX policy, но v1 рекомендуется ASK для предсказуемости; безопасность не зависит от запрета revoke.

### List

Read-only, без secret values. Candidate ALLOW.

## 9. Provider API

Authorization integration получает registry через setup-owned read-only provider:

```text
WorkspaceTrustProvider.lookup(observed_workspace_identity)
  -> WorkspaceTrustFact | None
```

Provider:

- сам определяет canonical registry location;
- не принимает registry path от model/caller;
- валидирует registry schema;
- invalid/unknown/corrupt registry -> NO_TRUST, не permissive fallback;
- exact-match использует consumer contract `workspace_trust.py`;
- не изменяет registry во время lookup.

## 10. Storage/atomicity

`agent-toolchain` уже имеет managed user state directory и ownership/reconciliation machinery. Producer должен использовать этот существующий state plane, а не создавать новый service/state root.

Минимальные требования write:

```text
read current valid registry
-> construct new complete registry
-> write temp in same state directory
-> fsync/close where supported by existing helper contract
-> atomic replace
-> read-back validate
```

При corrupt/unknown existing registry — fail closed/conflict, без blind overwrite.

## 11. Scope interaction

Workspace trust снимает только заранее названную uncertainty конкретной family.

Например future build policy:

```text
recognized cmake build
+ exact workspace match
+ scope=build
+ no other uncertainty/danger
=> candidate ALLOW
```

Но:

```text
trusted workspace + rm -rf ...            -> DENY/controlled path
trusted workspace + secret read           -> DENY
trusted workspace + sudo/service mutation -> DENY
trusted workspace + opaque nested command -> ASK/DENY по обычной policy
```

## 12. OpenCode 1.18.26 native capability note

Exact 1.18.26 permission documentation описывает path/permission rules и session `once/always/reject`, но отдельный persistent workspace-trust primitive для описанной build/test semantics не подтверждён.

Поэтому design не зависит от существования такого native primitive.

Если позже будет найден подходящий upstream mechanism, producer design следует пересмотреть в пользу native-first.

## 13. Acceptance producer implementation

Implementation в `agent-toolchain` считается готовой только если tests доказывают:

1. registry находится в canonical setup state, не project workspace;
2. add/list/remove deterministic;
3. atomic write + read-back;
4. corrupt/unknown registry -> conflict/no trust;
5. exact workspace identity сохраняется без casefold/Unicode guessing;
6. duplicate conflict semantics;
7. никакого secret/material grant в registry;
8. read-only lookup не мутирует state;
9. Windows/Linux path fixtures;
10. existing `toolchainctl check/apply/update` behavior не ломается.

## 14. Acceptance authorization integration

До первого trust-conditioned ALLOW отдельно доказать:

1. `workspace_trust_change` из model path = ASK_USER;
2. direct known write registry = DENY;
3. forged `trusted=true` ignored/rejected;
4. provider uses canonical state path, не caller path;
5. matching fact exact;
6. build/test paired positive/negative corpus;
7. hard-deny regression = 0 widening;
8. user-facing trust prompt объясняет persistent effect;
9. production integration проходит через managed setup, не ручной copy policy.

## 15. Non-goals

Producer не должен превращаться в:

- authorization broker;
- generic policy database;
- project resource lifecycle registry;
- `agent-safe` temporary/trash registry;
- signed capability service;
- sandbox manager.

Это маленький persistent user choice: **каким development workspace пользователь заранее доверяет выполнение конкретных распознанных families**.
