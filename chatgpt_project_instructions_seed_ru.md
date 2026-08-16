# OpenCode Permissions — Project Instructions

Проект: `dilukhin/opencode_permissions`.

Цель — разработать и проверить практическую модель разрешений OpenCode, которая уменьшает рутинные подтверждения, но сохраняет технические границы опасных действий. Нельзя достигать автономности через безусловный shell-доступ, широкое `bash: allow`, слепой `--auto` или промптовые запреты вместо технических ограничений.

## Источники истины

Для фактического состояния реализации первым источником является актуальный GitHub-репозиторий: код, tests, config, schemas, default branch и PR state.

Для изменяемого поведения OpenCode приоритет:
1. фактическая установленная/исследуемая версия;
2. актуальная официальная документация и при необходимости upstream source этой версии;
3. `opencode_permissions_project_baseline_ru.md`;
4. остальные project Sources;
5. findings, старые отчёты, диалоги и память — только evidence.

Roadmap/план не доказывает наличие реализации.

## Роли связанных проектов

- `opencode_permissions` — permission policy, command/effect classification, approval semantics и эксперименты;
- `agent-safe` — runtime-защита рискованных state-changing действий, verify/recovery;
- `opencode_setup` — установка, reconciliation и интеграция;
- `ssh_relay` — удалённый transport/machine contract.

Не дублировать их runtime-функции без доказанной необходимости.

## Рабочая модель

Основная последовательность:
`native deterministic rules -> deterministic parser/effect analysis -> optional auditor for gray zone -> ASK_USER`.

Жёсткий `DENY` имеет приоритет и не может быть отменён моделью-аудитором. Модель не должна получать право выполнения команды. Пользователь привлекается только при существенной остаточной неопределённости и должен видеть смысл действия, target, effects, risk, reversibility и причину запроса.

## Работа в ChatGPT Web

Сложное проектирование, исследование, анализ, review, подготовку документов и все поддерживаемые GitHub-операции выполнять максимально в ChatGPT Web.

Для GitHub использовать Connector первым. Не запускать `git`/`gh` как пробу remote-доступа. Локальный Git допустим для подтверждённого checkout или при доказанном gap Connector. После значимой write-операции делать targeted read-back через Connector.

Перед изменением архитектуры или реализации:
- проверить актуальное состояние репозитория;
- отделить подтверждённый факт от гипотезы;
- проверить version-sensitive утверждения;
- определить acceptance/verification.

Не переходить к следующему этапу roadmap, пока текущий gate явно не закрыт.

## Делегирование агенту

Локальный агент — bounded executor, а не архитектор. Делегировать только локально необходимые операции или механическую реализацию уже принятых решений. Задание должно содержать exact scope, paths, allowed changes, проверки, expected result и stop/escalation conditions. При неожиданном состоянии агент должен остановить affected path и вернуть evidence, а не импровизировать.

Подробные правила: `opencode_permissions_agent_guide_ru.md`.

## Safety

Опасные permission-кейсы не проверять разрушительным исполнением. Использовать parser-only, mocks, временные каталоги, synthetic fixtures и изолированные среды.

Не раскрывать secrets, credentials, tokens, private keys или содержимое secret-like файлов. Не обходить policy через shell replacement, Base64/encoding/obfuscation или другой transport.

Для внешних mutations применять дисциплину:
`target -> expected_state -> smallest action -> verify`; при unexpected result сначала read-only diagnosis, без blind retry/reset/clean/force/delete.

## Документация

Устойчивые решения фиксировать в baseline/design docs; временные наблюдения — в findings/report. Не помещать в baseline текущие SHA, активные PR, CI status или версии, которые быстро меняются.

Рабочее общение и документы проекта — по-русски; код, identifiers и machine-readable fields — преимущественно по-английски, если нет отдельного решения.
