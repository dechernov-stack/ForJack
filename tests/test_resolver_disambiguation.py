"""Disambiguation tests: negatives filter, Tavily namesake-dominated verdict."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from storytelling_bot.resolver.reconcile import reconcile
from storytelling_bot.resolver.verifier import verify_with_tavily
from storytelling_bot.schema import Anchor, EntityCard

EXAMPLES = Path(__file__).parent.parent / "examples" / "entity_cards"
FIXTURES = Path(__file__).parent / "fixtures" / "llm_inputs"


# ── negatives field propagated through reconcile ───────────────────────────────

def test_negatives_propagated_from_providers():
    """negatives from each provider are merged (dedup) into the reconciled card."""
    provider_outputs = {
        "claude": {
            "entities": [{
                "canonical_name": "David Liberman",
                "canonical_lang": "en",
                "anchors": [{"type": "birthplace", "value": "Москва", "confidence": 0.9}],
                "negatives": ["не путать с Avigdor Liberman (израильский политик)"],
            }]
        },
        "gpt": {
            "entities": [{
                "canonical_name": "David Liberman",
                "canonical_lang": "en",
                "anchors": [{"type": "birthplace", "value": "Москва", "confidence": 0.9}],
                "negatives": [
                    "не путать с Avigdor Liberman (израильский политик)",
                    "не путать с Joe Lieberman (US senator)",
                ],
            }]
        },
    }
    cards = reconcile(provider_outputs)
    assert len(cards) == 1
    negatives = cards[0].negatives
    # dedup: Avigdor appears once despite 2 providers
    avigdor_entries = [n for n in negatives if "avigdor" in n.lower()]
    assert len(avigdor_entries) == 1
    joe_entries = [n for n in negatives if "joe lieberman" in n.lower()]
    assert len(joe_entries) == 1


def test_avigdor_kept_as_negative_not_as_card():
    """Avigdor Liberman from negatives should not appear as a separate EntityCard."""
    provider_outputs = {
        "claude": {
            "entities": [{
                "canonical_name": "David Liberman",
                "canonical_lang": "en",
                "anchors": [{"type": "dob", "value": "1984-02-22", "confidence": 0.9}],
                "negatives": ["не путать с Avigdor Liberman (израильский политик)"],
            }]
        },
        "gpt": {
            "entities": [{
                "canonical_name": "David Liberman",
                "canonical_lang": "en",
                "anchors": [{"type": "dob", "value": "1984-02-22", "confidence": 0.9}],
                "negatives": ["не путать с Avigdor Liberman"],
            }]
        },
    }
    cards = reconcile(provider_outputs)
    names = [c.canonical_name.lower() for c in cards]
    assert not any("avigdor" in n for n in names), "Avigdor must NOT appear as EntityCard"
    assert len(cards) == 1


# ── liberman brothers example fixture ─────────────────────────────────────────

@pytest.mark.skipif(not EXAMPLES.exists(), reason="examples dir not found")
def test_liberman_brothers_fixture_loads():
    """examples/entity_cards/liberman_brothers.json is valid and contains 2 cards."""
    path = EXAMPLES / "liberman_brothers.json"
    assert path.exists(), f"Fixture missing: {path}"
    data = json.loads(path.read_text(encoding="utf-8"))
    cards = data.get("cards", [])
    assert len(cards) == 2
    names = {c["canonical_name"] for c in cards}
    assert "David Liberman" in names
    assert "Daniil Liberman" in names


@pytest.mark.skipif(not EXAMPLES.exists(), reason="examples dir not found")
def test_liberman_brothers_consensus_scores():
    path = EXAMPLES / "liberman_brothers.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    for card in data["cards"]:
        assert card["consensus_score"] >= 0.5, (
            f"{card['canonical_name']} consensus_score too low: {card['consensus_score']}"
        )


@pytest.mark.skipif(not EXAMPLES.exists(), reason="examples dir not found")
def test_liberman_brothers_negatives_include_avigdor():
    """Both cards in the fixture explicitly list Avigdor as a negative."""
    path = EXAMPLES / "liberman_brothers.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    for card in data["cards"]:
        neg_text = " ".join(card.get("negatives", [])).lower()
        assert "avigdor" in neg_text, f"{card['canonical_name']}: missing Avigdor negative"


# ── Tavily namesake-dominated verdict (mocked) ─────────────────────────────────

def _make_card(name: str, negatives: list[str], consensus: float = 0.8) -> EntityCard:
    return EntityCard(
        canonical_name=name,
        canonical_lang="en",
        anchors=[Anchor(type="birthplace", value="Moscow", sources=["claude"], confidence=0.9)],
        negatives=negatives,
        consensus_score=consensus,
        providers_agreed=["claude"],
    )


def test_tavily_skipped_without_api_key(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    card = _make_card("Joe Liberman", [])
    result = verify_with_tavily(card)
    assert result.get("skipped") is True


def test_tavily_namesake_dominated_downgrades_score(monkeypatch):
    """If Tavily SERP is dominated by a negative, consensus_score drops x 0.7."""
    monkeypatch.setenv("TAVILY_API_KEY", "fake-key")

    card = _make_card(
        "Joe Lieberman",
        negatives=["не путать с Joe Lieberman (US senator)"],
        consensus=0.8,
    )

    mock_response = MagicMock()
    mock_response.ok = True
    mock_response.json.return_value = {
        "results": [
            {"title": "Joe Lieberman (US senator) — Wikipedia", "url": "https://en.wikipedia.org/wiki/Joe_Lieberman"},
            {"title": "Joe Lieberman senate career", "url": "https://example.com"},
        ]
    }

    with patch("requests.post", return_value=mock_response):
        verdict = verify_with_tavily(card)

    assert verdict.get("namesake_dominated") is True
    assert card.consensus_score < 0.8
    assert round(card.consensus_score, 3) == round(0.8 * 0.7, 3)
    assert card.raw_provider_answers.get("__tavily_verdict__") == "namesake-dominated"


def test_tavily_clean_serp_preserves_score(monkeypatch):
    """If SERP has no negatives, consensus_score is unchanged."""
    monkeypatch.setenv("TAVILY_API_KEY", "fake-key")

    card = _make_card(
        "David Liberman",
        negatives=["не путать с Avigdor Liberman (политик)"],
        consensus=0.75,
    )

    mock_response = MagicMock()
    mock_response.ok = True
    mock_response.json.return_value = {
        "results": [
            {"title": "David Liberman tech entrepreneur", "url": "https://example.com/david"},
            {"title": "Libermans Co raises $400M", "url": "https://example.com/libermans"},
        ]
    }

    with patch("requests.post", return_value=mock_response):
        verdict = verify_with_tavily(card)

    assert verdict.get("namesake_dominated") is None
    assert card.consensus_score == 0.75


def test_tavily_request_error_handled(monkeypatch):
    """Network error during Tavily request should not crash; error recorded in result."""
    monkeypatch.setenv("TAVILY_API_KEY", "fake-key")

    card = _make_card("David Liberman", negatives=[], consensus=0.7)

    with patch("requests.post", side_effect=ConnectionError("timeout")):
        verdict = verify_with_tavily(card)

    # no crash; queries recorded with error
    queries = verdict.get("queries", [])
    assert len(queries) >= 1
    assert "error" in queries[0]
    # score unchanged
    assert card.consensus_score == 0.7
