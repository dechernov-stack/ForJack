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

import httpx

log = logging.getLogger(__name__)

_OPENSANCTIONS_API = "https://api.opensanctions.org"
_REQUEST_TIMEOUT = 10

# Local yente instance (preferred when YENTE_URL is set or default docker-compose address)
_YENTE_URL_DEFAULT = "http://localhost:8000"

_OPENSANCTIONS_DISABLED = False  # set to True after first 401/5xx to skip further calls


# ── OFAC/Sanctions keyword patterns (deterministic) ──────────────────────────

_HARD_PATTERNS: list[tuple[str, str, float]] = [
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


def _check_keyword_rules(text: str) -> tuple[str, float] | None:
    """Return first matching hard flag from keyword rules, or None."""
    for pattern, category, confidence in _HARD_PATTERN_COMPILED:
        if pattern.search(text):
            return category, confidence
    return None


# ── OpenSanctions / yente helpers ────────────────────────────────────────────

def _parse_sanctions_results(results: list[dict], entity_name: str) -> tuple[str, float] | None:
    """Shared result parser for both yente and public API responses."""
    for result in results:
        score = result.get("score", 0.0)
        datasets = result.get("datasets", [])
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


def _query_yente(entity_name: str) -> tuple[str, float] | None:
    """
    Query local yente instance (ghcr.io/opensanctions/yente) for entity matching.
    Yente uses POST /match with FtM entity payload — faster and no rate limit.
    """
    yente_url = os.environ.get("YENTE_URL", _YENTE_URL_DEFAULT)
    payload = {
        "queries": {
            "entity": {
                "schema": "Thing",
                "properties": {"name": [entity_name]},
            }
        }
    }
    try:
        resp = httpx.post(
            f"{yente_url}/match/default",
            json=payload,
            timeout=_REQUEST_TIMEOUT,
        )
    except Exception as e:
        log.debug("yente not reachable (%s) — will try public API", e)
        return None

    if resp.status_code != 200:
        log.debug("yente returned %d — will try public API", resp.status_code)
        return None

    try:
        data = resp.json()
    except Exception:
        return None

    results = data.get("responses", {}).get("entity", {}).get("results", [])
    return _parse_sanctions_results(results, entity_name)


def _query_opensanctions_public(entity_name: str) -> tuple[str, float] | None:
    """
    Fallback: query public api.opensanctions.org.
    API key optional (OPENSANCTIONS_API_KEY env var).
    """
    global _OPENSANCTIONS_DISABLED
    if _OPENSANCTIONS_DISABLED:
        return None

    api_key = os.environ.get("OPENSANCTIONS_API_KEY", "")
    headers = {"Authorization": f"ApiKey {api_key}"} if api_key else {}

    try:
        resp = httpx.get(
            f"{_OPENSANCTIONS_API}/entities/",
            params={"q": entity_name, "limit": 5, "datasets": "default"},
            headers=headers,
            timeout=_REQUEST_TIMEOUT,
        )
    except Exception as e:
        log.warning("OpenSanctions public API request failed for %r: %s", entity_name, e)
        return None

    if resp.status_code in (401, 403):
        log.warning("OpenSanctions returned %d — disabling for this run (set OPENSANCTIONS_API_KEY to enable)", resp.status_code)
        _OPENSANCTIONS_DISABLED = True
        return None
    if resp.status_code == 429:
        log.warning("OpenSanctions rate limit hit for %r", entity_name)
        _OPENSANCTIONS_DISABLED = True
        return None
    if resp.status_code != 200:
        log.warning("OpenSanctions returned %d for %r", resp.status_code, entity_name)
        return None

    try:
        data = resp.json()
    except Exception:
        return None

    return _parse_sanctions_results(data.get("results", []), entity_name)


def _query_opensanctions(entity_name: str) -> tuple[str, float] | None:
    """Try yente (local) first; fall back to public api.opensanctions.org."""
    result = _query_yente(entity_name)
    if result is not None:
        return result
    return _query_opensanctions_public(entity_name)


# ── Public API ────────────────────────────────────────────────────────────────

def check_sanctions(text: str, entity_name: str | None = None) -> tuple[str, float] | None:
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
