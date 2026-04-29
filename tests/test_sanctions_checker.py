"""Tests for sanctions checker: keyword rules + OpenSanctions API mock + yente."""
from __future__ import annotations

from unittest.mock import patch

import httpx
import respx

# ── keyword rule tests ────────────────────────────────────────────────────────

def test_ofac_keyword_triggers_hard_sanctions():
    from storytelling_bot.sanctions.checker import check_sanctions

    result = check_sanctions("The founder was placed on the OFAC SDN list in 2023.")
    assert result is not None
    cat, conf = result
    assert cat == "hard:sanctions"
    assert conf >= 0.85


def test_criminal_indictment_triggers_hard_criminal():
    from storytelling_bot.sanctions.checker import check_sanctions

    result = check_sanctions("The CEO was criminally indicted for wire fraud in 2022.")
    assert result is not None
    cat, conf = result
    assert cat == "hard:criminal"
    assert conf >= 0.85


def test_sec_enforcement_triggers_hard_sec():
    from storytelling_bot.sanctions.checker import check_sanctions

    result = check_sanctions("The SEC enforcement action resulted in a $50M fine.")
    assert result is not None
    cat, conf = result
    assert cat == "hard:sec_enforcement"
    assert conf >= 0.85


def test_ponzi_triggers_hard_fraud():
    from storytelling_bot.sanctions.checker import check_sanctions

    result = check_sanctions("The fund turned out to be a Ponzi scheme defrauding investors.")
    assert result is not None
    cat, conf = result
    assert cat == "hard:fraud"
    assert conf >= 0.85


def test_gdpr_fine_triggers_data_breach():
    from storytelling_bot.sanctions.checker import check_sanctions

    result = check_sanctions("Regulators issued a GDPR fine of €20M for the data breach.")
    assert result is not None
    cat, conf = result
    assert cat == "hard:data_breach_fine"
    assert conf >= 0.85


def test_clean_text_returns_none():
    from storytelling_bot.sanctions.checker import check_sanctions

    result = check_sanctions("Stripe processed $1 trillion in payments last year.")
    assert result is None


def test_case_insensitive_matching():
    from storytelling_bot.sanctions.checker import check_sanctions

    result = check_sanctions("company added to ofac sanctions list by treasury")
    assert result is not None
    assert result[0] == "hard:sanctions"


def test_eu_sanctions_triggers():
    from storytelling_bot.sanctions.checker import check_sanctions

    result = check_sanctions("The entity was subject to EU sanctions imposed last quarter.")
    assert result is not None
    assert "sanctions" in result[0]


def test_no_entity_name_skips_opensanctions():
    """Without entity_name, OpenSanctions API should not be called."""
    from storytelling_bot.sanctions.checker import check_sanctions

    with patch("storytelling_bot.sanctions.checker._query_opensanctions") as mock_qs:
        result = check_sanctions("Clean text with no red flags here.")
        mock_qs.assert_not_called()

    assert result is None


# ── OpenSanctions API mock tests ──────────────────────────────────────────────

@respx.mock
def test_opensanctions_hit_returns_hard_sanctions():
    from storytelling_bot.sanctions.checker import _query_opensanctions

    respx.get("https://api.opensanctions.org/entities/").mock(
        return_value=httpx.Response(200, json={
            "results": [
                {
                    "score": 0.85,
                    "datasets": ["us_ofac_sdn"],
                    "properties": {"name": ["Vladimir Badguy"]},
                }
            ]
        })
    )

    result = _query_opensanctions("Vladimir Badguy")
    assert result is not None
    cat, conf = result
    assert cat == "hard:sanctions"
    assert conf >= 0.85


@respx.mock
def test_opensanctions_low_score_returns_none():
    from storytelling_bot.sanctions.checker import _query_opensanctions

    respx.get("https://api.opensanctions.org/entities/").mock(
        return_value=httpx.Response(200, json={
            "results": [
                {
                    "score": 0.3,  # below threshold
                    "datasets": ["us_ofac_sdn"],
                    "properties": {"name": ["Someone"]},
                }
            ]
        })
    )

    result = _query_opensanctions("Someone")
    assert result is None


@respx.mock
def test_opensanctions_empty_returns_none():
    from storytelling_bot.sanctions.checker import _query_opensanctions

    respx.get("https://api.opensanctions.org/entities/").mock(
        return_value=httpx.Response(200, json={"results": []})
    )

    result = _query_opensanctions("Clean Company Inc")
    assert result is None


@respx.mock
def test_opensanctions_429_returns_none():
    from storytelling_bot.sanctions.checker import _query_opensanctions

    respx.get("https://api.opensanctions.org/entities/").mock(
        return_value=httpx.Response(429, text="Too Many Requests")
    )

    result = _query_opensanctions("any entity")
    assert result is None


@respx.mock
def test_check_sanctions_uses_keyword_first_skips_api():
    """If keyword rule fires, OpenSanctions API must NOT be called."""
    from storytelling_bot.sanctions.checker import check_sanctions

    with patch("storytelling_bot.sanctions.checker._query_opensanctions") as mock_qs:
        result = check_sanctions("Company on the OFAC SDN list.", entity_name="badco")
        mock_qs.assert_not_called()

    assert result is not None
    assert result[0] == "hard:sanctions"


# ── Integration: node_flag_detector uses sanctions checker ────────────────────

def test_flag_detector_uses_sanctions_before_llm():
    """Sanctions checker fires → flag=RED without LLM call."""
    import datetime as dt

    from storytelling_bot.nodes.flag_detector import node_flag_detector
    from storytelling_bot.schema import Fact, Flag, Layer, SourceType, State

    fact = Fact(
        entity_id="badco",
        layer=Layer.FOUNDER_PERSONAL,
        subcategory="Fears & Vulnerability",
        source_type=SourceType.ONLINE_RESEARCH,
        text="The founder was placed on the OFAC SDN list for financial crimes.",
        source_url="https://example.com",
        captured_at=dt.datetime.now(dt.UTC),
        flag=Flag.GREY,
        confidence=0.5,
    )
    state = State(entity_id="badco", facts=[fact])

    with patch("storytelling_bot.nodes.flag_detector.get_llm_client") as mock_llm:
        result = node_flag_detector(state)
        # LLM judge_red_flag should NOT have been called (keyword caught it first)
        mock_llm.return_value.judge_red_flag.assert_not_called()

    updated_facts = result["facts"]
    assert len(updated_facts) == 1
    assert updated_facts[0].flag == Flag.RED
    assert updated_facts[0].red_flag_category == "hard:sanctions"
    assert updated_facts[0].confidence >= 0.85


# ── yente (local OpenSanctions) tests ────────────────────────────────────────

@respx.mock
def test_yente_hit_returns_hard_sanctions(monkeypatch):
    """_query_yente returns hard:sanctions when yente POST /match returns a hit."""
    from storytelling_bot.sanctions.checker import _query_yente

    monkeypatch.setenv("YENTE_URL", "http://localhost:8000")
    respx.post("http://localhost:8000/match/default").mock(
        return_value=httpx.Response(200, json={
            "responses": {
                "entity": {
                    "results": [
                        {
                            "score": 0.92,
                            "datasets": ["us_ofac_sdn"],
                            "properties": {"name": ["Ivan Sanctioned"]},
                        }
                    ]
                }
            }
        })
    )

    result = _query_yente("Ivan Sanctioned")
    assert result is not None
    cat, conf = result
    assert cat == "hard:sanctions"
    assert conf >= 0.85


@respx.mock
def test_yente_fallback_to_public_api_on_failure(monkeypatch):
    """When yente is unreachable, _query_opensanctions falls back to public API."""
    from storytelling_bot.sanctions.checker import _query_opensanctions

    monkeypatch.setenv("YENTE_URL", "http://localhost:8000")
    # yente returns connection error (simulated by 503)
    respx.post("http://localhost:8000/match/default").mock(
        return_value=httpx.Response(503)
    )
    # public API returns a hit
    respx.get("https://api.opensanctions.org/entities/").mock(
        return_value=httpx.Response(200, json={
            "results": [
                {
                    "score": 0.80,
                    "datasets": ["us_ofac_sdn"],
                    "properties": {"name": ["Ivan Sanctioned"]},
                }
            ]
        })
    )

    result = _query_opensanctions("Ivan Sanctioned")
    assert result is not None
    assert result[0] == "hard:sanctions"


@respx.mock
def test_yente_preferred_over_public_api(monkeypatch):
    """When yente returns a hit, public API must not be called."""
    from storytelling_bot.sanctions.checker import _query_opensanctions

    monkeypatch.setenv("YENTE_URL", "http://localhost:8000")
    respx.post("http://localhost:8000/match/default").mock(
        return_value=httpx.Response(200, json={
            "responses": {
                "entity": {
                    "results": [
                        {
                            "score": 0.95,
                            "datasets": ["us_ofac_sdn"],
                            "properties": {"name": ["Suspect Person"]},
                        }
                    ]
                }
            }
        })
    )
    # If public API were called, respx would raise MockRouteError (unmocked GET)
    # — the test passes only if _query_yente returns a result and public API is skipped.
    result = _query_opensanctions("Suspect Person")
    assert result is not None
    assert result[0] == "hard:sanctions"


# ── SDN person → TERMINATE pipeline integration ───────────────────────────────

@respx.mock
def test_sdn_person_pipeline_terminates(monkeypatch):
    """Fake SDN entity with hard:sanctions → pipeline decision = terminate."""
    import datetime as dt

    from storytelling_bot.nodes.decision_engine import node_decision_engine
    from storytelling_bot.schema import Fact, Flag, Layer, SourceType, State

    monkeypatch.setenv("YENTE_URL", "http://localhost:8000")
    # Yente returns a hit for this entity
    respx.post("http://localhost:8000/match/default").mock(
        return_value=httpx.Response(200, json={
            "responses": {
                "entity": {
                    "results": [
                        {
                            "score": 0.94,
                            "datasets": ["us_ofac_sdn"],
                            "properties": {"name": ["Vladimir Sanctioned"]},
                        }
                    ]
                }
            }
        })
    )

    # Build state with a fact already flagged red (hard:sanctions)
    fact = Fact(
        entity_id="sdn_test_entity",
        layer=Layer.PEST_CONTEXT,
        subcategory="Policy & regulation",
        source_type=SourceType.ONLINE_RESEARCH,
        text="Vladimir Sanctioned added to OFAC SDN list for financial crimes.",
        source_url="https://ofac.treasury.gov/fake",
        captured_at=dt.datetime.now(dt.UTC),
        flag=Flag.RED,
        confidence=0.94,
        red_flag_category="hard:sanctions",
    )
    state = State(entity_id="sdn_test_entity", facts=[fact])
    result = node_decision_engine(state)
    decision = result["decision"]
    assert decision["recommendation"] == "terminate", (
        f"Expected TERMINATE for hard:sanctions, got {decision['recommendation']!r}"
    )
    assert decision["human_approval_required"] is True
