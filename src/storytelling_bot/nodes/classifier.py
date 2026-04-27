"""LayerClassifier node."""
from __future__ import annotations

import datetime as dt
import logging

from storytelling_bot.llm import get_llm_client
from storytelling_bot.schema import Fact, SourceType, State

log = logging.getLogger(__name__)


def node_layer_classifier(state: State) -> dict:
    llm = get_llm_client()
    facts: list[Fact] = []
    for chunk in state.raw_chunks:
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
    log.info("Classified %d facts across %d layers", len(facts), len({f.layer for f in facts}))
    return {"facts": facts}
