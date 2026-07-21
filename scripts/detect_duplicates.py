#!/usr/bin/env python
"""Этап: поиск дублей, переносов, каннибализации и дистрибуции в истории.

Пишет: 03_duplicates.csv (+ 01, 02).
Запуск:  python scripts/detect_duplicates.py
"""
from _bootstrap import run_stage

if __name__ == "__main__":
    run_stage("dedupe", "Поиск дублей и пересечений в истории")
