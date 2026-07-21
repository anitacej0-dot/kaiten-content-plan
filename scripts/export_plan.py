#!/usr/bin/env python
"""Этап: экспорт итогового Excel + plan_summary.md + пакеты handoff.

Пишет: content_plan.xlsx, plan_summary.md, handoff/ (+ все предыдущие).
Запуск:  python scripts/export_plan.py
"""
from _bootstrap import run_stage

if __name__ == "__main__":
    run_stage("export", "Экспорт Excel и сводки")
