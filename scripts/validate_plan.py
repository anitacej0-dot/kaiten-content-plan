#!/usr/bin/env python
"""Этап: финальная валидация плана (роли, кластеры, сигналы, CTA, риски).

Пишет: 10_validation_report.md (+ предыдущие).
Запуск:  python scripts/validate_plan.py
"""
from _bootstrap import run_stage

if __name__ == "__main__":
    run_stage("validate", "Валидация плана")
