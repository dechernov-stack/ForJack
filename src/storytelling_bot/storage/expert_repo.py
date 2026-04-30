"""Persistence helpers for ExpertProfile and FactScore records."""
from __future__ import annotations

import json
import logging
import uuid

from sqlalchemy import text

from storytelling_bot.schema import ExpertProfile, State

log = logging.getLogger(__name__)


def save_profile(store, entity_id: str, profile: ExpertProfile) -> None:
    """Insert ExpertProfile JSON into expert_profiles table."""
    try:
        with store._engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO expert_profiles "
                    "(entity_id, analyst_name, role, hypothesis, profile_json) "
                    "VALUES (:eid, :name, :role, :hyp, :json)"
                ),
                {
                    "eid": entity_id,
                    "name": profile.analyst_name,
                    "role": profile.role,
                    "hyp": profile.hypothesis,
                    "json": json.dumps(profile.to_jsonable(), ensure_ascii=False),
                },
            )
        log.info("Saved expert profile for %s", entity_id)
    except Exception as exc:
        log.warning("Could not save expert profile: %s", exc)


def save_scores(store, state: State, run_id: str | None = None) -> None:
    """Batch-insert FactScore records for this pipeline run."""
    if not state.fact_scores:
        return
    run_id = run_id or str(uuid.uuid4())
    rows = [
        {
            "entity_id": state.entity_id,
            "run_id": run_id,
            "fact_idx": s.fact_idx,
            "relevance": s.relevance,
            "narrative_value": s.narrative_value,
            "novelty": s.novelty,
            "challenges_hypothesis": s.challenges_hypothesis,
            "keep": s.keep,
            "expert_note": s.expert_note,
            "decision_source": s.decision_source,
        }
        for s in state.fact_scores
    ]
    try:
        with store._engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO fact_scores "
                    "(entity_id, run_id, fact_idx, relevance, narrative_value, novelty, "
                    "challenges_hypothesis, keep, expert_note, decision_source) "
                    "VALUES (:entity_id, :run_id, :fact_idx, :relevance, :narrative_value, :novelty, "
                    ":challenges_hypothesis, :keep, :expert_note, :decision_source)"
                ),
                rows,
            )
        log.info("Saved %d fact scores for %s run=%s", len(rows), state.entity_id, run_id)
    except Exception as exc:
        log.warning("Could not save fact scores: %s", exc)
