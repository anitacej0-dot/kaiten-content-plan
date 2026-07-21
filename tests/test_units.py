# -*- coding: utf-8 -*-
"""Юнит-тесты ядра pipeline (без реальных данных, безопасны для CI).

Запуск:
    .venv\\Scripts\\python tests\\test_units.py
    (или, если установлен pytest)  .venv\\Scripts\\python -m pytest tests
"""
import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from pipeline.config import load_config, resolve_cycle  # noqa: E402
from pipeline.legacy import parse_period, classify_sheet  # noqa: E402
from pipeline.scoring import Scorer  # noqa: E402
from pipeline.signals import translit  # noqa: E402
from pipeline.taxonomy import Classifier  # noqa: E402
from pipeline.text_utils import TextNormalizer, ratio  # noqa: E402

CFG = load_config()


def test_period_parsing():
    assert parse_period("Февраль 25")[0] == "2025-02"
    assert parse_period("Май 2025 (блог)")[0] == "2025-05"
    assert parse_period("Январь 26 (внешние)")[0] == "2026-01"
    assert parse_period("Лист11")[0] == ""


def test_sheet_classification():
    lc = CFG.pipeline.get("legacy_plan", {})
    assert classify_sheet("Кейсы", lc) == "case"
    assert classify_sheet("Февраль 25 (VC)", lc) == "external"
    assert classify_sheet("Апрель 25 (внешние)", lc) == "external"
    assert classify_sheet("Май 2025 (блог)", lc) == "blog"
    assert classify_sheet("Лист11", lc) == "ignore"


def test_cluster_not_fooled_by_kaiten():
    # 'kaiten' содержит подстроку 'ai' — не должно классифицироваться как AI
    clf = Classifier(CFG.taxonomy)
    label, _ = clf.product_cluster("Обзор Kaiten для управления проектами")
    assert label != "AI-функции", label
    ai_label, _ = clf.product_cluster("Лучшие нейросети для бизнеса")
    assert ai_label == "AI-функции", ai_label


def test_text_normalization_and_ratio():
    tn = TextNormalizer(CFG.taxonomy)
    assert "kaiten" in tn.clean("Рерайт: Кайтен для HR")
    # перестановка слов не должна ронять схожесть
    assert ratio("аналоги jira обзор", "обзор аналоги jira") >= 90


def test_translit():
    assert translit("Аналоги Jira") == "analogi-jira"
    assert "ganta" in translit("Диаграмма Ганта")


def test_scoring_ranges_and_rationale():
    scorer = Scorer(CFG.scoring)
    cand = {"strategy_role": "Convert", "content_type": "Сравнение / аналоги",
            "funnel_stage": "Решение (BoFu)", "effort": "средняя",
            "_flags": {"has_seo_tz", "is_comparison_or_alt"}, "_risks": set()}
    res = scorer.score(cand)
    assert 0 <= res.score <= 100
    assert res.breakdown and all(b.get("rationale") for b in res.breakdown)
    # штраф за дубль снижает балл
    cand2 = dict(cand, _risks={"duplicate"})
    assert scorer.score(cand2).score < res.score


def test_cycle_dates():
    cyc = resolve_cycle(CFG, start="2026-07-27", weeks=7)
    assert cyc.slug == "2026-07-27_2026-09-13"
    assert len(cyc.week_bounds()) == 7


def _run_all():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for t in tests:
        t()
        print(f"  ok  {t.__name__}")
        passed += 1
    print(f"\n{passed}/{len(tests)} тестов пройдено")
    return passed == len(tests)


if __name__ == "__main__":
    sys.exit(0 if _run_all() else 1)
