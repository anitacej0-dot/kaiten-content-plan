#!/usr/bin/env python
"""Этап: сборка портфеля (квоты ролей, мощность, недели) + применение решений.

Пишет: 07_draft_master_plan.csv, 08_placements.csv, decision_log.csv (+ предыдущие).
Запуск:  python scripts/build_portfolio.py
"""
from _bootstrap import run_stage

if __name__ == "__main__":
    run_stage("portfolio", "Сборка портфеля и распределение по неделям")
