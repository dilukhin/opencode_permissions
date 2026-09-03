# Gate B — Windows peer-process identity runtime probe

Статус: **REVIEWED RUNTIME EVIDENCE / B-P2 PASS / Windows kernel primitive only**  
Дата review: 2026-09-03  
Проект: `dilukhin/opencode_permissions`

Этот документ фиксирует только reviewed/sanitized выводы bounded synthetic B-P2 probe на Windows. Raw machine-specific report остаётся local evidence и не публикуется в repository.

## 1. Scope

B-P2 проверял feasibility Candidate B на Windows:

> может ли local authorization broker отличить заранее зарегистрированный trusted host process от same-user child/untrusted process по kernel-reported named-pipe peer PID и удерживать lifecycle-bound process reference без bearer secret.

Probe **не** запускал OpenCode и не является Windows OpenCode integration proof. Он проверяет Windows kernel/process primitive, необходимый Candidate B.

## 2. Environment

Reviewed probe выполнен на:

```text
Windows 10 Home Single Language
version/build 10.0.19045 / 19045
Windows PowerShell Desktop 5.1
```

Без elevation, package install, service/registry/firewall changes и без OpenCode/repository mutation.

## 3. Implementation method

Использован in-memory PowerShell `Add-Type` с C# P/Invoke и synthetic local processes.

Проверенные Windows APIs/primitives:

```text
NamedPipeServerStream
GetNamedPipeClientProcessId
OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE, inherit=false, pid)
GetProcessId
GetHandleInformation
WaitForSingleObject
CloseHandle
```

Bearer authorization secret клиенту не выдавался и для acceptance не требовался.

## 4. Trusted host identity

Broker заранее знал PID synthetic registered host и удерживал process object HANDLE, открытый с `inherit=false`.

При подключении registered host к local named pipe было подтверждено одновременно:

```text
kernel GetNamedPipeClientProcessId peer PID == registered host PID
GetProcessId(retained HANDLE) == registered host PID
registered host connection -> ACCEPT
```

`GetHandleInformation` подтвердил, что retained process HANDLE не наследуемый.

Результат: trusted peer identity не основывается на PID, присланном клиентом, или на model-visible token.

## 5. Same-user child rejection

Отдельный same-user synthetic child подключался к следующему pipe instance.

Наблюдение:

```text
kernel peer PID == actual child PID
child peer PID != registered host PID
child connection -> REJECT
```

Следовательно, знание pipe name и принадлежность тому же Windows user не делают child trusted caller.

## 6. Host lifecycle binding

Retained process HANDLE проверялся через `WaitForSingleObject(handle, 0)`.

Наблюдение:

```text
registered host жив:
  WAIT_TIMEOUT

after registered host exit:
  WAIT_OBJECT_0
```

После exit registration была инвалидирована.

Таким образом, bounded predicate может быть привязан к process object lifecycle, а не только к повторно используемому numeric PID.

## 7. Acceptance B-P2.1–B-P2.9

Reviewed raw report подтверждает все required acceptance items:

| ID | Requirement | Result |
|---|---|---|
| B-P2.1 | registered host peer PID obtained from kernel API | PASS |
| B-P2.2 | registered host connection accepted | PASS |
| B-P2.3 | same-user child gets distinct kernel PID | PASS |
| B-P2.4 | child/untrusted connection rejected | PASS |
| B-P2.5 | retained registered process HANDLE non-inheritable | PASS |
| B-P2.6 | host exit observable via retained HANDLE | PASS |
| B-P2.7 | registration invalidates after host exit | PASS |
| B-P2.8 | no bearer approval secret required | PASS |
| B-P2.9 | no elevation/destructive/system mutation | PASS |

Итог: **B-P2 PASS**.

## 8. Windows Candidate B bounded predicate

На проверенном Windows runtime подтверждена feasibility следующего local primitive:

```text
ACCEPT only if:
  pipe_peer_pid == GetProcessId(registered_process_handle)
  AND registered_process_handle represents a live registered host
  AND registration_generation is current

otherwise REJECT
```

`registration_generation` в B-P2 synthetic; production lifecycle/startup ownership остаётся отдельным implementation concern.

## 9. Что этот evidence НЕ доказывает

B-P2 не доказывает:

- установленную exact версию OpenCode на Windows;
- runtime execution project-local OpenCode custom tool на Windows;
- production broker concurrency/storage/ACL/pipe-namespace hardening;
- trusted startup/registration implementation;
- production permission artifact deployment;
- `agent-safe` PEP registration/handoff;
- remote named-pipe behavior.

OpenCode process/tool model для exact `1.18.26` остаётся source-revalidated; Linux real OpenCode integration отдельно подтверждён `docs/gate_b_linux_opencode_broker_probe_ru.md`.

## 10. Gate impact

B-P2 больше не является blocker Gate B.

Подтверждены обе OS-specific peer/lifecycle feasibility branches Candidate B:

```text
Linux:  SO_PEERCRED + pidfd      PASS
Windows: named-pipe peer PID + retained process HANDLE  PASS
```

Это закрывает cross-platform kernel peer-identity feasibility, но само по себе не делает current compatibility profile или permission artifact production `DEPLOYABLE`.

## 11. Safety

Probe выполнен synthetic/local-only:

- без destructive operations;
- без elevation/debug privilege/process injection;
- без package install/update;
- без OpenCode config mutation;
- без repository/GitHub mutation локальным агентом;
- без secret disclosure.
