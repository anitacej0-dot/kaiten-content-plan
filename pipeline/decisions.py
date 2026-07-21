"""Ручные редакционные решения (decision log).

Файл решений лежит в inputs/current_cycle/decisions.csv и является ВХОДОМ:
pipeline не хранит правки внутри себя, а ПЕРЕ-ПРИМЕНЯЕТ их при каждом запуске.
Поэтому повторный прогон не затирает ручные решения — они всегда берутся из файла.

Колонки decisions.csv:
    content_id, field, new_value, author, date, reason, is_exception
Поле field может быть любым ключом инициативы, а также специальным
'decision_status' (кандидат|выбрана|утверждена|в бэклог|отклонена) — тогда тема
принудительно перемещается между разделами плана.
"""
from __future__ import annotations

import datetime as _dt
import os
from typing import Dict, List

from .io_utils import read_csv

DECISION_COLUMNS = ["content_id", "field", "new_value", "author", "date",
                    "reason", "is_exception"]


def load_decisions(cfg) -> List[Dict]:
    path = os.path.join(cfg.inputs_current, "decisions.csv")
    rows = read_csv(path)
    out = []
    for r in rows:
        cid = (r.get("content_id") or "").strip()
        field = (r.get("field") or "").strip()
        if not cid or not field:
            continue
        out.append({
            "content_id": cid,
            "field": field,
            "new_value": (r.get("new_value") or "").strip(),
            "author": (r.get("author") or "главред").strip(),
            "date": (r.get("date") or "").strip(),
            "reason": (r.get("reason") or "").strip(),
            "is_exception": (r.get("is_exception") or "нет").strip(),
        })
    return out


def apply_decisions(portfolio: Dict, decisions: List[Dict], cycle, warn) -> List[Dict]:
    """Применить решения к портфелю. Возвращает журнал применённых решений."""
    selected = portfolio["selected"]
    backlog = portfolio["backlog"]
    rejected = portfolio["rejected"]
    all_by_cid = {}
    for lst in (selected, backlog, rejected):
        for c in lst:
            all_by_cid[c["content_id"]] = c

    status_to_list = {"выбрана": selected, "утверждена": selected,
                      "в бэклог": backlog, "отклонена": rejected}
    log: List[Dict] = []
    today = cycle.start.isoformat()

    for d in decisions:
        cid = d["content_id"]
        init = all_by_cid.get(cid)
        if not init:
            warn.warn("decisions", f"Решение для несуществующего {cid} пропущено")
            continue
        field = d["field"]
        old = str(init.get(field, ""))
        new = d["new_value"]

        if field == "decision_status" and new in status_to_list:
            # переместить между разделами
            for lst in (selected, backlog, rejected):
                if init in lst:
                    lst.remove(init)
            target = status_to_list[new]
            init["decision_status"] = new
            if new in ("выбрана", "утверждена") and not init.get("_week_no"):
                _assign_to_lightest_week(init, selected, cycle)
            target.append(init)
        else:
            init[field] = new

        log.append({
            "date": d["date"] or today,
            "author": d["author"],
            "content_id": cid,
            "field": field,
            "old_value": old,
            "new_value": new,
            "reason": d["reason"],
            "is_exception": d["is_exception"],
        })
    if log:
        warn.info("decisions", f"Применено ручных решений: {len(log)}")
    return log


def _assign_to_lightest_week(init, selected, cycle):
    load = {w: 0 for w in range(1, cycle.weeks + 1)}
    for c in selected:
        if c.get("_week_no"):
            load[c["_week_no"]] += 1
    w = min(load, key=lambda k: load[k]) if load else 1
    init["_week_no"] = w
    init["target_week"] = cycle.week_label(w)
