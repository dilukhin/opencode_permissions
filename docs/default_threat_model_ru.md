# Default threat model `opencode_permissions`

Статус: **ACCEPTED DEFAULT THREAT MODEL**.

Этот документ задаёт практическую модель угроз для обычного режима проекта. Более сильная защита допустима как отдельный high-assurance profile, но не должна автоматически становиться обязательной для default-пути.

## 1. Цель

`opencode_permissions` предназначен прежде всего для предотвращения ошибочных, слишком широких или плохо классифицированных действий агента/модели при сохранении разумной автономности.

Проект не является универсальной sandbox/EDR/host-integrity системой.

Коротко:

```text
защищаемся от ошибочного/model-controlled действия
не пытаемся по умолчанию победить уже скомпрометированный host
```

## 2. В default scope

Default profile обязан технически защищать от:

1. ошибочной или чрезмерно широкой команды модели;
2. model-controlled tool arguments и payload;
3. caller/model-controlled self-approval (`--approved`, похожие флаги, prose-маркеры);
4. wrapper/interpreter/remote envelope, скрывающего опасный nested payload;
5. compound/pipeline/redirection semantics, которые меняют effects операции;
6. unknown/opaque/unsupported syntax, ошибочно превращённого в `ALLOW`;
7. deterministic dangerous effects: destructive filesystem/Git, privilege, system/service mutation, secret access и аналогичные hard-deny families;
8. подмены authorization-relevant operation/target/effects между решением и продолжением execution path;
9. несовместимой или неподтверждённой версии OpenCode, если безопасность зависит от version-sensitive behavior;
10. competing/misconfigured effective permission layer, случайно расширяющего policy;
11. попадания secret values в classifier/auditor logs, fixtures или approval context;
12. второго authorization owner, способного повысить `ASK_USER`/`DENY` до `ALLOW`.

## 3. Вне default scope

Без отдельного high-assurance требования default profile не обязан защищать от:

1. намеренно вредоносного кода внутри уже доверенного OpenCode plugin/custom-tool implementation;
2. произвольного malware того же OS-user, не являющегося следствием model-controlled tool invocation;
3. root/administrator compromise;
4. kernel compromise;
5. process injection/debug-privilege attacks;
6. злонамеренной подмены системных executables привилегированным actor;
7. полного sandboxing пользовательского build/test/project code;
8. доказательства отсутствия любого возможного side effect у кода, который пользователь сознательно выбрал как trusted workspace;
9. защиты от физического/аппаратного compromise;
10. общей защиты ОС, сети или supply chain за пределами authorization contract.

Обнаружение такой угрозы не означает игнорирование проблемы. Оно означает:

```text
issue -> отдельный high-assurance requirement/profile
```

а не бесконтрольное усложнение default architecture.

## 4. Модель доверия

Default profile допускает существование технически заданных trust boundaries, если они:

- не задаются model/caller-controlled строкой;
- имеют явного owner;
- воспроизводимо читаются trusted runtime/setup layer;
- не скрывают hard DENY;
- не превращают unknown operation в blanket ALLOW.

Примеры потенциальных trusted facts:

```text
workspace trust class
managed OpenCode installation/profile
managed policy artifact identity
known repository identity
known remote host identity
```

Сам факт доверия не означает, что все операции внутри boundary безопасны. Он лишь позволяет применять другую детерминированную policy там, где threat model это допускает.

## 5. Что остаётся обязательным независимо от trust profile

Даже в trusted workspace:

- hard DENY сохраняет приоритет;
- secret boundaries сохраняются;
- destructive operation не становится safe только из-за workspace trust;
- wrapper/nested payload анализируется целиком;
- model-controlled approval marker не является authorization;
- изменение target/effects требует новой authorization;
- `agent-safe` остаётся владельцем execution safety для state-changing operations.

## 6. High-assurance profile

High-assurance profile может дополнительно требовать, например:

- kernel-authenticated local broker;
- process-lifecycle registration;
- stronger executable object/content identity;
- expanded replay/liveness protections;
- более строгий repository/config trust model;
- sandbox/confinement build/test code;
- дополнительные platform-specific proofs.

Но такой механизм становится обязательным только если одновременно выполнено:

1. сформулирована конкретная угроза;
2. угроза входит в выбранный high-assurance use case;
3. есть воспроизводимый bypass более простого default path или явное внешнее требование;
4. benefit оправдывает operational complexity.

## 7. Minimality test

Перед добавлением нового обязательного safety mechanism нужно ответить:

1. Какая конкретная ошибка/атака существует без него?
2. Входит ли она в default threat model?
3. Есть ли более простой existing owner/component, который уже закрывает её?
4. Что станет измеримо лучше для пользователя?

Если на пункты 1–2 нет ясного ответа, механизм не должен становиться default requirement.

## 8. Связь с `agent-safe`

Threat model не меняет ownership:

```text
opencode_permissions -> authorization decision + binding
agent-safe            -> execution safety + verify/recovery
```

Resource lifecycle (`temporary`, trash, permanent delete, retention, journal, recovery) остаётся за `agent-safe` и не переносится сюда даже в high-assurance profile.

## 9. Принцип проекта

Default режим должен быть **перилами**, а не бронированной клеткой:

> технически предотвращать опасные ошибки и model-controlled обходы, не пытаясь одновременно решить компрометацию всего доверенного host environment.
