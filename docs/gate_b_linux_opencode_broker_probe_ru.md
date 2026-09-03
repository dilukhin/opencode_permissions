# Gate B — Linux OpenCode authorization-broker runtime probe

Статус: **REVIEWED RUNTIME EVIDENCE / Linux only**  
Дата: 2026-09-02  
Проект: `dilukhin/opencode_permissions`

Этот документ фиксирует только reviewed/sanitized выводы локальных synthetic probes на Linux Mint машине ILUKHIN. Raw machine-specific reports остаются local evidence и не публикуются в repository.

## 1. Target runtime

Фактически наблюдавшийся runtime:

```text
OpenCode 1.18.26
Linux Mint 22.3
Linux kernel 6.14.x, x86_64
```

Это runtime observation конкретной машины, а не автоматическая декларация совместимости будущих OpenCode versions.

## 2. B-P1 — kernel peer identity / lifecycle

Synthetic Unix-domain-socket probe подтвердил:

- `SO_PEERCRED` возвращает PID фактического client process;
- registered host connection принимается только при совпадении kernel-reported peer PID;
- отдельный same-user child получает отличный PID и отвергается;
- `pidfd_open` доступен без elevation;
- pidfd не сигнализирует exit, пока registered host жив;
- host exit наблюдается через pidfd;
- registration после host exit инвалидируется;
- bearer authorization secret для этого механизма не нужен.

Результат: **B-P1 Linux PASS**.

## 3. B-P4a — real OpenCode host-process identity

Использовался disposable project-local custom tool и local broker. Production/user OpenCode config не менялся.

Controller запускал exact `opencode run` process, регистрировал его `Popen.pid` через private controller→broker control channel, после чего custom tool подключался к отдельному Unix authorization socket.

Broker durably observed:

```text
registered OpenCode PID == SO_PEERCRED peer PID
registered host live == true
decision == AUTHORIZED
```

Exact OpenCode 1.18.26 source separately confirms, что project/plugin custom `def.execute(...)` вызывается внутри ToolRegistry host runtime, а normal `opencode run` without `--attach` uses an in-process server path. Поэтому runtime peer PID observation относится к тому же host process, который выполняет custom tool.

Один ранний synthetic tool variant вернул result object не по `ToolResult` contract и получил adapter error уже после успешного IPC. Это не изменяет peer-identity evidence; последующий probe использовал корректный `output: string` result contract.

Результат: **B-P4a PASS by runtime evidence + exact-source corroboration**.

## 4. B-P4b — same-user child rejection / fail-closed / host lifecycle

В successful bounded probe:

- exact OpenCode host PID был registered через private controller channel;
- trusted custom-tool connection имел `SO_PEERCRED.peer_pid == registered OpenCode PID` и получил `AUTHORIZED`;
- custom tool `process.pid` совпал с registered OpenCode PID;
- same-user synthetic child имел другой kernel-reported peer PID и получил `REJECTED`;
- registered host pidfd оставался unsignaled, пока host был жив;
- после штатного завершения OpenCode host pidfd сигнализировал exit;
- registration generation была инвалидирована после host exit;
- отдельный broker-unavailable subtest вернул explicit `BROKER_UNAVAILABLE`, без fallback-to-allow;
- bearer secret, model-visible approval token, `--approved`, `--auto` и persistent approval не использовались.

Результат: **B-P4b PASS**.

## 5. Security conclusion for Linux Candidate B

На проверенном Linux/OpenCode 1.18.26 runtime подтверждён следующий bounded transport predicate:

```text
ACCEPT only if:
  kernel_peer_pid == registered_opencode_pid
  AND registered host is live
  AND registration_generation is current

otherwise REJECT
```

Model-controlled same-user child не становится trusted caller только из-за знания Unix socket path. Security boundary не зависит от bearer secret, доступного через argv/environment.

Это закрывает Linux feasibility части Candidate B для:

- trusted OpenCode host identification;
- same-user child rejection;
- host-lifecycle invalidation;
- broker-unavailable fail-closed behavior.

## 6. Что этот evidence НЕ закрывает

Документ не доказывает:

- Windows named-pipe peer identity — остаётся B-P2;
- production broker implementation/hardening;
- installer/reconciler integration;
- complete native permission policy/corpus acceptance;
- deterministic classifier;
- model auditor;
- compatibility будущих OpenCode releases.

Gate B остаётся OPEN до завершения остальных acceptance items.

## 7. Safety

Все probes были synthetic/local-only:

- без real destructive operations;
- без elevation;
- без package install/update;
- без production/user OpenCode config mutation;
- без repository mutation локальным агентом;
- без secret disclosure.
