"""ExpertProfile factory, load/save, and goal-based defaults."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from storytelling_bot.schema import ExpertProfile, Layer


def default_profile_for(entity_id: str) -> ExpertProfile:
    """Return a pre-configured ExpertProfile for known entities, or a generic fallback."""
    if entity_id == "accumulator":
        return ExpertProfile(
            analyst_name="Senior DD Analyst",
            role="Due-diligence lead, late-stage growth fund",
            hypothesis=(
                "Команда Accumulator способна построить устойчивую "
                "alternative-liquidity-платформу для late-stage equity, "
                "опираясь на сеть Founders Forum и track record Дэйва "
                "Вайзера в Gett. Главные риски — концентрация на одном "
                "фаундере и непрозрачная техническая команда."
            ),
            priority_layers=[
                Layer.FOUNDER_PROFESSIONAL,
                Layer.PRODUCT_BUSINESS,
                Layer.PEST_CONTEXT,
            ],
            priority_subcategories=[
                (Layer.FOUNDER_PERSONAL.value, "Fears & Vulnerability"),
                (Layer.FOUNDER_PROFESSIONAL.value, "Path to expertise"),
                (Layer.PRODUCT_BUSINESS.value, "Architecture of the solution"),
                (Layer.COMMUNITY_PRO_EXPERIENCE.value, "Expertise & Diversity"),
            ],
            taboo_topics=["личн", "семейн", "развод", "интим"],
            voice=(
                "взвешенный инвесторский тон; первое лицо множественного числа "
                "(«мы видим», «нам важно»); ставит факты до выводов; "
                "называет противоречия словами «однако», «при этом»; "
                "не использует превосходные степени без числа"
            ),
            keep_threshold=0.45,
            min_kept_per_subcat=1,
        )

    if entity_id == "stripe":
        return ExpertProfile(
            analyst_name="Senior DD Analyst",
            role="Due-diligence lead, fintech growth fund",
            hypothesis=(
                "Stripe построила устойчивую payments-инфраструктуру с "
                "enterprise-moat через API-first подход. Главные риски — "
                "регуляторное давление в ЕС и усиление конкуренции со стороны "
                "Adyen и Block в enterprise-сегменте."
            ),
            priority_layers=[
                Layer.FOUNDER_PROFESSIONAL,
                Layer.PRODUCT_BUSINESS,
                Layer.PEST_CONTEXT,
            ],
            priority_subcategories=[
                (Layer.FOUNDER_PROFESSIONAL.value, "Path to expertise"),
                (Layer.PRODUCT_BUSINESS.value, "Architecture of the solution"),
                (Layer.PEST_CONTEXT.value, "Policy & regulation"),
            ],
            taboo_topics=["личн", "семейн"],
            voice=(
                "аналитический, с акцентом на unit-экономику и рыночную долю; "
                "«данные показывают», «рынок сигнализирует»; без лирики"
            ),
            keep_threshold=0.45,
            min_kept_per_subcat=1,
        )

    if entity_id == "theranos":
        # TODO: build from open public court records and investigative journalism
        return ExpertProfile(
            analyst_name="Senior DD Analyst",
            role="Forensic due-diligence, post-mortem analysis",
            hypothesis=(
                "Theranos — учебный кейс провала governance и отсутствия "
                "technical due diligence. Ни один независимый эксперт не "
                "верифицировал технологию до массового раскрытия. Мы изучаем "
                "паттерн: харизматичный фаундер + закрытость + регуляторные "
                "нарушения."
            ),
            priority_layers=[
                Layer.FOUNDER_PERSONAL,
                Layer.PEST_CONTEXT,
                Layer.SOCIAL_IMPACT,
            ],
            priority_subcategories=[
                (Layer.FOUNDER_PERSONAL.value, "Fears & Vulnerability"),
                (Layer.PEST_CONTEXT.value, "Policy & regulation"),
                (Layer.SOCIAL_IMPACT.value, "Contradictions & cost"),
            ],
            taboo_topics=[],
            voice=(
                "обвинительно-нейтральный, журналист-расследователь; "
                "«документы показывают», «по материалам дела»; без сочувствия"
            ),
            keep_threshold=0.40,
            min_kept_per_subcat=1,
        )

    return ExpertProfile(
        analyst_name="Senior Analyst",
        role="Due-diligence lead",
        hypothesis=(
            f"Открытая гипотеза по {entity_id} — "
            "собираем факты, проверяем профиль и риски."
        ),
        priority_layers=[
            Layer.FOUNDER_PROFESSIONAL,
            Layer.PRODUCT_BUSINESS,
            Layer.PEST_CONTEXT,
        ],
        priority_subcategories=[],
        taboo_topics=[],
        voice="взвешенный, скептичный, инвесторский",
        keep_threshold=0.45,
        min_kept_per_subcat=1,
    )


def default_profile_for_goal(goal: str) -> ExpertProfile:
    """Return ExpertProfile preset for a given storytelling goal."""
    presets: dict[str, dict[str, Any]] = {
        "business": {
            "analyst_name": "Senior DD Analyst",
            "role": "Due-diligence lead, growth fund",
            "hypothesis": "Открытая гипотеза по бизнес-профилю объекта исследования.",
            "priority_layers": [
                Layer.FOUNDER_PROFESSIONAL,
                Layer.PRODUCT_BUSINESS,
                Layer.PEST_CONTEXT,
            ],
            "priority_subcategories": [
                (Layer.FOUNDER_PROFESSIONAL.value, "Path to expertise"),
                (Layer.PRODUCT_BUSINESS.value, "Architecture of the solution"),
                (Layer.PEST_CONTEXT.value, "Historical moment"),
            ],
            "taboo_topics": [],
            "voice": (
                "взвешенный инвесторский тон; «мы видим», «нам важно»; "
                "ставит факты до выводов; называет противоречия «однако», «при этом»"
            ),
            "keep_threshold": 0.45,
            "min_kept_per_subcat": 1,
        },
        "personality": {
            "analyst_name": "Senior Analyst",
            "role": "Биограф, журналист",
            "hypothesis": "Открытая гипотеза по личному профилю объекта исследования.",
            "priority_layers": [
                Layer.FOUNDER_PERSONAL,
                Layer.FOUNDER_PROFESSIONAL,
                Layer.SOCIAL_IMPACT,
            ],
            "priority_subcategories": [
                (Layer.FOUNDER_PERSONAL.value, "Origin & Childhood"),
                (Layer.FOUNDER_PERSONAL.value, "Values & Beliefs"),
                (Layer.SOCIAL_IMPACT.value, "Vision of change"),
            ],
            "taboo_topics": [],
            "voice": "биографический, эмпатичный, литературный; конкретные детали до выводов",
            "keep_threshold": 0.40,
            "min_kept_per_subcat": 1,
        },
        "politics": {
            "analyst_name": "Senior Analyst",
            "role": "Политический аналитик, журналист-расследователь",
            "hypothesis": "Открытая гипотеза по политическому/риск-профилю объекта.",
            "priority_layers": [
                Layer.COMMUNITY_CULTURE,
                Layer.COMMUNITY_PRO_EXPERIENCE,
                Layer.PEST_CONTEXT,
            ],
            "priority_subcategories": [
                (Layer.COMMUNITY_CULTURE.value, "Investors & Partners"),
                (Layer.PEST_CONTEXT.value, "Policy & regulation"),
            ],
            "taboo_topics": [],
            "voice": "обвинительно-нейтральный; «документы показывают», «по данным»; без сочувствия",
            "keep_threshold": 0.40,
            "min_kept_per_subcat": 1,
        },
        "impact": {
            "analyst_name": "Senior Analyst",
            "role": "Impact-аналитик, ESG",
            "hypothesis": "Открытая гипотеза по социальному импакту объекта исследования.",
            "priority_layers": [
                Layer.CLIENTS_STORIES,
                Layer.SOCIAL_IMPACT,
                Layer.PEST_CONTEXT,
            ],
            "priority_subcategories": [
                (Layer.CLIENTS_STORIES.value, "Client's challenge & context"),
                (Layer.SOCIAL_IMPACT.value, "Vision of change"),
                (Layer.SOCIAL_IMPACT.value, "Legacy"),
            ],
            "taboo_topics": [],
            "voice": "гуманитарный; конкретные истории до тезисов; «люди», «сообщество»",
            "keep_threshold": 0.40,
            "min_kept_per_subcat": 1,
        },
    }
    cfg = presets.get(goal, presets["business"])
    return ExpertProfile(**cfg)


def load_profile(path: str | Path) -> ExpertProfile:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return ExpertProfile.from_dict(data)


def save_profile(profile: ExpertProfile, path: str | Path) -> None:
    Path(path).write_text(
        json.dumps(profile.to_jsonable(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
