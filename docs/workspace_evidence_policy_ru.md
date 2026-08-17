# Workspace / Local Artifacts Policy

Статус: persistent operational rule  
Проект: `dilukhin/opencode_permissions`

## 1. Назначение

Локальный workspace должен физически отделять Git-репозиторий от raw evidence, локальных рабочих документов и временных файлов агента.

Стандартная структура:

```text
<workspace>/
  opencode_permissions/   # Git repository
  evidence/               # raw/local evidence
    stage0/
    <other-stage>/
  docs/                   # local-only working documents
  stash/                  # transient working files
```

Абсолютный путь конкретной машины не является частью project source-of-truth. Если для локальной работы нужна точная карта путей, хранить её в:

```text
<workspace>/docs/workspace_layout_local.md
```

Этот файл находится вне Git repository.

## 2. Что хранится в repository

Только артефакты, которые являются частью проекта и должны версионироваться:

- source code;
- tests/fixtures, специально созданные как regression assets;
- schemas/manifests;
- normative design/docs;
- approved/sanitized findings/report, если ChatGPT Web явно решил их публиковать;
- CI/config files.

Наличие полезной информации само по себе не делает файл repository artifact.

## 3. `evidence/`

Назначение: локальные доказательства фактического поведения и результаты экспериментов до Web review/sanitization.

По умолчанию сюда идут:

- raw inventory JSON;
- machine-specific metadata;
- локальные пути, обнаруженные во время аудита;
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

Evidence не является нормативным source-of-truth автоматически.

## 4. `docs/` вне repository

Назначение: локальные рабочие документы, которые полезно сохранять между итерациями, но которые пока не являются частью GitHub-проекта.

Сюда относятся:

- локальные starter prompts;
- handoff-документы;
- рабочие заметки;
- черновики дизайна/отчётов;
- machine-specific инструкции;
- `workspace_layout_local.md` с точными локальными путями;
- документы, подготовленные к возможной последующей публикации, но ещё не прошедшие Web review.

Local `docs/` не следует путать с `<repo>/docs/`.  
`<repo>/docs/` — version-controlled project documentation.  
`<workspace>/docs/` — local-only working documentation.

Если local doc становится устойчивой частью проекта, ChatGPT Web сначала проверяет его и задаёт exact destination внутри repository.

## 5. `stash/`

Назначение: transient/non-authoritative рабочие файлы.

Сюда относятся:

- промежуточные generated files;
- временные patches/diffs;
- transport copies;
- распакованные bundles;
- scratch input/output;
- файлы, нужные только для одной механической операции.

`stash/` не является evidence store и не является source-of-truth.

Не считать файл disposable только потому, что он лежит в `stash/`: агент не удаляет неизвестные или пользовательские файлы без явного разрешения.

## 6. Правило маршрутизации для агента

Перед созданием любого output-файла определить его класс:

```text
version-controlled project artifact
    -> exact path inside repository from task/design

raw observation / experiment result / runtime evidence
    -> <workspace>/evidence/<stage>/

persistent local-only draft / handoff / prompt / machine-specific note
    -> <workspace>/docs/

transient scratch / transfer / intermediate artifact
    -> <workspace>/stash/

unknown
    -> outside repository; prefer stash or evidence according to content, then escalate
```

Не создавать raw/local artifacts в repository root, `<repo>/docs/`, `<repo>/tests/` или `<repo>/tools/` только ради удобства передачи результата.

Не выполнять `git add` для workspace `evidence/`, `docs/` или `stash/` и не копировать их содержимое в repository без отдельного решения ChatGPT Web.

## 7. Publication rule

Если local artifact содержит устойчивый вывод, ChatGPT Web:

1. анализирует исходный artifact;
2. отделяет fact от inference;
3. удаляет machine-specific/sensitive/transient детали, если они не нужны проекту;
4. определяет, нужен ли вообще version-controlled artifact;
5. выбирает exact repository path;
6. публикует только reviewed/sanitized conclusion, document или специально одобренный fixture.

Исходный local artifact при этом может остаться только в workspace.

## 8. Secrets и privacy

Размещение файла вне repository не отменяет общие secret rules.

Не записывать credentials, tokens, passwords, private keys, auth headers или secret-file contents в `evidence/`, `docs/` или `stash/` без отдельной технической необходимости и безопасного протокола.

Machine-specific paths допустимы в local artifacts, но обычно не должны публиковаться в GitHub.

## 9. Defense in depth

Repository `.gitignore` может игнорировать известные случайные root-level evidence filenames, но это только страховка.

Основное правило — создавать local artifacts **сразу вне Git repository**.

Если старый task/example показывает output в repo root, использовать соответствующий workspace path из этого документа, если задача явно не требует version-controlled artifact.
