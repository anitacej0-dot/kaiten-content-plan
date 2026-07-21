"""Формирование пула кандидатов и нормализация в инициативы + размещения.

Источники кандидатов:
  A. Переносы (carryover) — недоделанные темы недавних месяцев истории.
  B. Protect по Roistat — топ-страницы блога по трафику -> кандидаты на обновление.
  C. Сигналы редакции — editorial_ideas.csv, seo_signals.csv,
     mandatory_publications.csv, product_priorities.md, sales_kam_signals.md,
     cases_and_experts.md (если файлы есть в inputs/current_cycle).

Реализуется двухуровневая модель: одинаковые темы (в т.ч. на разных площадках)
сводятся в ОДНУ инициативу с несколькими размещениями, а не в разные инициативы.
"""
from __future__ import annotations

import datetime as _dt
import re
from typing import Dict, List, Optional, Tuple

from .config import Cycle
from .dedupe import Matcher, dedupe_candidates, link_candidate_to_history
from .signals import Signals, translit
from .taxonomy import Classifier
from .text_utils import TextNormalizer, ratio
from .warnings_log import WarningLog

# Пользовательская проблема по кластеру (значение по умолчанию, помечается как гипотеза).
CLUSTER_PROBLEM = {
    "Управление проектами и задачами": "Команде не хватает прозрачности и контроля над задачами и сроками",
    "CRM": "Продажи ведутся хаотично, теряются сделки и клиенты",
    "Service Desk / ITSM": "Обращения теряются, поддержка не укладывается в SLA",
    "ВКС / видеоконференции": "Нужен надёжный корпоративный инструмент для видеовстреч",
    "Корпоративный мессенджер / чаты": "Рабочее общение разрознено по разным каналам",
    "Документы / база знаний": "Знания и документы разрознены, их трудно найти",
    "AI-функции": "Рутина отнимает время, которое можно автоматизировать",
    "HR / найм": "Процессы найма и адаптации непрозрачны и медленны",
    "Аналитика и методы управления": "Решения принимаются без данных и понятной методологии",
}

# Ожидаемое действие и CTA по стратегической роли.
ROLE_ACTION = {
    "Convert": ("Сравнить решения и начать пробный период Kaiten", "Попробовать Kaiten бесплатно"),
    "Build":   ("Разобраться в теме и перейти к возможностям Kaiten", "Узнать о Kaiten"),
    "Protect": ("Получить актуальную информацию и перейти к продукту", "Открыть актуальную страницу продукта"),
    "Prove":   ("Убедиться в результате и запросить демонстрацию", "Запросить демо Kaiten"),
}

EFFORT_BY_TYPE = {
    "Кейс": "высокая", "Исследование": "высокая", "Сравнение / аналоги": "средняя",
    "Подборка / топ": "средняя", "Продуктовая статья": "средняя",
    "Гайд / обучающая": "средняя", "Новость / инфоповод": "низкая",
}


def _month_add(d: _dt.date, months: int) -> _dt.date:
    m = d.month - 1 + months
    y = d.year + m // 12
    m = m % 12 + 1
    return _dt.date(y, m, 1)


def build_candidates(history: List[Dict], signals: Signals, cfg, cycle: Cycle,
                     warn: WarningLog) -> List[Dict]:
    raw: List[Dict] = []
    raw += _carryover_candidates(history, cfg, cycle, warn)
    raw += _case_candidates(history, warn)
    raw += _roistat_protect_candidates(history, signals, cfg, warn)
    raw += _signal_candidates(signals, cfg, warn)
    warn.info("build_candidates", f"Сырых кандидатов собрано: {len(raw)}")
    return raw


def _case_candidates(history, warn) -> List[Dict]:
    """Незавершённые кейсы из истории -> доказательные (Prove) кандидаты."""
    out = []
    for h in history:
        if h.get("channel") != "case" or h.get("is_done") == "да":
            continue
        c = _raw_from_history(h, source="Кейс из истории",
                              signal="Доступный/планируемый кейс клиента")
        c["strategy_role"] = "Prove"
        c["content_type"] = "Кейс"
        out.append(c)
    warn.info("build_candidates", f"Кейсы (незавершённые): {len(out)}")
    return out


# --------------------------------------------------------- A. переносы
def _carryover_candidates(history, cfg, cycle: Cycle, warn) -> List[Dict]:
    hist_cfg = cfg.pipeline.get("history", {})
    lookback = int(hist_cfg.get("carryover_lookback_months", 3))
    threshold = _month_add(cycle.start.replace(day=1), -lookback).strftime("%Y-%m")
    out = []
    for h in history:
        if h.get("is_done") == "да":
            continue
        if h.get("channel") == "case":
            continue  # кейсы обрабатываем отдельным источником
        period = h.get("period", "")
        if period and period < threshold:
            continue
        out.append(_raw_from_history(h, source="Перенос из истории",
                                     signal=f"Незавершённая тема из «{h.get('source_sheet','')}»"))
    warn.info("build_candidates", f"A. Переносы (недавние незавершённые): {len(out)}")
    return out


def _raw_from_history(h: Dict, source: str, signal: str, publication_kind: str = "") -> Dict:
    pk = publication_kind or ("обновление" if h.get("is_rewrite") == "да" else "новая")
    return {
        "title": h.get("original_title", ""),
        "description": h.get("description", ""),
        "_channel": h.get("channel", "blog"),
        "_platform": h.get("platform", "Блог Kaiten"),
        "product_cluster": h.get("product_cluster", ""),
        "strategy_role": h.get("strategy_role", ""),
        "content_type": h.get("content_type", ""),
        "period": h.get("period", ""),
        "source": source,
        "signal": signal,
        "publication_kind": pk,
        "author": h.get("author") or h.get("coauthor", ""),
        "expert": h.get("coauthor", ""),
        "kaiten_card": h.get("kaiten_card", ""),
        "seo_tz": h.get("seo_tz", ""),
        "ready_tz": h.get("ready_tz", ""),
        "source_sheet": h.get("source_sheet", ""),
        "original_title": h.get("original_title", ""),
    }


# --------------------------------------------------------- B. Protect по Roistat
def _roistat_protect_candidates(history, signals: Signals, cfg, warn) -> List[Dict]:
    pages = signals.roistat.get("pages", [])
    if not pages:
        return []
    hist_cfg = cfg.pipeline.get("history", {})
    top_n = int(hist_cfg.get("roistat_top_pages_for_protect", 25))
    # индекс истории по транслиту для сопоставления slug -> тема
    hist_translit = [(translit(h.get("original_title", "")), h) for h in history
                     if h.get("original_title")]
    out = []
    seen_titles = set()
    for p in pages[:top_n]:
        if p.slug in ("blog", "case", "cases", ""):
            continue
        matched, best = None, 0.0
        for t, h in hist_translit:
            if not t:
                continue
            sc = ratio(p.slug, t)
            if sc > best:
                best, matched = sc, h
        if matched and best >= 70:
            title = matched.get("original_title")
            cluster = matched.get("product_cluster", "")
            ctype = matched.get("content_type", "")
        else:
            title = _slug_to_title(p.slug)
            cluster = ""
            ctype = ""
        if title in seen_titles:
            continue
        seen_titles.add(title)
        signal = (f"Roistat: {int(p.visits)} визитов"
                  + (f", {int(p.leads)} заявок" if p.leads else "")
                  + (f", {int(p.sales)} продаж" if p.sales else "")
                  + " за период — защитить трафик")
        out.append({
            "title": title,
            "description": f"Обновить и усилить страницу блога (URL /{p.slug}), которая приносит трафик.",
            "_channel": "blog", "_platform": "Блог Kaiten",
            "product_cluster": cluster, "strategy_role": "Protect", "content_type": ctype,
            "period": "", "source": "Protect по Roistat",
            "signal": signal, "publication_kind": "обновление",
            "author": "", "expert": "", "kaiten_card": "",
            "seo_tz": "", "ready_tz": "", "source_sheet": "Roistat",
            "original_title": title,
            "_roistat_visits": p.visits, "_roistat_leads": p.leads,
        })
    warn.info("build_candidates", f"B. Protect по Roistat: {len(out)}")
    return out


def _slug_to_title(slug: str) -> str:
    s = slug.replace("-", " ").strip()
    return "Обновление страницы: " + (s[:60] if s else slug)


# --------------------------------------------------------- C. сигналы редакции
def _signal_candidates(signals: Signals, cfg, warn) -> List[Dict]:
    out = []
    # editorial_ideas.csv: title, description, cluster, note
    for r in signals.csv_rows.get("editorial_ideas.csv", []):
        title = (r.get("title") or r.get("тема") or "").strip()
        if not title:
            continue
        out.append(_raw_from_signal_row(r, title, "Идея редакции",
                                        r.get("note") or r.get("сигнал") or "Идея редакции"))
    # seo_signals.csv: keyword/title, url, volume, cluster
    for r in signals.csv_rows.get("seo_signals.csv", []):
        title = (r.get("title") or r.get("keyword") or r.get("запрос") or "").strip()
        if not title:
            continue
        vol = r.get("volume") or r.get("частотность") or ""
        c = _raw_from_signal_row(r, title, "SEO-сигнал",
                                 f"SEO-спрос{(' ~'+str(vol)) if vol else ''}")
        c["seo_tz"] = "есть"
        out.append(c)
    # mandatory_publications.csv: title, date, cluster, note
    for r in signals.csv_rows.get("mandatory_publications.csv", []):
        title = (r.get("title") or r.get("тема") or "").strip()
        if not title:
            continue
        c = _raw_from_signal_row(r, title, "Обязательная публикация",
                                 r.get("note") or "Обязательная публикация")
        c["mandatory"] = "да"
        c["_planned_date"] = (r.get("date") or r.get("дата") or "").strip()
        out.append(c)
    # текстовые приоритеты/запросы продаж -> буллеты как кандидаты
    out += _bullets_as_candidates(signals.text_files.get("sales_kam_signals.md", ""),
                                  "Запрос продаж/KAM", "from_sales_kam")
    if out:
        warn.info("build_candidates", f"C. Сигналы редакции: {len(out)}")
    return out


def _raw_from_signal_row(r: Dict, title: str, source: str, signal: str) -> Dict:
    return {
        "title": title,
        "description": (r.get("description") or r.get("описание") or "").strip(),
        "_channel": "blog", "_platform": "Блог Kaiten",
        "product_cluster": (r.get("cluster") or r.get("кластер") or "").strip(),
        "strategy_role": (r.get("role") or r.get("роль") or "").strip(),
        "content_type": "", "period": "",
        "source": source, "signal": signal, "publication_kind": "новая",
        "author": (r.get("author") or r.get("автор") or "").strip(),
        "expert": (r.get("expert") or r.get("эксперт") or "").strip(),
        "kaiten_card": "", "seo_tz": "", "ready_tz": "",
        "source_sheet": source, "original_title": title,
    }


def _bullets_as_candidates(text: str, source: str, flag: str) -> List[Dict]:
    out = []
    for line in (text or "").splitlines():
        m = re.match(r"^\s*[-*•]\s+(.+)$", line)
        if not m:
            continue
        title = m.group(1).strip()
        if len(title) < 4:
            continue
        out.append({
            "title": title[:120], "description": "",
            "_channel": "blog", "_platform": "Блог Kaiten",
            "product_cluster": "", "strategy_role": "", "content_type": "",
            "period": "", "source": source, "signal": source,
            "publication_kind": "новая", "author": "", "expert": "",
            "kaiten_card": "", "seo_tz": "", "ready_tz": "",
            "source_sheet": source, "original_title": title, "_extra_flag": flag,
        })
    return out


# =========================================================== НОРМАЛИЗАЦИЯ
def normalize_candidates(raw: List[Dict], history: List[Dict], cfg, cycle: Cycle,
                         signals: Signals, warn: WarningLog) -> Tuple[List[Dict], List[Dict]]:
    """Свести сырые кандидаты в инициативы (+ размещения), заполнить поля, флаги, риски."""
    classifier = Classifier(cfg.taxonomy)
    normalizer = TextNormalizer(cfg.taxonomy)

    # присвоить временный id
    for i, c in enumerate(raw):
        c["_cid"] = f"T{i:04d}"

    groups = dedupe_candidates(raw, cfg, normalizer)["groups"]

    # индекс только «готовых» исторических тем — для анти-повторов
    done_matcher = Matcher(normalizer)
    for h in history:
        if h.get("is_done") == "да":
            done_matcher.add(h["row_id"], h["original_title"],
                             platform=h.get("platform", ""), period=h.get("period", ""))

    priority_clusters = _priority_clusters(signals)
    ym = cycle.start.strftime("%Y%m")

    initiatives: List[Dict] = []
    placements: List[Dict] = []
    by_cid = {c["_cid"]: c for c in raw}
    seq = 0
    pl_seq = 0

    for rep_id, member_ids in groups.items():
        members = [by_cid[m] for m in member_ids]
        rep = _pick_representative(members)
        seq += 1
        content_id = f"CP-{ym}-{seq:03d}"

        init, flags, risks = _build_initiative(content_id, rep, members, classifier,
                                               normalizer, priority_clusters,
                                               done_matcher, cfg)
        initiatives.append(init)

        # размещения: по одному на уникальную площадку среди членов группы
        platforms_seen = {}
        for m in members:
            plat = m.get("_platform", "Блог Kaiten")
            if plat in platforms_seen:
                continue
            platforms_seen[plat] = m
            pl_seq += 1
            placements.append(_build_placement(f"PL-{ym}-{pl_seq:03d}", content_id,
                                               plat, m, init))
        # гарантируем хотя бы одно размещение (блог)
        if not placements or placements[-1]["content_id"] != content_id:
            pl_seq += 1
            placements.append(_build_placement(f"PL-{ym}-{pl_seq:03d}",
                                               content_id, "Блог Kaiten", rep, init))

    warn.info("normalize", f"Инициатив: {len(initiatives)}, размещений: {len(placements)}")
    return initiatives, placements


def _pick_representative(members: List[Dict]) -> Dict:
    def score(m):
        s = 0
        if m.get("_platform") == "Блог Kaiten":
            s += 3
        s += len(m.get("description") or "") / 100.0
        if m.get("seo_tz"):
            s += 1
        return s
    return sorted(members, key=score, reverse=True)[0]


def _priority_clusters(signals: Signals) -> set:
    txt = signals.text_files.get("product_priorities.md", "")
    clusters = set()
    for line in txt.splitlines():
        low = line.lower()
        for name in ("crm", "service desk", "itsm", "вкс", "мессенджер", "документ",
                     "база знаний", "ai", "ии", "проект"):
            if name in low:
                clusters.add(name)
    return clusters


def _build_initiative(content_id, rep, members, classifier, normalizer,
                      priority_clusters, done_matcher, cfg) -> Tuple[Dict, set, set]:
    from .schema import blank_initiative
    init = blank_initiative()
    title = rep.get("title", "")
    desc = rep.get("description", "")

    # классификация (доверяем истории, если уже есть)
    ctype_key, ctype_label, _ = classifier.content_type(title, desc)
    ctype = rep.get("content_type") or ctype_label
    cluster = rep.get("product_cluster") or classifier.product_cluster(title, desc)[0]
    role = rep.get("strategy_role") or classifier.strategy_role(title, desc, "", "", ctype_key)[0]
    funnel = classifier.funnel_stage(title, desc)[0]
    segment = classifier.segment(title, desc)[0]

    flags, risks = set(), set()
    # сигналы
    if rep.get("seo_tz") or any(m.get("seo_tz") for m in members):
        flags.add("has_seo_tz")
    if rep.get("ready_tz"):
        flags.add("has_ready_tz")
    if rep.get("_roistat_leads"):
        flags.add("has_roistat_leads")
    if rep.get("_roistat_visits"):
        flags.add("has_roistat_traffic")
    if ctype in ("Сравнение / аналоги",):
        flags.add("is_comparison_or_alt")
    if ctype in ("Кейс", "Исследование"):
        flags.add("is_case_or_research")
    if ctype == "Продуктовая статья":
        flags.add("is_product_article")
    if rep.get("expert"):
        flags.add("has_expert")
    if len(members) > 1:
        flags.add("history_repeat")
    if any(m.get("_extra_flag") == "from_sales_kam" for m in members):
        flags.add("from_sales_kam")
    if rep.get("mandatory") == "да":
        flags.add("from_product_launch")

    priority_cluster = any(pc in cluster.lower() for pc in priority_clusters) if priority_clusters else False

    # анти-повтор: совпадение с опубликованной темой
    best, sc, rel = link_candidate_to_history(title, done_matcher, cfg)
    related = ""
    if rel == "совпадает с историей":
        risks.add("review_duplicate")
        related = f"Уже публиковалось: «{best['title']}» ({best.get('platform','')}, {best.get('period','')})"
    elif rel == "похоже на историю":
        related = f"Похоже на: «{best['title']}» ({best.get('period','')})"

    if not flags:
        risks.add("no_signal")
    effort = EFFORT_BY_TYPE.get(ctype, "средняя")
    if effort == "высокая":
        flags.discard("")  # no-op; штраф считается в scoring по ценности
    if rep.get("expert") and ("аутсорс" not in (rep.get("expert") or "").lower()):
        # зависимость от эксперта — потенциальный риск сроков (мягко)
        pass

    action, cta = ROLE_ACTION.get(role, ROLE_ACTION["Build"])
    problem = CLUSTER_PROBLEM.get(cluster, "Проблема уточняется главредом")

    init.update({
        "content_id": content_id,
        "title": title,
        "description": desc or "(описание уточняется)",
        "user_problem": problem,
        "product_cluster": cluster,
        "product_feature": "",
        "segment": segment,
        "audience_role": segment,
        "funnel_stage": funnel,
        "strategy_role": role,
        "content_type": ctype,
        "idea_source": rep.get("source", ""),
        "signal": rep.get("signal", ""),
        "expected_action": action,
        "cta": cta,
        "product_route": "kaiten.ru — раздел продукта по кластеру",
        "publication_kind": rep.get("publication_kind", "новая"),
        "related_content": related,
        "lead_potential": "", "seo_potential": "", "product_priority": "",
        "segment_relevance": "приоритетный" if priority_cluster else "",
        "evidence_base": _evidence_text(rep, members),
        "effort": effort,
        "dependencies": rep.get("expert", ""),
        "expert": rep.get("expert", ""),
        "author": rep.get("author", ""),
        "target_week": "",
        "score": "", "rationale": "", "decision_status": "кандидат",
        "mandatory": "да" if rep.get("mandatory") == "да" else "нет",
        "risk_flags": "", "score_breakdown": "",
        "source": rep.get("source", ""),
        "original_title": rep.get("original_title", title),
        "source_sheet": rep.get("source_sheet", ""),
        "period": rep.get("period", ""),
        "kaiten_card": rep.get("kaiten_card", ""),
        "editor_comment": "",
        "group_id": content_id,
    })
    # служебные поля для scoring/portfolio
    init["_flags"] = flags
    init["_risks"] = risks
    init["_priority_cluster"] = priority_cluster
    init["_priority_segment"] = False
    init["_planned_date"] = rep.get("_planned_date", "")
    init["_platforms"] = sorted({m.get("_platform", "Блог Kaiten") for m in members})
    return init, flags, risks


def _evidence_text(rep, members) -> str:
    bits = []
    if rep.get("_roistat_visits"):
        bits.append(f"Roistat трафик {int(rep['_roistat_visits'])}")
    if rep.get("ready_tz"):
        bits.append("есть готовое ТЗ")
    if rep.get("seo_tz"):
        bits.append("есть ТЗ SEO")
    if rep.get("expert"):
        bits.append(f"эксперт: {rep['expert']}")
    if len(members) > 1:
        plats = sorted({m.get("_platform", "") for m in members})
        bits.append("встречалось на: " + ", ".join(p for p in plats if p))
    return "; ".join(bits)


def _build_placement(placement_id, content_id, platform, member, init) -> Dict:
    from .schema import blank_placement
    pl = blank_placement()
    is_blog = platform == "Блог Kaiten"
    fmt = "статья" if is_blog else "экспертная статья"
    goal = "Собрать трафик и подвести к продукту" if is_blog else \
           "Охватить аудиторию площадки и получить переходы"
    angle = init.get("title", "") if is_blog else \
            f"{init.get('title','')} — под аудиторию {platform}"
    pl.update({
        "placement_id": placement_id,
        "content_id": content_id,
        "platform": platform,
        "format": fmt,
        "angle": angle,
        "platform_audience": init.get("segment", ""),
        "placement_goal": goal,
        "cta": init.get("cta", ""),
        "planned_date": init.get("_planned_date", ""),
        "status": "идея",
        "canonical_link": "" if is_blog else "канонично: блог Kaiten",
        "platform_requirements": "" if is_blog else "уточнить требования площадки",
        "author": member.get("author", "") or init.get("author", ""),
        "kaiten_card": member.get("kaiten_card", ""),
    })
    return pl
