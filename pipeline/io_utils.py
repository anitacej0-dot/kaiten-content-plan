"""Безопасные хелперы ввода-вывода (CSV в UTF-8-SIG, чтобы Excel читал кириллицу)."""
from __future__ import annotations

import csv
import json
import os
from typing import Dict, Iterable, List, Optional

# UTF-8 с BOM: Excel на Windows корректно открывает кириллицу без «кракозябр».
ENCODING = "utf-8-sig"


def ensure_dir(path: str) -> str:
    os.makedirs(path, exist_ok=True)
    return path


def write_csv(path: str, rows: List[Dict], fieldnames: Optional[List[str]] = None) -> str:
    """Записать список словарей в CSV. Пустой список -> файл только с заголовком."""
    ensure_dir(os.path.dirname(path))
    if fieldnames is None:
        fieldnames = list(rows[0].keys()) if rows else []
    with open(path, "w", encoding=ENCODING, newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for r in rows:
            writer.writerow({k: _cell(r.get(k, "")) for k in fieldnames})
    return path


def read_csv(path: str) -> List[Dict[str, str]]:
    """Прочитать CSV в список словарей. Отсутствующий файл -> []."""
    if not path or not os.path.exists(path):
        return []
    # Пробуем utf-8-sig, затем cp1251 как фолбэк для «ручных» файлов.
    for enc in (ENCODING, "utf-8", "cp1251"):
        try:
            with open(path, "r", encoding=enc, newline="") as f:
                return [dict(r) for r in csv.DictReader(f)]
        except (UnicodeDecodeError, UnicodeError):
            continue
    with open(path, "r", encoding=ENCODING, errors="replace", newline="") as f:
        return [dict(r) for r in csv.DictReader(f)]


def write_text(path: str, text: str) -> str:
    ensure_dir(os.path.dirname(path))
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


def read_text(path: str) -> str:
    if not path or not os.path.exists(path):
        return ""
    for enc in ("utf-8", "utf-8-sig", "cp1251"):
        try:
            with open(path, "r", encoding=enc) as f:
                return f.read()
        except (UnicodeDecodeError, UnicodeError):
            continue
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def write_json(path: str, obj) -> str:
    ensure_dir(os.path.dirname(path))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    return path


def read_json(path: str):
    if not path or not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _cell(value) -> str:
    """Привести значение к строке для CSV, аккуратно с None и списками/словарями."""
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return "; ".join(str(v) for v in value if v not in (None, ""))
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, float):
        # аккуратные числа: 3.0 -> "3", 3.14 -> "3.14"
        return str(int(value)) if value.is_integer() else f"{value:.2f}"
    return str(value)


def find_files(directory: str, extensions: Iterable[str]) -> List[str]:
    """Все файлы каталога с указанными расширениями (без рекурсии), кроме временных ~$."""
    if not os.path.isdir(directory):
        return []
    exts = tuple(e.lower() for e in extensions)
    out = []
    for name in sorted(os.listdir(directory)):
        if name.startswith("~$"):
            continue
        if name.lower().endswith(exts):
            out.append(os.path.join(directory, name))
    return out
