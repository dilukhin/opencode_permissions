# YC transitional runtime: рабочий переходный контракт

Статус: переходный runtime-срез для разблокирования LanFabric. Это не закрытие полного Gate B authorization binding.

## Назначение

Артефакт материализует текущую каноническую YC-политику из `policy/yc/yc_policy.v1.json` вместе с тем же `classifier_yc.py`, classifier core и NormalizedOperation identity. YC runtime/guard является PEP: он не имеет собственной таблицы разрешений и не расширяет решения `opencode_permissions`.

Переходное исключение намеренно узкое: операции, которые канонический classifier уже классифицирует как exact `ALLOW` с эффектом `cloud_state_change`, могут быть переданы executor без отдельного пользовательского approval. В текущей policy это только exact start/stop VM `epd42hrnss08t2440g90` с exact argv.

Это исключение нужно только для временного рабочего контура LanFabric. В полной версии оно заменяется trusted authorization binding.

## Runtime contract

Порядок:

1. setup/reconciliation фиксирует downstream YC executable как trusted `resolved_path + object_identity`;
2. parser/preflight формирует exact `parsed-simple/v1` fact;
3. adapter проверяет, что executable identity fact точно равна trusted target;
4. canonical `classifier_yc.analyze_yc` возвращает `ALLOW | ASK_USER | DENY`;
5. `DENY` и `ASK_USER` никогда не передаются executor;
6. `ALLOW` передаётся executor как exact trusted executable path + argv tail, без PATH lookup.

Runtime не принимает `approved=True`, `authorized`, `policy_allow`, `skip_guard` или аналогичный caller-controlled сигнал как доказательство разрешения.

## Границы переходного среза

Артефакт не:

- устанавливает guard и не меняет PATH;
- ищет скрытый реальный `yc.exe`;
- читает credentials/config;
- выполняет реальные cloud mutations в тестах;
- меняет `agent-safe`;
- меняет LanFabric;
- добавляет второй PDP или отдельную semantic policy;
- объявляет переходный auto-allow state change полноценной authorization binding моделью.

`agent-safe` по-прежнему владеет runtime safety/preflight/verify/recovery. setup/agent-toolchain владеет установкой, pinning downstream executable и reconciliation.

## Fail-closed

Следующие состояния являются runtime contract/integrity failure и не превращаются в пользовательский override:

- mismatch trusted executable path/object identity;
- повреждение manifest или любого bundle file;
- несовместимая schema/policy;
- попытка caller-controlled approval/bypass;
- отсутствие canonical runtime component.

Неопределённая или неразрешённая семантика classifier остаётся `ASK_USER`, hard deny остаётся `DENY`.

## Следующий gate

После зелёного parser-only/mock CI следующий отдельный этап — installation/reconciliation design и controlled deployment поверх текущего YC guard. Только после read-back effective state допускается возвращение в LanFabric. Полная версия затем заменяет transitional state-change exception на trusted authorization binding.
