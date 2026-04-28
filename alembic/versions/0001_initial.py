"""Initial schema: facts and decisions tables.

Revision ID: 0001
Revises:
Create Date: 2026-04-28
"""
from __future__ import annotations

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade() -> None:
    op.create_table(
        "facts",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("entity_id", sa.Text, nullable=False),
        sa.Column("layer", sa.Integer, nullable=False),
        sa.Column("subcategory", sa.Text, nullable=False),
        sa.Column("source_type", sa.Text, nullable=False),
        sa.Column("source_url", sa.Text, nullable=False),
        sa.Column("source_hash", sa.Text),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("flag", sa.Text, nullable=False, server_default="grey"),
        sa.Column("confidence", sa.Float, nullable=False, server_default="0.5"),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("event_date", sa.Date),
        sa.Column("red_flag_category", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )

    op.create_table(
        "decisions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("entity_id", sa.Text, nullable=False),
        sa.Column("recommendation", sa.Text, nullable=False),
        sa.Column("rationale", sa.Text),
        sa.Column("human_approval_required", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("hard_flag_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("soft_flag_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("green_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("payload", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )


def downgrade() -> None:
    op.drop_table("decisions")
    op.drop_table("facts")
