"""Построение отчётов (Markdown) и финальная валидация плана."""
from __future__ import annotations

from collections import Counter
from typing import Dict, List


def _counter_md(title: str, counter: Counter, top: int = None) -> str:
    items = counter.most_common(top) if top else sorted(counter.items(),
                                                        key=lambda x: (-x[1], x[0]))
    lines = [f"- {k or '—'}: {v}" for k, v in items]
    return f"**{title}**\n" + "\n".join(lines) if lines else f"**{title}**\n- нет данных"


def input_audit_md(cycle, signals, warn, legacy_file: str) -> str:
    md = ["# 01. Аудит входных данных", ""]
    md.append(f"**Цикл планирования:** {cycle.start.isoformat()} — {cycle.end.isoformat()} "
              f"({cycle.weeks} недель)")
    md.append("")
    md.append(f"**Файл контент-плана:** `{legacy_file or 'не найден'}`")
    md.append("")
    md.append("## Что найдено")
    for p in signals.present:
        md.append(f"- ✅ {p}")
    if not signals.present:
        md.append("- (структурированных сигналов не найдено, кроме контент-плана)")
    md.append("")
    md.append("## Чего не хватает (не блокирует, снижает уверенность)")
    for m in signals.missing:
        md.append(f"- ⚠️ {m}")
    if not signals.missing:
        md.append("- всё на месте")
    md.append("")
    if signals.roistat.get("totals"):
        t = signals.roistat["totals"]
        md.append("## Roistat (заявки/трафик)")
        md.append(f"- страниц: {t['pages']}, визитов: {int(t['visits'])}, "
                  f"заявок: {int(t['leads'])}, продаж: {int(t['sales'])}")
        if t["leads"] < 10:
            md.append("- ⚠️ Заявок с блога мало — лид-потенциал по блогу оцениваем осторожно "
                      "(вывод помечен как гипотеза).")
        md.append("")
    if signals.metrika:
        mk = signals.metrika
        md.append("## Метрика (посещаемость)")
        md.append(f"- дней: {mk['days']}, всего визитов: {int(mk['total'])}, "
                  f"средн/день: {int(mk['avg'])}, тренд: {mk['trend_pct']:+.0f}%")
        md.append("")
    md.append("## Журнал предупреждений")
    md.append(warn.to_markdown())
    return "\n".join(md)


def history_audit_md(history: List[Dict], dedupe_result: Dict) -> str:
    md = ["# 02. Аудит истории контента", ""]
    md.append(f"Разобрано исторических строк: **{len(history)}**")
    md.append("")
    md.append(_counter_md("По каналам", Counter(h["channel"] for h in history)))
    md.append("")
    md.append(_counter_md("По площадкам", Counter(h["platform"] for h in history), top=12))
    md.append("")
    md.append(_counter_md("По продуктовым кластерам",
                          Counter(h["product_cluster"] for h in history)))
    md.append("")
    md.append(_counter_md("По ролям (эвристика)",
                          Counter(h["strategy_role"] for h in history)))
    md.append("")
    md.append(_counter_md("По типам материала",
                          Counter(h["content_type"] for h in history)))
    md.append("")
    done = Counter(h["is_done"] for h in history)
    md.append(f"**Готовность:** готово — {done.get('да',0)}, не готово/без статуса — {done.get('нет',0)}")
    md.append("")
    summary = dedupe_result.get("summary", {})
    md.append("## Пересечения и повторы")
    if summary:
        for rel, cnt in sorted(summary.items(), key=lambda x: -x[1]):
            md.append(f"- {rel}: {cnt} пар")
    else:
        md.append("- пересечений не найдено")
    md.append("")
    md.append("Подробности — в `03_duplicates.csv`. Дистрибуция (та же тема на разных "
              "площадках) НЕ считается дублем — это одна инициатива с размещениями.")
    md.append("")
    # перекосы
    clusters = Counter(h["product_cluster"] for h in history)
    total = sum(clusters.values()) or 1
    top_cluster, top_n = clusters.most_common(1)[0]
    md.append("## Замечания")
    md.append(f"- Доминирующий кластер: «{top_cluster}» — {top_n/total*100:.0f}% истории.")
    rewrites = sum(1 for h in history if h.get("is_rewrite") == "да")
    md.append(f"- Обновлений/рерайтов в истории: {rewrites} — база для Protect.")
    return "\n".join(md)


def validate_plan(initiatives: List[Dict], placements: List[Dict], portfolio: Dict,
                  cfg) -> List[Dict]:
    """Финальные проверки плана. Возвращает список находок."""
    findings = []

    def add(sev, area, msg):
        findings.append({"severity": sev, "area": area, "message": msg})

    selected = portfolio["selected"]
    if not selected:
        add("критично", "план", "План пуст — не отобрано ни одной инициативы")
        return findings

    # роли
    roles = Counter((c.get("strategy_role") or "").lower() for c in selected)
    n = len(selected)
    mix = cfg.portfolio.get("strategy_mix", {})
    for role in ("protect", "convert", "build", "prove"):
        share = roles.get(role, 0) / n
        lo = float(mix.get(role, {}).get("min", 0))
        if share < lo - 0.001:
            add("предупреждение", "баланс ролей",
                f"Доля {role} = {share*100:.0f}% ниже минимума {lo*100:.0f}%")

    # кластерный перекос
    clusters = Counter(c.get("product_cluster") for c in selected)
    top_cluster, top_n = clusters.most_common(1)[0]
    cap = float(cfg.portfolio.get("balance", {}).get("max_share_single_cluster", 0.4))
    if top_n / n > cap + 0.001:
        add("предупреждение", "баланс кластеров",
            f"Кластер «{top_cluster}» = {top_n/n*100:.0f}% (> {cap*100:.0f}%)")

    # у каждой темы — роль, сигнал, CTA, воронка
    for c in selected:
        if not c.get("strategy_role"):
            add("предупреждение", "роль", f"{c['content_id']}: нет стратегической роли")
        if not c.get("signal"):
            add("предупреждение", "сигнал", f"{c['content_id']}: нет подтверждающего сигнала")
        if not c.get("cta"):
            add("предупреждение", "CTA", f"{c['content_id']}: нет CTA")
        if c.get("risk_flags"):
            add("на проверку", "риски", f"{c['content_id']}: {c['risk_flags']}")

    # score ниже порога reject — так быть не должно (только mandatory/ручное решение)
    reject_below = float(cfg.scoring.get("thresholds", {}).get("reject_below", 44))
    consider = float(cfg.scoring.get("thresholds", {}).get("consider", 58))

    def _score(c):
        try:
            return float(c.get("score") or 0)
        except ValueError:
            return 0.0
    below_floor = [c for c in selected if _score(c) < reject_below
                   and c.get("mandatory") != "да"
                   and c.get("decision_status") != "утверждена"]
    for c in below_floor:
        add("на проверку", "очень низкий score",
            f"{c['content_id']} (score {_score(c)}) ниже порога — проверить включение")
    # темы 44–58 включены по балансу ролей/квотам — это норма, но стоит взглянуть
    quota_fill = [c for c in selected if reject_below <= _score(c) < consider
                  and c.get("mandatory") != "да"]
    if quota_fill:
        add("на проверку", "включены по квоте",
            f"{len(quota_fill)} тем со score 44–58 включены для баланса ролей "
            f"(не по высокому score) — проверьте приоритет: "
            + ", ".join(c["content_id"] for c in quota_fill[:10])
            + ("…" if len(quota_fill) > 10 else ""))

    # Prove/Protect минимум
    if roles.get("prove", 0) < 1:
        add("предупреждение", "Prove", "В плане нет ни одного доказательного материала (Prove)")
    if roles.get("protect", 0) < 1:
        add("предупреждение", "Protect", "В плане нет ни одного Protect-материала")

    # внешние размещения — свой угол
    ext = [p for p in placements if p.get("platform") != "Блог Kaiten"]
    for p in ext:
        if not p.get("angle"):
            add("предупреждение", "внешние", f"{p['placement_id']}: нет отдельного угла")
    return findings


def validation_md(findings: List[Dict]) -> str:
    md = ["# 10. Отчёт валидации плана", ""]
    if not findings:
        md.append("✅ Критичных замечаний не найдено. План готов к ревью главреда.")
        return "\n".join(md)
    by_sev = {}
    for f in findings:
        by_sev.setdefault(f["severity"], []).append(f)
    order = ["критично", "предупреждение", "на проверку"]
    icon = {"критично": "❌", "предупреждение": "⚠️", "на проверку": "🔎"}
    for sev in order:
        items = by_sev.get(sev, [])
        if not items:
            continue
        md.append(f"## {icon.get(sev,'')} {sev.capitalize()} ({len(items)})")
        for f in items:
            md.append(f"- **{f['area']}** — {f['message']}")
        md.append("")
    md.append("_Замечания не блокируют экспорт: решение принимает главред._")
    return "\n".join(md)


def capacity_md(capacity_check: Dict, cycle, capacity: Dict) -> str:
    md = ["# 09. Проверка мощности редакции", ""]
    md.append(f"Отобрано инициатив: **{capacity_check['total_selected']}** "
              f"из ~{capacity_check['total_slots']} слотов "
              f"({capacity['items_per_week']} материалов/нед × {cycle.weeks} нед)")
    md.append("")
    md.append("| Неделя | Материалов | Тяжёлых | Пометка |")
    md.append("|---|---|---|---|")
    for line in capacity_check["week_lines"]:
        md.append(f"| {line['week']} | {line['count']} | {line['high_effort']} | {line['flag']} |")
    md.append("")
    if capacity_check["capacity_ok"]:
        md.append("✅ Недельная нагрузка в пределах потолка.")
    else:
        md.append("⚠️ Есть перегруженные недели — часть тем стоит перенести в бэклог.")
    for w in capacity_check.get("streak_warnings", []):
        md.append(f"- ⚠️ {w}")
    return "\n".join(md)


def plan_summary_md(cycle, portfolio, initiatives, placements, signals,
                    findings, warn) -> str:
    selected = portfolio["selected"]
    roles = Counter((c.get("strategy_role") or "") for c in selected)
    clusters = Counter(c.get("product_cluster") for c in selected)
    n = len(selected) or 1
    md = ["# Сводка контент-плана", ""]
    md.append(f"**Цикл:** {cycle.start.isoformat()} — {cycle.end.isoformat()} "
              f"({cycle.weeks} недель)")
    md.append(f"**Отобрано инициатив:** {len(selected)} · "
              f"**в бэклоге:** {len(portfolio['backlog'])} · "
              f"**отклонено:** {len(portfolio['rejected'])}")
    md.append(f"**Размещений:** {len(placements)} "
              f"(в т.ч. внешних: {sum(1 for p in placements if p.get('platform') != 'Блог Kaiten')})")
    md.append("")
    md.append("## Баланс Protect / Convert / Build / Prove")
    for role in ("Protect", "Convert", "Build", "Prove"):
        md.append(f"- {role}: {roles.get(role,0)} ({roles.get(role,0)/n*100:.0f}%)")
    md.append("")
    md.append("## Продуктовые кластеры")
    for cl, c in clusters.most_common():
        md.append(f"- {cl or '—'}: {c}")
    md.append("")
    md.append("## Обязательные публикации")
    mand = [c for c in selected if c.get("mandatory") == "да"]
    if mand:
        for c in mand:
            md.append(f"- {c['content_id']} — {c['title']}")
    else:
        md.append("- не заданы (файл mandatory_publications.csv отсутствует или пуст)")
    md.append("")
    md.append("## Ограничения и допущения этого цикла")
    for m in signals.missing:
        md.append(f"- нет данных: {m} → соответствующие выводы помечены как гипотезы")
    md.append("- Стратегические роли и кластеры проставлены эвристикой по тексту — "
              "требуют быстрой проверки главреда.")
    if signals.roistat.get("totals", {}).get("leads", 0) < 10:
        md.append("- Заявок с блога в Roistat мало → лид-потенциал оценён осторожно.")
    md.append("")
    md.append("## Вопросы главреду (требуют решения)")
    review = [f for f in findings if f["severity"] in ("критично", "на проверку")]
    if review:
        for f in review[:15]:
            md.append(f"- {f['area']}: {f['message']}")
    else:
        md.append("- ключевых развилок нет; проверить общий баланс и приоритеты.")
    md.append("")
    md.append("_Правки вносите в `inputs/current_cycle/decisions.csv` и запускайте `/update-plan`._")
    return "\n".join(md)
