"""Deterministic sanctions checking: OpenSanctions API + OFAC keyword rules.

Hard flag logic (conf ≥ 0.85):
  - OpenSanctions match with score ≥ 0.7  → hard:sanctions
  - OFAC SDN keyword pattern in text       → hard:sanctions
  - Criminal indictment keyword pattern    → hard:criminal
  - SEC/FCA enforcement keyword pattern    → hard:sec_enforcement
  - Confirmed fraud pattern               → hard:fraud
"""
from __future__ import annotations

import logging
import os
import re
from typing import Optional, Tuple

import httpx

log = logging.getLogger(__name__)

_OPENSANCTIONS_API = "https://api.opensanctions.org"
_REQUEST_TIMEOUT = 10


# ── OFAC/Sanctions keyword patterns (deterministic) ──────────────────────────

_HARD_PATTERNS: list[Tuple[str, str, float]] = [
    # (regex, flag_category, confidence)
    (
        r"\b(OFAC|SDN list|sanctioned|sanctions list|treasury sanctions|EU sanctions|UN sanctions|UK sanctions)\b",
        "hard:sanctions",
        0.90,
    ),
    (
        r"\b(criminal indictment|indicted for|convicted of|criminal conviction|felony conviction)\b",
        "hard:criminal",
        0.90,
    ),
    (
        r"\b(SEC enforcement|FCA enforcement|regulatory fine|SEC fraud charge|securities fraud charge)\b",
        "hard:sec_enforcement",
        0.88,
    ),
    (
        r"\b(confirmed fraud|Ponzi scheme|fictitious bankruptcy|fraudulent scheme)\b",
        "hard:fraud",
        0.92,
    ),
    (
        r"\b(GDPR fine|CCPA fine|ICO fine|data breach penalty)\b",
        "hard:data_breach_fine",
        0.88,
    ),
]

_HARD_PATTERN_COMPILED = [
    (re.compile(pat, re.IGNORECASE), cat, conf)
    for pat, cat, conf in _HARD_PATTERNS
]


def _check_keyword_rules(text: str) -> Optional[Tuple[str, float]]:
    """Return first matching hard flag from keyword rules, or None."""
    for pattern, category, confidence in _HARD_PATTERN_COMPILED:
        if pattern.search(text):
            return category, confidence
    return None


# ── OpenSanctions API ─────────────────────────────────────────────────────────

def _query_opensanctions(entity_name: str) -> Optional[Tuple[str, float]]:
    """
    Query OpenSanctions /match endpoint for entity name.
    Returns hard:sanctions if a match with score ≥ 0.7 is found.
    API key optional (OPENSANCTIONS_API_KEY env var).
    """
    api_key = os.environ.get("OPENSANCTIONS_API_KEY", "")
    headers = {"Authorization": f"ApiKey {api_key}"} if api_key else {}

    # Use the /entities search endpoint (free, no key required for basic use)
    try:
        resp = httpx.get(
            f"{_OPENSANCTIONS_API}/entities/",
            params={"q": entity_name, "limit": 5, "datasets": "default"},
            headers=headers,
            timeout=_REQUEST_TIMEOUT,
        )
    except Exception as e:
        log.warning("OpenSanctions request failed for %r: %s", entity_name, e)
        return None

    if resp.status_code == 429:
        log.warning("OpenSanctions rate limit hit for %r", entity_name)
        return None
    if resp.status_code != 200:
        log.warning("OpenSanctions returned %d for %r", resp.status_code, entity_name)
        return None

    try:
        data = resp.json()
    except Exception:
        return None

    results = data.get("results", [])
    for result in results:
        score = result.get("score", 0.0)
        datasets = result.get("datasets", [])
        # "default" dataset includes OFAC SDN and other major watchlists
        if score >= 0.7 and datasets:
            properties = result.get("properties", {})
            name_in_result = (properties.get("name") or [""])[0]
            log.warning(
                "OpenSanctions HIT for %r: name=%r score=%.2f datasets=%s",
                entity_name,
                name_in_result,
                score,
                datasets[:3],
            )
            return "hard:sanctions", min(0.95, 0.70 + score * 0.25)

    return None


# ── Public API ────────────────────────────────────────────────────────────────

def check_sanctions(text: str, entity_name: Optional[str] = None) -> Optional[Tuple[str, float]]:
    """
    Check text and optional entity name for hard red flags.

    Priority:
    1. Keyword rules on text (deterministic, no network call)
    2. OpenSanctions API lookup for entity_name (if provided)

    Returns (flag_category, confidence) or None.
    """
    # Step 1: deterministic keyword check on text
    result = _check_keyword_rules(text)
    if result:
        return result

    # Step 2: OpenSanctions entity lookup (network, may be slow)
    if entity_name:
        result = _query_opensanctions(entity_name)
        if result:
            return result

    return None
