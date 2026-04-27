"""InterviewCollector — mock (online_interview). Real impl in Task 5."""
from __future__ import annotations

from typing import Any, Dict, List

from storytelling_bot.collectors.base import DEMO_CORPUS
from storytelling_bot.schema import SourceType


class InterviewCollector:
    source_type = SourceType.ONLINE_INTERVIEW

    def collect(self, entity_id: str) -> List[Dict[str, Any]]:
        corpus = DEMO_CORPUS.get(entity_id, [])
        return [c for c in corpus if c["source_type"] == self.source_type]
