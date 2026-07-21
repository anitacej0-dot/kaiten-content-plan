"""Оценка тем по config/scoring.yaml.

Для каждого критерия считается значение [0..1] и сохраняется короткое обоснование
(почему столько). Итог нормируется к 0..100, затем вычитаются штрафы. Балл — не
финальное решение, а вход для сборки портфеля и ручного ревью.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Set

from .text_utils import contains_any


@dataclass
class ScoreResult:
    score: float
    breakdown: List[Dict] = field(default_factory=list)
    penalties: List[Dict] = field(default_factory=list)
    rationale: str = ""
    band: str = ""

    def breakdown_str(self) -> str:
        parts = [f"{b['criterion']}={b['value']:.2f}×{b['weight']}" for b in self.breakdown]
        pen = [f"{p['name']}({p['delta']})" for p in self.penalties]
        s = "; ".join(parts)
        if pen:
            s += " | штрафы: " + ", ".join(pen)
        return s


class Scorer:
    def __init__(self, scoring_cfg: Dict):
        self.cfg = scoring_cfg or {}
        self.criteria = self.cfg.get("criteria", {})
        self.penalties = self.cfg.get("penalties", {})
        self.thresholds = self.cfg.get("thresholds", {})
        self.max_score = float(self.cfg.get("max_score", 100))
        self.total_weight = sum(c.get("weight", 0) for c in self.criteria.values()) or 1

    def score(self, cand: Dict, context: Dict = None) -> ScoreResult:
        context = context or {}
        flags: Set[str] = set(cand.get("_flags", set()))
        risks: Set[str] = set(cand.get("_risks", set()))
        role = (cand.get("strategy_role") or "").lower()
        ctype = (cand.get("content_type") or "").lower()
        funnel = (cand.get("funnel_stage") or "").lower()
        effort = (cand.get("effort") or "средняя").lower()

        vals: Dict[str, tuple] = {}  # crit -> (value, rationale)

        def has(*keys):
            return any(k in flags for k in keys)

        # ---- лидовый потенциал ----
        if has("has_roistat_leads"):
            vals["lead_potential"] = (0.95, "есть заявки Roistat по теме/кластеру")
        elif "решение" in funnel or "сравнен" in ctype or "convert" in role:
            vals["lead_potential"] = (0.65, "коммерческий интент (сравнение/BoFu/Convert)")
        elif "продуктов" in ctype:
            vals["lead_potential"] = (0.55, "продуктовая тема")
        elif has("is_case_or_research"):
            vals["lead_potential"] = (0.5, "кейс/исследование конвертирует доверием")
        else:
            vals["lead_potential"] = (0.25, "информационная тема, лид-потенциал ниже")

        # ---- близость к продукту ----
        if "convert" in role or "сравнен" in ctype or "решение" in funnel:
            vals["commercial_proximity"] = (0.85, "Convert / сравнение / этап решения")
        elif "продуктов" in ctype:
            vals["commercial_proximity"] = (0.7, "продуктовая статья")
        elif "build" in role:
            vals["commercial_proximity"] = (0.4, "строит кластер, до продукта ещё шаг")
        else:
            vals["commercial_proximity"] = (0.35, "слабая прямая связь с продуктом")

        # ---- CTA ----
        if (cand.get("product_route") or "").strip() or "продуктов" in ctype or "сравнен" in ctype:
            vals["clear_cta"] = (0.75, "есть естественный маршрут к продукту")
        else:
            vals["clear_cta"] = (0.45, "CTA задаётся по умолчанию, требует уточнения")

        # ---- подтверждённый спрос ----
        demand_hits = [k for k in ("has_seo_tz", "has_roistat_traffic", "history_repeat",
                                   "from_sales_kam", "is_case_or_research",
                                   "from_product_launch") if k in flags]
        if demand_hits:
            vals["confirmed_demand"] = (min(1.0, 0.4 + 0.2 * len(demand_hits)),
                                        "сигналы спроса: " + ", ".join(demand_hits))
        else:
            vals["confirmed_demand"] = (0.2, "прямых сигналов спроса нет")

        # ---- SEO ----
        if has("has_seo_tz"):
            vals["seo_potential"] = (0.75, "есть ТЗ SEO / ключ")
        elif "сравнен" in ctype or "подборк" in ctype:
            vals["seo_potential"] = (0.6, "сравнение/подборка обычно даёт трафик")
        else:
            vals["seo_potential"] = (0.35, "SEO-потенциал не подтверждён")

        # ---- продуктовый приоритет ----
        if has("from_product_launch"):
            vals["product_priority"] = (0.9, "привязано к запуску")
        elif cand.get("_priority_cluster"):
            vals["product_priority"] = (0.75, "кластер в списке продуктовых приоритетов")
        elif "продуктов" in ctype:
            vals["product_priority"] = (0.6, "продуктовая тема")
        else:
            vals["product_priority"] = (0.4, "средний приоритет направления")

        # ---- сегмент ----
        if cand.get("_priority_segment"):
            vals["segment_fit"] = (0.8, "приоритетный сегмент")
        else:
            vals["segment_fit"] = (0.5, "сегмент не в приоритете/не задан")

        # ---- фактура ----
        ev = [k for k in ("has_ready_tz", "is_case_or_research", "has_expert",
                          "has_roistat_traffic") if k in flags]
        if ev:
            vals["evidence_strength"] = (min(1.0, 0.35 + 0.2 * len(ev)),
                                         "фактура: " + ", ".join(ev))
        else:
            vals["evidence_strength"] = (0.3, "фактура ограничена")

        # ---- потенциал доказательства/кейса ----
        if "кейс" in ctype or "исследован" in ctype or "prove" in role:
            vals["proof_or_case_potential"] = (0.85, "кейс/исследование/Prove")
        else:
            vals["proof_or_case_potential"] = (0.35, "доказательная ценность средняя")

        # ---- внешняя дистрибуция ----
        if contains_any(ctype, ["сравнен", "подборк", "кейс", "исследован"]):
            vals["distribution_potential"] = (0.75, "формат хорошо заходит на внешние площадки")
        else:
            vals["distribution_potential"] = (0.4, "дистрибуция возможна с адаптацией")

        # ---- Protect ----
        if "protect" in role or has("has_roistat_traffic") or cand.get("publication_kind") == "обновление":
            vals["protect_value"] = (0.8, "защита существующего трафика/позиций")
        else:
            vals["protect_value"] = (0.3, "не про защиту трафика")

        # ---- тайминг ----
        if has("from_product_launch") or cand.get("mandatory") == "да" or "новост" in ctype:
            vals["timing"] = (0.8, "запуск/обязательная/инфоповод — тайминг критичен")
        else:
            vals["timing"] = (0.4, "без жёсткой привязки по времени")

        # ---- взвешенная сумма ----
        breakdown = []
        weighted = 0.0
        for crit, spec in self.criteria.items():
            w = float(spec.get("weight", 0))
            value, why = vals.get(crit, (0.4, "оценка по умолчанию"))
            contribution = value * w
            weighted += contribution
            breakdown.append({"criterion": crit, "weight": w, "value": round(value, 2),
                              "contribution": round(contribution, 2), "rationale": why})
        raw100 = weighted / self.total_weight * self.max_score

        # ---- штрафы ----
        applied_penalties = []
        risk_to_penalty = {
            "duplicate": "duplicate_or_cannibalization",
            "cannibalization": "duplicate_or_cannibalization",
            "no_business_role": "no_clear_business_role",
            "no_signal": "no_source_signal",
            "hard_dependency": "unrealistic_dependency",
            "high_effort": "excessive_effort",
            "review_duplicate": "review_duplicate_soft",
        }
        seen_pen = set()
        for risk in risks:
            pen_key = risk_to_penalty.get(risk)
            if pen_key and pen_key in self.penalties and pen_key not in seen_pen:
                delta = float(self.penalties[pen_key])
                applied_penalties.append({"name": pen_key, "delta": delta})
                seen_pen.add(pen_key)
        if effort == "высокая" and "excessive_effort" not in seen_pen:
            # мягкий сигнал: высокая трудоёмкость учитывается только если ценность низка
            if raw100 < 60 and "excessive_effort" in self.penalties:
                delta = float(self.penalties["excessive_effort"])
                applied_penalties.append({"name": "excessive_effort", "delta": delta})

        final = max(0.0, raw100 + sum(p["delta"] for p in applied_penalties))
        final = round(final, 1)

        band = self._band(final)
        top = sorted(breakdown, key=lambda b: b["contribution"], reverse=True)[:3]
        rationale = "; ".join(f"{b['criterion']}: {b['rationale']}" for b in top)
        if applied_penalties:
            rationale += ". Штрафы: " + ", ".join(p["name"] for p in applied_penalties)

        return ScoreResult(score=final, breakdown=breakdown, penalties=applied_penalties,
                           rationale=rationale, band=band)

    def _band(self, score: float) -> str:
        t = self.thresholds
        if score >= float(t.get("must_plan", 72)):
            return "в план"
        if score >= float(t.get("consider", 58)):
            return "рассмотреть"
        if score >= float(t.get("backlog", 44)):
            return "бэклог"
        return "отклонить"
