"""PostgreSQL persistence via SQLAlchemy 2.0 (Core, no ORM)."""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

_CREATE_FACTS = """
CREATE TABLE IF NOT EXISTS facts (
    id          SERIAL PRIMARY KEY,
    entity_id   TEXT        NOT NULL,
    layer       INTEGER     NOT NULL,
    subcategory TEXT        NOT NULL,
    source_type TEXT        NOT NULL,
    source_url  TEXT        NOT NULL,
    source_hash TEXT,
    text        TEXT        NOT NULL,
    flag        TEXT        NOT NULL DEFAULT 'grey',
    confidence  REAL        NOT NULL DEFAULT 0.5,
    captured_at TIMESTAMPTZ NOT NULL,
    event_date  DATE,
    red_flag_category TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

_CREATE_DECISIONS = """
CREATE TABLE IF NOT EXISTS decisions (
    id          SERIAL PRIMARY KEY,
    entity_id   TEXT        NOT NULL,
    recommendation TEXT     NOT NULL,
    rationale   TEXT,
    human_approval_required BOOLEAN NOT NULL DEFAULT TRUE,
    hard_flag_count INTEGER NOT NULL DEFAULT 0,
    soft_flag_count INTEGER NOT NULL DEFAULT 0,
    green_count INTEGER NOT NULL DEFAULT 0,
    payload     JSONB,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""


class PostgresStore:
    def __init__(self, database_url: Optional[str] = None) -> None:
        self._url = database_url or os.environ.get(
            "DATABASE_URL", "postgresql://storyteller:storyteller@localhost:5432/storyteller"
        )
        self._engine = None

    def _get_engine(self):
        if self._engine is None:
            from sqlalchemy import create_engine, text  # noqa: PLC0415
            self._engine = create_engine(self._url, pool_pre_ping=True)
            with self._engine.connect() as conn:
                conn.execute(text(_CREATE_FACTS))
                conn.execute(text(_CREATE_DECISIONS))
                conn.commit()
        return self._engine

    def save_facts(self, facts: list) -> None:
        from sqlalchemy import text  # noqa: PLC0415
        engine = self._get_engine()
        rows = []
        for f in facts:
            d = f.to_jsonable() if hasattr(f, "to_jsonable") else f
            rows.append({
                "entity_id": d.get("entity_id", ""),
                "layer": int(d.get("layer", 1)),
                "subcategory": d.get("subcategory", ""),
                "source_type": d.get("source_type", ""),
                "source_url": d.get("source_url", ""),
                "source_hash": d.get("source_hash"),
                "text": d.get("text", ""),
                "flag": d.get("flag", "grey"),
                "confidence": float(d.get("confidence", 0.5)),
                "captured_at": d.get("captured_at", datetime.now(timezone.utc).isoformat()),
                "event_date": d.get("event_date"),
                "red_flag_category": d.get("red_flag_category"),
            })
        if not rows:
            return
        with engine.connect() as conn:
            conn.execute(
                text("""
                    INSERT INTO facts
                        (entity_id, layer, subcategory, source_type, source_url,
                         source_hash, text, flag, confidence, captured_at, event_date,
                         red_flag_category)
                    VALUES
                        (:entity_id, :layer, :subcategory, :source_type, :source_url,
                         :source_hash, :text, :flag, :confidence, :captured_at, :event_date,
                         :red_flag_category)
                    ON CONFLICT DO NOTHING
                """),
                rows,
            )
            conn.commit()
        log.info("PostgresStore: saved %d facts", len(rows))

    def save_decision(self, entity_id: str, decision: Dict[str, Any]) -> None:
        from sqlalchemy import text  # noqa: PLC0415
        engine = self._get_engine()
        with engine.connect() as conn:
            conn.execute(
                text("""
                    INSERT INTO decisions
                        (entity_id, recommendation, rationale, human_approval_required,
                         hard_flag_count, soft_flag_count, green_count, payload)
                    VALUES
                        (:entity_id, :recommendation, :rationale, :human_approval_required,
                         :hard_flag_count, :soft_flag_count, :green_count, :payload)
                """),
                {
                    "entity_id": entity_id,
                    "recommendation": decision.get("recommendation", "continue"),
                    "rationale": decision.get("rationale", ""),
                    "human_approval_required": bool(decision.get("human_approval_required", True)),
                    "hard_flag_count": int(decision.get("hard_flag_count", 0)),
                    "soft_flag_count": int(decision.get("soft_flag_count", 0)),
                    "green_count": int(decision.get("green_count", 0)),
                    "payload": json.dumps(decision, default=str),
                },
            )
            conn.commit()
        log.info("PostgresStore: saved decision for %s", entity_id)

    def load_facts(self, entity_id: str) -> List[Dict[str, Any]]:
        from sqlalchemy import text  # noqa: PLC0415
        engine = self._get_engine()
        with engine.connect() as conn:
            result = conn.execute(
                text("SELECT * FROM facts WHERE entity_id = :eid ORDER BY captured_at"),
                {"eid": entity_id},
            )
            return [dict(row._mapping) for row in result]
