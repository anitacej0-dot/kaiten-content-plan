# Архитектура

## Слои

```
config/*.yaml         параметры (пороги, веса, квоты, таксономия)
        │
pipeline/             ЯДРО (импортируемый пакет, вся логика)
        │
scripts/*.py          тонкие CLI-обёртки этапов + run_pipeline.py
        │
outputs/<цикл>/       артефакты этапов + content_plan.xlsx + handoff/
```

Разделение: скрипты не содержат логику — они строят `Context` и вызывают этап из
`pipeline/orchestrator.py`. Это делает pipeline тестируемым и повторяемым.

## Модули `pipeline/`

| Модуль | Ответственность |
|---|---|
| `config.py` | загрузка `config/*.yaml`, разрешение путей и дат цикла |
| `warnings_log.py` | журнал предупреждений (pipeline не падает из-за одной ошибки) |
| `io_utils.py` | CSV/JSON/текст в UTF-8-SIG (Excel читает кириллицу) |
| `schema.py` | канонические поля инициатив, размещений, истории (+ рус. подписи) |
| `text_utils.py` | нормализация текста, ключевые слова, fuzzy (rapidfuzz) |
| `taxonomy.py` | эвристическая классификация: кластер, роль, воронка, тип, площадка |
| `legacy.py` | разбор Excel-книги плана в единую историческую схему |
| `signals.py` | загрузка сигналов: Roistat, Метрика, шаблоны CSV/MD |
| `dedupe.py` | дубли, переносы, дистрибуция, каннибализация (blocking + union-find) |
| `candidates.py` | сбор кандидатов и нормализация в инициативы + размещения |
| `scoring.py` | оценка по `scoring.yaml` с обоснованием каждого критерия |
| `portfolio.py` | квоты ролей, мощность, распределение по неделям, проверка нагрузки |
| `decisions.py` | применение ручных решений (decision log) |
| `reports.py` | Markdown-отчёты + финальная валидация |
| `excelout.py` | экспорт `.xlsx` (11 листов, форматирование, выпадающие списки) |
| `orchestrator.py` | Context + этапы + `run_upto()` / `run_all()` |

## Этапы (и их артефакты)

| Этап | Скрипт | Выход |
|---|---|---|
| parse | `parse_legacy_plan.py` | `01_input_audit.md` |
| dedupe | `detect_duplicates.py` | `02_history_audit.md`, `03_duplicates.csv` |
| candidates | `build_candidates.py` | `04_candidates.csv` |
| normalize | `normalize_topics.py` | `05_normalized_candidates.csv` |
| score | `score_candidates.py` | `06_scored_candidates.csv` |
| portfolio | `build_portfolio.py` | `07_draft_master_plan.csv`, `08_placements.csv`, `decision_log.csv` |
| capacity | `validate_capacity.py` | `09_capacity_check.md` |
| validate | `validate_plan.py` | `10_validation_report.md` |
| export | `export_plan.py` | `content_plan.xlsx`, `plan_summary.md`, `handoff/` |

`run_pipeline.py` = все этапы. Каждый скрипт выполняет все этапы **до своего
включительно** (repeatable), поэтому запуск любого этапа самодостаточен.

## Двухуровневая модель

- **Инициатива** (`master_plan`) — один замысел, один `content_id`, ~40 полей.
- **Размещение** (`placements`) — реализация на площадке, свой `placement_id` и угол.

Одинаковые темы (в т.ч. на разных площадках) сводятся `dedupe_candidates` в одну
инициативу с несколькими размещениями.

## Ключевые решения

- **UTF-8-SIG** для всех CSV — корректная кириллица в Excel на Windows.
- **Сигналы распознаются по содержимому** (Roistat — по «Посадочная страница»,
  Метрика — по «Отчёт за период»), а не по имени файла.
- **Детерминизм**: при одинаковом входе `content_id` и план стабильны между запусками
  (нет случайности/времени в логике).
- **Ручные решения — вход**, а не состояние: применяются заново каждый запуск.
