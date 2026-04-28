"""Unique index on facts(entity_id, layer, subcategory, source_url) + data dedup.

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-28
"""
from __future__ import annotations

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade() -> None:
    # Remove duplicate rows, keeping the one with highest confidence per unique key.
    op.execute("""
        DELETE FROM facts
        WHERE id NOT IN (
            SELECT DISTINCT ON (entity_id, layer, subcategory, source_url) id
            FROM facts
            ORDER BY entity_id, layer, subcategory, source_url, confidence DESC
        )
    """)

    op.create_index(
        "uq_facts_key",
        "facts",
        ["entity_id", "layer", "subcategory", "source_url"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_facts_key", table_name="facts")
