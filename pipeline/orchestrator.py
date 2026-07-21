"""Оркестратор pipeline: последовательные этапы + запись артефактов цикла.

Каждый этап складывает данные в Context и пишет свой файл в outputs/<цикл>/.
run_upto(name) выполняет все этапы до указанного включительно (repeatable).
Промежуточные CSV — интерфейс между этапами для человека; сам pipeline держит
состояние в памяти и не зависит от ручного копирования файлов.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from . import excelout, reports
from .candidates import build_candidates, normalize_candidates
from .config import Config, Cycle, load_config, resolve_cycle
from .decisions import apply_decisions, load_decisions
from .dedupe import analyze_history
from .io_utils import ensure_dir, write_csv, write_text
from .legacy import LegacyParser, find_legacy_file
from .portfolio import build_portfolio, resolve_capacity, validate_capacity
from .scoring import Scorer
from . import schema
from .signals import load_signals
from .text_utils import TextNormalizer
from .warnings_log import WarningLog

STAGES = ["parse", "dedupe", "candidates", "normalize", "score",
          "portfolio", "capacity", "validate", "export"]

RISK_LABELS = {
    "review_duplicate": "похоже на опубликованное — проверить",
    "duplicate": "дубль истории",
    "cannibalization": "каннибализация",
    "no_signal": "нет подтверждающего сигнала",
    "hard_dependency": "зависимость от эксперта",
    "high_effort": "высокая трудоёмкость",
}


@dataclass
class Context:
    cfg: Config
    cycle: Cycle
    warn: WarningLog
    out_dir: str
    include_selected_in_handoff: bool = False
    # промежуточные данные
    legacy_file: Optional[str] = None
    signals=None
    history: List[Dict] = field(default_factory=list)
    dedupe_result: Dict = field(default_factory=dict)
    raw_candidates: List[Dict] = field(default_factory=list)
    initiatives: List[Dict] = field(default_factory=list)
    placements: List[Dict] = field(default_factory=list)
    portfolio: Dict = field(default_factory=dict)
    capacity: Dict = field(default_factory=dict)
    capacity_check: Dict = field(default_factory=dict)
    findings: List[Dict] = field(default_factory=list)
    decision_log: List[Dict] = field(default_factory=list)
    _done: set = field(default_factory=set)


def make_context(start=None, weeks=None, out_root=None,
                 include_selected_in_handoff=False) -> Context:
    cfg = load_config()
    cycle = resolve_cycle(cfg, start=start, weeks=weeks)
    warn = WarningLog()
    root = out_root or cfg.outputs_dir
    out_dir = ensure_dir(os.path.join(root, cycle.slug))
    return Context(cfg=cfg, cycle=cycle, warn=warn, out_dir=out_dir,
                   include_selected_in_handoff=include_selected_in_handoff)


# --------------------------------------------------------------- этапы
def stage_parse(ctx: Context):
    ctx.legacy_file = find_legacy_file(
        ctx.cfg.inputs_current,
        ctx.cfg.pipeline.get("legacy_plan", {}).get("filename_globs", ["*.xlsx"]),
        ctx.warn)
    if ctx.legacy_file:
        ctx.warn.info("parse", f"Файл плана: {os.path.basename(ctx.legacy_file)}")
        parser = LegacyParser(ctx.cfg, ctx.warn)
        ctx.history = parser.parse(ctx.legacy_file)
    else:
        ctx.warn.error("parse", "Не найден Excel контент-плана в inputs/current_cycle/")
        ctx.history = []
    ctx.signals = load_signals(ctx.cfg, ctx.warn)
    write_text(os.path.join(ctx.out_dir, "01_input_audit.md"),
               reports.input_audit_md(ctx.cycle, ctx.signals, ctx.warn,
                                       os.path.basename(ctx.legacy_file or "")))


def stage_dedupe(ctx: Context):
    normalizer = TextNormalizer(ctx.cfg.taxonomy)
    ctx.dedupe_result = analyze_history(ctx.history, ctx.cfg, normalizer)
    write_csv(os.path.join(ctx.out_dir, "03_duplicates.csv"),
              ctx.dedupe_result["duplicates"],
              fieldnames=["group_id", "relationship", "similarity",
                          "theme_a", "platform_a", "period_a", "sheet_a",
                          "theme_b", "platform_b", "period_b", "sheet_b", "note"])
    write_text(os.path.join(ctx.out_dir, "02_history_audit.md"),
               reports.history_audit_md(ctx.history, ctx.dedupe_result))


def stage_candidates(ctx: Context):
    ctx.raw_candidates = build_candidates(ctx.history, ctx.signals, ctx.cfg,
                                          ctx.cycle, ctx.warn)
    write_csv(os.path.join(ctx.out_dir, "04_candidates.csv"),
              [_raw_view(c) for c in ctx.raw_candidates],
              fieldnames=["title", "source", "signal", "_channel", "_platform",
                          "product_cluster", "strategy_role", "content_type",
                          "publication_kind", "period", "source_sheet"])


def _raw_view(c: Dict) -> Dict:
    return {k: c.get(k, "") for k in ["title", "source", "signal", "_channel",
            "_platform", "product_cluster", "strategy_role", "content_type",
            "publication_kind", "period", "source_sheet"]}


def stage_normalize(ctx: Context):
    ctx.initiatives, ctx.placements = normalize_candidates(
        ctx.raw_candidates, ctx.history, ctx.cfg, ctx.cycle, ctx.signals, ctx.warn)
    write_csv(os.path.join(ctx.out_dir, "05_normalized_candidates.csv"),
              ctx.initiatives, fieldnames=schema.INITIATIVE_KEYS)


def stage_score(ctx: Context):
    scorer = Scorer(ctx.cfg.scoring)
    for c in ctx.initiatives:
        res = scorer.score(c)
        c["score"] = res.score
        c["_band"] = res.band
        c["rationale"] = res.rationale
        c["score_breakdown"] = res.breakdown_str()
        c["risk_flags"] = "; ".join(RISK_LABELS.get(r, r) for r in c.get("_risks", []))
        # качественные метки
        c["lead_potential"] = _qual(res, "lead_potential")
        c["seo_potential"] = _qual(res, "seo_potential")
        c["product_priority"] = _qual(res, "product_priority")
    write_csv(os.path.join(ctx.out_dir, "06_scored_candidates.csv"),
              ctx.initiatives, fieldnames=schema.INITIATIVE_KEYS)


def _qual(res, crit) -> str:
    for b in res.breakdown:
        if b["criterion"] == crit:
            v = b["value"]
            return "высокий" if v >= 0.7 else ("средний" if v >= 0.45 else "низкий")
    return ""


def stage_portfolio(ctx: Context):
    cap_text = ctx.signals.text_files.get("editorial_capacity.md", "") if ctx.signals else ""
    ctx.capacity = resolve_capacity(ctx.cfg, cap_text)
    ctx.portfolio = build_portfolio(ctx.initiatives, ctx.cfg, ctx.cycle, ctx.capacity)
    # ручные решения (re-applied каждый запуск -> не затираются)
    decisions = load_decisions(ctx.cfg)
    ctx.decision_log = apply_decisions(ctx.portfolio, decisions, ctx.cycle, ctx.warn)

    # порядок для чтения: по неделям, внутри недели — по score
    ctx.portfolio["selected"].sort(
        key=lambda c: (c.get("_week_no") or 99, -float(c.get("score") or 0)))

    # master plan = выбранные; статусы уже проставлены
    write_csv(os.path.join(ctx.out_dir, "07_draft_master_plan.csv"),
              ctx.portfolio["selected"], fieldnames=schema.INITIATIVE_KEYS)
    # размещения только для выбранных инициатив
    sel_ids = {c["content_id"] for c in ctx.portfolio["selected"]}
    sel_placements = [p for p in ctx.placements if p["content_id"] in sel_ids]
    write_csv(os.path.join(ctx.out_dir, "08_placements.csv"),
              sel_placements, fieldnames=schema.PLACEMENT_KEYS)
    write_csv(os.path.join(ctx.out_dir, "decision_log.csv"), ctx.decision_log,
              fieldnames=["date", "author", "content_id", "field", "old_value",
                          "new_value", "reason", "is_exception"])


def stage_capacity(ctx: Context):
    ctx.capacity_check = validate_capacity(ctx.portfolio, ctx.cfg, ctx.cycle)
    write_text(os.path.join(ctx.out_dir, "09_capacity_check.md"),
               reports.capacity_md(ctx.capacity_check, ctx.cycle, ctx.capacity))


def stage_validate(ctx: Context):
    ctx.findings = reports.validate_plan(ctx.initiatives, ctx.placements,
                                         ctx.portfolio, ctx.cfg)
    write_text(os.path.join(ctx.out_dir, "10_validation_report.md"),
               reports.validation_md(ctx.findings))


def stage_export(ctx: Context):
    # разложить выбранные по разделам
    selected = ctx.portfolio["selected"]
    sel_ids = {c["content_id"] for c in selected}
    updates = [c for c in selected if (c.get("strategy_role") == "Protect"
               or c.get("publication_kind") == "обновление")]
    cases = [c for c in selected if c.get("content_type") == "Кейс"
             or c.get("strategy_role") == "Prove"]
    sel_placements = [p for p in ctx.placements if p["content_id"] in sel_ids]

    signal_rows = _signal_rows(ctx)
    cycle_info = {"slug": ctx.cycle.slug, "per_week": ctx.capacity.get("items_per_week"),
                  "max_per_week": ctx.capacity.get("max_items_per_week")}
    platforms = _platform_labels(ctx.cfg)

    data = {
        "selected": selected, "placements": sel_placements,
        "backlog": ctx.portfolio["backlog"], "updates": updates, "cases": cases,
        "rejected": ctx.portfolio["rejected"],
        "duplicates": ctx.dedupe_result.get("duplicates", []),
        "capacity_lines": ctx.capacity_check.get("week_lines", []),
        "signal_rows": signal_rows, "decision_log": ctx.decision_log,
        "cycle_info": cycle_info, "platforms": platforms,
    }
    wb = excelout.build_workbook(data)
    xlsx_path = os.path.join(ctx.out_dir, "content_plan.xlsx")
    excelout.save_workbook(wb, xlsx_path)

    write_text(os.path.join(ctx.out_dir, "plan_summary.md"),
               reports.plan_summary_md(ctx.cycle, ctx.portfolio, ctx.initiatives,
                                       sel_placements, ctx.signals, ctx.findings, ctx.warn))
    _write_handoff(ctx, selected, sel_placements)


def _signal_rows(ctx) -> List[Dict]:
    rows = []
    for p in ctx.signals.present:
        rows.append({"source": p, "status": "есть", "detail": ""})
    for m in ctx.signals.missing:
        rows.append({"source": m, "status": "отсутствует", "detail": "снижена уверенность"})
    if ctx.signals.roistat.get("totals"):
        t = ctx.signals.roistat["totals"]
        rows.append({"source": "Roistat — сводка", "status": "есть",
                     "detail": f"страниц {t['pages']}, визитов {int(t['visits'])}, "
                               f"заявок {int(t['leads'])}, продаж {int(t['sales'])}"})
    if ctx.signals.metrika:
        mk = ctx.signals.metrika
        rows.append({"source": "Метрика — сводка", "status": "есть",
                     "detail": f"{mk['days']} дней, средн/день {int(mk['avg'])}, "
                               f"тренд {mk['trend_pct']:+.0f}%"})
    return rows


def _platform_labels(cfg) -> List[str]:
    plats = cfg.taxonomy.get("platforms", {})
    return [spec.get("label", k) for k, spec in plats.items()]


def _write_handoff(ctx: Context, selected, placements):
    statuses = ["утверждена"]
    if ctx.include_selected_in_handoff:
        statuses.append("выбрана")
    approved = [c for c in selected if c.get("decision_status") in statuses]
    handoff_dir = ensure_dir(os.path.join(ctx.out_dir, "handoff"))
    pl_by_cid: Dict[str, List[Dict]] = {}
    for p in placements:
        pl_by_cid.setdefault(p["content_id"], []).append(p)
    if not approved:
        write_text(os.path.join(handoff_dir, "README.md"),
                   "# Handoff\n\nПока нет утверждённых инициатив.\n\n"
                   "Утвердите темы: в `inputs/current_cycle/decisions.csv` поставьте "
                   "`decision_status=утверждена` и запустите `/handoff-plan` "
                   "(или `/update-plan`).\n")
        ctx.warn.info("handoff", "Утверждённых инициатив нет — пакеты не созданы")
        return
    for c in approved:
        _write_handoff_package(handoff_dir, c, pl_by_cid.get(c["content_id"], []))
    ctx.warn.info("handoff", f"Создано пакетов handoff: {len(approved)}")


def _write_handoff_package(handoff_dir, c, placements):
    import yaml
    pkg = {
        "content_id": c["content_id"],
        "тема": c["title"],
        "цель": c.get("expected_action", ""),
        "аудитория": c.get("segment", ""),
        "роль_читателя": c.get("audience_role", ""),
        "продукт": c.get("product_cluster", ""),
        "продукт_функция": c.get("product_feature", ""),
        "пользовательская_проблема": c.get("user_problem", ""),
        "роль_в_стратегии": c.get("strategy_role", ""),
        "тип_материала": c.get("content_type", ""),
        "этап_воронки": c.get("funnel_stage", ""),
        "ключевой_угол": c.get("title", ""),
        "cta": c.get("cta", ""),
        "маршрут_к_продукту": c.get("product_route", ""),
        "источники_сигнала": c.get("signal", ""),
        "доказательная_база": c.get("evidence_base", ""),
        "связанные_материалы": c.get("related_content", ""),
        "ограничения": c.get("dependencies", ""),
        "предполагаемый_дедлайн": c.get("target_week", ""),
        "необходимые_эксперты": c.get("expert", ""),
        "площадки": [
            {"площадка": p["platform"], "формат": p["format"], "угол": p["angle"],
             "cta": p["cta"], "требования": p.get("platform_requirements", "")}
            for p in placements
        ],
        "комментарий_главреда": c.get("editor_comment", ""),
    }
    safe = c["content_id"]
    path = os.path.join(handoff_dir, f"{safe}.yaml")
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(pkg, f, allow_unicode=True, sort_keys=False)


# --------------------------------------------------------------- запуск
_STAGE_FUNCS = {
    "parse": stage_parse, "dedupe": stage_dedupe, "candidates": stage_candidates,
    "normalize": stage_normalize, "score": stage_score, "portfolio": stage_portfolio,
    "capacity": stage_capacity, "validate": stage_validate, "export": stage_export,
}


def run_upto(ctx: Context, stage: str):
    if stage not in STAGES:
        raise ValueError(f"Неизвестный этап: {stage}")
    target = STAGES.index(stage)
    for name in STAGES[:target + 1]:
        if name in ctx._done:
            continue
        _STAGE_FUNCS[name](ctx)
        ctx._done.add(name)
    return ctx


def run_all(ctx: Context):
    return run_upto(ctx, "export")
