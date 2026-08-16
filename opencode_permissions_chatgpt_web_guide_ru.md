# OpenCode Permissions — ChatGPT Web Guide

Статус: persistent working guide  
Дата: 2026-08-16

Документ описывает, как вести проект из ChatGPT Web. Архитектурные требования находятся в `opencode_permissions_project_baseline_ru.md`.

---

## 1. Роль ChatGPT Web

ChatGPT Web — основная среда для:

- архитектуры и исследования;
- проверки актуальной публичной документации;
- анализа GitHub state;
- разработки policy/test corpus;
- подготовки кода и документов;
- review;
- GitHub writes, доступных через Connector;
- анализа отчётов локального агента.

Не делегировать агенту whole task только потому, что один шаг требует локальной машины.

---

## 2. Начало содержательной задачи

1. Прочитать Project Instructions.
2. Прочитать baseline и только релевантные Sources.
3. Через GitHub Connector проверить актуальное состояние `dilukhin/opencode_permissions`.
4. Если задача зависит от OpenCode semantics/version — проверить актуальные официальные источники и/или фактическую исследуемую версию.
5. Определить:
   - confirmed facts;
   - assumptions;
   - open decisions;
   - expected outputs;
   - verification.
6. Только после этого изменять design/code/docs.

Не считать roadmap или старый findings доказательством реализации.

---

## 3. Web-first decomposition

Для каждой задачи разделять:

```text
Web-capable:
  research
  architecture
  policy
  code/doc drafting
  GitHub inspection/write
  review
  test-case design
  result analysis

Local-only:
  installed OpenCode observation
  local config discovery
  Windows shell behavior
  local workspace/build
  real UI prompt capture
  isolated local experiment
```

Web завершает reasoning до делегирования.

---

## 4. Делегирование локальному агенту

Задание должно содержать:

1. exact workspace/repository path;
2. branch/base state;
3. documents/files to read;
4. objective;
5. allowed files/commands;
6. forbidden scope;
7. expected observations/change;
8. exact checks;
9. acceptance criteria;
10. report schema;
11. stop/escalation conditions.

Предпочитать:

> «Собери эти 12 read-only observations и верни JSON/report»

вместо:

> «Разберись с permissions и исправь».

Если агент обнаружил решение, которое требует новой архитектуры, Web принимает решение отдельно.

---

## 5. GitHub policy

GitHub Connector — основной remote channel.

Перед remote `git/gh`:
- сначала определить, есть ли нужная Connector operation;
- не использовать `git/gh` как connectivity probe.

Local Git:
- только подтверждённый local checkout;
- diff/history/tests;
- либо доказанный Connector capability gap.

Для multi-file writes через Connector предпочтительна атомарная публикация через Git Data API (`blob -> tree -> commit -> ref`), если это доступно и оправдано.

Перед перемещением ref:
- перечитать актуальный HEAD;
- не force-update неизвестное состояние.

После значимого write:
- один targeted Connector read-back;
- подтвердить GitHub-side state.

PR/review/CI:
- не объявлять success по локальному состоянию;
- проверять фактический PR head/checks;
- не смешивать unrelated changes.

---

## 6. Decision discipline

Использовать статусы:

- **approved** — принято и нормативно;
- **preference** — сильный default, но может измениться по evidence;
- **candidate** — рассматриваемый вариант;
- **experiment** — проверяемая гипотеза;
- **future idea** — вне текущего scope.

Не превращать brainstorm в архитектуру без явного решения.

---

## 7. Version-sensitive research

Для OpenCode нельзя полагаться на старую память.

При исследовании фиксировать:

```yaml
opencode_version:
platform:
install_method:
config_paths:
experiment_id:
input:
observed_result:
source:
confidence:
```

Если docs и runtime расходятся, зафиксировать расхождение и проверить upstream source/tests прежде чем менять policy.

---

## 8. Experiment design

Перед экспериментом определить:

```text
question
hypothesis
environment
input
expected observations
execution safety
stop condition
```

Классы:

- read-only;
- parser-only/mock;
- isolated temp fixture;
- real mutation.

Для deny/destructive tests использовать parser-only/mock или временную среду.

Нельзя проверять «сработает ли deny» удалением реального рабочего объекта.

---

## 9. Native-first workflow

Для нового permission gap:

1. воспроизвести prompt/decision;
2. сделать минимальный testcase;
3. проверить native pattern semantics;
4. попытаться решить точным native rule;
5. измерить false allow/false block;
6. только если native rule недостаточен — проектировать classifier;
7. auditor рассматривать последним.

---

## 10. Работа с `agent-safe`, `ssh_relay`, `opencode_setup`

Не переносить их код/правила внутрь проекта автоматически.

### `agent-safe`

Использовать runtime protocol для risky state changes; permission classifier должен лишь решить routing/decision.

### `ssh_relay`

Не считать `ssh_relay` safe по имени. Анализировать remote intent/payload и учитывать machine outcome/unknown semantics.

### `opencode_setup`

После стабилизации feature передать integration/deployment contract в `opencode_setup`; не встраивать setup logic в classifier.

---

## 11. Review checklist

Перед завершением design/code slice проверить:

- scope не расширен;
- hard deny не ослаблен;
- unknown не стал allow;
- compound/nested effects разобраны;
- secrets не попали в logs/tests;
- regression corpus обновлён;
- negative cases безопасны;
- docs не утверждают version-sensitive факт без проверки;
- repository state подтверждён;
- следующий gate не начат автоматически.

---

## 12. Обновление Sources

Изменять baseline только при изменении устойчивой архитектуры/границы.

Findings/report использовать для:
- наблюдений;
- версии OpenCode;
- конкретного incident;
- экспериментальных результатов.

Не помещать в persistent Sources:
- текущие SHA;
- текущие PR numbers;
- transient CI status;
- длинные raw logs;
- копию всего репозитория.

---

## 13. Формат завершения существенной итерации

Кратко фиксировать:

```text
Что проверено
Что подтверждено
Что изменено
Какие tests/evidence
Какие assumptions сняты
Какие open questions остались
Закрыт ли текущий gate
Следующая bounded задача
```

Если требуется локальный агент, выдавать отдельный детерминированный prompt после Web-анализа.
