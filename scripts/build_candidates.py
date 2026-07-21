#!/usr/bin/env python
"""Этап: собрать пул кандидатов (переносы, Protect по Roistat, кейсы, сигналы).

Пишет: 04_candidates.csv (+ предыдущие).
Запуск:  python scripts/build_candidates.py
"""
from _bootstrap import run_stage

if __name__ == "__main__":
    run_stage("candidates", "Сбор пула кандидатов")
