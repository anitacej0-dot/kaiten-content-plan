# Команды Claude Code

Все команды лежат в `.claude/commands/`. Их можно вызывать в Claude Code как
`/new-plan` и т.д. Каждая команда под капотом запускает соответствующий скрипт и
помогает прочитать результат.

## `/new-plan`
Полный цикл: проверка входов → аудит истории → кандидаты → нормализация → дубли →
оценка → портфель → недели → размещения → Excel → сводка и вопросы главреду.
Скрипт: `scripts/run_pipeline.py`.

## `/review-plan`
Редакционная проверка чернового плана: дубли, каннибализация, связь с продуктом и
сегментом, роль, сигнал, CTA, корректность площадки, перегрузка по неделям,
перекосы по кластерам/типам, наличие обоснования. Скрипт: `scripts/validate_plan.py`.

## `/update-plan`
Пересобирает план с учётом ручных решений из `inputs/current_cycle/decisions.csv`
и не теряет их (решения — вход, применяются заново). Скрипт: `scripts/run_pipeline.py`.

## `/export-plan`
Формирует финальный `content_plan.xlsx` и `plan_summary.md`.
Скрипт: `scripts/export_plan.py`.

## `/handoff-plan`
Собирает YAML-пакеты утверждённых инициатив в `outputs/<цикл>/handoff/` для
`kaiten-article-pipeline`. Скрипт: `scripts/export_plan.py`
(флаг `--include-selected-in-handoff` — включить и «выбранные»).

## Ручной запуск без Claude Code

Любой этап можно запустить напрямую (каждый выполняет всё до своего включительно):
```
.venv\Scripts\python scripts\parse_legacy_plan.py
.venv\Scripts\python scripts\build_candidates.py
.venv\Scripts\python scripts\score_candidates.py
.venv\Scripts\python scripts\build_portfolio.py
.venv\Scripts\python scripts\run_pipeline.py        # всё целиком
```
Флаги: `--start YYYY-MM-DD`, `--weeks N`, `--out <каталог>`.
