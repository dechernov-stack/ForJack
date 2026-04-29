"""TimelineBuilder node."""
from __future__ import annotations

import logging
from typing import Any

from storytelling_bot.schema import LAYER_LABEL, State

log = logging.getLogger(__name__)


def node_timeline_builder(state: State) -> dict:
    events: list[dict[str, Any]] = []
    for f in state.facts:
        if f.event_date:
            events.append({
                "date": f.event_date.isoformat(),
                "entity": f.entity_id,
                "layer": LAYER_LABEL[f.layer],
                "text": f.text,
                "source": f.source_url,
            })
    events.sort(key=lambda e: e["date"])
    log.info("Timeline: %d datable events", len(events))
    return {"timeline": events}
