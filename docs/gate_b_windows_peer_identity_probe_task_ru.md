# Local agent task — Gate B B-P2 Windows peer-process identity probe

Статус: **READY FOR DELEGATION / no architecture changes allowed**

## 1. Scope

Выполнить только безопасный synthetic Windows feasibility probe для Candidate B из:

- `docs/gate_b_handoff_candidate_comparison_ru.md`;
- `docs/gate_b_linux_peer_identity_probe_ru.md`.

Не реализовывать production broker, permission policy, deterministic classifier, auditor или `agent-safe` integration.

## 2. Workspace

Создать отдельный temporary workspace:

```text
%TEMP%\opencode_permissions_gate_b_b_p2
```

Перед работой вывести его resolved absolute path.

Не нужен checkout репозитория. Не изменять OpenCode config, user/project config, services, registry или installed software.

## 3. Environment inventory

В отчёте зафиксировать:

```text
Windows edition/version/build
PowerShell edition/version
resolved temp workspace
current process PID
```

Не выводить environment dump и secret-like variables.

## 4. Question

Может ли Windows local authorization broker отличить зарегистрированный trusted host process от его same-user child/unrelated process по kernel-reported named-pipe peer identity и удерживать lifecycle-bound process reference, не используя bearer secret?

## 5. Required API evidence

Использовать штатные Windows API; предпочтительный набор:

```text
CreateNamedPipe / .NET NamedPipeServerStream
GetNamedPipeClientProcessId
OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE, inherit=false, pid)
GetProcessId(process_handle)
WaitForSingleObject(process_handle, 0)
CloseHandle
```

Допустим PowerShell + `Add-Type`/PInvoke или небольшой source file, компилируемый уже доступным штатным toolchain. Не устанавливать dependencies/packages.

Если необходимый API/toolchain недоступен — остановить affected path и вернуть evidence, не искать обход через сторонний transport.

## 6. Synthetic scenario

Предпочтительно использовать три роли:

```text
broker process
registered host client process
child/untrusted client process
```

Минимальная последовательность:

1. Broker создаёт local named pipe с уникальным именем в temp/test scope.
2. Broker запускает/получает PID synthetic registered host process.
3. Broker удерживает **non-inheritable** process HANDLE зарегистрированного host (`OpenProcess`).
4. Registered host подключается к pipe.
5. Broker получает client PID через `GetNamedPipeClientProcessId`.
6. Проверить:
   - peer PID == registered host PID;
   - `GetProcessId(retained_handle)` == registered host PID;
   - retained handle не signaled пока host жив.
7. Registered host или broker запускает отдельный same-user child/untrusted process, который подключается к новому pipe instance.
8. Broker получает peer PID и проверяет:
   - peer PID == фактический child PID;
   - peer PID != registered host PID;
   - authorization predicate возвращает REJECT.
9. Завершить synthetic registered host штатно.
10. Проверить, что retained process handle становится signaled/exit-observable и registration invalidates.
11. Закрыть handles/pipes и удалить только собственные temp files.

Не пытаться специально добиться реального PID reuse; достаточно доказать, что registration опирается на retained process object handle/liveness, а не только numeric PID.

## 7. Required authorization predicate

Зафиксировать и проверить логически:

```text
ACCEPT only if:
  pipe_peer_pid == GetProcessId(registered_process_handle)
  AND registered_process_handle still represents a live registered host
  AND registration_generation is current

otherwise REJECT
```

`registration_generation` в этом probe может быть synthetic monotonically increasing identifier; bearer secret для клиента не нужен.

## 8. Safety

Разрешено:

- temp directory/files;
- named pipes;
- краткоживущие synthetic child processes;
- read-only process queries;
- штатное завершение только собственных synthetic processes.

Запрещено:

- OpenCode runtime/config mutation;
- реальный permission approval;
- запуск destructive commands;
- service/registry/firewall/network changes;
- admin/elevation;
- debug privilege;
- process injection;
- чтение/печать secrets;
- установка software/packages;
- изменение репозитория/GitHub.

## 9. Acceptance

PASS только если все пункты подтверждены:

```text
B-P2.1 registered host peer PID obtained from kernel API
B-P2.2 registered host connection accepted
B-P2.3 same-user child/untrusted peer gets distinct kernel PID
B-P2.4 child/untrusted connection rejected
B-P2.5 retained registered process HANDLE is non-inheritable
B-P2.6 host exit is observable via retained HANDLE
B-P2.7 registration invalidates after host exit
B-P2.8 no bearer approval secret required
B-P2.9 no elevation/destructive/system mutation used
```

Если хотя бы одно core API property невозможно проверить безопасно, result = INCOMPLETE/FAIL с evidence, не импровизировать архитектуру.

## 10. Output report

Создать только:

```text
%TEMP%\opencode_permissions_gate_b_b_p2\gate_b_windows_peer_identity_probe_report.md
```

Report schema:

```text
Environment
Implementation method
Exact APIs used
Scenario
Observed peer identities (PIDs допустимы; никаких secrets)
Process-handle lifecycle observation
Acceptance B-P2.1..B-P2.9
Unexpected/deviations
Temp files/processes cleanup status
Conclusion: PASS | INCOMPLETE | FAIL
```

Не публиковать report в GitHub. Вернуть его ChatGPT Web для review; Web отдельно решит, что и как фиксировать в repository evidence.
