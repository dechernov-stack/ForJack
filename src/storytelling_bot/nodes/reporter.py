"""Reporter node — serialize Diamond layer to JSON and persist to storage."""
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

    _persist(state)

    return {"metrics": {**state.metrics, "_payload": payload}}


def _persist(state: State) -> None:
    """Write facts + decision atomically to Postgres; best-effort, never fails the pipeline."""
    try:
        from storytelling_bot import langfuse_ctx
        from storytelling_bot.storage.postgres import PostgresStore
        store = PostgresStore()
        with langfuse_ctx.span(
            "storage.postgres.upsert_facts",
            input_data={"entity_id": state.entity_id, "fact_count": len(state.facts)},
        ):
            store.persist_run(state.facts, state.entity_id, state.decision)
        if state.person_meta:
            store.upsert_person(state.entity_id, state.person_meta)
    except Exception:
        log.exception("PostgresStore persistence failed (pipeline continues)")
