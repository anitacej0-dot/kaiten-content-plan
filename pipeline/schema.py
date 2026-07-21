"""Канонические схемы данных.

Два уровня планирования:
  * ИНИЦИАТИВА (master plan) — один content_id = один контентный замысел.
  * РАЗМЕЩЕНИЕ (placement)   — реализация инициативы на конкретной площадке.

Каждое поле описано как (key, ru_label). key — стабильный ключ во всех CSV,
ru_label — подпись для Excel и человекочитаемых отчётов.
"""
from __future__ import annotations

from typing import Dict, List, Tuple

# --------------------------------------------------------------- ИНИЦИАТИВА
# Порядок важен: в этом порядке пишутся CSV и колонки листа «Контент-план».
INITIATIVE_FIELDS: List[Tuple[str, str]] = [
    ("content_id",        "content_id"),
    ("title",             "Тема (рабочее название)"),
    ("description",       "Краткое описание"),
    ("user_problem",      "Пользовательская проблема"),
    ("product_cluster",   "Продуктовый кластер"),
    ("product_feature",   "Продукт / функция"),
    ("segment",           "Сегмент аудитории"),
    ("audience_role",     "Роль / должность читателя"),
    ("funnel_stage",      "Этап воронки"),
    ("strategy_role",     "Роль (Protect/Convert/Build/Prove)"),
    ("content_type",      "Тип материала"),
    ("idea_source",       "Источник идеи"),
    ("signal",            "Подтверждающий сигнал"),
    ("expected_action",   "Ожидаемое действие пользователя"),
    ("cta",               "CTA"),
    ("product_route",     "Маршрут к продукту"),
    ("publication_kind",  "Новая / обновление / переупаковка"),
    ("related_content",   "Связь с существующими материалами"),
    ("lead_potential",    "Лидовый потенциал"),
    ("seo_potential",     "SEO-потенциал"),
    ("product_priority",  "Продуктовый приоритет"),
    ("segment_relevance", "Актуальность для сегмента"),
    ("evidence_base",     "Доказательная база"),
    ("effort",            "Трудоёмкость"),
    ("dependencies",      "Зависимости"),
    ("expert",            "Эксперт"),
    ("author",            "Предполагаемый автор"),
    ("target_week",       "Неделя выпуска"),
    ("score",             "Score"),
    ("rationale",         "Редакционное обоснование"),
    ("decision_status",   "Статус решения"),
    # служебные/аналитические поля:
    ("mandatory",         "Обязательная"),
    ("risk_flags",        "Риски"),
    ("score_breakdown",   "Разбор score"),
    ("source",            "Происхождение кандидата"),
    ("original_title",    "Исходная формулировка"),
    ("source_sheet",      "Исходный лист"),
    ("period",            "Исходный период"),
    ("kaiten_card",       "Карточка Kaiten"),
    ("editor_comment",    "Комментарий главреда"),
    ("group_id",          "ID группы (дубли/дистрибуция)"),
]

INITIATIVE_KEYS: List[str] = [k for k, _ in INITIATIVE_FIELDS]
INITIATIVE_LABELS: Dict[str, str] = {k: v for k, v in INITIATIVE_FIELDS}

# --------------------------------------------------------------- РАЗМЕЩЕНИЕ
PLACEMENT_FIELDS: List[Tuple[str, str]] = [
    ("placement_id",          "placement_id"),
    ("content_id",            "content_id"),
    ("platform",              "Площадка"),
    ("format",                "Формат"),
    ("angle",                 "Угол / тезис"),
    ("platform_audience",     "Аудитория площадки"),
    ("placement_goal",        "Цель размещения"),
    ("cta",                   "CTA / маршрут"),
    ("planned_date",          "Предполагаемая дата"),
    ("status",                "Статус"),
    ("canonical_link",        "Связь с оригиналом"),
    ("platform_requirements", "Требования площадки"),
    ("author",                "Автор"),
    ("kaiten_card",           "Карточка Kaiten"),
]

PLACEMENT_KEYS: List[str] = [k for k, _ in PLACEMENT_FIELDS]
PLACEMENT_LABELS: Dict[str, str] = {k: v for k, v in PLACEMENT_FIELDS}

# --------------------------------------------------------------- ПЕРЕЧИСЛЕНИЯ
# Значения для выпадающих списков в Excel и для валидации.
STRATEGY_ROLES = ["Protect", "Convert", "Build", "Prove"]
FUNNEL_STAGES = ["Осведомлённость (ToFu)", "Рассмотрение (MoFu)",
                 "Решение (BoFu)", "Удержание"]
PUBLICATION_KINDS = ["новая", "обновление", "переупаковка"]
EFFORT_LEVELS = ["низкая", "средняя", "высокая"]
DECISION_STATUSES = ["кандидат", "выбрана", "утверждена", "в бэклог", "отклонена"]
PLACEMENT_STATUSES = ["идея", "запланировано", "согласовано", "в работе",
                      "опубликовано", "отклонено"]
YES_NO = ["да", "нет"]

# --------------------------------------------------------------- ИСТОРИЯ
# Схема строки исторического контента (результат разбора легаси-Excel).
HISTORY_FIELDS: List[Tuple[str, str]] = [
    ("row_id",          "row_id"),
    ("source_sheet",    "Исходный лист"),
    ("sheet_kind",      "Тип листа"),        # blog | external | case | unknown
    ("period",          "Период"),           # напр. 2025-02
    ("period_label",    "Период (текст)"),
    ("channel",         "Канал"),            # blog | external | case
    ("platform",        "Площадка"),
    ("original_title",  "Исходная тема"),
    ("norm_title",      "Норм. тема"),
    ("description",     "Описание"),
    ("rubric",          "Рубрика"),
    ("section",         "Раздел"),
    ("date_planned",    "Дата план"),
    ("date_fact",       "Дата факт"),
    ("author",          "Автор"),
    ("coauthor",        "С кем пишем"),
    ("seo_tz",          "ТЗ SEO"),
    ("ready_tz",        "Готовое ТЗ"),
    ("comment",         "Комментарий"),
    ("status",          "Статус"),
    ("kaiten_card",     "Карточка Kaiten"),
    ("product_cluster", "Кластер"),
    ("strategy_role",   "Роль"),
    ("content_type",    "Тип"),
    ("is_done",         "Готово"),
    ("is_rewrite",      "Рерайт/обновление"),
]
HISTORY_KEYS: List[str] = [k for k, _ in HISTORY_FIELDS]
HISTORY_LABELS: Dict[str, str] = {k: v for k, v in HISTORY_FIELDS}


def blank_initiative() -> Dict[str, str]:
    return {k: "" for k in INITIATIVE_KEYS}


def blank_placement() -> Dict[str, str]:
    return {k: "" for k in PLACEMENT_KEYS}
