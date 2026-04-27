"""Reporter node — serialize Diamond layer to JSON."""
from __future__ import annotations

import datetime as dt
import json
import logging

from storytelling_bot.schema import State

log = logging.getLogger(__name__)


def node_reporter(state: State) -> dict:
    payload = {
        "entity_id": state.entity_id,
        "generated_at": dt.datetime.now(dt.UTC).isoformat(),
        "metrics": state.metrics,
        "decision": state.decision,
        "timeline": state.timeline,
        "story": state.story,
        "facts": [f.to_jsonable() for f in state.facts],
    }
    if state.report_path:
        with open(state.report_path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        log.info("Report saved → %s", state.report_path)
    return {"metrics": {**state.metrics, "_payload": payload}}
