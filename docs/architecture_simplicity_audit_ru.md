# Аудит архитектурной минимальности `opencode_permissions`

Статус: **REVIEW FINDINGS / BRAINSTORM INPUT**.  
Изменения runtime/policy этим документом не выполняются.

## 1. Вопрос аудита

Проект начинался как практический способ убрать рутинные подтверждения OpenCode, сохранив технические границы опасных действий.

Аудит проверяет, не произошёл ли сдвиг от этой задачи к более сильной и дорогой цели:

> построить локальную security sandbox, устойчивую к намеренно враждебному коду внутри доверенного пользовательского окружения.

Полезная аналогия:

```text
перила:
  не дать агенту случайно/через ошибочную команду сделать опасное действие

бронированная клетка:
  не дать уже исполняющемуся в доверенном окружении враждебному коду атаковать сам механизм разрешений
```

Основной вывод аудита:

> **ядро проекта соразмерно задаче, но вокруг authorization handoff, runtime identity и некоторых "safe development" команд накопился избыточно сильный threat model.**

Эти механизмы полезны как research/high-assurance evidence, но не все должны становиться обязательной production архитектурой.

## 2. Предлагаемая минимальная модель угроз

Перед следующими архитектурными изменениями проекту нужен явный threat model.

### 2.1 В default scope

`opencode_permissions` должен защищать от:

1. ошибочной или слишком широкой команды модели;
2. model-controlled tool arguments/payload;
3. попытки использовать generic wrapper или caller-controlled approval marker как доказательство разрешения;
4. compound/nested payload, скрывающего опасный эффект;
5. неизвестного или неоднозначного эффекта;
6. подмены authorization-relevant target/payload между решением и продолжением операции;
7. stale/incompatible OpenCode permission semantics;
8. случайного configuration drift, создающего более широкое effective разрешение;
9. чтения/попадания secrets в анализ и логи.

### 2.2 Не должно быть default scope

Без отдельного high-assurance требования проект не должен пытаться защищаться от:

1. намеренно вредоносного кода внутри уже доверенного OpenCode plugin/custom-tool implementation;
2. произвольного malware того же OS-user, существующего независимо от model tool path;
3. root/administrator compromise;
4. kernel/process injection/debug privilege attacks;
5. злонамеренной замены системного executable привилегированным actor;
6. общего sandboxing пользовательского project code;
7. доказательства, что любой build/test script в выбранном пользователем проекте физически не способен сделать произвольный system call.

Если в будущем появится реальная потребность в такой защите, её следует оформить отдельным **high-assurance profile**, а не повышать сложность default режима.

## 3. Что в текущей архитектуре выглядит соразмерно

Следующие решения являются именно "перилами" и должны сохраниться:

### 3.1 Native-first

Сначала штатные OpenCode rules, затем deterministic classifier только для gaps.

Это уменьшает собственный runtime code и поддерживает исходную цель проекта.

### 3.2 Hard DENY

Некоторые прямые destructive/system/secret actions должны технически блокироваться до model auditor.

### 3.3 Unknown -> не ALLOW

Непонятный payload не должен становиться безопасным из-за уверенного prose explanation модели.

### 3.4 Whole-operation analysis

Wrapper, interpreter, compound command и remote payload нельзя классифицировать только по безопасному первому executable.

### 3.5 Target/effects binding

Разрешение должно относиться к конкретному target/effects, а не к флагу `approved=true`.

### 3.6 Secret boundary

Permission analysis не должен читать secrets только ради удобства классификации.

### 3.7 Synthetic/non-destructive verification

Опасные negative cases должны проверяться parser-only/mock/temp fixtures.

### 3.8 Один владелец authorization

Разделение `opencode_permissions` / `agent-safe` / `ssh_relay` / `opencode_setup` снижает сложность всей системы, если соблюдается и не дублируется.

## 4. Где обнаружено переусложнение

### F1. Kernel-authenticated authorization broker как default requirement

Gate B исследовал broker с:

- `SO_PEERCRED`/Named Pipe peer PID;
- retained process handles;
- host/PEP registration generations;
- broker generation;
- single-use grant state;
- source-call liveness;
- replay/substitution protection.

Это качественный high-assurance proof, но документ исходно сам называл broker **candidate**, а не approved architecture.

Позже DC-4 доказал рабочий более простой путь через фактический OpenCode permission lifecycle: call-ID/command correlation, deterministic classifier и one-shot permission continuation.

#### Оценка

Для default threat model broker выглядит как **клетка**: он главным образом защищает от отдельного same-user/model-adjacent процесса, который уже пытается атаковать локальный authorization transport.

#### Рекомендация

- не удалять исследования и тесты;
- пометить broker как `HIGH_ASSURANCE OPTION / NOT DEFAULT`;
- не делать его обязательным для первого integrated production path;
- вернуть broker в default architecture только при конкретном воспроизводимом bypass более простого trusted OpenCode path.

### F2. Полный object hash системного executable на каждую authorization revalidation

DC-4 proof требует для `/usr/bin/printf`:

- root owner;
- отсутствие group/world write;
- отсутствие symlink;
- inode/device/mode;
- SHA-256 содержимого;
- повторный полный hash при revalidation.

#### Оценка

Для proof это хорошая демонстрация exact binding. Для production default это защищает уже от tampering системного executable, что ближе к host-integrity problem, чем к permission problem.

Кроме того, это:

- добавляет I/O и latency;
- создаёт хрупкость при package update;
- плохо масштабируется на большие executables;
- усложняет cross-platform поддержку.

#### Рекомендация

Production profile по умолчанию должен связывать только минимально необходимую executable identity:

- resolved executable из доверенного installation/search boundary;
- при необходимости basic object identity;
- content hash только для конкретных высокорисковых случаев или immutable artifact profile.

### F3. Snapshot всего process environment

DC-4 proof сохраняет полный `process.env` и требует его полного равенства перед spawn.

#### Оценка

Это чрезмерно широкая dependency boundary:

- большинство переменных не меняют authorization semantics;
- окружение может содержать secrets, которые permission layer вообще не должен читать без необходимости;
- любое безобидное изменение переменной инвалидирует operation;
- сложно объяснить пользователю и поддерживать.

#### Рекомендация

Bind только **явно authorization-relevant environment dependencies** конкретного analyzer/profile.

Default:

```text
no declared env dependency -> environment не входит в authorization identity
```

Если analyzer реально зависит от `PATH`, конкретного config env или host selector, фиксируются только эти поля или их безопасные derived values.

### F4. Build/test фактически приравнены к недоверенному arbitrary code

Baseline относит build, unit tests и static checks к обычным development operations, которые проект должен выполнять практически без участия пользователя.

Classifier design, однако, оставляет `cmake --build`, `ctest`, `pytest` в `ASK_USER`, потому что project code технически способен выполнить arbitrary actions.

#### Оценка

Это наиболее заметный функциональный симптом "клетки".

Если пользователь сознательно открыл и разрабатывает репозиторий, требование доказать, что его build/test code неспособен выполнить произвольный system call, превращает permission project в sandbox project.

#### Рекомендация

Ввести **технически заданную workspace trust boundary**, не контролируемую моделью.

Например:

```text
trusted_workspace = user/setup-managed fact
```

Внутри такого workspace стандартные build/test/static-check families могут получать отдельную policy, не утверждая при этом, что проектный код математически side-effect-free.

Для unknown/untrusted workspace они остаются ASK.

Важно: это authorization context, а не `agent-safe` resource lifecycle.

### F5. Read-only Git может быть защищён сильнее практической угрозы

Текущий classifier требует для `git diff` отключения external diff/textconv, потому что Git configuration теоретически способен запускать внешние программы.

#### Оценка

Это корректно для adversarial repository/config threat model, но может быть чрезмерно для user-selected trusted repository.

#### Рекомендация

Рассмотреть два профиля:

```text
untrusted repository -> hardened invocation / ASK
trusted repository   -> обычные read-only git commands ALLOW
```

При этом model-write в `.git/config` должен оставаться отдельно защищённым.

### F6. Exact-version compatibility может превратиться в профильный комбинаторный взрыв

Fail-closed на неизвестной версии OpenCode — правильный принцип.

Но отдельные профили для каждой patch-version с повторением одинаковых fingerprints могут стать дорогими в сопровождении.

#### Рекомендация

Сохранить exact target-version check, но разрешить reusable **capability/fingerprint profile family**:

```text
version X -> fingerprints set P -> runtime probe P
version Y -> same fingerprints P -> revalidation with same contract
```

Не делать nearest-version fallback. Упрощение касается хранения evidence, а не ослабления проверки.

### F7. Auditor сейчас преждевременен

Архитектура предполагает optional model auditor после deterministic classifier.

Но classifier gate уже поднял sound safe capture с 54.5% до 69.2% на своей фиксированной projection, а production/pilot интеграция ещё не измеряла реальные остаточные prompts.

#### Оценка

Переход прямо к auditor рискует создать новый сложный компонент до доказательства его ценности.

#### Рекомендация

**Не начинать auditor следующим шагом.**

Сначала:

1. привести документацию в актуальное состояние;
2. интегрировать deterministic path в ограниченный managed pilot через `opencode_setup`;
3. собрать реальную статистику residual ASK;
4. классифицировать причины ASK;
5. попробовать дешёвые deterministic/native улучшения;
6. только если остаётся значимый gray zone — проектировать auditor.

Auditor должен появиться как решение измеренной проблемы, а не потому, что он стоит следующим блоком на старой схеме.

### F8. Спекулятивные cross-project wire contracts

Master plan заранее перечисляет `ContextFacts`, `AuthorizationGrant`, `ExecutionPreflight`, `ExecutionResult`, `RemoteOutcome`, `ManagedArtifactOwnership`.

Часть этих понятий полезна как vocabulary, но полный wire schema до появления реального consumer/provider может создавать архитектуру ради архитектуры.

#### Рекомендация

Стабилизировать только interface, который нужен следующей реальной интеграции.

Например, не детализировать ScopedKB wire format до момента, когда policy действительно потребляет такой context.

### F9. Research evidence смешано с текущей рекомендуемой архитектурой

README и Gate B list показывают broker docs рядом с canonical production-facing artifacts. Старые candidate documents остаются легко воспринимаемыми как действующие требования.

#### Рекомендация

Разделить документы на:

```text
CURRENT CONTRACTS
CURRENT IMPLEMENTATION/CLOSURE
RESEARCH / ALTERNATIVES / HISTORICAL EVIDENCE
```

Research не удалять — он полезен, но он не должен автоматически превращаться в обязательный roadmap.

## 5. Документационные несоответствия, найденные аудитом

### D1. README устарел

README после фактического closure classifier всё ещё говорит:

```text
Deterministic parser/effect analysis — NOT STARTED
Model auditor — NOT STARTED
```

Первое уже неверно.

### D2. `cross_project_unresolved_decisions_ru.md` отстаёт от DC-4

U2 всё ещё описывает trusted-boundary recomputation как deferred, хотя DC-4 уже доказал runtime acquisition/revalidation для ограниченного Linux/OpenCode 1.18.26 profile.

Корректнее:

```text
U2 CLOSED for proven profile;
new command/platform profiles require their own evidence.
```

### D3. Deterministic design document выглядит как активный pre-implementation plan

`deterministic_classifier_gate_design_ru.md` всё ещё имеет статус `IMPLEMENTATION NOT STARTED`, хотя gate закрыт.

Документ следует пометить как historical design, superseded closure-документом по состоянию реализации.

### D4. Master plan всё ещё ведёт к Stage B как к следующему шагу

Это исторически полезно, но навигационно устарело после закрытия B и deterministic classifier.

## 6. Что предлагается упростить, а что не трогать

### Оставить обязательным

- hard DENY;
- unknown/opaque -> ASK;
- secret boundaries;
- whole-operation/nested analysis;
- exact semantic target/effects binding;
- native-first policy;
- non-destructive regression corpus;
- один authorization owner;
- `agent-safe` как отдельный execution-safety owner;
- version-sensitive verification OpenCode.

### Упростить default production path

- broker -> optional high-assurance alternative;
- executable content hashing -> не default requirement;
- full environment snapshot -> explicit dependency subset;
- trusted workspace development operations -> разрешать практичнее;
- read-only Git -> policy зависит от repository trust boundary;
- version profiles -> capability/fingerprint reuse без nearest fallback;
- cross-project wire schemas -> just-in-time.

### Отложить

- model auditor до реальных residual-ASK metrics;
- ScopedKB runtime policy integration до конкретного consumer use case;
- broker-owned approval UI;
- Windows high-assurance IPC path как production blocker Linux pilot.

## 7. Предлагаемая упрощённая последовательность дальнейшей работы

Вместо:

```text
classifier closed
-> auditor
-> ещё contracts
-> integration
```

предлагается:

```text
classifier closed
-> architecture simplicity reconciliation
-> minimal Linux pilot integration through opencode_setup
-> measure real residual prompts
-> deterministic/native tuning
-> auditor only if justified by measurements
```

Параллельно `agent-safe` продолжает свою execution-safety работу независимо и не блокируется auditor research.

## 8. Minimality gate для нового механизма

Перед созданием нового safety component задавать четыре вопроса:

1. **Какая воспроизводимая ошибка/атака существует без него?**
2. **Входит ли эта угроза в default threat model?**
3. **Можно ли закрыть её существующим owner/component проще?**
4. **Как измерится пользовательская польза после добавления?**

Если на первый или второй вопрос нет ясного ответа, механизм не должен становиться default architecture.

## 9. Итог аудита

Проект **не нужно переписывать**.

Основная ценность уже создана:

```text
native policy
+
deterministic whole-operation classifier
+
fail-closed unknown handling
+
clean project ownership boundary
```

Проблема локальная:

> proof-driven разработка местами превратила сильные доказательные fixtures в предполагаемые production requirements.

Поэтому правильная коррекция — не удалить safety, а разделить два уровня:

```text
DEFAULT PRACTICAL GUARDRAILS
    защита от ошибочных/model-controlled операций

OPTIONAL HIGH-ASSURANCE HARDENING
    защита от более сильного локального adversary
```

После такого разделения проект снова соответствует исходной цели: меньше бессмысленных подтверждений при технических, но не чрезмерных, границах опасных действий.
