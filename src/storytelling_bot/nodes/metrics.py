"""Metrics node — coverage, freshness, flag counts."""
from __future__ import annotations

import datetime as dt
import logging

from storytelling_bot.schema import SUBCATEGORIES, Flag, State

log = logging.getLogger(__name__)

_TOTAL_SUBCATS = sum(len(v) for v in SUBCATEGORIES.values())


def _median(xs: list[float]) -> float | None:
    if not xs:
        return None
    s = sorted(xs)
    n = len(s)
    return float(s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2)


def node_metrics(state: State) -> dict:
    covered = len({(f.layer, f.subcategory) for f in state.facts})
    now = dt.datetime.now(dt.UTC)
    freshness = [
        (now - (f.captured_at if f.captured_at.tzinfo else f.captured_at.replace(tzinfo=dt.UTC))).days
        for f in state.facts
    ]

    total = len(state.facts)
    kept = sum(1 for s in state.fact_scores if s.keep)
    challenges = sum(1 for s in state.fact_scores if s.challenges_hypothesis)

    metrics = {
        "coverage_pct": round(100 * covered / _TOTAL_SUBCATS, 1),
        "fact_count": total,
        "kept_count": kept,
        "keep_rate": round(kept / total, 3) if total else 0.0,
        "challenges_count": challenges,
        "challenges_per_case": round(challenges / total, 3) if total else 0.0,
        "green_count": sum(1 for f in state.facts if f.flag == Flag.GREEN),
        "red_count": sum(1 for f in state.facts if f.flag == Flag.RED),
        "grey_count": sum(1 for f in state.facts if f.flag == Flag.GREY),
        "freshness_days_p50": _median(freshness),
        "theses_count": len(state.theses),
    }
    log.info("Metrics: %s", metrics)
    return {"metrics": metrics}
