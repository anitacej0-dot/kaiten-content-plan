"""Загрузка конфигурации и разрешение путей/дат цикла."""
from __future__ import annotations

import datetime as _dt
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import yaml

# Корень репозитория = родитель каталога pipeline/
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_DIR = os.path.join(ROOT, "config")


def _load_yaml(name: str) -> Dict[str, Any]:
    path = os.path.join(CONFIG_DIR, name)
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


@dataclass
class Config:
    pipeline: Dict[str, Any]
    scoring: Dict[str, Any]
    portfolio: Dict[str, Any]
    taxonomy: Dict[str, Any]

    # ------- пути (абсолютные) -------
    def path(self, key: str) -> str:
        rel = self.pipeline.get("paths", {}).get(key, key)
        return os.path.join(ROOT, rel)

    @property
    def inputs_current(self) -> str:
        return self.path("inputs_current")

    @property
    def outputs_dir(self) -> str:
        return self.path("outputs")

    @property
    def handoff_dir(self) -> str:
        return self.path("handoff")

    @property
    def templates_dir(self) -> str:
        return self.path("inputs_templates")


def load_config() -> Config:
    return Config(
        pipeline=_load_yaml("pipeline.yaml"),
        scoring=_load_yaml("scoring.yaml"),
        portfolio=_load_yaml("portfolio.yaml"),
        taxonomy=_load_yaml("taxonomy.yaml"),
    )


# --------------------------------------------------------------- даты цикла
def next_monday(from_date: _dt.date) -> _dt.date:
    days_ahead = (7 - from_date.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    return from_date + _dt.timedelta(days=days_ahead)


@dataclass
class Cycle:
    start: _dt.date
    weeks: int

    @property
    def end(self) -> _dt.date:
        return self.start + _dt.timedelta(weeks=self.weeks) - _dt.timedelta(days=1)

    @property
    def slug(self) -> str:
        return f"{self.start.isoformat()}_{self.end.isoformat()}"

    def week_bounds(self) -> List[tuple]:
        """Список (номер_недели, дата_начала, дата_конца)."""
        out = []
        for i in range(self.weeks):
            s = self.start + _dt.timedelta(weeks=i)
            e = s + _dt.timedelta(days=6)
            out.append((i + 1, s, e))
        return out

    def week_label(self, week_no: int) -> str:
        for n, s, e in self.week_bounds():
            if n == week_no:
                return f"Неделя {n} ({s.strftime('%d.%m')}–{e.strftime('%d.%m')})"
        return f"Неделя {week_no}"


def resolve_cycle(cfg: Config,
                  start: Optional[str] = None,
                  weeks: Optional[int] = None,
                  today: Optional[_dt.date] = None) -> Cycle:
    """Определяет окно планирования.

    Приоритет: аргументы CLI -> config.horizon -> дефолт (ближайший понедельник).
    """
    hz = cfg.pipeline.get("horizon", {})
    if weeks is None:
        weeks = int(hz.get("weeks", 7))
    if start:
        start_date = _dt.date.fromisoformat(start)
    elif hz.get("start_date"):
        start_date = _dt.date.fromisoformat(str(hz["start_date"]))
    else:
        base = today or _dt.date.today()
        start_date = next_monday(base)
    return Cycle(start=start_date, weeks=int(weeks))
