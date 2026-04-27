"""Tests for ArchivalCollector — Wayback Machine CDX + snapshot, respx mocked."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
import respx
import httpx

from storytelling_bot.schema import SourceType


@pytest.fixture(autouse=True)
def tmp_data_dirs(tmp_path, monkeypatch):
    import storytelling_bot.collectors.archival as mod
    monkeypatch.setattr(mod, "_BRONZE_ROOT", tmp_path / "bronze")
    monkeypatch.setattr(mod, "_SILVER_ROOT", tmp_path / "silver")
    return tmp_path


# CDX API mock data
_CDX_HEADERS = ["timestamp", "original", "statuscode", "digest"]
_CDX_ROW = ["20200615120000", "https://stripe.com/", "200", "ABCDEF1234"]
_CDX_RESPONSE = [_CDX_HEADERS, _CDX_ROW]

_SNAPSHOT_HTML = """
<html><head><title>Stripe</title></head>
<body>
<p>Stripe was founded in 2010 by Patrick and John Collison.</p>
<p>The company processes billions of dollars in payments annually.</p>
<p>It is valued at over $70 billion as of 2023.</p>
</body></html>
"""


# ── CDX search ────────────────────────────────────────────────────────────────

@respx.mock
def test_cdx_search_returns_captures():
    from storytelling_bot.collectors.archival import _cdx_search

    respx.get("https://web.archive.org/cdx/search/cdx").mock(
        return_value=httpx.Response(200, json=_CDX_RESPONSE)
    )

    captures = _cdx_search("https://stripe.com/*")
    assert len(captures) == 1
    assert captures[0]["timestamp"] == "20200615120000"
    assert captures[0]["original"] == "https://stripe.com/"


@respx.mock
def test_cdx_search_empty_returns_empty():
    from storytelling_bot.collectors.archival import _cdx_search

    respx.get("https://web.archive.org/cdx/search/cdx").mock(
        return_value=httpx.Response(200, json=[])
    )

    captures = _cdx_search("https://unknown.com/*")
    assert captures == []


@respx.mock
def test_cdx_search_429_raises_rate_limit():
    from storytelling_bot.collectors.archival import _cdx_search, _WaybackRateLimit

    respx.get("https://web.archive.org/cdx/search/cdx").mock(
        return_value=httpx.Response(429, text="Too Many Requests")
    )

    with pytest.raises(_WaybackRateLimit):
        _cdx_search("https://stripe.com/*")


@respx.mock
def test_cdx_search_non_200_returns_empty():
    from storytelling_bot.collectors.archival import _cdx_search

    respx.get("https://web.archive.org/cdx/search/cdx").mock(
        return_value=httpx.Response(503, text="Service Unavailable")
    )

    captures = _cdx_search("https://stripe.com/*")
    assert captures == []


# ── snapshot fetch ────────────────────────────────────────────────────────────

@respx.mock
def test_fetch_snapshot_extracts_text():
    from storytelling_bot.collectors.archival import _fetch_snapshot_text

    respx.get(url__startswith="https://web.archive.org/web/").mock(
        return_value=httpx.Response(200, text=_SNAPSHOT_HTML, headers={"content-type": "text/html"})
    )

    text = _fetch_snapshot_text("20200615120000", "https://stripe.com/")
    assert text is not None
    assert "Stripe" in text or "stripe" in text.lower()
    assert len(text) > 50


@respx.mock
def test_fetch_snapshot_non_200_returns_none():
    from storytelling_bot.collectors.archival import _fetch_snapshot_text

    respx.get(url__startswith="https://web.archive.org/web/").mock(
        return_value=httpx.Response(404, text="Not Found")
    )

    result = _fetch_snapshot_text("20200615120000", "https://stripe.com/")
    assert result is None


# ── full wayback collection ───────────────────────────────────────────────────

@respx.mock
def test_collect_wayback_produces_silver_records():
    from storytelling_bot.collectors.archival import _collect_wayback

    respx.get("https://web.archive.org/cdx/search/cdx").mock(
        return_value=httpx.Response(200, json=_CDX_RESPONSE)
    )
    respx.get(url__startswith="https://web.archive.org/web/").mock(
        return_value=httpx.Response(200, text=_SNAPSHOT_HTML, headers={"content-type": "text/html"})
    )

    chunks = _collect_wayback("stripe")
    assert len(chunks) > 0
    chunk = chunks[0]
    assert chunk["source_type"] == SourceType.ARCHIVAL
    assert "source_hash" in chunk
    assert "captured_at" in chunk
    assert "url" in chunk


@respx.mock
def test_collect_wayback_dedup():
    from storytelling_bot.collectors.archival import _collect_wayback

    respx.get("https://web.archive.org/cdx/search/cdx").mock(
        return_value=httpx.Response(200, json=_CDX_RESPONSE)
    )
    respx.get(url__startswith="https://web.archive.org/web/").mock(
        return_value=httpx.Response(200, text=_SNAPSHOT_HTML, headers={"content-type": "text/html"})
    )

    chunks1 = _collect_wayback("stripe")
    chunks2 = _collect_wayback("stripe")
    assert len(chunks1) > 0
    assert len(chunks2) == 0  # all deduped by Bronze sha


# ── ArchivalCollector ─────────────────────────────────────────────────────────

def test_collect_returns_demo_corpus_for_known_entity():
    from storytelling_bot.collectors.archival import ArchivalCollector

    with patch("storytelling_bot.collectors.archival._collect_wayback", return_value=[]):
        result = ArchivalCollector().collect("accumulator")

    assert len(result) > 0
    assert all(c["source_type"] == SourceType.ARCHIVAL for c in result)


def test_collect_merges_demo_and_live():
    from storytelling_bot.collectors.archival import ArchivalCollector

    live_chunk = {
        "source_type": SourceType.ARCHIVAL,
        "url": "https://web.archive.org/web/20200101/https://stripe.com/",
        "captured_at": "2020-01-01T00:00:00+00:00",
        "text": "Stripe launched payment infrastructure globally.",
        "entity_focus": "accumulator",
        "source_hash": "fakehash123",
    }

    with patch("storytelling_bot.collectors.archival._collect_wayback", return_value=[live_chunk]):
        result = ArchivalCollector().collect("accumulator")

    # Should have both demo corpus items AND the live chunk
    assert live_chunk in result
    assert len(result) > 1


def test_strip_html_removes_tags():
    from storytelling_bot.collectors.archival import _strip_html

    html = "<html><body><h1>Title</h1><p>Some <b>bold</b> text.</p></body></html>"
    text = _strip_html(html)
    assert "<" not in text
    assert "Title" in text
    assert "Some" in text


def test_strip_html_removes_scripts():
    from storytelling_bot.collectors.archival import _strip_html

    html = "<html><head><script>var x=1;</script></head><body><p>Clean text</p></body></html>"
    text = _strip_html(html)
    assert "var x" not in text
    assert "Clean text" in text
