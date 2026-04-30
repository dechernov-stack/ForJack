"""QuoteDecomposer: transcript chunk → list[Fact] with layer/subcat/timestamp/tone."""
from __future__ import annotations

import datetime as dt
import json
import logging
import re
from typing import Any

from storytelling_bot.schema import Fact, Flag, Layer, SourceType

log = logging.getLogger(__name__)

_TONE_VALUES = ("рассказывает", "признаётся", "уворачивается", "противоречит", "отчитывается")

_LAYER_KEYWORDS: dict[Layer, list[str]] = {
    Layer.FOUNDER_PERSONAL: ["детство", "семья", "личн", "страх", "мечт", "ценност", "происхождение"],
    Layer.FOUNDER_PROFESSIONAL: ["карьера", "опыт", "роль", "основатель", "навык", "экспертиза"],
    Layer.COMMUNITY_CULTURE: ["команда", "культура", "партнёр", "инвестор", "ценности компании"],
    Layer.COMMUNITY_PRO_EXPERIENCE: ["сотрудник", "найм", "рост", "трансформация", "провал команды"],
    Layer.CLIENTS_STORIES: ["клиент", "пользователь", "кейс", "история клиента", "доверие"],
    Layer.PRODUCT_BUSINESS: ["продукт", "бизнес", "архитектура", "стратегия", "выручка", "метрик"],
    Layer.SOCIAL_IMPACT: ["импакт", "изменение", "наследие", "общество", "противоречие", "цена"],
    Layer.PEST_CONTEXT: ["рынок", "регулятор", "закон", "технология", "политика", "экономик"],
}


def _heuristic_layer(text: str) -> Layer:
    text_lower = text.lower()
    scores: dict[Layer, int] = {}
    for layer, keywords in _LAYER_KEYWORDS.items():
        scores[layer] = sum(1 for kw in keywords if kw in text_lower)
    return max(scores, key=lambda la: scores[la], default=Layer.FOUNDER_PROFESSIONAL)


def _parse_llm_quotes(raw: str, source_url: str, chunk_id: int) -> list[dict[str, Any]]:
    """Parse JSON list from LLM output; return list of quote dicts."""
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and "quotes" in data:
            return data["quotes"]
    except (json.JSONDecodeError, TypeError):
        pass
    return []


def decompose_chunk(
    chunk: str,
    *,
    chunk_id: int = 0,
    source_url: str = "",
    event_date: str = "",
    entity_name: str = "",
    llm_client=None,
    expert_profile=None,
) -> list[Fact]:
    """Decompose one transcript chunk into Fact objects.

    Uses heuristic layer assignment (no LLM) when llm_client is None.
    """
    sentences = [s.strip() for s in re.split(r"[.!?]\s+", chunk) if len(s.strip()) > 20]
    if not sentences:
        return []

    facts = []
    for i, sentence in enumerate(sentences):
        layer = _heuristic_layer(sentence)

        from storytelling_bot.schema import SUBCATEGORIES
        subcats = SUBCATEGORIES.get(layer, ("",))
        sub = subcats[0]

        facts.append(Fact(
            entity_id=entity_name or "unknown",
            text=sentence[:500],
            source_url=f"{source_url}#chunk={chunk_id}&sent={i}",
            source_type=SourceType.ONLINE_INTERVIEW,
            layer=layer,
            subcategory=sub,
            flag=Flag.GREY,
            captured_at=dt.datetime.fromisoformat(event_date) if event_date else dt.datetime.now(dt.UTC),
            metadata={
                "tone": "рассказывает",
                "chunk_id": chunk_id,
                "layer_secondary": [],
            },
        ))
    return facts


def decompose_transcript(
    transcript: str,
    *,
    source_url: str = "",
    event_date: str = "",
    entity_name: str = "",
    chunk_size: int = 800,
    llm_client=None,
    expert_profile=None,
) -> list[Fact]:
    """Split transcript into chunks and decompose each into Facts."""
    words = transcript.split()
    chunks = []
    buf: list[str] = []
    for word in words:
        buf.append(word)
        if len(" ".join(buf)) >= chunk_size:
            chunks.append(" ".join(buf))
            buf = []
    if buf:
        chunks.append(" ".join(buf))

    facts: list[Fact] = []
    for chunk_id, chunk in enumerate(chunks):
        chunk_facts = decompose_chunk(
            chunk,
            chunk_id=chunk_id,
            source_url=source_url,
            event_date=event_date,
            entity_name=entity_name,
            llm_client=llm_client,
            expert_profile=expert_profile,
        )
        facts.extend(chunk_facts)
        log.info("QuoteDecomposer: chunk %d → %d facts", chunk_id, len(chunk_facts))

    return facts
