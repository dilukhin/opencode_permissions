# OpenCode Permissions

Проект по разработке и проверке практической модели разрешений OpenCode: меньше рутинных подтверждений без отказа от технических границ опасных действий.

## Цель

Штатная модель принятия решения:

```text
native deterministic rules
-> deterministic parser/effect analysis
-> optional auditor for gray zone
-> ASK_USER only for residual uncertainty
```

Жёсткий `DENY` имеет приоритет и не может быть отменён моделью-аудитором. Неизвестный эффект не считается безопасным.

## Границы проекта

- `opencode_permissions` — permission policy, command/effect classification, approval semantics и эксперименты;
- [`agent-safe`](https://github.com/dilukhin/agent-safe) — runtime-защита рискованных state-changing действий, verify/recovery;
- [`opencode_setup`](https://github.com/dilukhin/opencode_setup) — установка, reconciliation и интеграция;
- [`ssh_relay`](https://github.com/dilukhin/ssh_relay) — удалённый transport/machine contract.

Проект не должен дублировать runtime-функции этих компонентов без доказанной необходимости.

## Актуальные документы

- [`opencode_permissions_project_baseline_ru.md`](opencode_permissions_project_baseline_ru.md) — нормативный persistent baseline: scope, архитектурные инварианты, safety, gates, test strategy и критерии успеха.
- [`opencode_permissions_chatgpt_web_guide_ru.md`](opencode_permissions_chatgpt_web_guide_ru.md) — правила Web-first разработки, исследований, GitHub workflow и делегирования.
- [`opencode_permissions_agent_guide_ru.md`](opencode_permissions_agent_guide_ru.md) — подробный operational contract локального агента.
- [`AGENTS.md`](AGENTS.md) — короткий seed для локального агента.
- [`chatgpt_project_instructions_seed_ru.md`](chatgpt_project_instructions_seed_ru.md) — переносимая копия коротких ChatGPT Project Instructions; активная копия живёт в настройках проекта ChatGPT.
- [`github_project_bootstrap.md`](github_project_bootstrap.md) — project-specific GitHub Connector bootstrap.
- [`opencode_permissions_findings_ru.md`](opencode_permissions_findings_ru.md) — historical/evidence findings; version-sensitive утверждения из него необходимо перепроверять.
- [`docs/stage0_gate_closure_ru.md`](docs/stage0_gate_closure_ru.md) — formal closure Stage 0 для OpenCode 1.18.18, acceptance matrix и native-policy gaps.

Старые управляющие документы сохранены в [`docs/archive/`](docs/archive/) только как historical material и не являются нормативными.

## Источники истины

Для фактического состояния реализации первым источником является текущий GitHub-репозиторий.

Для изменяемого поведения OpenCode приоритет:

1. фактическая установленная/исследуемая версия;
2. актуальная официальная документация и при необходимости upstream source/tests этой версии;
3. project baseline;
4. остальные устойчивые project docs;
5. findings/reports/dialogs — только evidence.

Roadmap и design plan сами по себе не доказывают наличие реализации.

## Основные принципы

- Не добиваться автономности через широкий `bash: allow`, blanket auto-approval или prompt-only запреты.
- Сначала использовать максимально точные native permissions; parser/classifier добавлять только для доказанных gaps.
- Анализировать всю операцию, включая pipelines, redirects, nested interpreters и remote payload.
- Опасные negative cases проверять parser-only/mock или в disposable fixtures, а не разрушительным исполнением на рабочей системе.
- Пользователь привлекается только при существенной остаточной неопределённости и получает описание цели, target, effects, risk и reversibility.

## Текущий этап

**Stage 0 / Baseline audit gate закрыт** для исследованного OpenCode `1.18.18`. Acceptance и ограничения зафиксированы в [`docs/stage0_gate_closure_ru.md`](docs/stage0_gate_closure_ru.md).

Следующий этап — **Native-policy gate**: спроектировать максимально точные version-locked native rules поверх подтверждённой baseline policy и корпуса cases. Нужно определить hard-deny invariants, deterministic safe allow patterns, обязательные `ask`-зоны, external-directory/secret boundaries и ожидаемое снижение prompts.

Deterministic classifier пока **не реализуется** и остаётся `NOT STARTED` до явного закрытия Native-policy gate.

Ключевые Stage 0 артефакты:

- [`docs/stage0_baseline_audit_ru.md`](docs/stage0_baseline_audit_ru.md) — sub-gates 0A–0D, research questions, evidence model, safety и acceptance;
- [`docs/stage0_v1_18_18_source_audit_ru.md`](docs/stage0_v1_18_18_source_audit_ru.md) — version-locked source/test audit OpenCode 1.18.18;
- [`docs/stage0c_interpreter_parser_closure_ru.md`](docs/stage0c_interpreter_parser_closure_ru.md) — closure nested-interpreter/parser uncertainty;
- [`docs/stage0_gate_closure_ru.md`](docs/stage0_gate_closure_ru.md) — итоговое решение Stage 0 и native-policy gap inventory;
- [`tools/stage0_inventory.py`](tools/stage0_inventory.py) — read-only inventory установленного OpenCode;
- [`tests/permission_cases/`](tests/permission_cases/) — machine-readable corpus из 49 safe/gray/dangerous cases.

Документация и рабочее общение проекта ведутся преимущественно на русском языке; code identifiers и machine-readable fields — преимущественно на английском.
