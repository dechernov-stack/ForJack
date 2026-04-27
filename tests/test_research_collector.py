"""Tests for ResearchCollector — Tavily + GDELT + SEC, with respx mocks."""
from __future__ import annotations

import json
import os
import hashlib
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
import respx
import httpx

from storytelling_bot.schema import SourceType


# ── fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def tmp_data_dirs(tmp_path, monkeypatch):
    """Redirect Bronze/Silver writes to a temp dir so tests don't pollute repo."""
    import storytelling_bot.collectors.research as mod
    monkeypatch.setattr(mod, "_BRONZE_ROOT", tmp_path / "bronze")
    monkeypatch.setattr(mod, "_SILVER_ROOT", tmp_path / "silver")
    return tmp_path


@pytest.fixture(autouse=True)
def set_tavily_key(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "test-key-fake")


# ── Tavily ───────────────────────────────────────────────────────────────────

def _make_tavily_client(results):
    mock = MagicMock()
    mock.search.return_value = {"results": results}
    return mock


def test_tavily_normalizes_to_fact():
    """Tavily result must produce a chunk with all required provenance fields."""
    from storytelling_bot.collectors.research import _collect_tavily

    tavily_results = [
        {"url": "https://example.com/stripe", "content": "Stripe processes billions annually."},
    ]

    with patch("storytelling_bot.collectors.research.TavilyClient", return_value=_make_tavily_client(tavily_results)):
        with patch("storytelling_bot.collectors.research._get_aliases", return_value=[]):
            chunks = _collect_tavily("stripe")

    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk["url"] == "https://example.com/stripe"
    assert chunk["source_type"] == SourceType.ONLINE_RESEARCH
    assert "source_hash" in chunk
    assert "captured_at" in chunk
    assert chunk["entity_focus"] == "stripe"


def test_tavily_dedup_skips_duplicate():
    """Same content written twice must not duplicate Bronze files."""
    from storytelling_bot.collectors.research import _collect_tavily

    tavily_results = [
        {"url": "https://example.com/stripe", "content": "Stripe processes billions annually."},
    ]

    mock_client = _make_tavily_client(tavily_results)
    with patch("storytelling_bot.collectors.research.TavilyClient", return_value=mock_client):
        with patch("storytelling_bot.collectors.research._get_aliases", return_value=[]):
            chunks1 = _collect_tavily("stripe")
            chunks2 = _collect_tavily("stripe")

    # Second call: same content → deduped → no new chunks
    assert len(chunks1) == 1
    assert len(chunks2) == 0


def test_tavily_skipped_when_no_key(monkeypatch):
    """Missing TAVILY_API_KEY must return empty list, not raise."""
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    from storytelling_bot.collectors.research import _collect_tavily
    chunks = _collect_tavily("stripe")
    assert chunks == []


def test_tavily_429_triggers_retry():
    """429-like error from Tavily triggers tenacity retry (max 4 attempts)."""
    from storytelling_bot.collectors.research import _collect_tavily, _TavilyRateLimit

    mock_client = MagicMock()
    mock_client.search.side_effect = Exception("429 rate limit exceeded")

    with patch("storytelling_bot.collectors.research.TavilyClient", return_value=mock_client):
        with patch("storytelling_bot.collectors.research._get_aliases", return_value=[]):
            # Should exhaust retries and return empty (reraise=True → _TavilyRateLimit)
            with pytest.raises(_TavilyRateLimit):
                _collect_tavily("stripe")

    # Called 4 times (initial + 3 retries)
    assert mock_client.search.call_count == 4


# ── GDELT ────────────────────────────────────────────────────────────────────

GDELT_RESPONSE = {
    "articles": [
        {
            "url": "https://gdelt.example/news1",
            "title": "Stripe expands into Africa",
            "tone": "2.5",
            "seendate": "20260101T120000Z",
        },
        {
            "url": "https://gdelt.example/news2",
            "title": "Stripe launches new API",
            "tone": "1.0",
            "seendate": "20260102T090000Z",
        },
    ]
}


@respx.mock
def test_gdelt_collects_articles():
    """GDELT mock returns 2 articles → 2 Silver records."""
    from storytelling_bot.collectors.research import _collect_gdelt

    respx.get("https://api.gdeltproject.org/api/v2/doc/doc").mock(
        return_value=httpx.Response(200, json=GDELT_RESPONSE)
    )

    chunks = _collect_gdelt("stripe")
    assert len(chunks) == 2
    assert all(c["source_type"] == SourceType.ONLINE_RESEARCH for c in chunks)
    assert all("url" in c for c in chunks)


@respx.mock
def test_gdelt_non_200_returns_empty():
    """GDELT 503 → empty list, no exception."""
    from storytelling_bot.collectors.research import _collect_gdelt

    respx.get("https://api.gdeltproject.org/api/v2/doc/doc").mock(
        return_value=httpx.Response(503, text="Service Unavailable")
    )

    chunks = _collect_gdelt("stripe")
    assert chunks == []


@respx.mock
def test_gdelt_dedup():
    """Running GDELT twice for same entity → second call returns empty."""
    from storytelling_bot.collectors.research import _collect_gdelt

    respx.get("https://api.gdeltproject.org/api/v2/doc/doc").mock(
        return_value=httpx.Response(200, json=GDELT_RESPONSE)
    )

    chunks1 = _collect_gdelt("stripe")
    chunks2 = _collect_gdelt("stripe")
    assert len(chunks1) == 2
    assert len(chunks2) == 0


# ── SEC ───────────────────────────────────────────────────────────────────────

SEC_RESPONSE = {
    "hits": {
        "hits": [
            {
                "_source": {
                    "form_type": "D",
                    "file_date": "2024-01-15",
                    "display_names": ["Stripe, Inc."],
                }
            }
        ]
    }
}


@respx.mock
def test_sec_private_company_returns_empty():
    """No EDGAR hits → private company assumed → empty list."""
    from storytelling_bot.collectors.research import _collect_sec

    respx.get(url__startswith="https://efts.sec.gov/").mock(
        return_value=httpx.Response(200, json={"hits": {"hits": []}})
    )

    chunks = _collect_sec("stripe-private")
    assert chunks == []


@respx.mock
def test_sec_filing_produces_chunk():
    """SEC hit → 1 Silver chunk with provenance."""
    from storytelling_bot.collectors.research import _collect_sec

    respx.get(url__startswith="https://efts.sec.gov/").mock(
        return_value=httpx.Response(200, json=SEC_RESPONSE)
    )

    chunks = _collect_sec("stripe")
    assert len(chunks) == 1
    assert "SEC" in chunks[0]["text"] or "Stripe" in chunks[0]["text"]
    assert "source_hash" in chunks[0]


# ── full collector ────────────────────────────────────────────────────────────

def test_collect_returns_list_of_dicts():
    """ResearchCollector.collect() returns a list even if all sources empty."""
    from storytelling_bot.collectors.research import ResearchCollector

    with patch("storytelling_bot.collectors.research._collect_tavily", return_value=[]):
        with patch("storytelling_bot.collectors.research._collect_gdelt", return_value=[]):
            with patch("storytelling_bot.collectors.research._collect_sec", return_value=[]):
                result = ResearchCollector().collect("test-entity")

    assert isinstance(result, list)


def test_collect_source_type_is_online_research():
    """All returned chunks must have source_type=online_research."""
    from storytelling_bot.collectors.research import ResearchCollector

    fake_chunk = {
        "source_type": SourceType.ONLINE_RESEARCH,
        "url": "https://x.com",
        "captured_at": "2026-01-01T00:00:00+00:00",
        "text": "Some text",
        "entity_focus": "stripe",
        "source_hash": "abc123",
    }

    with patch("storytelling_bot.collectors.research._collect_tavily", return_value=[fake_chunk]):
        with patch("storytelling_bot.collectors.research._collect_gdelt", return_value=[]):
            with patch("storytelling_bot.collectors.research._collect_sec", return_value=[]):
                result = ResearchCollector().collect("stripe")

    assert all(c["source_type"] == SourceType.ONLINE_RESEARCH for c in result)
