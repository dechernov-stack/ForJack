"""PostgreSQL store — implemented in Task 8."""
from __future__ import annotations


class PostgresStore:
    """Stub — full SQLAlchemy + Alembic implementation in Task 8."""

    def __init__(self, database_url: str) -> None:
        self._url = database_url

    def save_facts(self, facts: list) -> None:
        raise NotImplementedError("Implement in Task 8")

    def save_decision(self, decision: dict) -> None:
        raise NotImplementedError("Implement in Task 8")
