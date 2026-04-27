"""ResearchCollector — mock (online_research). Real Tavily/GDELT/SEC impl in Task 4."""
from __future__ import annotations

from typing import Any, Dict, List

from storytelling_bot.collectors.base import DEMO_CORPUS
from storytelling_bot.schema import SourceType


class ResearchCollector:
    source_type = SourceType.ONLINE_RESEARCH

    def collect(self, entity_id: str) -> List[Dict[str, Any]]:
        corpus = DEMO_CORPUS.get(entity_id, [])
        return [c for c in corpus if c["source_type"] == self.source_type]
