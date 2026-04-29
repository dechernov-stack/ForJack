"""Persons, name variants, identifying IDs, roles and connections tables.

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-29
"""
from __future__ import annotations

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade() -> None:
    op.create_table(
        "persons",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("entity_id", sa.Text, nullable=False, unique=True),
        sa.Column("display_name", sa.Text, nullable=False),
        sa.Column("birth_date", sa.Date, nullable=True),
        sa.Column("nationalities", sa.Text, nullable=False, server_default="[]"),
        sa.Column("photo_url", sa.Text, nullable=True),
        sa.Column("risk_level", sa.Text, nullable=False, server_default="unknown"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )

    op.create_table(
        "name_variants",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("person_id", sa.Integer, sa.ForeignKey("persons.id", ondelete="CASCADE"), nullable=False),
        sa.Column("variant", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )
    op.create_index("uq_name_variants", "name_variants", ["person_id", "variant"], unique=True)

    op.create_table(
        "identifying_ids",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("person_id", sa.Integer, sa.ForeignKey("persons.id", ondelete="CASCADE"), nullable=False),
        sa.Column("id_type", sa.Text, nullable=False),
        sa.Column("id_value", sa.Text, nullable=False),
        sa.Column("issuing_country", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )
    op.create_index("uq_identifying_ids", "identifying_ids", ["person_id", "id_type", "id_value"], unique=True)

    op.create_table(
        "person_company_role",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("person_id", sa.Integer, sa.ForeignKey("persons.id", ondelete="CASCADE"), nullable=False),
        sa.Column("entity_id", sa.Text, nullable=False),
        sa.Column("company_name", sa.Text, nullable=False),
        sa.Column("role", sa.Text, nullable=False),
        sa.Column("start_date", sa.Date, nullable=True),
        sa.Column("end_date", sa.Date, nullable=True),
        sa.Column("is_current", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("source_fact_id", sa.Integer, sa.ForeignKey("facts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )
    op.create_index("idx_person_company_role_person", "person_company_role", ["person_id"])
    op.create_index("idx_person_company_role_entity", "person_company_role", ["entity_id"])

    op.create_table(
        "connections",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("person_id_a", sa.Integer, sa.ForeignKey("persons.id", ondelete="CASCADE"), nullable=False),
        sa.Column("person_id_b", sa.Integer, sa.ForeignKey("persons.id", ondelete="SET NULL"), nullable=True),
        sa.Column("entity_id_b", sa.Text, nullable=True),
        sa.Column("relation_type", sa.Text, nullable=False),
        sa.Column("strength", sa.Float, nullable=False, server_default="0.5"),
        sa.Column("source_fact_id", sa.Integer, sa.ForeignKey("facts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )
    op.create_index("idx_connections_a", "connections", ["person_id_a"])
    op.create_index("idx_connections_b", "connections", ["person_id_b"])


def downgrade() -> None:
    op.drop_table("connections")
    op.drop_table("person_company_role")
    op.drop_table("identifying_ids")
    op.drop_table("name_variants")
    op.drop_table("persons")
