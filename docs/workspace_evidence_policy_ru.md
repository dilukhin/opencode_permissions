# Workspace / Evidence Policy

Статус: persistent operational rule  
Проект: `dilukhin/opencode_permissions`

## 1. Назначение

Локальный workspace должен физически отделять Git-репозиторий от raw evidence и временных результатов агента.

Стандартная структура:

```text
<workspace>/
  opencode_permissions/   # Git repository
  evidence/               # local, non-versioned evidence
    stage0/
    <other-stage>/
```

Для текущего Windows workspace это означает:

```text
C:\Users\d.ilyhin\Projects\opencode_permissions\
  opencode_permissions\
  evidence\
    stage0\
```

## 2. Что хранится в repository

Только артефакты, которые являются частью проекта и должны версионироваться:

- source code;
- tests/fixtures, специально созданные как regression assets;
- schemas/manifests;
- normative design/docs;
- approved/sanitized findings/report, если ChatGPT Web явно решил их публиковать;
- CI/config files.

Наличие полезной информации само по себе не делает файл repository artifact.

## 3. Что хранится в workspace evidence

По умолчанию сюда идут:

- raw inventory JSON;
- machine-specific metadata;
- локальные пути;
- prompt/approval captures;
- временные audit reports;
- execution transcripts;
- intermediate experiment output;
- screenshots/log extracts;
- результаты, которые ещё не прошли Web review/sanitization.

Для Stage 0 использовать:

```text
<workspace>/evidence/stage0/
```

Рекомендуемые имена:

```text
stage0_inventory_<date>.json
stage0_resolved_permissions_<date>.json
stage0_local_audit_report_<date>.md
stage0_probe_<id>_<date>.*
```

## 4. Правило агента

Перед созданием любого output-файла определить его класс:

```text
version-controlled project artifact -> exact path inside repository from task/design
raw/local evidence                  -> <workspace>/evidence/<stage>/
unknown                             -> evidence, then escalate if publication is needed
```

Не создавать raw evidence в repository root, `docs/`, `tests/` или `tools/` только ради удобства передачи результата.

Не выполнять `git add` для evidence и не копировать его в repository без отдельного решения ChatGPT Web.

## 5. Publication rule

Если evidence содержит устойчивый вывод, ChatGPT Web:

1. анализирует raw artifact;
2. отделяет fact от inference;
3. удаляет machine-specific/sensitive/transient детали;
4. выбирает подходящий repository document;
5. публикует только sanitized conclusion или специально одобренный fixture.

Raw artifact при этом может остаться только в workspace evidence.

## 6. Secrets и privacy

Evidence area не отменяет общие secret rules.

Не записывать туда secrets без явной технической необходимости. Не включать credentials, tokens, private keys, auth headers или secret-file contents в отчёты для ChatGPT Web.

Machine-specific paths допустимы в local evidence, но обычно не нужны в публичном repository.

## 7. Defense in depth

Repository `.gitignore` может игнорировать известные случайные root-level Stage 0 evidence filenames, но это только страховка.

Основное правило — создавать raw evidence **сразу вне Git repository**.

Если старый task/example показывает `--output stage0_inventory.json` из repo root, использовать workspace evidence path из этого документа, если задача явно не требует иного.
