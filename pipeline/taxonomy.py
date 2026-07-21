"""Эвристическая классификация тем по таксономии (config/taxonomy.yaml).

Все методы возвращают (значение, обоснование) — обоснование объясняет, по каким
словам сделан вывод. Это важно: pipeline не должен «молча» назначать кластер/роль.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from .text_utils import count_hits


class Classifier:
    def __init__(self, taxonomy: Dict):
        self.tax = taxonomy or {}

    # --------- общий механизм: выбрать категорию с макс. числом совпадений ---------
    def _best(self, text: str, groups: Dict[str, Dict], default_key: str
              ) -> Tuple[str, str, List[str]]:
        best_key = default_key
        best_hits = 0
        matched: List[str] = []
        for key, spec in groups.items():
            kws = spec.get("keywords", [])
            hits = [k for k in kws if k in text]
            if len(hits) > best_hits:
                best_hits = len(hits)
                best_key = key
                matched = hits
        label = groups.get(best_key, {}).get("label", best_key)
        return best_key, label, matched

    def _prep(self, *parts: str) -> str:
        return " ".join(p for p in parts if p).lower().replace("ё", "е")

    # ------------------------------------------------------------- кластер
    def product_cluster(self, title: str, description: str = "",
                        rubric: str = "", section: str = "") -> Tuple[str, str]:
        text = self._prep(title, description, rubric, section)
        groups = self.tax.get("product_clusters", {})
        default = self.tax.get("default_cluster", "project_management")
        key, label, hits = self._best(text, groups, default)
        if hits:
            why = f"по словам: {', '.join(hits[:3])}"
        else:
            why = "по умолчанию (сигналов кластера не найдено)"
        return label, why

    # ------------------------------------------------------------- роль
    def strategy_role(self, title: str, description: str = "",
                     rubric: str = "", section: str = "",
                     content_type_key: str = "") -> Tuple[str, str]:
        text = self._prep(title, description, rubric, section)
        groups = self.tax.get("strategy_roles", {})
        default = self.tax.get("default_role", "build")
        # Кейсы/исследования почти всегда Prove вне зависимости от прочего.
        if content_type_key in ("case", "research"):
            return "Prove", "тип материала — кейс/исследование"
        key, _label, hits = self._best(text, groups, default)
        label = {"protect": "Protect", "convert": "Convert",
                 "build": "Build", "prove": "Prove"}.get(key, "Build")
        if hits:
            why = f"по словам: {', '.join(hits[:3])}"
        else:
            why = "по умолчанию (нет явных сигналов роли)"
        return label, why

    # ------------------------------------------------------------- воронка
    def funnel_stage(self, title: str, description: str = "",
                    rubric: str = "", section: str = "") -> Tuple[str, str]:
        text = self._prep(title, description, rubric, section)
        groups = self.tax.get("funnel_stages", {})
        default = self.tax.get("default_funnel", "awareness")
        key, label, hits = self._best(text, groups, default)
        why = f"по словам: {', '.join(hits[:2])}" if hits else "по умолчанию"
        return label, why

    # ------------------------------------------------------------- тип
    def content_type(self, title: str, description: str = "",
                    rubric: str = "", section: str = "") -> Tuple[str, str, str]:
        """Возвращает (key, label, why) — key нужен для правила роли."""
        text = self._prep(title, description, rubric, section)
        groups = self.tax.get("content_types", {})
        default = self.tax.get("default_content_type", "guide")
        key, label, hits = self._best(text, groups, default)
        why = f"по словам: {', '.join(hits[:2])}" if hits else "по умолчанию"
        return key, label, why

    # ------------------------------------------------------------- сегмент
    def segment(self, title: str, description: str = "",
               rubric: str = "", section: str = "") -> Tuple[str, str]:
        text = self._prep(title, description, rubric, section)
        groups = self.tax.get("segments", {})
        default = self.tax.get("default_segment", "management")
        key, label, hits = self._best(text, groups, default)
        why = f"по словам: {', '.join(hits[:2])}" if hits else "по умолчанию"
        return label, why

    # ------------------------------------------------------------- площадка
    def platform(self, raw: str, sheet_name: str = "") -> Tuple[str, str]:
        """Нормализовать площадку из значения колонки или имени листа."""
        text = self._prep(raw, sheet_name)
        platforms = self.tax.get("platforms", {})
        for key, spec in platforms.items():
            for alias in spec.get("aliases", []):
                if alias in text:
                    return spec.get("label", key), key
        default = self.tax.get("default_platform", "blog")
        return platforms.get(default, {}).get("label", "Блог Kaiten"), default

    # ------------------------------------------------------------- готовность
    def is_done(self, status: str) -> bool:
        s = (status or "").strip().lower().replace("ё", "е")
        if not s:
            return False
        return any(m in s for m in self.tax.get("done_statuses", []))

    def status_norm(self, status: str) -> str:
        s = (status or "").strip().lower().replace("ё", "е")
        if not s:
            return "не задан"
        if any(m in s for m in self.tax.get("done_statuses", [])):
            return "готово"
        if any(m in s for m in self.tax.get("in_progress_statuses", [])):
            return "в работе"
        return "не начата"
