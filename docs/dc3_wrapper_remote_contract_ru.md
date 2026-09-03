# DC-3 — wrapper / remote recursive extraction

Статус: **PASS**  
Дата: 2026-09-03

## 1. Scope

DC-3 добавляет deterministic analysis известных wrapper/transport CLI поверх DC-0/DC-1/DC-2.

Главная цель этого slice — не дополнительный `ALLOW`, а сохранение видимости nested payload/effects и fail-closed semantics:

```text
outer wrapper/transport
-> exact outer argv
-> recognized payload boundary
-> bounded child analysis where technically available
-> DENY dominates wrapper
-> otherwise ASK_USER
```

DC-3 намеренно не превращает `safe`, `python -m agent_safe` или `ssh_relay` в authorization tunnel.

## 2. Exact external contracts used

### agent-safe

Source target:

```text
repository: dilukhin/agent-safe
branch: master
commit: 95545d20533b2dfa1de7d75a30fa1bbfb1d428e3
version: 0.4.0
CLI: src/agent_safe/cli.py
```

Подтверждено source-level:

- `exec-risky`, `exec-readonly`, `system-change`, `system-readonly`, `yc-change`, `yc-readonly` используют `argparse.REMAINDER` для payload;
- `_remainder()` удаляет только leading `--`;
- risky/change paths принимают caller-controlled `--approved` и/или `--allow-critical`;
- `opencode-bootstrap --apply` меняет OpenCode integration state.

### ssh_relay

Source target:

```text
repository: dilukhin/ssh_relay
branch: main
commit: af5ae0249c8c045c97eaa8099935fc16e1ebff68
version: 0.9.0
```

Подтверждено source-level:

- `exec` / `sudo-exec` принимают remote command как одну shell-строку;
- `--risky` означает receipt/outcome semantics, а не authorization evidence;
- `upload` / `download` — first-class transfer operations с explicit source/destination/overwrite semantics;
- `job start` принимает remote command как одну shell-строку;
- `job status/list/wait/tail/stop` имеют отдельные lifecycle semantics;
- machine contract запрещает blind retry для `unknown` и `partial_success`.

## 3. Input contract

Implementation:

```text
tools/classifier_wrappers.py
```

Outer fact:

```text
parsed-wrapper/v1
```

Для analysis требуется:

- parser status `exact`;
- exact outer `argv` boundaries;
- executable object identity;
- cwd object identity;
- `argv[0] == executable.invoked`.

Opaque/missing boundary -> `ASK_USER`.

DC-3 сам не парсит raw local shell string. Real OpenCode adapter остаётся DC-4.

## 4. agent-safe semantics

Поддерживаются outer forms:

```text
safe <subcommand> ...
python -m agent_safe <subcommand> ...
```

### Approval substitution

Caller-controlled:

```text
--approved
--allow-critical
```

на recognized change path -> `DENY` с `approval_substitution`.

Это не approval evidence integrated architecture.

### Payload binding

Для remainder-based commands nested `parsed-simple/v1` должен exact-match payload argv после `--`.

Если child:

- `DENY` -> wrapper result `DENY`;
- `ALLOW` -> outer controlled wrapper всё равно `ASK_USER`;
- `ASK_USER` -> outer `ASK_USER`;
- absent/mismatched/opaque -> `ASK_USER` + residual uncertainty.

То есть benign child не делает wrapper auto-ALLOW.

### Policy mutation

```text
safe opencode-bootstrap ... --apply
```

-> `DENY` с `authorization_policy_mutation`.

Other stateful agent-safe operations остаются ASK unless already denied by native layer.

## 5. ssh_relay semantics

### `sudo-exec`

Privilege path -> `DENY`.

### `exec`

Remote command остаётся shell string. Если exact nested remote-shell fact не предоставлен, результат:

```text
ASK_USER
unknown_code_execution
```

Если synthetic/exact nested child предоставлен:

- child DENY -> remote operation DENY;
- child ALLOW/ASK -> remote operation всё равно ASK.

Это deliberate boundary: source-level outer CLI contract ещё не доказывает production remote shell parser/preflight adapter.

### `--risky`

Добавляет explicit effects:

```text
risk_label
remote_state_change
```

но не меняет authorization на ALLOW.

### Transfers

`upload` и `download` получают полноценный `NormalizedOperation`:

```text
operation_kind: transfer
channel: transfer
transport: ssh_relay
direction: upload|download
source target
destination target
remote host identity
overwrite: replace|fail_if_exists
```

При complete exact identity classifier result остаётся `ASK_USER`, но содержит reproducible `operation_identity`.

Missing remote host/source/destination identity -> ASK без identity.

### Jobs

`job start` анализирует nested remote payload по тем же правилам, но остаётся ASK unless payload proves hard DENY.

`job status/list/wait/tail` остаются ASK at this layer; `tail` включает `possible_sensitive_output`.

`job stop` отмечается как process control / remote state change и остаётся ASK.

## 6. Projection

Machine-readable projection:

```text
tests/classifier_cases/dc3_cases.json
```

20 cases покрывают:

- benign agent-safe controlled payload;
- nested system write;
- forged `--approved` / `--allow-critical`;
- `python -m agent_safe` equivalent boundary;
- policy bootstrap mutation;
- opaque child;
- benign/destructive/risky `ssh_relay exec`;
- `sudo-exec`;
- upload/download exact identity;
- job start benign/destructive;
- job tail sensitivity;
- unknown/opaque wrapper;
- native DENY terminal;
- incomplete transfer identity.

## 7. Safety acceptance

CI подтвердил:

```text
wrapper_auto_allow                 = 0
unsafe_auto_allow                  = 0
dangerous_false_safe               = 0
unknown_false_safe                 = 0
native_deny_override               = 0
approval_substitution_false_safe   = 0
exact_transfer_identity_missing    = 0
```

`exact_transfer_identity_missing` считается только для complete synthetic upload/download cases; deliberately incomplete host case fail-closes.

## 8. Deliberate non-claims

DC-3 не доказывает:

- production OpenCode raw shell AST adapter;
- production remote shell parsing;
- actual remote machine identity provider integration;
- trusted-boundary executable/path revalidation immediately before execution;
- authorization broker / agent-safe PEP production integration;
- ssh_relay outcome integration Gate D;
- wrapper/remote prompt reduction;
- live OpenCode deployment.

`wrapper_auto_allow = 0` — intentional safety property этого slice.

## 9. Acceptance evidence / next step

GitHub Actions run 69 на head `5f773a6ed87424acebc1a6243716eeba5ea4958b` завершён `success` на полном Linux/Windows Python matrix; Gate B/DC-0/DC-1/DC-2 regressions сохранены.

Следующий обязательный slice — **DC-4 exact OpenCode 1.18.26 parser/preflight adapter**. Он должен доказать происхождение `parsed-simple/v1` / `parsed-wrapper/v1` facts из реального OpenCode tool path и определить, какие trusted identity fields можно получить source/runtime-technically без model-controlled substitution.
