"""ExpertCritic — heuristic (and optional LLM) fact scoring node."""
from __future__ import annotations

import logging
import re
from collections import defaultdict

from storytelling_bot.schema import (
    ExpertProfile,
    Fact,
    FactScore,
    Flag,
    Layer,
    SourceType,
    State,
)

log = logging.getLogger(__name__)

_NUM_RE = re.compile(r"\$?\d+[\d,.]*\s*(m|b|k|млрд|млн|тыс|%)?", re.IGNORECASE)
_QUOTE_RE = re.compile(r"[«\"'][^«\"']{8,}[»\"']")


def _hypothesis_keywords(hypothesis: str) -> list[str]:
    tokens = re.findall(r"[A-Za-zА-Яа-я]{4,}", hypothesis.lower())
    stop = {"которая", "который", "которое", "против", "between", "способ", "опираясь", "главные"}
    return [t for t in tokens if t not in stop]


def _signature(text: str) -> str:
    s = re.sub(r"\s+", " ", text.lower()).strip()
    return s[:80]


def _score_relevance(fact: Fact, profile: ExpertProfile, hyp_kw: list[str]) -> float:
    score = 0.0
    if fact.layer in profile.priority_layers:
        score += 0.30
    if (fact.layer.value, fact.subcategory) in profile.priority_subcategories:
        score += 0.20
    t = fact.text.lower()
    hits = sum(1 for kw in hyp_kw if kw in t)
    score += min(0.30, 0.05 * hits)
    score += 0.10 * fact.confidence
    if fact.flag == Flag.RED:
        score += 0.20
    elif fact.flag == Flag.GREEN:
        score += 0.10
    return min(1.0, score)


def _score_narrative(fact: Fact) -> float:
    score = 0.0
    if _QUOTE_RE.search(fact.text):
        score += 0.40
    nums = _NUM_RE.findall(fact.text)
    score += min(0.30, 0.10 * len(nums))
    if fact.event_date:
        score += 0.10
    if fact.source_type in (SourceType.ONLINE_INTERVIEW, SourceType.OFFLINE_INTERVIEW):
        score += 0.15
    if fact.source_type == SourceType.ARCHIVAL:
        score += 0.05
    if any(k in fact.text.lower() for k in
           ["переломн", "урок", "ошибк", "признаёт", "одержим", "тревог", "the turning point"]):
        score += 0.20
    return min(1.0, score)


def _challenges_hypothesis(fact: Fact, profile: ExpertProfile) -> bool:
    if fact.flag == Flag.RED:
        return True
    t = fact.text.lower()
    contrarian = ["нет публично известного", "нет cto", "признаёт, что нет", "300 миллионов",
                  "ошибка", "потерял", "уничтожал капитал"]
    return any(k in t for k in contrarian)


def _is_taboo(fact: Fact, profile: ExpertProfile) -> bool:
    if not profile.taboo_topics:
        return False
    t = fact.text.lower()
    return any(tb in t for tb in profile.taboo_topics)


def _make_expert_note(fact: Fact, score: FactScore, profile: ExpertProfile) -> str:
    if not score.keep:
        if score.relevance < 0.3:
            return "вне приоритетов профиля — в приложение"
        if score.narrative_value < 0.2:
            return "слабая драматургия, нет цитат/чисел/даты"
        if score.novelty < 0.5:
            return "дублирует уже отобранный факт"
        return "не дотянул до порога keep_threshold"
    notes = []
    if score.challenges_hypothesis:
        notes.append("⚠ ставит гипотезу под вопрос — обязательно в нарратив")
    if fact.source_type in (SourceType.ONLINE_INTERVIEW, SourceType.OFFLINE_INTERVIEW):
        notes.append("первичный источник, голос фаундера")
    if fact.flag == Flag.RED:
        notes.append("красный сигнал — не обсуждать без юридической валидации")
    if not notes:
        notes.append("опорный факт")
    return "; ".join(notes)


def _formulate_thesis(layer: Layer, sub: str, kept: list[Fact], profile: ExpertProfile) -> str:
    if layer == Layer.FOUNDER_PERSONAL:
        if sub == "Fears & Vulnerability":
            return ("Мы видим, что главный страх фаундера — потерять ликвидность из-за внешнего "
                    "шока, и именно этот страх объясняет архитектуру продукта. Это рабочая мотивация, "
                    "однако она же создаёт риск персональной зависимости.")
        if sub == "Origin & Childhood":
            return ("Происхождение фаундера задаёт устойчивую установку «не пускать капитал на "
                    "самотёк»; это согласуется с дисциплиной, которую мы ожидаем от управляющего late-stage фондом.")
        return ("Личностный слой подтверждает: ценности фаундера выровнены с продуктом, "
                "но требуют независимого подтверждения у близкого окружения.")
    if layer == Layer.FOUNDER_PROFESSIONAL:
        if sub == "Path to expertise":
            return ("Профессиональный трек фаундера соответствует мандату DD; "
                    "при этом опыт single-product не равен опыту построения регулируемого фонда.")
        return ("Профессиональный трек фаундера соответствует мандату, "
                "но мы фиксируем зону неопределённости вокруг team depth.")
    if layer == Layer.COMMUNITY_CULTURE:
        return ("Культурный контур — invite-only, опирается на репутационные сети. "
                "Это даёт качественный deal flow и одновременно концентрирует риск на репутации фаундера.")
    if layer == Layer.COMMUNITY_PRO_EXPERIENCE:
        return ("Команда формируется через личные сети, что объясняет скорость, но непрозрачно "
                "для DD. Нам важно увидеть публичный профиль CTO до закрытия раунда.")
    if layer == Layer.CLIENTS_STORIES:
        return ("Клиентская сторона пока представлена через сетевой канал; чтобы валидировать "
                "тягу, нам нужны независимые подтверждения от 2–3 клиентов из заявленных категорий.")
    if layer == Layer.PRODUCT_BUSINESS:
        if sub == "Architecture of the solution":
            return ("Архитектура продукта — консервативный, юридически чистый каркас. "
                    "Мы видим, что продукт сделан под регуляторное давление, а не вопреки ему.")
        if sub == "Evolution":
            return ("Динамика капитала подтверждает product-market fit на ранней траектории, "
                    "но не отвечает на вопрос об устойчивости через цикл.")
        return ("Бизнес-модель опирается на сетевой эффект и регуляторную дисциплину; "
                "ключевая зона риска — операционная масштабируемость.")
    if layer == Layer.SOCIAL_IMPACT:
        return ("Миссия оценивается как искренняя, "
                "но требует количественной метрики через 24 месяца.")
    if layer == Layer.PEST_CONTEXT:
        return ("Макроконтекст работает на компанию: структурный сдвиг к stay-private "
                "и удлинение пути к IPO формируют объёмный TAM.")
    return f"Опорные факты по «{sub}» собраны; голос эксперта — {profile.voice.split(';')[0]}."


def node_expert_critic(state: State) -> State:
    """Score facts, enforce min coverage, formulate theses."""
    from storytelling_bot.expert.profile import default_profile_for

    profile = state.expert_profile or default_profile_for(state.entity_id)
    state.expert_profile = profile

    hyp_kw = _hypothesis_keywords(profile.hypothesis)
    seen: set = set()

    scores: list[FactScore] = []
    for i, f in enumerate(state.facts):
        sig = _signature(f.text)
        novelty = 0.0 if sig in seen else 1.0
        seen.add(sig)
        relevance = _score_relevance(f, profile, hyp_kw)
        narrative = _score_narrative(f)
        challenges = _challenges_hypothesis(f, profile)
        taboo = _is_taboo(f, profile)
        composite = 0.5 * relevance + 0.4 * narrative + 0.1 * novelty
        keep = (composite >= profile.keep_threshold) and not taboo
        if challenges and not taboo:
            keep = True
        score = FactScore(
            fact_idx=i,
            relevance=round(relevance, 3),
            narrative_value=round(narrative, 3),
            novelty=round(novelty, 3),
            challenges_hypothesis=challenges,
            keep=keep,
            expert_note="",
        )
        score.expert_note = _make_expert_note(f, score, profile)
        scores.append(score)

    by_subcat: dict[tuple[Layer, str], list[FactScore]] = defaultdict(list)
    for f, s in zip(state.facts, scores):
        by_subcat[(f.layer, f.subcategory)].append(s)

    for (layer, sub), s_list in by_subcat.items():
        if (layer.value, sub) not in profile.priority_subcategories:
            continue
        kept = [s for s in s_list if s.keep]
        if len(kept) >= profile.min_kept_per_subcat:
            continue
        candidates = sorted(
            [s for s in s_list if not s.keep],
            key=lambda x: 0.5 * x.relevance + 0.4 * x.narrative_value + 0.1 * x.novelty,
            reverse=True,
        )
        need = profile.min_kept_per_subcat - len(kept)
        for s in candidates[:need]:
            f = state.facts[s.fact_idx]
            if _is_taboo(f, profile):
                continue
            s.keep = True
            s.expert_note = (s.expert_note + "; добавлен принудительно — приоритет профиля").strip("; ")

    state.fact_scores = scores

    theses: dict[str, str] = {}
    for (layer, sub), s_list in by_subcat.items():
        kept_facts = [state.facts[s.fact_idx] for s in s_list if s.keep]
        if not kept_facts:
            continue
        theses[f"{layer.value}|{sub}"] = _formulate_thesis(layer, sub, kept_facts, profile)
    state.theses = theses

    kept_total = sum(1 for s in scores if s.keep)
    log.info("ExpertCritic: kept %d / %d facts; %d theses", kept_total, len(scores), len(theses))
    return state
