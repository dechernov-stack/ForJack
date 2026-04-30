"""Tests for EntityResolver 2-of-3 consensus on mock inputs."""
from __future__ import annotations

from pathlib import Path

import pytest

from storytelling_bot.resolver.card import resolve
from storytelling_bot.resolver.providers import parse_provider_answer
from storytelling_bot.resolver.reconcile import _norm_anchor_value, _norm_lastname, reconcile

FIXTURES = Path(__file__).parent / "fixtures" / "llm_inputs"


# ── normalizers ────────────────────────────────────────────────────────────────

def test_norm_lastname_cyrillic():
    assert _norm_lastname("Либерман") == "liberman"


def test_norm_lastname_lieberman():
    assert _norm_lastname("Liebermann") == "liberman"


def test_norm_anchor_dob_iso():
    assert _norm_anchor_value("1984-02-22") == "1984-02-22"


def test_norm_anchor_dob_year_only():
    assert _norm_anchor_value("1982") == "1982"


def test_norm_anchor_birthplace_moscow():
    assert _norm_anchor_value("Москва") == "moscow"


def test_norm_anchor_birthplace_strips_country():
    assert "ussr" not in _norm_anchor_value("Moscow, USSR")


# ── parse ──────────────────────────────────────────────────────────────────────

def test_parse_provider_answer_json():
    raw = '{"entities": [{"canonical_name": "David Liberman", "canonical_lang": "en"}]}'
    out = parse_provider_answer("test", raw)
    assert len(out["entities"]) == 1
    assert out["entities"][0]["canonical_name"] == "David Liberman"


def test_parse_provider_answer_single_card():
    raw = '{"canonical_name": "David Liberman", "canonical_lang": "en", "anchors": []}'
    out = parse_provider_answer("test", raw)
    assert len(out["entities"]) == 1


def test_parse_provider_answer_invalid():
    out = parse_provider_answer("test", "не JSON вообще")
    assert out["entities"] == []
    assert "uncertainty_note" in out


# ── reconcile on mock fixtures ─────────────────────────────────────────────────

@pytest.mark.skipif(not FIXTURES.exists(), reason="fixtures not found")
def test_reconcile_liberman_mock():
    """2-of-3 on saved claude/gpt/deepseek answers → 2 EntityCard (David + Daniil)."""
    provider_outputs = {}
    for name in ("claude", "gpt", "deepseek"):
        path = FIXTURES / f"{name}_liberman.json"
        if path.exists():
            raw = path.read_text(encoding="utf-8")
            if "RAW_ANSWER:" in raw:
                raw = raw.split("RAW_ANSWER:", 1)[1].strip()
            provider_outputs[name] = parse_provider_answer(name, raw)

    assert len(provider_outputs) >= 2, "Need at least 2 provider fixtures"
    cards = reconcile(provider_outputs)

    assert len(cards) >= 1
    names_lower = [c.canonical_name.lower() for c in cards]
    assert any("liberman" in n for n in names_lower)


@pytest.mark.skipif(not FIXTURES.exists(), reason="fixtures not found")
def test_consensus_score_above_threshold():
    provider_outputs = {}
    for name in ("claude", "gpt", "deepseek"):
        path = FIXTURES / f"{name}_liberman.json"
        if path.exists():
            raw = path.read_text(encoding="utf-8")
            if "RAW_ANSWER:" in raw:
                raw = raw.split("RAW_ANSWER:", 1)[1].strip()
            provider_outputs[name] = parse_provider_answer(name, raw)

    cards = reconcile(provider_outputs)
    for card in cards:
        assert card.consensus_score >= 0.5, f"{card.canonical_name} consensus too low: {card.consensus_score}"


@pytest.mark.skipif(not FIXTURES.exists(), reason="fixtures not found")
def test_anchors_have_multi_provider_sources():
    provider_outputs = {}
    for name in ("claude", "gpt", "deepseek"):
        path = FIXTURES / f"{name}_liberman.json"
        if path.exists():
            raw = path.read_text(encoding="utf-8")
            if "RAW_ANSWER:" in raw:
                raw = raw.split("RAW_ANSWER:", 1)[1].strip()
            provider_outputs[name] = parse_provider_answer(name, raw)

    cards = reconcile(provider_outputs)
    for card in cards:
        multi_source = [a for a in card.anchors if len(a.sources) >= 2]
        assert len(multi_source) >= 1, f"{card.canonical_name}: no multi-provider anchors"


# ── mock_provider ──────────────────────────────────────────────────────────────

@pytest.mark.skipif(not FIXTURES.exists(), reason="fixtures not found")
def test_resolve_with_mock_dir():
    cards = resolve(
        query="братья Либерман предприниматели",
        providers=["claude", "gpt", "deepseek"],
        mock_dir=FIXTURES,
        use_tavily=False,
    )
    assert len(cards) >= 1
    assert all(c.consensus_score > 0 for c in cards)
