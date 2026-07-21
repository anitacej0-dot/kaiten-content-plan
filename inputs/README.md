# Входные данные

На каждый цикл создаётся папка `inputs/current_cycle/`.

Минимальный набор:
- `legacy_or_previous_plan.xlsx` или выгрузка истории;
- `product_priorities.md`;
- `editorial_capacity.md`;
- `launches_and_deadlines.md`;
- `seo_signals.csv`;
- `analytics_signals.csv`;
- `sales_kam_signals.md`;
- `cases_and_experts.md`;
- `mandatory_publications.md`.

Если какого-то источника нет, pipeline продолжает работу, но снижает `evidence_strength` и фиксирует ограничение в summary.
