"""Поиск дублей, переносов, каннибализации и дистрибуции.

Ключевой принцип из ТЗ: одинаковая тема для блога и Habr — это НЕ два дубля,
а одна инициатива с разными размещениями (дистрибуция). Дубль — это повтор
одной темы на одной площадке. Каннибализация — разные материалы под один интент.
При слабой уверенности тему НЕ склеиваем автоматически, а помечаем на ручную проверку.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from .text_utils import TextNormalizer, ratio


class Matcher:
    """Индекс тем для быстрого поиска похожих (блокировка по ключевым словам)."""

    def __init__(self, normalizer: TextNormalizer):
        self.norm = normalizer
        self.items: List[Dict] = []
        self._kw_index: Dict[str, List[int]] = defaultdict(list)

    def add(self, item_id: str, title: str, **meta) -> Dict:
        kws = self.norm.keyword_set(title)
        rec = {"id": item_id, "title": title,
               "norm": self.norm.norm_title(title), "keywords": kws, **meta}
        i = len(self.items)
        self.items.append(rec)
        for kw in kws:
            self._kw_index[kw].append(i)
        return rec

    def candidates_for(self, rec: Dict) -> List[Dict]:
        seen = set()
        out = []
        for kw in rec["keywords"]:
            for i in self._kw_index.get(kw, []):
                if i not in seen and self.items[i]["id"] != rec["id"]:
                    seen.add(i)
                    out.append(self.items[i])
        return out

    def best_match(self, title: str) -> Tuple[Optional[Dict], float]:
        probe = {"id": "__probe__", "keywords": self.norm.keyword_set(title),
                 "norm": self.norm.norm_title(title)}
        best, best_score = None, 0.0
        for other in self.candidates_for(probe):
            sc = ratio(probe["norm"], other["norm"])
            if sc > best_score:
                best, best_score = other, sc
        return best, best_score


# ------------------------------------------------------------ union-find
class _UF:
    def __init__(self):
        self.parent: Dict[int, int] = {}

    def find(self, x):
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[ra] = rb


def analyze_history(history: List[Dict], cfg, normalizer: TextNormalizer) -> Dict:
    """Найти группы связанных тем в истории и классифицировать связи."""
    dd = cfg.pipeline.get("dedupe", {})
    dup_th = float(dd.get("duplicate_threshold", 88))
    review_th = float(dd.get("review_threshold", 74))

    matcher = Matcher(normalizer)
    for h in history:
        matcher.add(h["row_id"], h["original_title"],
                    platform=h.get("platform", ""), period=h.get("period", ""),
                    cluster=h.get("product_cluster", ""), channel=h.get("channel", ""),
                    sheet=h.get("source_sheet", ""), is_done=h.get("is_done", ""))

    uf = _UF()
    n = len(matcher.items)
    # быстрая карта id->index для поиска позиции похожей темы
    id2idx = {it["id"]: k for k, it in enumerate(matcher.items)}

    strong_pairs: List[Tuple[int, int, float]] = []   # sc >= dup_th -> та же тема
    cannibal_rows: List[Dict] = []                    # близкие темы под один интент
    cross_platform_distribution = dd.get("cross_platform_is_distribution", True)

    for i in range(n):
        rec = matcher.items[i]
        for other in matcher.candidates_for(rec):
            j = id2idx[other["id"]]
            if j <= i:
                continue
            sc = ratio(rec["norm"], other["norm"])
            if sc >= dup_th:
                strong_pairs.append((i, j, sc))
                uf.union(i, j)
            elif sc >= review_th:
                # близкие, но не одинаковые: каннибализация только при общем кластере/канале
                ra, rb = matcher.items[i], matcher.items[j]
                same_cluster = (ra["cluster"] or "").lower() == (rb["cluster"] or "").lower()
                same_channel = ra.get("channel") == rb.get("channel")
                if same_cluster and same_channel and ra["norm"] != rb["norm"]:
                    cannibal_rows.append(_pair_row("—", "каннибализация", sc, ra, rb,
                        "близкие темы одного кластера/канала — риск каннибализации"))

    # группы из сильных пар
    groups: Dict[int, List[int]] = defaultdict(list)
    for i in range(n):
        if i in uf.parent:
            groups[uf.find(i)].append(i)
    groups = {k: v for k, v in groups.items() if len(v) >= 2}

    dup_rows: List[Dict] = []
    row_flags: Dict[str, List[str]] = defaultdict(list)
    group_seq = 0
    member_to_group: Dict[int, str] = {}
    for members in groups.values():
        group_seq += 1
        gid = f"G{group_seq:03d}"
        for m in members:
            member_to_group[m] = gid
    for a, b, sc in strong_pairs:
        gid = member_to_group.get(a, "—")
        ra, rb = matcher.items[a], matcher.items[b]
        rel, note = _classify_strong(ra, rb, cross_platform_distribution)
        dup_rows.append(_pair_row(gid, rel, sc, ra, rb, note))
        row_flags[ra["id"]].append(rel)
        row_flags[rb["id"]].append(rel)

    dup_rows.extend(cannibal_rows)
    summary = _summarize(dup_rows)
    return {"duplicates": dup_rows, "groups": groups, "row_flags": row_flags,
            "matcher": matcher, "id2idx": id2idx, "summary": summary}


def _pair_row(gid, rel, sc, ra, rb, note) -> Dict:
    return {
        "group_id": gid, "relationship": rel, "similarity": round(sc, 1),
        "theme_a": ra["title"], "platform_a": ra["platform"],
        "period_a": ra["period"], "sheet_a": ra["sheet"],
        "theme_b": rb["title"], "platform_b": rb["platform"],
        "period_b": rb["period"], "sheet_b": rb["sheet"], "note": note,
    }


def _classify_strong(ra, rb, cross_distribution) -> Tuple[str, str]:
    same_platform = (ra["platform"] or "").lower() == (rb["platform"] or "").lower()
    same_period = ra["period"] == rb["period"] and ra["period"] != ""
    if not same_platform and cross_distribution:
        return "дистрибуция", "та же тема на разных площадках — одна инициатива, разные размещения"
    if same_platform and same_period:
        return "дубль", "та же тема, площадка и период — вероятный дубль"
    return "перенос", "та же тема и площадка в разные месяцы — перенос/повтор"


def _summarize(dup_rows: List[Dict]) -> Dict[str, int]:
    s = defaultdict(int)
    for r in dup_rows:
        s[r["relationship"]] += 1
    return dict(s)


def link_candidate_to_history(title: str, matcher: Matcher, cfg
                             ) -> Tuple[Optional[Dict], float, str]:
    """Найти ближайшую историческую тему для кандидата (анти-повтор / Protect-связь)."""
    dd = cfg.pipeline.get("dedupe", {})
    dup_th = float(dd.get("duplicate_threshold", 88))
    review_th = float(dd.get("review_threshold", 74))
    best, sc = matcher.best_match(title)
    if best is None:
        return None, 0.0, ""
    if sc >= dup_th:
        rel = "совпадает с историей"
    elif sc >= review_th:
        rel = "похоже на историю"
    else:
        rel = ""
    return best, sc, rel


def dedupe_candidates(cands: List[Dict], cfg, normalizer: TextNormalizer) -> Dict:
    """Сгруппировать почти одинаковые кандидаты (для склейки размещений).

    Возвращает {rep_of: {cand_id: group_rep_id}, groups: {rep_id:[ids]}}.
    Не удаляет — только помечает, чтобы дистрибуцию свести к одной инициативе.
    """
    dd = cfg.pipeline.get("dedupe", {})
    dup_th = float(dd.get("duplicate_threshold", 88))
    matcher = Matcher(normalizer)
    for c in cands:
        matcher.add(c["_cid"], c.get("title", ""),
                    platform=c.get("_platform", ""), cluster=c.get("product_cluster", ""))
    id2idx = {it["id"]: k for k, it in enumerate(matcher.items)}
    uf = _UF()
    for i, rec in enumerate(matcher.items):
        for other in matcher.candidates_for(rec):
            j = id2idx[other["id"]]
            if j <= i:
                continue
            if ratio(rec["norm"], other["norm"]) >= dup_th:
                uf.union(i, j)
    groups: Dict[int, List[str]] = defaultdict(list)
    for i, it in enumerate(matcher.items):
        root = uf.find(i) if i in uf.parent else i
        groups[root].append(it["id"])
    rep_of: Dict[str, str] = {}
    out_groups: Dict[str, List[str]] = {}
    for members in groups.values():
        rep = members[0]
        out_groups[rep] = members
        for m in members:
            rep_of[m] = rep
    return {"rep_of": rep_of, "groups": out_groups}
