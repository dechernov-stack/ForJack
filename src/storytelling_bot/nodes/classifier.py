"""LayerClassifier node."""
from __future__ import annotations

import datetime as dt
import logging

from storytelling_bot.llm import get_llm_client
from storytelling_bot.schema import Fact, SourceType, State
from storytelling_bot.storage.vector_store import VectorStore

log = logging.getLogger(__name__)

_DEDUP_COSINE_THRESHOLD = 0.92


def node_layer_classifier(state: State) -> dict:
    llm = get_llm_client()
    facts: list[Fact] = []
    skipped = 0
    for chunk in state.raw_chunks:
        if chunk.get("_layer_hint") is not None:
            try:
                from storytelling_bot.schema import SUBCATEGORIES
                from storytelling_bot.schema import Layer as _Layer
                layer = _Layer(int(chunk["_layer_hint"]))
                sub = chunk.get("_subcategory_hint") or SUBCATEGORIES[layer][0]
                conf = 0.9
            except (ValueError, KeyError):
                layer, sub, conf = llm.classify_fact(chunk["text"])
        else:
            layer, sub, conf = llm.classify_fact(chunk["text"])
        event_date = None
        if chunk.get("event_date"):
            event_date = dt.date.fromisoformat(chunk["event_date"])
        source_type = chunk["source_type"]
        if not isinstance(source_type, SourceType):
            source_type = SourceType(source_type)
        captured_at = chunk["captured_at"]
        if isinstance(captured_at, str):
            if len(captured_at) == 10:
                captured_at = dt.datetime.fromisoformat(captured_at + "T00:00:00")
            else:
                captured_at = dt.datetime.fromisoformat(captured_at)

        if _is_near_duplicate(chunk["text"], state.entity_id, llm):
            skipped += 1
            continue

        facts.append(Fact(
            entity_id=chunk.get("entity_focus", state.entity_id),
            layer=layer,
            subcategory=sub,
            source_type=source_type,
            text=chunk["text"][:500],
            source_url=chunk["url"],
            captured_at=captured_at,
            confidence=conf,
            event_date=event_date,
        ))

    log.info(
        "Classified %d facts across %d layers (%d near-duplicates skipped)",
        len(facts), len({f.layer for f in facts}), skipped,
    )
    return {"facts": facts}


def _is_near_duplicate(text: str, entity_id: str, llm) -> bool:
    """Check Qdrant for semantically similar facts from previous runs."""
    try:
        vs = VectorStore()
        vectors = llm.embed([text])
        results = vs.search_with_filter(
            vectors[0], entity_id=entity_id, limit=5, min_score=_DEDUP_COSINE_THRESHOLD
        )
        return len(results) > 0
    except Exception:
        return False
