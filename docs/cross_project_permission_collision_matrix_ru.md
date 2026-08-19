# Cross-project permission collision matrix

Статус: **working audit / design input**.  
Назначение — фиксировать текущие и legacy каналы, которые способны влиять на effective authorization semantics, и определить требуемого канонического владельца/миграцию.

Документ не заменяет повторную проверку актуального default branch каждого проекта перед изменением реализации.

## 1. Классы collision

| Класс | Смысл |
|---|---|
| `DIRECT_POLICY_WRITER` | Компонент прямо пишет native/agent permission config |
| `APPROVAL_SEMANTICS` | Компонент сам определяет, когда/как считать approval полученным |
| `WRAPPER_TUNNEL` | Внешняя разрешённая команда может скрывать вложенный effect/payload |
| `PROMPT_POLICY` | Skill/AGENTS/instruction фактически задаёт authorization rule |
| `CONFIG_LAYER` | Отдельный effective config source может сохранить старую/конфликтующую policy |
| `CONTEXT_POLICY` | Context provider может начать подмешивать authorization semantics |
| `RECONCILER_OWNERSHIP` | Несколько installers могут независимо менять один live artifact |

## 2. Текущая матрица

| Project / artifact | Collision class | Текущее наблюдение | Риск | Целевой owner | Требуемое действие |
|---|---|---|---|---|---|
| `agent-safe/opencode/opencode.json` | `DIRECT_POLICY_WRITER` | Содержит собственный `permission`, включая blanket `safe *` и `python -m agent_safe * -> allow`, secret read deny и другие bash rules | HIGH | `opencode_permissions` для authorization semantics; deploy через `opencode_setup` | В integrated mode прекратить независимое владение production permission config; определить standalone compatibility |
| `agent-safe/src/agent_safe/opencode_bootstrap.py` | `DIRECT_POLICY_WRITER`, `RECONCILER_OWNERSHIP` | `merge_opencode_config()` добавляет permission defaults и bootstrap может обновлять OpenCode config/AGENTS/skills | HIGH | source artifacts — соответствующие проекты; shared live reconciliation — `opencode_setup` | Депрецировать/отделить permission-writing integrated path; сохранить standalone только явно |
| `agent-safe exec-risky --approved` | `APPROVAL_SEMANTICS` | Caller-controlled Boolean рассматривается как подтверждение после user review | CRITICAL architectural gap | `opencode_permissions` authorization handoff; `agent-safe` runtime enforcement | В integrated mode заменить на non-forgeable exact-bound authorization evidence |
| `safe *` native allow + nested payload | `WRAPPER_TUNNEL` | Внешний wrapper может быть ALLOW, тогда как semantic effect вложенного payload не гарантированно эквивалентно проверяется native matcher | CRITICAL candidate bypass | `opencode_permissions` | Не использовать blanket wrapper allow как proof безопасности; добавить parser/mock regression cases |
| `python -m agent_safe *` native allow | `WRAPPER_TUNNEL` | Аналогичный wrapper channel к agent-safe CLI | HIGH | `opencode_permissions` | То же: semantic authorization nested operation либо controlled tool path |
| `agent-safe risk-gate` / `safe-cli` skills | `PROMPT_POLICY` | Skills маршрутизируют state-changing/high/unknown actions и местами связывают risky path с `safe`/approval workflow | MEDIUM/HIGH | Workflow routing может остаться `agent-safe`; ASK semantics — `opencode_permissions` | Переписать integrated wording: `risky/unknown -> controlled execution path`, не `risky -> independently ask user` |
| `opencode_setup/templates/AGENTS.md` | `PROMPT_POLICY` distribution | Global instructions требуют загрузить agent-safe skills перед risky actions | MEDIUM indirect | `opencode_setup` deploys; semantic content owner должен быть явным | Разрешить routing instructions, но исключить скрытую authorization policy из распространяемых skills/blocks |
| `opencode_setup/templates/opencode.jsonc` | `CONFIG_LAYER` | Сейчас permission отсутствует; template содержит provider/model/autoupdate | LOW current | `opencode_setup` для provider/install fields; permission — `opencode_permissions` | Сохранить отсутствие собственной permission semantics; позже включать canonical policy artifact только как owned source другого проекта |
| `opencode_setup/reconcile_opencode_config` | `RECONCILER_OWNERSHIP` | Сохраняет existing user settings, умеет conflict detection/backup/manifest ownership | POSITIVE BASE | `opencode_setup` | Расширить semantic ownership/legacy detection на permission artifacts и effective config layers |
| legacy `~/.config/opencode/opencode.json` от agent-safe | `CONFIG_LAYER` | Может сосуществовать с `opencode_setup`-managed `.jsonc`; старые rules могут оставаться effective | HIGH | `opencode_setup` reconciliation по source artifact `opencode_permissions` | Inventory всех effective config channels, known legacy signature migration, unknown -> preserve/conflict |
| `OPENCODE_PERMISSION` / другие effective overlays целевой версии | `CONFIG_LAYER` | Environment layer способен влиять на final permission semantics | HIGH | `opencode_permissions` defines semantics; `opencode_setup` detects managed conflicts where feasible | Включить в inventory/acceptance; не считать disk config единственным source of truth |
| project-level OpenCode config | `CONFIG_LAYER` | Может дополнять/override global rules согласно version-specific merge semantics | HIGH | project policy rules под общей моделью `opencode_permissions` | Явно определить ownership и precedence; добавить corpus/reconciliation scenarios |
| `ssh_relay --risky` | `PROMPT_POLICY`/label overlap | Сейчас описан как контракт для коротких изменяющих remote commands; сам skill не формирует ALLOW/ASK/DENY | LOW/MEDIUM | `ssh_relay` transport label; authorization — `opencode_permissions` | Формализовать, что `--risky` не является approval evidence |
| `ssh_relay exec/sudo-exec/job <payload>` | `WRAPPER_TUNNEL` | Remote payload проходит через generic relay primitive | HIGH | `opencode_permissions` semantic authorization; `ssh_relay` transport | Payload/operation binding upstream; не blanket-allow relay wrapper |
| `ssh_relay upload/download` | `WRAPPER_TUNNEL`/effect channel | Transfer меняет remote/local state, но не всегда выглядит как shell command | MEDIUM/HIGH | `opencode_permissions` effects; `ssh_relay` transport; `agent-safe` runtime safety если integrated | Явно классифицировать transfer effects и target; не ограничиваться command parser |
| ScopedKB current bootstrap | `CONTEXT_POLICY` | Текущий bootstrap не меняет system settings и не подключает real KB | NONE current | ScopedKB | Сохранить отсутствие authorization writer |
| ScopedKB future `context`/startup compilation | `CONTEXT_POLICY`, `PROMPT_POLICY` | Specification предусматривает startup safety/context policy и compiled context | FUTURE MEDIUM/HIGH | Facts/provenance — ScopedKB; authorization — `opencode_permissions` | Запретить generated `allow/deny/ask` semantics; разрешить facts/index/routing only |
| ScopedKB fact status/provenance | `CONTEXT_POLICY` | Spec различает observed/verified/provenance/freshness-like fields | POSITIVE BASE | ScopedKB | Использовать как PIP attributes; stale/weaker fact не должен ослаблять policy |

## 3. Critical collisions, блокирующие Gate A/B

### C1. Blanket allow внешнего `safe` wrapper

Текущее сочетание:

```text
native: safe * -> ALLOW
agent-safe: safe exec-risky ... --approved -- <payload>
```

опасно архитектурно, потому что authorization внешнего wrapper не доказывает authorization вложенного payload.

Статус: **confirmed composition gap; destructive exploit validation не требуется и запрещена**. Требуется parser/mock/synthetic regression.

### C2. Caller-controlled `--approved`

Boolean, который может сформировать сама модель/CLI caller, не может служить integrated proof пользовательского approval.

Статус: **confirmed by current code**.

### C3. Multiple live config writers/layers

`agent-safe` и `opencode_setup` исторически/функционально способны затрагивать OpenCode live artifacts разными путями; JSON/JSONC и environment/project layers могут одновременно влиять на effective policy.

Статус: **requires reconciliation inventory**.

## 4. Non-blocking but mandatory design collisions

### N1. `risk-gate` wording

Risk classification полезна для routing в controlled path, но не должна становиться вторым PDP.

### N2. `ssh_relay --risky`

Полезный transport/runtime label, но не approval semantics.

### N3. ScopedKB startup safety/context policy

Можно распространять factual context и routing rules, но authorization policy должна оставаться технически принадлежащей `opencode_permissions`.

## 5. Effective permission channels, которые обязаны попасть в inventory

Минимум:

- global `opencode.json`;
- global `opencode.jsonc`;
- project OpenCode config;
- `.opencode`-related config/artifacts, если они effective для целевой версии;
- `OPENCODE_CONFIG`;
- `OPENCODE_CONFIG_CONTENT`;
- `OPENCODE_PERMISSION`;
- agent-specific/managed config, если используется целевой версией;
- global/project `AGENTS.md` и skills как non-technical but authorization-relevant prompt channels;
- wrapper/custom-tool allow rules;
- legacy bootstrap artifacts известных версий.

Secret-bearing config не должен выводиться целиком; inventory обязан иметь sanitized representation.

## 6. Migration classifications

Каждый обнаруженный live artifact классифицируется:

```text
CURRENT_MANAGED
KNOWN_LEGACY_EXACT
KNOWN_LEGACY_MODIFIED
USER_OWNED
UNKNOWN
CONFLICTING_EFFECTIVE_LAYER
```

Рекомендуемая реакция:

| Class | Action |
|---|---|
| `CURRENT_MANAGED` | reconcile + verify |
| `KNOWN_LEGACY_EXACT` | migrate/remove по explicit rule + verify |
| `KNOWN_LEGACY_MODIFIED` | preserve + conflict; отдельное решение |
| `USER_OWNED` | preserve; merge только в явно разрешённом semantic scope |
| `UNKNOWN` | preserve + report |
| `CONFLICTING_EFFECTIVE_LAYER` | fail integration gate до явного решения |

## 7. Regression families для `opencode_permissions`

Обязательные synthetic cases:

1. benign direct command;
2. hard-denied direct command;
3. benign `safe` nested payload;
4. dangerous `safe` nested payload;
5. same dangerous payload with forged `--approved`;
6. `python -m agent_safe` nested variant;
7. benign ssh_relay exec payload;
8. dangerous ssh_relay exec payload;
9. remote transfer write;
10. nested interpreter behind wrapper;
11. authorization grant for A + execution B;
12. stale ContextFact vs verified ContextFact;
13. legacy `opencode.json` + current `.jsonc` mixed state;
14. environment overlay conflicts with managed disk policy;
15. project config conflicts with global policy.

## 8. Gate condition

Cross-project collision review считается завершённым только когда каждая `HIGH/CRITICAL` строка имеет:

- canonical owner;
- target architecture;
- migration/compatibility decision;
- regression/verification method;
- отдельное project gate, где будет реализовано изменение;
- отсутствие зависимости только от prompt-инструкции.
