"""Нормализация текста и нечёткое сравнение тем.

Используется для поиска дублей, переносов и каннибализации. Работает с русским
текстом. Нормализация: нижний регистр, замена ё->е, удаление пунктуации, срез
служебных префиксов, применение синонимов, удаление стоп-слов.
"""
from __future__ import annotations

import re
from typing import Dict, Iterable, List, Optional, Set

try:
    from rapidfuzz import fuzz
    _HAVE_RAPIDFUZZ = True
except Exception:  # pragma: no cover
    _HAVE_RAPIDFUZZ = False
    import difflib


_PUNCT_RE = re.compile(r"[^\w\s]+", re.UNICODE)
_SPACE_RE = re.compile(r"\s+", re.UNICODE)


class TextNormalizer:
    def __init__(self, taxonomy: Optional[Dict] = None):
        taxonomy = taxonomy or {}
        self.stopwords: Set[str] = set(taxonomy.get("stopwords", []))
        self.synonyms: Dict[str, str] = dict(taxonomy.get("synonyms", {}))
        self.strip_prefixes: List[str] = list(taxonomy.get("strip_prefixes", []))

    # ---------- базовая очистка ----------
    def clean(self, text: str) -> str:
        if not text:
            return ""
        t = str(text).lower().replace("ё", "е").strip()
        # срезаем служебные префиксы в начале
        changed = True
        while changed:
            changed = False
            for pref in self.strip_prefixes:
                if t.startswith(pref):
                    t = t[len(pref):].strip(" :–-")
                    changed = True
        # применяем синонимы (по подстрокам)
        for src, dst in self.synonyms.items():
            if src in t:
                t = t.replace(src, dst)
        t = _PUNCT_RE.sub(" ", t)
        t = _SPACE_RE.sub(" ", t).strip()
        return t

    # ---------- ключевые слова ----------
    def keywords(self, text: str, min_len: int = 3) -> List[str]:
        cleaned = self.clean(text)
        words = [w for w in cleaned.split()
                 if len(w) >= min_len and w not in self.stopwords]
        # уникализируем, сохраняя порядок
        seen: Set[str] = set()
        out: List[str] = []
        for w in words:
            if w not in seen:
                seen.add(w)
                out.append(w)
        return out

    def keyword_set(self, text: str, min_len: int = 3) -> Set[str]:
        return set(self.keywords(text, min_len))

    def norm_title(self, text: str) -> str:
        """Нормализованная тема: ключевые слова, отсортированные и склеенные."""
        return " ".join(sorted(self.keyword_set(text)))


def ratio(a: str, b: str) -> float:
    """Схожесть 0..100 по множеству токенов (устойчиво к перестановкам слов)."""
    if not a or not b:
        return 0.0
    if _HAVE_RAPIDFUZZ:
        return float(fuzz.token_set_ratio(a, b))
    return difflib.SequenceMatcher(None, a, b).ratio() * 100.0


def jaccard(a: Iterable[str], b: Iterable[str]) -> float:
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def contains_any(text: str, needles: Iterable[str]) -> bool:
    t = (text or "").lower().replace("ё", "е")
    return any(n in t for n in needles)


def count_hits(text: str, needles: Iterable[str]) -> int:
    t = (text or "").lower().replace("ё", "е")
    return sum(1 for n in needles if n in t)
