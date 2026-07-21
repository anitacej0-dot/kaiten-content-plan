#!/usr/bin/env python
"""Этап: нормализация кандидатов в инициативы + размещения (двухуровневая модель).

Пишет: 05_normalized_candidates.csv (+ предыдущие).
Запуск:  python scripts/normalize_topics.py
"""
from _bootstrap import run_stage

if __name__ == "__main__":
    run_stage("normalize", "Нормализация тем и сборка инициатив")
