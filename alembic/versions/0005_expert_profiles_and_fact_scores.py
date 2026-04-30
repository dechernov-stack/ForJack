"""Add expert_profiles and fact_scores tables.

Revision ID: 0005
Revises: 0004
Create Date: 2026-04-29
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "expert_profiles",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("entity_id", sa.Text, nullable=False),
        sa.Column("analyst_name", sa.Text, nullable=False),
        sa.Column("role", sa.Text, nullable=False, server_default=""),
        sa.Column("hypothesis", sa.Text, nullable=False, server_default=""),
        sa.Column("profile_json", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )
    op.create_index("ix_expert_profiles_entity_id", "expert_profiles", ["entity_id"])

    op.create_table(
        "fact_scores",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("entity_id", sa.Text, nullable=False),
        sa.Column("run_id", sa.Text, nullable=False, server_default=""),
        sa.Column("fact_idx", sa.Integer, nullable=False),
        sa.Column("relevance", sa.Float, nullable=False),
        sa.Column("narrative_value", sa.Float, nullable=False),
        sa.Column("novelty", sa.Float, nullable=False),
        sa.Column("challenges_hypothesis", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("keep", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("expert_note", sa.Text, nullable=False, server_default=""),
        sa.Column("decision_source", sa.Text, nullable=False, server_default="critic"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )
    op.create_index("ix_fact_scores_entity_id", "fact_scores", ["entity_id"])
    op.create_index("ix_fact_scores_run_id", "fact_scores", ["run_id"])


def downgrade() -> None:
    op.drop_table("fact_scores")
    op.drop_table("expert_profiles")
