# Gate B B-P1 — Linux peer-process identity synthetic probe

Статус: **PASS / Linux feasibility evidence only**  
Дата: 2026-09-02

## 1. Вопрос

Может ли локальный authorization broker на Linux технически отличить запрос, сделанный зарегистрированным trusted host-процессом, от запроса его дочернего model-controlled процесса без bearer token в arguments/environment?

Это B-P1 из `gate_b_handoff_candidate_comparison_ru.md`.

## 2. Environment

```text
platform: Linux, isolated ChatGPT execution environment
language/runtime: Python stdlib
IPC: AF_UNIX stream socket in TemporaryDirectory
peer identity: SO_PEERCRED
process lifecycle reference: pidfd_open + poll
external network: not used
project/user files: not touched
destructive operations: none
```

Это не target Windows/OpenCode runtime и не заменяет installed-runtime acceptance.

## 3. Probe A — registered host vs child

Synthetic broker logic:

```text
registered_host_pid = current host process PID
accept Unix socket connection
kernel returns peer {pid, uid, gid} via SO_PEERCRED
accept iff peer.pid == registered_host_pid
```

Два клиента:

1. connection из самого registered host process;
2. connection из дочернего process того же пользователя/UID.

Observed:

```text
same-process client:
  kernel peer PID == registered host PID
  result: ACCEPT

child-process client:
  kernel peer PID == actual child PID
  kernel peer PID != registered host PID
  UID/GID same as parent
  result: REJECT
```

Таким образом, same-user child не становится trusted peer только потому, что знает Unix-socket path или наследует environment.

## 4. Probe B — lifecycle binding / PID reuse defense primitive

Одного числового PID недостаточно для long-lived registration из-за возможного reuse после process exit.

Synthetic lifecycle probe:

1. создан child process;
2. broker-like process вызвал `pidfd_open(child_pid, 0)`;
3. до exit `poll(pidfd, timeout=0)` не показывал termination readiness;
4. после normal child exit тот же pidfd стал ready;
5. pidfd закрыт явно.

Observed result:

```text
pidfd available: yes
before registered process exit: not signaled
post exit: signaled
```

Design consequence:

- Linux registration должна хранить `registered_pid + pidfd`;
- connection принимается только если `SO_PEERCRED.pid == registered_pid` **и** registered pidfd всё ещё представляет live registered process;
- после process exit registration invalidates до нового trusted registration;
- новый process, даже если ОС когда-либо повторно использует то же numeric PID, не должен наследовать старую registration.

Exact low-level liveness implementation (`poll`, pidfd state API, race handling) фиксируется implementation slice; этот probe доказывает доступность необходимого kernel primitive, а не полный broker.

## 5. Security result

B-P1 подтверждает необходимое свойство Candidate B для Linux:

> kernel-observed IPC peer process identity позволяет отличить trusted host process от его model-controlled child process без model-visible approval secret.

Это существенно сильнее схемы, где child может унаследовать bearer credential через environment.

B-P1 **не** доказывает:

- Windows behavior;
- фактический process model OpenCode custom tool;
- resistance к same-process malicious plugin/code execution внутри самого trusted OpenCode host;
- exact `NormalizedOperation` binding;
- approval UI semantics;
- downstream `agent-safe` handoff.

## 6. Threat-boundary note

Candidate B доверяет коду, исполняющемуся **внутри зарегистрированного OpenCode host process**. Если arbitrary untrusted/model-controlled code уже может выполняться в этом самом process context, peer PID distinction исчезает.

Следовательно, B-P4 обязан отдельно доказать, что proposed trusted gate/custom tool path не даёт model-controlled plugin/code прямого same-process доступа к broker client capability/API. Plugin/tool loading boundaries остаются частью threat model.

## 7. Acceptance

| Criterion | Result |
|---|---|
| registered host identified by kernel peer credentials | PASS |
| child of same UID obtains distinct peer PID | PASS |
| child rejected by host-PID rule | PASS |
| no bearer secret needed for this distinction | PASS |
| process-exit lifecycle reference available | PASS (`pidfd`) |
| destructive execution avoided | PASS |
| Windows parity | NOT TESTED — B-P2 |
| actual OpenCode host integration | NOT TESTED — B-P4 |

## 8. Next bounded step

B-P2 Windows synthetic fixture:

```text
named pipe
-> GetNamedPipeClientProcessId
-> retained non-inheritable process HANDLE for registered host
-> host accepted
-> same-user child rejected
-> registered host exit invalidates registration
```

Затем B-P3 exact operation binding остаётся pure unit/mock, а B-P4 — no-mutation OpenCode custom-tool feasibility probe.
