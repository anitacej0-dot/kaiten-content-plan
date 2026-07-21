#!/usr/bin/env python
"""Этап 1-2: разобрать Excel контент-плана и построить аудит истории + дубли.

Пишет: 01_input_audit.md, 02_history_audit.md, 03_duplicates.csv.
Запуск:  python scripts/parse_legacy_plan.py
"""
from _bootstrap import run_stage

if __name__ == "__main__":
    run_stage("dedupe", "Разбор легаси-плана и аудит истории")
