"""Add cases and case_transitions tables for workflow state machine.

Revision ID: 0006
Revises: 0005
Create Date: 2026-04-30
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cases",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("goal", sa.Text, nullable=False),
        sa.Column("stage", sa.Text, nullable=False, server_default="draft"),
        sa.Column("entity_query", sa.Text, nullable=True),
        sa.Column("expert_profile_id", sa.BigInteger, sa.ForeignKey("expert_profiles.id"), nullable=True),
        sa.Column("entity_card_ids", sa.ARRAY(sa.BigInteger), nullable=True),
        sa.Column("depth", sa.Text, nullable=True),
        sa.Column("last_report_id", sa.BigInteger, nullable=True),
        sa.Column("monitor_mode", sa.Text, nullable=True),
        sa.Column("created_by", sa.Text, nullable=False),
        sa.Column("confirmed_by", sa.Text, nullable=True),
        sa.Column("metadata", sa.JSON, nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("transitioned_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_table(
        "case_transitions",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("case_id", sa.BigInteger, sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("from_stage", sa.Text, nullable=True),
        sa.Column("to_stage", sa.Text, nullable=False),
        sa.Column("actor", sa.Text, nullable=False),
        sa.Column("rationale", sa.Text, nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("idx_cases_stage", "cases", ["stage"])
    op.create_index("idx_case_transitions_case_id", "case_transitions", ["case_id"])


def downgrade() -> None:
    op.drop_index("idx_case_transitions_case_id")
    op.drop_index("idx_cases_stage")
    op.drop_table("case_transitions")
    op.drop_table("cases")
