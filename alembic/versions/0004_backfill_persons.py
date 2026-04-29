"""Backfill persons table from existing decisions.entity_id rows.

Creates one Person record per unique entity_id found in the decisions table,
using the entity_id as the display_name seed. Risk level is derived from
the most recent recommendation for that entity.

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-29
"""
from __future__ import annotations

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


_RISK_MAP = {
    "terminate": "high_risk",
    "pause": "watch",
    "watch": "watch",
    "continue": "low_risk",
}


def upgrade() -> None:
    conn = op.get_bind()

    rows = conn.execute(sa.text("""
        SELECT DISTINCT ON (entity_id) entity_id, recommendation
        FROM decisions
        ORDER BY entity_id, created_at DESC
    """)).fetchall()

    for row in rows:
        entity_id = row[0]
        recommendation = row[1]
        display_name = entity_id.replace("-", " ").replace("_", " ").title()
        risk_level = _RISK_MAP.get(recommendation, "unknown")

        existing = conn.execute(
            sa.text("SELECT id FROM persons WHERE entity_id = :eid"),
            {"eid": entity_id},
        ).fetchone()
        if existing:
            continue

        conn.execute(
            sa.text("""
                INSERT INTO persons (entity_id, display_name, risk_level)
                VALUES (:eid, :name, :risk)
            """),
            {"eid": entity_id, "name": display_name, "risk": risk_level},
        )


def downgrade() -> None:
    conn = op.get_bind()
    entity_ids = conn.execute(sa.text(
        "SELECT DISTINCT entity_id FROM decisions"
    )).fetchall()
    for row in entity_ids:
        conn.execute(
            sa.text("DELETE FROM persons WHERE entity_id = :eid"),
            {"eid": row[0]},
        )
