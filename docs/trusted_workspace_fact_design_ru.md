# Trusted workspace fact — design и acceptance

Статус: **CONSUMER CONTRACT PASS / PRODUCER INTEGRATION PENDING / NO POLICY WIDENING**.

Этот slice реализует F4 из `architecture_simplicity_reconciliation_ru.md` только на уровне consumer contract и deterministic matching.

Он **не** меняет текущие classifier decisions: `cmake --build`, `ctest`, `pytest` и другие project-code families остаются `ASK_USER`, пока отдельно не доказан trusted producer/integration path.

## 1. Зачем нужен trust fact

Default threat model не требует sandboxing кода проекта, который пользователь сознательно выбрал как доверенный workspace.

Но строка из model/tool input:

```text
trusted_workspace=true
```

не может быть основанием для ALLOW.

Нужен внешний технически установленный факт, который относится к конкретному workspace identity и ограниченному набору development families.

## 2. Главный инвариант

> **Fact validity не равна fact authenticity.**

JSON может быть синтаксически правильным и полностью model-forged.

Поэтому будущий classifier/integration adapter не должен принимать `WorkspaceTrustFact` из:

- command argv;
- tool args;
- prompt/model prose;
- project-local tracked/untracked file, доступного обычному model-controlled write path;
- caller-controlled environment variable.

Fact имеет authorization значение только если он получен через отдельно доказанный trusted provider.

## 3. Owner

`opencode_permissions` владеет:

- schema/semantics trust fact как policy input;
- exact matching observed workspace к fact;
- тем, какие command families могут потреблять конкретный scope;
- правилом, что trust никогда не отменяет hard DENY/secrets boundaries.

Managed setup plane владеет:

- UX/операцией, которой пользователь создаёт/отзывает trust;
- хранением registry/state;
- защитой registry от обычного model-controlled self-modification;
- установкой provider integration.

`agent-safe` не является owner workspace authorization trust. Его resource lifecycle остаётся отдельным execution-safety concern.

## 4. Logical schema

Минимальный fact:

```yaml
schema: workspace-trust-fact/v1
trust_class: development
workspace:
  platform: linux|windows
  requested_root: ...
  resolved_root: ...
  object_identity: ...
scopes:
  - build
  - test
  - static_check
  - git_read
```

### `workspace`

Trust привязан не просто к строке пути.

Обязательны:

- platform;
- exact requested root representation;
- resolved root;
- basic directory object identity, полученная trusted preflight/runtime layer.

Замена workspace другим объектом по тому же пути должна инвалидировать fact до нового user/setup trust action.

Content hash всего репозитория не требуется: обычная разработка должна менять файлы без постоянного re-trust.

### `scopes`

Scopes — не permissions сами по себе.

Они только разрешают classifier применить отдельную заранее доказанную family policy.

Допустимые v1 scopes:

```text
build
test
static_check
git_read
```

Не существует scopes:

```text
all
shell
write_anything
delete
system
privilege
secrets
```

## 5. Почему это не blanket trust

Даже при:

```text
trust_class=development
scopes=[build,test]
```

сохраняются:

- native hard DENY;
- secret read DENY;
- explicit destructive command DENY;
- system/service/privilege boundaries;
- wrapper/nested payload analysis;
- external target semantics;
- target/effects authorization binding.

Trust может изменить только заранее определённую uncertainty:

```text
execution.project_code
```

для конкретной development family, если отдельный policy slice это разрешит.

Он не должен удалять другие uncertainties/effects.

## 6. Consumer contract

Предлагается интерфейс уровня adapter/composer:

```text
TrustedWorkspaceProvider.lookup(observed_workspace_identity)
    -> WorkspaceTrustFact | None
```

Ключевое требование:

> classifier analyzer не принимает trust fact как поле `parsed-simple/v1` от caller/model.

Trusted provider является отдельной dependency integration layer.

Pure code этого slice реализует только:

```text
validate_workspace_trust_fact(fact)
match_workspace_trust_fact(fact, observed_workspace_identity)
```

и **не** утверждает authenticity provider-а.

## 7. Exact matching

Fact применяется только если одновременно совпадают:

```text
schema
trust_class
platform
requested_root
resolved_root
object_identity
```

Scopes должны быть известными, уникальными и непустыми.

Никаких:

- prefix/path-parent matching;
- nearest workspace;
- case folding;
- Unicode normalization;
- wildcard scopes;
- inherited trust дочернему checkout как отдельному repository object без explicit policy.

Если observed identity неполна или не совпадает — `NO_TRUST`.

## 8. Отзыв/замена workspace

V1 intentionally прост:

- registry entry отсутствует -> no trust;
- object identity изменилась -> no trust;
- setup/user удалил entry -> no trust;
- scope отсутствует -> эта family не trusted.

TTL, автоматическая expiry и сложная generation protocol не нужны в default profile без evidence необходимости.

Это соответствует принципу «перил», а не high-assurance broker model.

## 9. Build/test semantics после будущего integration gate

Этот design не даёт ALLOW прямо сейчас.

Будущий отдельный policy slice может рассматривать, например:

```text
cmake --build <workspace build dir>
ctest --test-dir <workspace build dir>
python -m pytest ...
```

как development code execution при выполнении всех условий:

1. native decision = ASK, не DENY;
2. exact parser/command family распознана;
3. workspace identity exact;
4. trusted provider вернул matching fact;
5. требуемый scope присутствует;
6. нет дополнительного explicit dangerous/nested/system effect;
7. production profile для этой family отдельно принят и протестирован.

Главное изменение threat model здесь:

> в trusted development workspace project-code execution само по себе больше не считается неизвестностью, требующей человека при каждом запуске.

Это не утверждение, что project code side-effect-free. Пользователь заранее доверил workspace для этой family.

## 10. Git read

Scope `git_read` допускается в schema, но F5 не реализуется автоматически.

Plain `git diff` и другие read-only Git commands получают отдельное решение только после paired positive/negative corpus и проверки repository/config boundaries.

## 11. Security negative cases

Executable regression покрывает:

- unknown schema -> reject;
- unknown trust class -> reject;
- empty scopes -> reject;
- unknown/wildcard scope -> reject;
- duplicate scope -> reject;
- platform substitution -> no match;
- requested root substitution -> no match;
- resolved root substitution -> no match;
- object identity substitution -> no match;
- missing observed field -> no match;
- caller-supplied `trusted=true` -> invalid shape;
- fact JSON сам по себе не получает признак provider authenticity;
- Windows path matching остаётся case-sensitive/conservative.

## 12. Acceptance result

Consumer-contract slice PASS:

1. schema/validator deterministic;
2. exact matcher fail-closed;
3. classifier/native decisions не расширялись;
4. текущие safety regressions остаются зелёными;
5. Linux/Windows Python matrix PASS;
6. документация явно отделяет validity от authenticity;
7. future producer/integration остаётся отдельным gate.

Implementation evidence:

```text
tools/workspace_trust.py
tests/test_workspace_trust.py
```

## 13. Что нужно перед первым trust-conditioned ALLOW

Отдельно доказать:

1. trusted provider/storage path;
2. user/setup create/revoke lifecycle;
3. model-controlled tools не могут автоматически изменить effective trust registry;
4. runtime acquisition observed workspace identity;
5. exact matching provider fact;
6. paired build/test positive/negative corpus;
7. prompt-reduction benefit;
8. effective integration через managed setup plane.

До этого текущий conservative build/test ASK остаётся действующим.
