"""Общий бутстрап для скриптов-этапов.

Каждый скрипт в scripts/ — тонкая обёртка: строит Context, выполняет этапы до
своего включительно и печатает краткую сводку. Логика — в пакете pipeline/.
"""
from __future__ import annotations

import argparse
import io
import os
import sys

# Кодировка консоли под кириллицу (Windows).
try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
except Exception:
    pass

# Корень проекта = родитель каталога scripts/
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from pipeline.orchestrator import make_context, run_upto  # noqa: E402


def parse_args(description: str) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=description)
    ap.add_argument("--start", help="дата начала цикла YYYY-MM-DD (по умолч. — ближайший понедельник)")
    ap.add_argument("--weeks", type=int, help="горизонт в неделях (по умолч. из config)")
    ap.add_argument("--out", help="корень для outputs/ (по умолч. из config)")
    ap.add_argument("--include-selected-in-handoff", action="store_true",
                    help="включать в handoff не только утверждённые, но и выбранные темы")
    return ap.parse_args()


def run_stage(stage: str, description: str):
    args = parse_args(description)
    ctx = make_context(start=args.start, weeks=args.weeks, out_root=args.out,
                       include_selected_in_handoff=args.include_selected_in_handoff)
    run_upto(ctx, stage)
    _print_summary(ctx, stage)
    return ctx


def _print_summary(ctx, stage: str):
    c = ctx.warn.counts()
    print("\n" + "=" * 64)
    print(f"Этап «{stage}» завершён. Цикл: {ctx.cycle.slug}")
    print(f"Каталог результатов: {os.path.relpath(ctx.out_dir, _ROOT)}")
    if ctx.history:
        print(f"История: {len(ctx.history)} строк")
    if ctx.raw_candidates:
        print(f"Сырых кандидатов: {len(ctx.raw_candidates)}")
    if ctx.initiatives:
        print(f"Инициатив: {len(ctx.initiatives)} · размещений: {len(ctx.placements)}")
    if ctx.portfolio:
        p = ctx.portfolio
        print(f"В план: {len(p['selected'])} · бэклог: {len(p['backlog'])} · "
              f"отклонено: {len(p['rejected'])}")
    if ctx.findings:
        crit = sum(1 for f in ctx.findings if f["severity"] == "критично")
        print(f"Валидация: {len(ctx.findings)} замечаний (критичных: {crit})")
    print(f"Предупреждения: info={c['info']} warn={c['warning']} error={c['error']}")
    xlsx = os.path.join(ctx.out_dir, "content_plan.xlsx")
    if os.path.exists(xlsx):
        print(f"Excel: {os.path.relpath(xlsx, _ROOT)}")
    print("=" * 64)
