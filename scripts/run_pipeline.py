#!/usr/bin/env python
"""Полный запуск pipeline от разбора Excel до итогового content_plan.xlsx.

Это основная команда. Выполняет все этапы и складывает результаты в
outputs/<дата_начала>_<дата_конца>/.

Запуск:
    python scripts/run_pipeline.py
    python scripts/run_pipeline.py --start 2026-07-28 --weeks 7
"""
from _bootstrap import run_stage

if __name__ == "__main__":
    run_stage("export", "Полный запуск pipeline контент-плана")
