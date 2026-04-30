"""PostgreSQL persistence via SQLAlchemy 2.0 (Core, no ORM)."""
from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from typing import Any

log = logging.getLogger(__name__)

# DDL strings kept for SQLite-based unit tests that bypass Alembic.
_CREATE_FACTS_SQLITE = """
CREATE TABLE IF NOT EXISTS facts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_id   TEXT        NOT NULL,
    layer       INTEGER     NOT NULL,
    subcategory TEXT        NOT NULL,
    source_type TEXT        NOT NULL,
    source_url  TEXT        NOT NULL,
    source_hash TEXT,
    text        TEXT        NOT NULL,
    flag        TEXT        NOT NULL DEFAULT 'grey',
    confidence  REAL        NOT NULL DEFAULT 0.5,
    captured_at TEXT        NOT NULL,
    event_date  TEXT,
    red_flag_category TEXT,
    created_at  TEXT        DEFAULT (datetime('now'))
)
"""

_CREATE_DECISIONS_SQLITE = """
CREATE TABLE IF NOT EXISTS decisions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_id   TEXT        NOT NULL,
    recommendation TEXT     NOT NULL,
    rationale   TEXT,
    human_approval_required INTEGER NOT NULL DEFAULT 1,
    hard_flag_count INTEGER NOT NULL DEFAULT 0,
    soft_flag_count INTEGER NOT NULL DEFAULT 0,
    green_count INTEGER NOT NULL DEFAULT 0,
    payload     TEXT,
    created_at  TEXT DEFAULT (datetime('now'))
)
"""

_CREATE_FACTS_UNIQUE_SQLITE = (
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_facts_key "
    "ON facts (entity_id, layer, subcategory, source_url)"
)


class PostgresStore:
    def __init__(self, database_url: str | None = None) -> None:
        self._url = database_url or os.environ.get(
            "DATABASE_URL", "postgresql://storyteller:storyteller@localhost:5432/storyteller"
        )
        self._engine = None

    def _get_engine(self):
        if self._engine is None:
            from sqlalchemy import create_engine
            self._engine = create_engine(self._url, pool_pre_ping=True)
        return self._engine

    def _setup_sqlite(self) -> None:
        """Create tables + unique index for in-memory SQLite (tests only)."""
        from sqlalchemy import text
        engine = self._get_engine()
        with engine.connect() as conn:
            conn.execute(text(_CREATE_FACTS_SQLITE))
            conn.execute(text(_CREATE_DECISIONS_SQLITE))
            conn.execute(text(_CREATE_FACTS_UNIQUE_SQLITE))
            conn.commit()

    def upsert_facts(self, facts: list) -> None:
        """Insert facts; on duplicate key update confidence if new value is higher."""
        from sqlalchemy import text
        engine = self._get_engine()
        rows = [_fact_to_row(f) for f in facts]
        if not rows:
            return

        is_sqlite = "sqlite" in self._url
        if is_sqlite:
            stmt = text("""
                INSERT INTO facts
                    (entity_id, layer, subcategory, source_type, source_url,
                     source_hash, text, flag, confidence, captured_at, event_date,
                     red_flag_category)
                VALUES
                    (:entity_id, :layer, :subcategory, :source_type, :source_url,
                     :source_hash, :text, :flag, :confidence, :captured_at, :event_date,
                     :red_flag_category)
                ON CONFLICT(entity_id, layer, subcategory, source_url)
                DO UPDATE SET confidence = excluded.confidence
                WHERE excluded.confidence > facts.confidence
            """)
        else:
            stmt = text("""
                INSERT INTO facts
                    (entity_id, layer, subcategory, source_type, source_url,
                     source_hash, text, flag, confidence, captured_at, event_date,
                     red_flag_category)
                VALUES
                    (:entity_id, :layer, :subcategory, :source_type, :source_url,
                     :source_hash, :text, :flag, :confidence, :captured_at, :event_date,
                     :red_flag_category)
                ON CONFLICT (entity_id, layer, subcategory, source_url)
                DO UPDATE SET confidence = EXCLUDED.confidence
                WHERE EXCLUDED.confidence > facts.confidence
            """)

        with engine.begin() as conn:
            conn.execute(stmt, rows)
        log.info("PostgresStore: upserted %d facts", len(rows))

    def upsert_decision(self, entity_id: str, decision: dict[str, Any]) -> None:
        """Append a new decision row (decisions are an append-only audit log)."""
        from sqlalchemy import text
        engine = self._get_engine()
        with engine.begin() as conn:
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
        log.info("PostgresStore: saved decision for %s", entity_id)

    # ── backward-compat aliases ───────────────────────────────────────────────

    def save_facts(self, facts: list) -> None:
        self.upsert_facts(facts)

    def save_decision(self, entity_id: str, decision: dict[str, Any]) -> None:
        self.upsert_decision(entity_id, decision)

    # ── reads ─────────────────────────────────────────────────────────────────

    def load_facts(self, entity_id: str) -> list[dict[str, Any]]:
        from sqlalchemy import text
        engine = self._get_engine()
        with engine.connect() as conn:
            result = conn.execute(
                text("SELECT * FROM facts WHERE entity_id = :eid ORDER BY captured_at"),
                {"eid": entity_id},
            )
            return [dict(row._mapping) for row in result]

    def load_latest_decision(self, entity_id: str) -> dict[str, Any] | None:
        from sqlalchemy import text
        engine = self._get_engine()
        with engine.connect() as conn:
            row = conn.execute(
                text("""
                    SELECT recommendation, rationale, hard_flag_count,
                           soft_flag_count, green_count, created_at
                    FROM decisions WHERE entity_id = :eid
                    ORDER BY created_at DESC LIMIT 1
                """),
                {"eid": entity_id},
            ).fetchone()
        if row is None:
            return None
        return dict(row._mapping)

    def upsert_person(self, entity_id: str, meta: dict[str, Any]) -> None:
        if not meta or not meta.get("display_name"):
            return
        from sqlalchemy import text
        import datetime as dt
        display_name = meta["display_name"]
        birth_date_str = meta.get("birth_date")
        birth_date = None
        if birth_date_str:
            try:
                birth_date = dt.date.fromisoformat(str(birth_date_str)[:10])
            except ValueError:
                pass
        nationalities = json.dumps(meta.get("nationalities", []))
        risk_level = meta.get("risk_level", "unknown")
        engine = self._get_engine()
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO persons (entity_id, display_name, birth_date, nationalities, risk_level)
                VALUES (:entity_id, :display_name, :birth_date, :nationalities, :risk_level)
                ON CONFLICT (entity_id) DO UPDATE SET
                    display_name = EXCLUDED.display_name,
                    birth_date = COALESCE(EXCLUDED.birth_date, persons.birth_date),
                    nationalities = EXCLUDED.nationalities,
                    risk_level = EXCLUDED.risk_level,
                    updated_at = NOW()
            """), {
                "entity_id": entity_id, "display_name": display_name,
                "birth_date": birth_date, "nationalities": nationalities,
                "risk_level": risk_level,
            })
            person_id = conn.execute(
                text("SELECT id FROM persons WHERE entity_id = :eid"), {"eid": entity_id}
            ).fetchone()[0]
            conn.execute(
                text("DELETE FROM person_company_role WHERE person_id = :pid"), {"pid": person_id}
            )
            for r in meta.get("roles", []):
                start_year = r.get("start_year")
                start_date = dt.date(int(start_year), 1, 1) if start_year else None
                conn.execute(text("""
                    INSERT INTO person_company_role
                        (person_id, entity_id, company_name, role, start_date, is_current)
                    VALUES (:person_id, :entity_id, :company_name, :role, :start_date, :is_current)
                """), {
                    "person_id": person_id, "entity_id": entity_id,
                    "company_name": r.get("company", ""), "role": r.get("title", ""),
                    "start_date": start_date, "is_current": bool(r.get("is_current", True)),
                })
        log.info("PostgresStore: upserted person %s", entity_id)

    def load_person(self, entity_id: str) -> dict[str, Any] | None:
        from sqlalchemy import text
        engine = self._get_engine()
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT * FROM persons WHERE entity_id = :eid"), {"eid": entity_id}
            ).fetchone()
            if row is None:
                return None
            person = dict(row._mapping)
            roles = conn.execute(
                text("SELECT * FROM person_company_role WHERE person_id = :pid ORDER BY start_date"),
                {"pid": person["id"]},
            ).fetchall()
            person["roles"] = [dict(r._mapping) for r in roles]
        return person

    def count_facts(self, entity_id: str) -> int:
        from sqlalchemy import text
        engine = self._get_engine()
        with engine.connect() as conn:
            result = conn.execute(
                text("SELECT COUNT(*) FROM facts WHERE entity_id = :eid"),
                {"eid": entity_id},
            )
            return result.scalar() or 0

    def persist_run(self, facts: list, entity_id: str, decision: dict[str, Any]) -> None:
        """Persist facts + decision atomically in a single transaction."""
        from sqlalchemy import text
        engine = self._get_engine()
        rows = [_fact_to_row(f) for f in facts]
        is_sqlite = "sqlite" in self._url

        if is_sqlite:
            conflict_stmt = text("""
                INSERT INTO facts
                    (entity_id, layer, subcategory, source_type, source_url,
                     source_hash, text, flag, confidence, captured_at, event_date,
                     red_flag_category)
                VALUES
                    (:entity_id, :layer, :subcategory, :source_type, :source_url,
                     :source_hash, :text, :flag, :confidence, :captured_at, :event_date,
                     :red_flag_category)
                ON CONFLICT(entity_id, layer, subcategory, source_url)
                DO UPDATE SET confidence = excluded.confidence
                WHERE excluded.confidence > facts.confidence
            """)
        else:
            conflict_stmt = text("""
                INSERT INTO facts
                    (entity_id, layer, subcategory, source_type, source_url,
                     source_hash, text, flag, confidence, captured_at, event_date,
                     red_flag_category)
                VALUES
                    (:entity_id, :layer, :subcategory, :source_type, :source_url,
                     :source_hash, :text, :flag, :confidence, :captured_at, :event_date,
                     :red_flag_category)
                ON CONFLICT (entity_id, layer, subcategory, source_url)
                DO UPDATE SET confidence = EXCLUDED.confidence
                WHERE EXCLUDED.confidence > facts.confidence
            """)

        with engine.begin() as conn:
            if rows:
                conn.execute(conflict_stmt, rows)
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
        log.info("PostgresStore: persisted %d facts + decision for %s", len(rows), entity_id)


def _fact_to_row(f: Any) -> dict[str, Any]:
    d = f.to_jsonable() if hasattr(f, "to_jsonable") else f
    return {
        "entity_id": d.get("entity_id", ""),
        "layer": int(d.get("layer", 1)),
        "subcategory": d.get("subcategory", ""),
        "source_type": d.get("source_type", ""),
        "source_url": d.get("source_url", ""),
        "source_hash": d.get("source_hash"),
        "text": d.get("text", ""),
        "flag": d.get("flag", "grey"),
        "confidence": float(d.get("confidence", 0.5)),
        "captured_at": d.get("captured_at", datetime.now(UTC).isoformat()),
        "event_date": d.get("event_date"),
        "red_flag_category": d.get("red_flag_category"),
    }
