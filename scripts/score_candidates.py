#!/usr/bin/env python
"""Этап: оценка инициатив по config/scoring.yaml (с обоснованием каждого критерия).

Пишет: 06_scored_candidates.csv (+ предыдущие).
Запуск:  python scripts/score_candidates.py
"""
from _bootstrap import run_stage

if __name__ == "__main__":
    run_stage("score", "Оценка тем")
