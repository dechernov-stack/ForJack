"""MockClient — deterministic keyword heuristics (no real LLM calls)."""
from __future__ import annotations

from typing import Optional, Tuple

from storytelling_bot.schema import Fact, Flag, Layer, SUBCATEGORIES

_LAYER_KEYWORDS = {
    Layer.FOUNDER_PERSONAL: ["детств", "семь", "родил", "ценност", "страх", "мечт", "вера", "переломн", "the turning point"],
    Layer.FOUNDER_PROFESSIONAL: ["gett", "kupivip", "carprice", "опыт", "руководил", "масштаб", "ipo", "$1b", "$1 b", "млрд", "карьер"],
    Layer.COMMUNITY_CULTURE: ["invite-only", "сообщество", "клуб", "доверие", "founders forum", "нетворк", "ангел", "wix", "zalando"],
    Layer.COMMUNITY_PRO_EXPERIENCE: ["команда", "cxo", "ангелов", "управляющ", "advisory", "темчук", "хартманн"],
    Layer.CLIENTS_STORIES: ["клиент", "spacex", "discord", "vercel", "perplexity", "n26", "monzo", "qonto", "акционер"],
    Layer.PRODUCT_BUSINESS: ["equity pooling", "fund i", "fund ii", "fund iii", "secondary", "rule 506", "section 3(c)", "aum", "valuation", "оценк", "$46m", "$140m", "$60m"],
    Layer.SOCIAL_IMPACT: ["миссия", "защит", "ликвидност", "founders os", "наследие", "5 миллиард", "12 000"],
    Layer.PEST_CONTEXT: ["sec", "регулятор", "1996", "nsmia", "jobs act", "stay private", "макро", "ставк", "кризис", "война"],
}

_SUBCAT_KEYWORDS = {
    Layer.FOUNDER_PERSONAL: {
        "Origin & Childhood": ["детств", "родил", "семь", "казахстан"],
        "Values & Beliefs": ["верит", "ценност", "вера", "убежден"],
        "Fears & Vulnerability": ["страх", "уязвим", "урок", "ошибк", "the turning point", "переломн"],
        "Dreams & Identity": ["мечт", "идентичност", "founders os"],
    },
    Layer.FOUNDER_PROFESSIONAL: {
        "Path to expertise": ["gett", "kupivip", "carprice", "масштаб", "руководил", "$1b", "млрд"],
        "Founder role & motivation": ["мотивац", "роль", "архитект"],
        "Co-founder dynamics": ["темчук", "хартманн", "со-основа", "сооснова"],
    },
    Layer.PRODUCT_BUSINESS: {
        "Architecture of the solution": ["equity pooling", "fund i", "fund ii", "fund iii", "rule 506", "section 3(c)"],
        "Philosophy of decisions": ["philosophy", "founders os", "взаимн", "интерес"],
        "Evolution": ["evolution", "$46m", "$140m", "оценк", "стелс"],
    },
}

_HARD_KEYWORDS = {
    "sanctions": ["sanction", "ofac", "санкц", "embargo"],
    "criminal": ["обвин", "indict", "уголовн", "fraud", "мошенниче"],
    "sec_enforcement": ["sec enforcement", "fcа fine", "fca fine", "регулятор штраф"],
    "data_breach_fine": ["data breach", "gdpr fine", "ico fine", "утечк"],
}

_SOFT_KEYWORDS = {
    "toxic_communication": ["унизил", "угрожал", "культ личности", "оскорбил", "harass"],
    "exec_exodus": ["массовый исход", "ушли все", "увольнен", "exodus"],
    "investor_lawsuit": ["суд от инвесторов", "иск инвесторов", "investor lawsuit"],
    "deadpool_pattern": ["закрыли", "deadpool", "обанкротил"],
}

_GREEN_SIGNALS = [
    "$1b", "$1 b", "млрд", "масштаб", "лидер рынка", "fortune 500",
    "advisory", "founders forum", "wix", "zalando", "регулиру",
    "track record", "довери", "честность", "признаёт", "признаёт ошибк",
    "опыт", "опытом", "ipo", "стелс-режим",
]


class MockClient:
    def classify_fact(self, text: str) -> Tuple[Layer, str, float]:
        t = text.lower()
        best_layer, best_score = Layer.PRODUCT_BUSINESS, 0
        for layer, keys in _LAYER_KEYWORDS.items():
            score = sum(1 for k in keys if k in t)
            if score > best_score:
                best_layer, best_score = layer, score
        subs = _SUBCAT_KEYWORDS.get(best_layer, {})
        best_sub = SUBCATEGORIES[best_layer][0]
        best_sub_score = 0
        for sub, keys in subs.items():
            score = sum(1 for k in keys if k in t)
            if score > best_sub_score:
                best_sub, best_sub_score = sub, score
        confidence = min(0.6 + 0.1 * best_score, 0.95)
        return best_layer, best_sub, confidence

    def synthesize_layer(self, layer: Layer, facts: list[Fact]) -> str:
        from storytelling_bot.schema import LAYER_LABEL
        parts = [f"  · {f.text} [src: {f.source_url}]" for f in facts]
        return f"{LAYER_LABEL[layer]}:\n" + "\n".join(parts) if parts else "(нет данных)"

    def judge_red_flag(self, text: str) -> Optional[Tuple[str, float]]:
        t = text.lower()
        for cat, kws in _HARD_KEYWORDS.items():
            if any(k in t for k in kws):
                return f"hard:{cat}", 0.92
        for cat, kws in _SOFT_KEYWORDS.items():
            if any(k in t for k in kws):
                return f"soft:{cat}", 0.78
        return None

    def classify_green(self, text: str) -> bool:
        t = text.lower()
        return any(s in t for s in _GREEN_SIGNALS)
