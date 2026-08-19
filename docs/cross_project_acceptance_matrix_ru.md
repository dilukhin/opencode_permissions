# Cross-project integration acceptance matrix

Статус: **ACCEPTED acceptance plan / execution pending**.

Матрица задаёт evidence, необходимое для project gates B–G. Проверки опасных кейсов выполняются parser-only, mocks, synthetic fixtures, temp/isolation; destructive validation запрещён.

| ID | Scenario | Expected result | Primary gate | Evidence |
|---|---|---|---|---|
| A1 | Direct deterministic-safe operation | native `ALLOW`, без лишнего ASK | B | corpus/policy test |
| A2 | Hard-dangerous direct operation | hard `DENY` до mutation | B | parser/policy test |
| A3 | Unknown/ambiguous effect | не auto-ALLOW; controlled/ASK according policy | B | corpus test |
| A4 | Secret-like read boundary | canonical deny/ask semantics сохраняются | B | synthetic path cases |
| A5 | External-directory boundary | version-locked native behavior + conservative policy | B | synthetic path cases |
| A6 | `safe exec-risky ... --approved` с risky nested payload | outer wrapper не даёт blanket authorization | B/C | mock/parser regression |
| A7 | `python -m agent_safe exec-risky ... --approved` | caller flag не создаёт integrated authorization | B/C | unit/mock regression |
| A8 | Grant соответствует operation | execution path может продолжиться при runtime preconditions | B/C | contract unit test |
| A9 | Grant/payload mismatch | reject до mutation | B/C | contract unit test |
| A10 | Grant/target mismatch | reject до mutation | B/C | contract unit test |
| A11 | Replay вне разрешённого scope/lifetime | reject | B/C | grant lifecycle test |
| A12 | Pre-ASK preflight | только read-only evidence, без mutation | C | unit/mocked execution |
| A13 | Runtime state drift после authorization | повторный preflight обнаруживает blocker -> `RUNTIME_REJECT` | C | fixture |
| A14 | Authorized mutation с verify success | `DONE` + verification evidence | C | safe temp fixture |
| A15 | Authorized mutation с unexpected result | `UNEXPECTED`/incident path, no blind cleanup | C | mocked/safe fixture |
| A16 | `ssh_relay exec/sudo-exec` dangerous payload | relay wrapper не даёт blanket authorization | B/D | parser/contract mock |
| A17 | `ssh_relay job` payload | authorization относится к payload/effects, не только `job start` | B/D | mock |
| A18 | relay `upload/download` | transfer effects/target видимы upstream policy | B/D | synthetic transfer model |
| A19 | Remote outcome `unknown` | no success assumption, no blind retry | D | state-machine test |
| A20 | `--risky` transport label | не считается approval evidence | D | CLI/contract test |
| A21 | Verified ScopedKB fact | policy может использовать только по explicit rule | E/B | context-policy fixture |
| A22 | Stale/unknown/missing ScopedKB fact | policy не становится более permissive | E/B | context-policy fixture |
| A23 | Generated ScopedKB context содержит factual routing only | нет самостоятельных `ALLOW/ASK/DENY` semantics | E | schema/content test |
| A24 | Fresh setup environment | managed `opencode_permissions` checkout + agreed artifact deployed | F | isolated validator |
| A25 | Current managed checkout | reconcile no-op | F | idempotency test |
| A26 | Outdated clean managed checkout | safe update по version policy | F | repository fixture |
| A27 | Managed checkout с tracked/local changes | conflict, no reset/clean/force | F | repository fixture |
| A28 | Legacy exact `agent-safe` permission artifact | explicit migrate/remove + verify | F | synthetic filesystem fixture |
| A29 | Legacy modified artifact | preserve + conflict | F | synthetic fixture |
| A30 | Unknown/user-owned permission artifact | preserve + conflict/no blind delete | F | synthetic fixture |
| A31 | Mixed `opencode.json`/`opencode.jsonc` effective state | managed scope converges к desired state | F | config-layer fixture |
| A32 | Environment/project competing permission layer | обнаружен inventory/conflict или управляемое решение по contract | B/F | sanitized inventory fixture |
| A33 | Repeated deploy desired state | idempotent `C -> C` | F | validator |
| A34 | Deploy exit 0, effective state неверен | gate fails; exit code insufficient | F | negative validator |
| A35 | Auditor предлагает override hard deny | hard deny сохраняется | later auditor/G | mock decision test |
| A36 | Runtime/context/transport metadata пытается broaden deny | deny сохраняется | G | integration mock |
| A37 | Full controlled local mutation | normalize -> authorize -> grant -> preflight -> execute -> verify | G | safe integration fixture |
| A38 | Full controlled remote mutation | authorization upstream -> relay transport -> runtime verify | G | mocked/isolated integration fixture |

## Метрики Gate B

Native-policy work должно сравнивать baseline prompts Stage 0 и новую policy минимум по:

- total cases;
- auto-ALLOW count;
- mandatory ASK count;
- hard DENY count;
- false-safe regressions = **0** по dangerous/unknown invariant cases;
- prompt reduction на safe deterministic families;
- wrapper cases отдельно, чтобы снижение prompts не достигалось blanket trust.

## Gate closure rule

Каждый gate закрывается только по применимым строкам этой матрицы с явным evidence. `deferred`/`not applicable` требует причины. Roadmap/design text не заменяет выполненную verification.
