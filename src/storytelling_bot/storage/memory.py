"""In-memory store for tests and local dev."""
from __future__ import annotations

from typing import Any


class MemoryStore:
    def __init__(self) -> None:
        self._facts: list[dict[str, Any]] = []
        self._decisions: list[dict[str, Any]] = []

    def save_facts(self, facts: list[dict[str, Any]]) -> None:
        keys = {(f["source_url"], f["text"]) for f in self._facts}
        for f in facts:
            if (f["source_url"], f["text"]) not in keys:
                self._facts.append(f)
                keys.add((f["source_url"], f["text"]))

    def save_decision(self, decision: dict[str, Any]) -> None:
        self._decisions.append(decision)

    def get_facts(self, entity_id: str) -> list[dict[str, Any]]:
        return [f for f in self._facts if f.get("entity_id") == entity_id]

    def clear(self) -> None:
        self._facts.clear()
        self._decisions.clear()
