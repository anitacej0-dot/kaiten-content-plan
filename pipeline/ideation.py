"""Генерация НОВЫХ тем на основе данных (а не переносов из истории).

Идея каждой темы обоснована реальным сигналом:
  * спрос по кластеру из Roistat (визиты/заявки по страницам блога);
  * продуктивные паттерны редакции («Как выбрать…», «Аналоги <конкурент>»,
    «<продукт> для <сегмента>») — берутся из того, что уже приносит трафик;
  * связка Build → Convert → Prove внутри кластера.

Всё, что уже встречалось в истории, отсеивается (fuzzy-дедуп). Каждая идея
помечается как ГИПОТЕЗА: её нужно подтвердить SEO/приоритетом/запросом продаж.
Конкуренты — реальные рыночные продукты (редакционное знание), не выдуманные данные.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Dict, List

from .config import Cycle
from .dedupe import Matcher
from .signals import Signals
from .text_utils import TextNormalizer
from .warnings_log import WarningLog

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

# База знаний редакции: реальные рыночные продукты и сегменты по кластерам.
_CLUSTER_KB = {
    "Управление проектами и задачами": {
        "noun_choose": "таск-трекер",
        "noun_for": "Таск-трекер",
        "competitors": ["Jira", "Trello", "Asana", "Monday", "Wrike", "ClickUp",
                        "Redmine", "YouGile", "Weeek", "Планфикс"],
        "segments": ["IT-команд", "маркетинга", "агентств", "производства", "строительства"],
    },
    "CRM": {
        "noun_choose": "CRM-систему",
        "noun_for": "CRM",
        "competitors": ["Bitrix24", "amoCRM", "Мегаплан", "RetailCRM", "Salesforce", "HubSpot"],
        "segments": ["ритейла", "услуг", "оптовой торговли", "медицины", "образования"],
    },
    "Service Desk / ITSM": {
        "noun_choose": "Service Desk",
        "noun_for": "Service Desk",
        "competitors": ["Zendesk", "UseDesk", "Okdesk", "Admin24", "HappyDesk", "Naumen"],
        "segments": ["IT-компаний", "аутсорса", "ритейла", "производства"],
    },
    "ВКС / видеоконференции": {
        "noun_choose": "сервис видеосвязи",
        "noun_for": "Видеосвязь",
        "competitors": ["Zoom", "Google Meet", "Microsoft Teams", "TrueConf", "SberJazz", "Vinteo"],
        "segments": ["распределённых команд", "образования", "медицины"],
    },
    "Корпоративный мессенджер / чаты": {
        "noun_choose": "корпоративный мессенджер",
        "noun_for": "Корпоративный мессенджер",
        "competitors": ["Slack", "Mattermost", "Пачка", "eXpress", "VK Teams", "Compass"],
        "segments": ["крупных компаний", "распределённых команд", "госсектора"],
    },
    "Документы / база знаний": {
        "noun_choose": "базу знаний",
        "noun_for": "База знаний",
        "competitors": ["Notion", "Confluence", "Teamly", "Яндекс Wiki", "Obsidian"],
        "segments": ["IT-команд", "поддержки", "HR-команд"],
    },
    "AI-функции": {
        "noun_choose": "AI-ассистент для работы",
        "noun_for": "AI-ассистент",
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


def generate_ideas(history: List[Dict], signals: Signals, cfg, cycle: Cycle,
                   warn: WarningLog) -> List[Dict]:
    normalizer = TextNormalizer(cfg.taxonomy)
    hist_matcher = Matcher(normalizer)
    for h in history:
        if h.get("original_title"):
            hist_matcher.add(h["row_id"], h["original_title"])

    review_th = float(cfg.pipeline.get("dedupe", {}).get("review_threshold", 82))
    priority_clusters = _priority_cluster_labels(signals)
    demand = _cluster_demand(signals)

    # Порядок кластеров: приоритетные -> по спросу Roistat.
    def cluster_rank(cl):
        d = demand.get(cl, {})
        pr = 1 if cl in priority_clusters else 0
        return (pr, d.get("visits", 0))
    clusters = sorted(_CLUSTER_KB.keys(), key=cluster_rank, reverse=True)

    ideas: List[Dict] = []
    seen_norms = set()

    def is_new(title: str) -> bool:
        best, sc = hist_matcher.best_match(title)
        if sc >= review_th:
            return False
        nt = normalizer.norm_title(title)
        if nt in seen_norms:
            return False
        seen_norms.add(nt)
        return True

    def add_idea(title, role, ctype, cluster, why_extra=""):
        if not is_new(title):
            return False
        d = demand.get(cluster, {})
        vis = int(d.get("visits", 0))
        signal = (f"Кластер «{cluster}»"
                  + (f": Roistat {vis} визитов" if vis else "")
                  + (" (продуктовый приоритет)" if cluster in priority_clusters else "")
                  + f"; паттерн редакции{('; ' + why_extra) if why_extra else ''}; "
                  "в истории не найдено")
        ideas.append({
            "title": title, "description": f"Новая тема (гипотеза) для кластера «{cluster}».",
            "_channel": "blog", "_platform": "Блог Kaiten",
            "product_cluster": cluster, "strategy_role": role, "content_type": ctype,
            "period": "", "source": "Новая идея (данные)", "signal": signal,
            "publication_kind": "новая", "author": "", "expert": "",
            "kaiten_card": "", "seo_tz": "", "ready_tz": "", "source_sheet": "Идеи (данные)",
            "original_title": title, "_idea": True,
            "_idea_cluster_demand": d.get("visits", 0) > 0,
            "_hypothesis": True,
        })
        return True

    for cluster in clusters:
        kb = _CLUSTER_KB[cluster]
        d = demand.get(cluster, {})
        # не генерируем для кластеров без спроса и не в приоритете
        if d.get("visits", 0) <= 0 and cluster not in priority_clusters:
            continue
        # сколько идей на кластер — пропорционально спросу (2..5)
        quota = 5 if d.get("visits", 0) >= 3000 else (4 if d.get("visits", 0) >= 1000 else 3)
        made = 0
        # 1) «Как выбрать <noun>» — сравнительный коммерческий материал
        if made < quota and add_idea(f"Как выбрать {kb['noun_choose']}: критерии и сравнение",
                                     "Convert", "Сравнение / аналоги", cluster,
                                     "связка: коммерческий выбор"):
            made += 1
        # 2) «Аналоги <конкурент>» — по реальным продуктам, которых нет в истории
        for comp in kb["competitors"]:
            if made >= quota:
                break
            if add_idea(f"Аналоги {comp}", "Convert", "Сравнение / аналоги", cluster,
                        f"спрос на альтернативы {comp}"):
                made += 1
        # 3) «<noun_for> для <сегмент>» — отраслевой Convert
        for seg in kb["segments"]:
            if made >= quota:
                break
            if add_idea(f"{kb['noun_for']} для {seg}", "Convert", "Продуктовая статья",
                        cluster, "отраслевой сценарий"):
                made += 1
        # 4) Prove — кейс внедрения (гипотеза, нужен реальный клиент)
        if made < quota:
            add_idea(f"Кейс: внедрение Kaiten для кластера «{cluster}»", "Prove", "Кейс",
                     cluster, "доказательный материал (нужен клиент)")
    warn.info("ideation", f"Сгенерировано новых тем-идей: {len(ideas)}")
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
