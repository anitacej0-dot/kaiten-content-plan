# Подготовка входных данных

Все данные месяца кладутся в `inputs/current_cycle/`. Шаблоны — в `inputs/templates/`
(скопируйте нужный, заполните, положите в `current_cycle`). Реальные файлы не
попадают в GitHub (`.gitignore`).

## Обязательный минимум

- **Excel предыдущего/текущего контент-плана** — любой `.xlsx` в `current_cycle/`.
  Формат «как есть»: десятки листов по месяцам и площадкам, разные заголовки —
  парсер это учитывает. Файл не изменяется.

## Рекомендуемые (сильно повышают качество)

| Файл | Куда | Что даёт |
|---|---|---|
| Выгрузка **Roistat** (`Report`) | `current_cycle/analytics/` | лид-потенциал и Protect по страницам блога |
| Выгрузка **Метрики** (`Отчет`) | `current_cycle/analytics/` | тренд посещаемости (контекст) |
| `seo_signals.csv` | `current_cycle/` | SEO-запросы/кластеры |
| `editorial_ideas.csv` | `current_cycle/` | идеи редакции |
| `mandatory_publications.csv` | `current_cycle/` | обязательные публикации (вне score) |
| `product_priorities.md` | `current_cycle/` | приоритетные направления |
| `sales_kam_signals.md` | `current_cycle/` | запросы продаж и KAM |
| `cases_and_experts.md` | `current_cycle/` | доступные кейсы и эксперты |
| `editorial_capacity.md` | `current_cycle/` | мощность редакции |
| `launches_and_deadlines.md` | `current_cycle/` | запуски и дедлайны |

Roistat и Метрика распознаются по содержимому — имена файлов любые.

## Форматы шаблонов (обязательные/необязательные поля)

### `seo_signals.csv`
`title` **или** `keyword` (обязательно одно), `url`, `volume`, `cluster`, `role`, `note`.

### `editorial_ideas.csv`
`title` (обяз.), `description`, `cluster`, `role`, `author`, `expert`, `note`.

### `mandatory_publications.csv`
`title` (обяз.), `date` (YYYY-MM-DD — попадёт в нужную неделю), `cluster`, `note`.
Такие темы попадают в план **вне score** и помечаются как обязательные.

### Markdown-файлы (`product_priorities`, `sales_kam_signals`, `cases_and_experts`,
`editorial_capacity`, `launches_and_deadlines`)
Свободный текст. Пункты маркированного списка (`- ...`) в `sales_kam_signals.md`
становятся кандидат-темами. В `editorial_capacity.md` pipeline ищет фразы вида
«5 материалов в неделю» и «3 автора».

## Если данных нет

Pipeline **не останавливается**: помечает пропуск в `01_input_audit.md`, снижает
соответствующие оценки и выносит ограничения в `plan_summary.md`. Минимально
достаточно одного Excel контент-плана.

## Что не подключается автоматически

Личные/несогласованные документы (например, файлы сверки) не трактуются как сигнал.
Чтобы использовать их данные — перенесите нужное в шаблоны выше.
