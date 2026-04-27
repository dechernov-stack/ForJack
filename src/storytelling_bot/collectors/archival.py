"""ArchivalCollector — mock (archival). Real Wayback Machine impl in Task 6."""
from __future__ import annotations

from typing import Any, Dict, List

from storytelling_bot.collectors.base import DEMO_CORPUS
from storytelling_bot.schema import SourceType


class ArchivalCollector:
    source_type = SourceType.ARCHIVAL

    def collect(self, entity_id: str) -> List[Dict[str, Any]]:
        corpus = DEMO_CORPUS.get(entity_id, [])
        return [c for c in corpus if c["source_type"] == self.source_type]
