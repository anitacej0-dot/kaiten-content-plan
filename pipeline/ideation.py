"""Генерация НОВЫХ тем на основе данных (а не переносов из истории).

Идея каждой темы обоснована реальным сигналом:
  * спрос по кластеру из Roistat (визиты/заявки по страницам блога);
  * продуктивные паттерны редакции («Как выбрать…», «Аналоги <конкурент>»,
    «<продукт> для <сегмента>») — берутся из того, что уже приносит трафик;
  * связка Build → Convert → Prove внутри кластера.

Дедуп в ДВА слоя, чтобы не предлагать уже существующее:
  1) против ИСТОРИИ контент-плана (Excel) — fuzzy по темам;
  2) против ОПУБЛИКОВАННОГО блога — по списку URL из Roistat (kaiten.ru/blog/<slug>).
     Слаги сайта латиницей, поэтому бренды конкурентов и интент («vybrat/luchshie/
     analog») сверяем по латинским токенам — это надёжно, без ошибок транслитерации.

Конкуренты — реальные рыночные продукты (редакционное знание), не выдуманные данные.
Каждая идея помечается как ГИПОТЕЗА: подтвердить SEO/приоритетом/запросом продаж.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Tuple

from .config import Cycle
from .dedupe import Matcher
from .signals import Signals, translit
from .text_utils import TextNormalizer
from .warnings_log import WarningLog


def translit_prefix(text: str, n: int) -> str:
    return translit(text)[:n]

# slug (латиница Roistat) -> кластер таксономии
_SLUG_KW = {
    "CRM": ["crm", "srm", "sdelk", "klient", "prodazh", "voronk"],
    "Service Desk / ITSM": ["service", "desk", "itsm", "itil", "podderzh", "help",
                            "zayav", "usedesk", "admin24", "okdesk"],
    "ВКС / видеоконференции": ["video", "zoom", "meet", "telemost", "sozvon", "vks",
                              "konferenc", "tolk", "webinar"],
    "Корпоративный мессенджер / чаты": ["messenger", "messendzh", "chat", "slack"],
    "Документы / база знаний": ["document", "dokument", "shablon", "baz", "znaniy",
                               "redaktor", "wiki", "notion", "zametok"],
    "AI-функции": ["nejroset", "ai-", "ii-", "gpt", "iskusstvenn"],
    "Управление проектами и задачами": ["proekt", "zadach", "task", "kanban", "scrum",
        "gantt", "ganta", "agile", "sprint", "trekr", "planir", "metodolog", "diagramm"],
}

# Токены интента в слагах сайта (латиница).
_INTENT_TOKENS = ["vybrat", "vybor", "luchshi", "luchshie", "top-", "-top",
                  "sravneni", "obzor", "analog", "kak-vybrat"]

# База знаний редакции: реальные продукты (name, латинский_токен_в_слаге) и сегменты.
_CLUSTER_KB = {
    "Управление проектами и задачами": {
        "noun_choose": "таск-трекер", "noun_for": "Таск-трекер",
        "slug_tokens": ["task", "trekk", "trek", "proekt", "zadach", "kanban",
                        "scrum", "gantt", "ganta", "planirovsh"],
        "competitors": [("Jira", "jira"), ("Trello", "trello"), ("Asana", "asana"),
                        ("Monday", "monday"), ("Wrike", "wrike"), ("ClickUp", "clickup"),
                        ("Redmine", "redmine"), ("YouGile", "yougile"),
                        ("Weeek", "weeek"), ("Планфикс", "planfix")],
        "segments": ["IT-команд", "маркетинга", "агентств", "производства", "строительства"],
    },
    "CRM": {
        "noun_choose": "CRM-систему", "noun_for": "CRM",
        "slug_tokens": ["crm"],
        "competitors": [("Bitrix24", "bitri"), ("amoCRM", "amocrm"),
                        ("Мегаплан", "megaplan"), ("RetailCRM", "retailcrm"),
                        ("Salesforce", "salesforce"), ("HubSpot", "hubspot")],
        "segments": ["ритейла", "услуг", "оптовой торговли", "медицины", "образования"],
    },
    "Service Desk / ITSM": {
        "noun_choose": "Service Desk", "noun_for": "Service Desk",
        "slug_tokens": ["service-desk", "servis-desk", "itsm", "help-desk", "helpdesk"],
        "competitors": [("Zendesk", "zendesk"), ("UseDesk", "usedesk"),
                        ("Okdesk", "okdesk"), ("Admin24", "admin24"),
                        ("HappyDesk", "happydesk"), ("Naumen", "naumen")],
        "segments": ["IT-компаний", "аутсорса", "ритейла", "производства"],
    },
    "ВКС / видеоконференции": {
        "noun_choose": "сервис видеосвязи", "noun_for": "Видеосвязь",
        "slug_tokens": ["videokonferenc", "videozvon", "video-zvon", "sozvon", "konferenc", "vks"],
        "competitors": [("Zoom", "zoom"), ("Google Meet", "google-meet"),
                        ("Microsoft Teams", "-teams"), ("TrueConf", "trueconf"),
                        ("SberJazz", "sberjazz"), ("Vinteo", "vinteo")],
        "segments": ["распределённых команд", "образования", "медицины"],
    },
    "Корпоративный мессенджер / чаты": {
        "noun_choose": "корпоративный мессенджер", "noun_for": "Корпоративный мессенджер",
        "slug_tokens": ["messendzh", "messeng"],
        "competitors": [("Slack", "slack"), ("Mattermost", "mattermost"),
                        ("Пачка", "pachka"), ("eXpress", "express"),
                        ("VK Teams", "vk-teams"), ("Compass", "compass")],
        "segments": ["крупных компаний", "распределённых команд", "госсектора"],
    },
    "Документы / база знаний": {
        "noun_choose": "базу знаний", "noun_for": "База знаний",
        "slug_tokens": ["bazy-znanij", "baza-znan", "znanij", "wiki"],
        "competitors": [("Notion", "notion"), ("Confluence", "confluence"),
                        ("Teamly", "teamly"), ("Яндекс Wiki", "-wiki"),
                        ("Obsidian", "obsidian")],
        "segments": ["IT-команд", "поддержки", "HR-команд"],
    },
    "AI-функции": {
        "noun_choose": "AI-ассистент для работы", "noun_for": "AI-ассистент",
        "slug_tokens": ["nejroset", "ii-", "ai-"],
        "competitors": [],
        "segments": ["проектных команд", "поддержки", "аналитиков"],
    },
}


def _cluster_demand(signals: Signals) -> Dict[str, Dict]:
    agg: Dict[str, Dict] = defaultdict(lambda: {"visits": 0.0, "leads": 0.0, "pages": 0})
    for p in signals.roistat.get("pages", []):
        s = p.slug.lower()
        for cluster, kws in _SLUG_KW.items():
            if any(k in s for k in kws):
                agg[cluster]["visits"] += p.visits
                agg[cluster]["leads"] += p.leads
                agg[cluster]["pages"] += 1
                break
    return agg


class _Published:
    """Индекс опубликованного блога по слагам из Roistat."""

    def __init__(self, signals: Signals):
        self.slugs = [p.slug.lower() for p in signals.roistat.get("pages", [])]
        self.blob = " ".join(self.slugs)

    def has_token(self, token: str) -> bool:
        return bool(token) and token in self.blob

    def has_choose_page(self, cluster_tokens: List[str]) -> bool:
        for s in self.slugs:
            if any(ct in s for ct in cluster_tokens) and any(i in s for i in _INTENT_TOKENS):
                return True
        return False

    def has_cluster_segment(self, cluster_tokens: List[str], seg_prefix: str) -> bool:
        if not seg_prefix:
            return False
        for s in self.slugs:
            if any(ct in s for ct in cluster_tokens) and seg_prefix in s:
                return True
        return False


def generate_ideas(history: List[Dict], signals: Signals, cfg, cycle: Cycle,
                   warn: WarningLog) -> List[Dict]:
    normalizer = TextNormalizer(cfg.taxonomy)
    hist_matcher = Matcher(normalizer)
    for h in history:
        if h.get("original_title"):
            hist_matcher.add(h["row_id"], h["original_title"])
    published = _Published(signals)

    review_th = float(cfg.pipeline.get("dedupe", {}).get("review_threshold", 82))
    priority_clusters = _priority_cluster_labels(signals)
    demand = _cluster_demand(signals)

    def cluster_rank(cl):
        d = demand.get(cl, {})
        return (1 if cl in priority_clusters else 0, d.get("visits", 0))
    clusters = sorted(_CLUSTER_KB.keys(), key=cluster_rank, reverse=True)

    ideas: List[Dict] = []
    seen_norms = set()
    skipped = {"история": 0, "блог": 0}

    def not_in_history(title: str) -> bool:
        best, sc = hist_matcher.best_match(title)
        if sc >= review_th:
            skipped["история"] += 1
            return False
        nt = normalizer.norm_title(title)
        if nt in seen_norms:
            return False
        seen_norms.add(nt)
        return True

    def emit(title, role, ctype, cluster, why_extra=""):
        d = demand.get(cluster, {})
        vis = int(d.get("visits", 0))
        signal = (f"Кластер «{cluster}»"
                  + (f": Roistat {vis} визитов" if vis else "")
                  + (" (продуктовый приоритет)" if cluster in priority_clusters else "")
                  + f"; паттерн редакции{('; ' + why_extra) if why_extra else ''}; "
                  "нет ни в истории, ни в опубликованном блоге")
        ideas.append({
            "title": title, "description": f"Новая тема (гипотеза) для кластера «{cluster}».",
            "_channel": "blog", "_platform": "Блог Kaiten",
            "product_cluster": cluster, "strategy_role": role, "content_type": ctype,
            "period": "", "source": "Новая идея (данные)", "signal": signal,
            "publication_kind": "новая", "author": "", "expert": "",
            "kaiten_card": "", "seo_tz": "", "ready_tz": "", "source_sheet": "Идеи (данные)",
            "original_title": title, "_idea": True,
            "_idea_cluster_demand": d.get("visits", 0) > 0, "_hypothesis": True,
        })

    for cluster in clusters:
        kb = _CLUSTER_KB[cluster]
        d = demand.get(cluster, {})
        if d.get("visits", 0) <= 0 and cluster not in priority_clusters:
            continue
        quota = 5 if d.get("visits", 0) >= 3000 else (4 if d.get("visits", 0) >= 1000 else 3)
        made = 0
        ct = kb["slug_tokens"]

        # 1) «Как выбрать <noun>» — только если такой страницы ещё НЕТ в блоге
        if made < quota and not published.has_choose_page(ct):
            title = f"Как выбрать {kb['noun_choose']}: критерии и сравнение"
            if not_in_history(title):
                emit(title, "Convert", "Сравнение / аналоги", cluster, "коммерческий выбор")
                made += 1

        # 2) «Аналоги <конкурент>» — только для брендов, которых НЕТ в блоге
        for name, token in kb["competitors"]:
            if made >= quota:
                break
            if published.has_token(token):
                skipped["блог"] += 1
                continue
            title = f"Аналоги {name}"
            if not_in_history(title):
                emit(title, "Convert", "Сравнение / аналоги", cluster,
                     f"альтернатива {name} — в блоге не раскрыта")
                made += 1

        # 3) «<noun_for> для <сегмент>» — если такой связки ещё нет в блоге
        for seg in kb["segments"]:
            if made >= quota:
                break
            seg_pref = translit_prefix(seg, 5)
            if published.has_cluster_segment(ct, seg_pref):
                skipped["блог"] += 1
                continue
            title = f"{kb['noun_for']} для {seg}"
            if not_in_history(title):
                emit(title, "Convert", "Продуктовая статья", cluster, "отраслевой сценарий")
                made += 1

        # 4) Prove — кейс внедрения (гипотеза, нужен реальный клиент)
        if made < quota:
            title = f"Кейс: внедрение Kaiten для кластера «{cluster}»"
            if not_in_history(title):
                emit(title, "Prove", "Кейс", cluster, "доказательный материал (нужен клиент)")

    warn.info("ideation",
              f"Новых тем-идей: {len(ideas)} (отсеяно: история {skipped['история']}, "
              f"уже в блоге {skipped['блог']})")
    return ideas


def _priority_cluster_labels(signals: Signals) -> set:
    txt = signals.text_files.get("product_priorities.md", "").lower()
    labels = set()
    mapping = {
        "crm": "CRM", "service desk": "Service Desk / ITSM", "itsm": "Service Desk / ITSM",
        "вкс": "ВКС / видеоконференции", "видео": "ВКС / видеоконференции",
        "мессендж": "Корпоративный мессенджер / чаты",
        "документ": "Документы / база знаний", "база знаний": "Документы / база знаний",
        "ai": "AI-функции", "ии": "AI-функции", "проект": "Управление проектами и задачами",
    }
    for key, label in mapping.items():
        if key in txt:
            labels.add(label)
    return labels
