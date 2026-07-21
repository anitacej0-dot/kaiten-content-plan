"""Сборка портфеля на 6-7 недель: квоты ролей, мощность, баланс, распределение по неделям.

Логика (из ТЗ):
  * сначала обязательные материалы (mandatory) — вне score, но помечены;
  * затем — по score, с учётом квот ролей и потолка на кластер;
  * распределение по неделям без перегруза и без «одного продукта подряд»;
  * что не влезло по мощности -> бэклог (а не снижение качества).
"""
from __future__ import annotations

import math
import re
from typing import Dict, List, Optional

from .config import Cycle


def resolve_capacity(cfg, capacity_text: str = "") -> Dict:
    """Мощность редакции: из editorial_capacity.md (если разобрали) или дефолты."""
    defaults = dict(cfg.portfolio.get("capacity_defaults", {}))
    cap = dict(defaults)
    if capacity_text:
        m = re.search(r"(\d+)\s*(?:материал\w*|тем\w*|статьи|публикаци\w*)\s*в\s*недел",
                      capacity_text.lower())
        if m:
            cap["items_per_week"] = int(m.group(1))
        m2 = re.search(r"(\d+)\s*(?:автор\w*|исполнител\w*)", capacity_text.lower())
        if m2:
            cap["authors"] = int(m2.group(1))
    cap.setdefault("items_per_week", 5)
    cap.setdefault("max_items_per_week", cap["items_per_week"] + 2)
    cap.setdefault("authors", 3)
    cap.setdefault("max_high_effort_per_week", 2)
    return cap


def build_portfolio(cands: List[Dict], cfg, cycle: Cycle, capacity: Dict) -> Dict:
    """Отобрать инициативы в план, остальное — в бэклог/отклонённые."""
    weeks = cycle.weeks
    total_slots = int(capacity["items_per_week"]) * weeks
    mix = cfg.portfolio.get("strategy_mix", {})
    balance = cfg.portfolio.get("balance", {})
    cluster_cap = max(1, int(math.floor(
        float(balance.get("max_share_single_cluster", 0.4)) * total_slots)))

    def role_key(c):
        return (c.get("strategy_role") or "").lower()

    # ---- обязательные ----
    mandatory = [c for c in cands if c.get("mandatory") == "да"]
    selected: List[Dict] = []
    sel_ids = set()
    role_count: Dict[str, int] = {"protect": 0, "convert": 0, "build": 0, "prove": 0}
    cluster_count: Dict[str, int] = {}

    def take(c, reason):
        if c["content_id"] in sel_ids:
            return
        selected.append(c)
        sel_ids.add(c["content_id"])
        role_count[role_key(c)] = role_count.get(role_key(c), 0) + 1
        cl = c.get("product_cluster", "")
        cluster_count[cl] = cluster_count.get(cl, 0) + 1
        c["_select_reason"] = reason

    for c in mandatory:
        take(c, "обязательная публикация")

    reject_floor = float(cfg.scoring.get("thresholds", {}).get("reject_below", 44))

    def score_of(c):
        try:
            return float(c.get("score") or 0)
        except (TypeError, ValueError):
            return 0.0

    def cluster_free(cl):
        return cluster_count.get(cl, 0) < cluster_cap

    # Пул по ролям, отсортированный по score. Отбрасываем только явный reject.
    pools = {r: [] for r in ("protect", "convert", "build", "prove")}
    for c in cands:
        if c["content_id"] in sel_ids:
            continue
        pools.setdefault(role_key(c), []).append(c)
    for r in pools:
        pools[r].sort(key=score_of, reverse=True)

    # Целевые квоты по ролям (target-доля * слоты).
    role_target = {r: int(round(float(mix.get(r, {}).get("target", 0.25)) * total_slots))
                   for r in ("protect", "convert", "build", "prove")}

    # ---- проход 1: наполняем квоту каждой роли её лучшими кандидатами (>= reject_floor) ----
    for r in ("convert", "build", "protect", "prove"):
        for c in pools[r]:
            if role_count.get(r, 0) >= role_target.get(r, 0):
                break
            if len(selected) >= total_slots:
                break
            if score_of(c) < reject_floor:
                continue
            if not cluster_free(c.get("product_cluster", "")):
                continue
            take(c, f"квота роли {r}, score {c.get('score')}")

    # ---- проход 2: добираем оставшиеся слоты глобально по score (кластерный потолок держим) ----
    leftovers = sorted([c for c in cands if c["content_id"] not in sel_ids
                        and score_of(c) >= reject_floor],
                       key=score_of, reverse=True)
    for c in leftovers:
        if len(selected) >= total_slots:
            break
        if not cluster_free(c.get("product_cluster", "")):
            continue
        take(c, f"добор по score {c.get('score')}")

    # ---- минимумы Prove / Protect ----
    _ensure_minimum(selected, sel_ids, cands, role_count, cluster_count, take,
                    balance.get("min_prove_items", 1), "prove", total_slots)
    _ensure_minimum(selected, sel_ids, cands, role_count, cluster_count, take,
                    balance.get("min_protect_items", 1), "protect", total_slots)

    # ---- распределение по неделям ----
    _assign_weeks(selected, cycle, capacity, balance)

    # ---- бэклог и отклонённые ----
    backlog, rejected = [], []
    for c in cands:
        if c["content_id"] in sel_ids:
            c["decision_status"] = c.get("decision_status") or "выбрана"
            continue
        if c.get("_band") == "отклонить":
            c["decision_status"] = "отклонена"
            rejected.append(c)
        else:
            c["decision_status"] = "в бэклог"
            backlog.append(c)

    return {
        "selected": selected, "backlog": backlog, "rejected": rejected,
        "role_count": role_count, "cluster_count": cluster_count,
        "total_slots": total_slots, "cluster_cap": cluster_cap,
        "capacity": capacity,
    }


def _ensure_minimum(selected, sel_ids, cands, role_count, cluster_count, take,
                    minimum, role, total_slots):
    minimum = int(minimum or 0)
    if role_count.get(role, 0) >= minimum:
        return
    extras = sorted([c for c in cands if c["content_id"] not in sel_ids
                     and (c.get("strategy_role") or "").lower() == role
                     and c.get("_band") != "отклонить"],
                    key=lambda c: float(c.get("score") or 0), reverse=True)
    for c in extras:
        if role_count.get(role, 0) >= minimum:
            break
        take(c, f"минимум по роли {role}")


def _assign_weeks(selected: List[Dict], cycle: Cycle, capacity: Dict, balance: Dict):
    weeks = cycle.weeks
    max_per_week = int(capacity.get("max_items_per_week", 7))
    max_high = int(capacity.get("max_high_effort_per_week", 2))
    load = {w: 0 for w in range(1, weeks + 1)}
    high = {w: 0 for w in range(1, weeks + 1)}
    week_clusters = {w: [] for w in range(1, weeks + 1)}

    # 1) обязательные с датой -> в свою неделю
    for c in selected:
        wk = _week_of_date(c.get("_planned_date"), cycle)
        if wk:
            c["target_week"] = cycle.week_label(wk)
            c["_week_no"] = wk
            load[wk] += 1
            week_clusters[wk].append(c.get("product_cluster", ""))
            if (c.get("effort") or "").lower() == "высокая":
                high[wk] += 1

    # 2) остальные — по возрастанию загрузки, избегая перегруза и стрельбы одним кластером
    rest = sorted([c for c in selected if not c.get("_week_no")],
                  key=lambda c: float(c.get("score") or 0), reverse=True)
    for c in rest:
        is_high = (c.get("effort") or "").lower() == "высокая"
        cl = c.get("product_cluster", "")
        best_w = None
        best_key = None
        for w in range(1, weeks + 1):
            if load[w] >= max_per_week:
                continue
            if is_high and high[w] >= max_high:
                continue
            same_cluster = week_clusters[w].count(cl)
            key = (load[w], same_cluster)  # меньше загрузка и меньше того же кластера
            if best_key is None or key < best_key:
                best_key, best_w = key, w
        if best_w is None:  # всё переполнено — кладём в наименее загруженную
            best_w = min(load, key=lambda w: load[w])
        c["target_week"] = cycle.week_label(best_w)
        c["_week_no"] = best_w
        load[best_w] += 1
        week_clusters[best_w].append(cl)
        if is_high:
            high[best_w] += 1


def _week_of_date(date_str: Optional[str], cycle: Cycle) -> Optional[int]:
    if not date_str:
        return None
    import datetime as dt
    try:
        d = dt.date.fromisoformat(str(date_str)[:10])
    except (ValueError, TypeError):
        return None
    for n, s, e in cycle.week_bounds():
        if s <= d <= e:
            return n
    return None


def validate_capacity(portfolio: Dict, cfg, cycle: Cycle) -> Dict:
    """Проверить недельную нагрузку, тяжёлые материалы, стрельбу кластером."""
    selected = portfolio["selected"]
    capacity = portfolio["capacity"]
    balance = cfg.portfolio.get("balance", {})
    max_per_week = int(capacity.get("max_items_per_week", 7))
    per_week = int(capacity.get("items_per_week", 5))
    weeks = cycle.weeks

    by_week: Dict[int, List[Dict]] = {w: [] for w in range(1, weeks + 1)}
    for c in selected:
        w = c.get("_week_no")
        if w:
            by_week[w].append(c)

    lines, ok = [], True
    for w in range(1, weeks + 1):
        items = by_week[w]
        highs = sum(1 for c in items if (c.get("effort") or "").lower() == "высокая")
        flag = ""
        if len(items) > max_per_week:
            ok = False
            flag = f"  ⚠️ перегруз (> {max_per_week})"
        elif len(items) > per_week:
            flag = "  (выше целевой нагрузки)"
        lines.append({"week": cycle.week_label(w), "count": len(items),
                      "high_effort": highs, "flag": flag.strip()})

    # доля внешних (по числу размещений считается отдельно; тут — по инициативам)
    # проверка «3+ одного продукта подряд» по последовательности недель
    streak_warn = _check_streaks(selected, cycle, balance)

    return {"by_week": by_week, "week_lines": lines, "capacity_ok": ok,
            "streak_warnings": streak_warn, "total_selected": len(selected),
            "total_slots": portfolio["total_slots"]}


def _check_streaks(selected, cycle, balance) -> List[str]:
    seq = sorted([c for c in selected if c.get("_week_no")],
                 key=lambda c: (c["_week_no"], -float(c.get("score") or 0)))
    warns = []
    max_streak = int(balance.get("max_same_product_article_streak", 2))
    run_cluster, run_len = None, 0
    for c in seq:
        cl = c.get("product_cluster", "")
        if cl == run_cluster:
            run_len += 1
        else:
            run_cluster, run_len = cl, 1
        if run_len == max_streak + 1:
            warns.append(f"Подряд {run_len} материала кластера «{cl}» — проверить чередование")
    return warns
