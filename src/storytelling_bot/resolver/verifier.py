"""Tavily-based verification of EntityCard anchors."""
from __future__ import annotations

import logging
import os
import re
from typing import Any

from storytelling_bot.schema import EntityCard

_NEG_PREFIX = re.compile(r"^(не путать\s*:?\s*с?\s*|don.t confuse\s*:?\s*)", re.IGNORECASE)

log = logging.getLogger(__name__)


def verify_with_tavily(card: EntityCard, max_queries: int = 2) -> dict[str, Any]:
    """Search canonical_name + top anchors; downgrade consensus_score if namesake dominates."""
    api_key = os.environ.get("TAVILY_API_KEY")
    if not api_key:
        return {"skipped": True, "reason": "TAVILY_API_KEY not set"}
    try:
        import requests
    except ImportError:
        return {"skipped": True, "reason": "pip install requests"}

    queries = [card.canonical_name]
    for a in card.anchors[:2]:
        queries.append(f"{card.canonical_name} {a.value}")

    results = []
    namesake_hit = False
    for q in queries[:max_queries]:
        try:
            r = requests.post(
                "https://api.tavily.com/search",
                json={"api_key": api_key, "query": q, "max_results": 5},
                timeout=30,
            )
            hits = []
            if r.ok:
                for h in r.json().get("results", []):
                    title = h.get("title", "").lower()
                    url = h.get("url", "")
                    neg_terms = [_NEG_PREFIX.sub("", n).strip().lower() for n in card.negatives]
                    if any(term and term in title for term in neg_terms):
                        namesake_hit = True
                    hits.append({"title": h.get("title", ""), "url": url})
            results.append({"query": q, "hits": hits})
        except Exception as exc:
            results.append({"query": q, "error": str(exc)})

    verdict: dict[str, Any] = {"queries": results}
    if namesake_hit:
        log.warning("Tavily: namesake dominates SERP for '%s' — downgrading consensus", card.canonical_name)
        card.consensus_score = round(card.consensus_score * 0.7, 3)
        card.raw_provider_answers["__tavily_verdict__"] = "namesake-dominated"
        verdict["namesake_dominated"] = True

    return verdict
