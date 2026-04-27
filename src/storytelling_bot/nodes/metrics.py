"""Metrics node — coverage, freshness, flag counts."""
from __future__ import annotations

import datetime as dt
import logging
from typing import List, Optional

from storytelling_bot.schema import Flag, SUBCATEGORIES, State

log = logging.getLogger(__name__)

_TOTAL_SUBCATS = sum(len(v) for v in SUBCATEGORIES.values())


def _median(xs: List[float]) -> Optional[float]:
    if not xs:
        return None
    s = sorted(xs)
    n = len(s)
    return float(s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2)


def node_metrics(state: State) -> dict:
    covered = len({(f.layer, f.subcategory) for f in state.facts})
    now = dt.datetime.now(dt.UTC)
    freshness = [
        (now - (f.captured_at if f.captured_at.tzinfo else f.captured_at.replace(tzinfo=dt.timezone.utc))).days
        for f in state.facts
    ]
    metrics = {
        "coverage_pct": round(100 * covered / _TOTAL_SUBCATS, 1),
        "fact_count": len(state.facts),
        "green_count": sum(1 for f in state.facts if f.flag == Flag.GREEN),
        "red_count": sum(1 for f in state.facts if f.flag == Flag.RED),
        "grey_count": sum(1 for f in state.facts if f.flag == Flag.GREY),
        "freshness_days_p50": _median(freshness),
    }
    log.info("Metrics: %s", metrics)
    return {"metrics": metrics}
