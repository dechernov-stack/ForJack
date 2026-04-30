"""Focus prompt presets for monitoring ticks — per-tick ExpertProfile patches."""
from __future__ import annotations

from storytelling_bot.schema import ExpertProfile, Layer

FOCUS_PROMPTS: dict[str, dict] = {
    "business-pulse": {
        "boost_layers": [Layer.PRODUCT_BUSINESS, Layer.CLIENTS_STORIES, Layer.PEST_CONTEXT],
        "boost_amount": 0.15,
        "extra_tools": ["sec_edgar", "crunchbase"],
        "description": "Штатное обновление бизнес-профиля, раз в неделю",
    },
    "red-flag-watch": {
        "boost_layers": [Layer.COMMUNITY_CULTURE, Layer.COMMUNITY_PRO_EXPERIENCE],
        "boost_amount": 0.20,
        "extra_tools": ["opensanctions", "gdelt"],
        "description": "При пограничных decisions (watch / pause): приоритет hard-flags",
    },
    "personal-shift": {
        "boost_layers": [Layer.FOUNDER_PERSONAL, Layer.FOUNDER_PROFESSIONAL, Layer.SOCIAL_IMPACT],
        "boost_amount": 0.15,
        "extra_tools": [],
        "description": "Новый pivot фаундера или личное событие",
    },
    "policy-shift": {
        "boost_layers": [Layer.PEST_CONTEXT],
        "boost_amount": 0.25,
        "extra_tools": ["sec_edgar", "gdelt"],
        "description": "Регуляторная хайп-неделя (SEC enforcement, GDPR fine)",
    },
    "quotes-only": {
        "boost_layers": [],
        "boost_amount": 0.0,
        "extra_tools": [],
        "only_audio": True,
        "description": "Разбор только новых выступлений (audio/video)",
    },
}


def apply_focus(profile: ExpertProfile, mode: str) -> ExpertProfile:
    """Return a patched ExpertProfile for one monitoring tick (not saved to DB)."""
    cfg = FOCUS_PROMPTS.get(mode)
    if not cfg or not cfg.get("boost_layers"):
        return profile

    boost = cfg["boost_amount"]
    boosted = list(cfg["boost_layers"])

    new_priority = list(profile.priority_layers)
    for lay in boosted:
        if lay not in new_priority:
            new_priority.insert(0, lay)

    new_threshold = max(0.0, profile.keep_threshold - boost)
    return profile.model_copy(update={
        "priority_layers": new_priority,
        "keep_threshold": new_threshold,
    })
