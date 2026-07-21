"""Журнал предупреждений.

Цель — pipeline не должен падать из-за одного плохого листа или пустого файла.
Вместо исключения мы фиксируем предупреждение и продолжаем работу.
Все предупреждения попадают в итоговое резюме и в 01_input_audit.md.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import List


@dataclass
class Warning_:
    stage: str
    message: str
    level: str = "warning"  # info | warning | error


@dataclass
class WarningLog:
    items: List[Warning_] = field(default_factory=list)

    def add(self, stage: str, message: str, level: str = "warning") -> None:
        self.items.append(Warning_(stage=stage, message=message, level=level))
        prefix = {"info": "i", "warning": "!", "error": "x"}.get(level, "!")
        # Печатаем в stderr, чтобы не мешать возможному stdout-выводу данных.
        try:
            sys.stderr.write(f"  [{prefix}] {stage}: {message}\n")
        except Exception:
            pass

    def info(self, stage: str, message: str) -> None:
        self.add(stage, message, "info")

    def warn(self, stage: str, message: str) -> None:
        self.add(stage, message, "warning")

    def error(self, stage: str, message: str) -> None:
        self.add(stage, message, "error")

    def extend(self, other: "WarningLog") -> None:
        self.items.extend(other.items)

    def counts(self) -> dict:
        c = {"info": 0, "warning": 0, "error": 0}
        for w in self.items:
            c[w.level] = c.get(w.level, 0) + 1
        return c

    def to_markdown(self) -> str:
        if not self.items:
            return "_Предупреждений нет._"
        lines = []
        for w in self.items:
            icon = {"info": "ℹ️", "warning": "⚠️", "error": "❌"}.get(w.level, "⚠️")
            lines.append(f"- {icon} **{w.stage}** — {w.message}")
        return "\n".join(lines)
