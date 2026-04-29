"""Tests for EventWatcher — RSS + GDELT + Slack mock, all external calls mocked."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest
import respx

from storytelling_bot.watcher.event_watcher import (
    EventWatcher,
    _event_id,
    _fetch_gdelt_events,
    _fetch_rss_events,
    _load_seen,
    _save_seen,
    _send_slack_alert,
)


@pytest.fixture(autouse=True)
def tmp_state_dir(tmp_path, monkeypatch):
    import storytelling_bot.watcher.event_watcher as mod
    monkeypatch.setattr(mod, "_STATE_DIR", tmp_path / "watcher")
    return tmp_path


# ── dedup helpers ─────────────────────────────────────────────────────────────

def test_event_id_stable():
    id1 = _event_id("https://example.com/news", "2026-01-01")
    id2 = _event_id("https://example.com/news", "2026-01-01")
    assert id1 == id2


def test_event_id_different_for_different_url():
    id1 = _event_id("https://example.com/news1", "2026-01-01")
    id2 = _event_id("https://example.com/news2", "2026-01-01")
    assert id1 != id2


def test_save_and_load_seen(tmp_path, monkeypatch):
    import storytelling_bot.watcher.event_watcher as mod
    monkeypatch.setattr(mod, "_STATE_DIR", tmp_path)

    seen = {"abc", "def", "ghi"}
    _save_seen("stripe", seen)
    loaded = _load_seen("stripe")
    assert loaded == seen


def test_load_seen_empty_when_missing(tmp_path):
    result = _load_seen("nonexistent-entity")
    assert result == set()


# ── RSS ───────────────────────────────────────────────────────────────────────

def _make_rss_entry(title: str, link: str, published: str = "2026-01-01"):
    m = MagicMock()
    m.get = lambda k, default="": {
        "title": title,
        "link": link,
        "summary": title,
        "published": published,
    }.get(k, default)
    return m


def test_fetch_rss_filters_by_entity():
    mock_parsed = MagicMock()
    mock_parsed.entries = [
        _make_rss_entry("Stripe raises $1B", "https://tc.com/stripe-raises"),
        _make_rss_entry("Unrelated tech news", "https://tc.com/unrelated"),
        _make_rss_entry("Patrick Collison on Stripe growth", "https://tc.com/stripe-growth"),
    ]

    with patch("storytelling_bot.watcher.event_watcher.feedparser") as mock_fp:
        mock_fp.parse.return_value = mock_parsed
        events = _fetch_rss_events("stripe", feeds=["https://techcrunch.com/feed/"])

    # Only articles mentioning "stripe" should be returned
    assert len(events) == 2
    assert all("stripe" in e["title"].lower() or "Stripe" in e["title"] for e in events)


def test_fetch_rss_returns_empty_on_error():
    with patch("storytelling_bot.watcher.event_watcher.feedparser") as mock_fp:
        mock_fp.parse.side_effect = Exception("connection refused")
        events = _fetch_rss_events("stripe", feeds=["https://bad.feed/"])
    assert events == []


# ── GDELT ─────────────────────────────────────────────────────────────────────

_GDELT_WATCH_RESPONSE = {
    "articles": [
        {"url": "https://news1.com", "title": "Stripe expands to Africa", "seendate": "20260101120000Z", "tone": "2.5"},
        {"url": "https://news2.com", "title": "Stripe API update", "seendate": "20260102090000Z", "tone": "0.0"},
    ]
}


@respx.mock
def test_fetch_gdelt_events_returns_events():
    respx.get("https://api.gdeltproject.org/api/v2/doc/doc").mock(
        return_value=httpx.Response(200, json=_GDELT_WATCH_RESPONSE)
    )

    events = _fetch_gdelt_events("stripe", days=1)
    assert len(events) == 2
    assert events[0]["source"] == "gdelt"
    assert "url" in events[0]
    assert "date" in events[0]


@respx.mock
def test_fetch_gdelt_events_empty_on_error():
    respx.get("https://api.gdeltproject.org/api/v2/doc/doc").mock(
        return_value=httpx.Response(503, text="Unavailable")
    )
    events = _fetch_gdelt_events("stripe")
    assert events == []


# ── Slack alert ───────────────────────────────────────────────────────────────

def test_slack_mock_when_no_webhook(caplog):
    import logging
    events = [{"url": "https://x.com", "title": "Stripe alert", "date": "2026-01-01"}]
    with caplog.at_level(logging.INFO):
        _send_slack_alert("stripe", events)
    assert "MOCK SLACK ALERT" in caplog.text


@respx.mock
def test_slack_posts_to_webhook(monkeypatch):
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/test")
    respx.post("https://hooks.slack.com/test").mock(return_value=httpx.Response(200, text="ok"))

    events = [{"url": "https://x.com", "title": "Stripe alert", "date": "2026-01-01"}]
    _send_slack_alert("stripe", events)

    assert respx.calls.call_count == 1


def test_slack_no_alert_for_empty_events():
    with patch("storytelling_bot.watcher.event_watcher.httpx") as mock_httpx:
        _send_slack_alert("stripe", [])
        mock_httpx.post.assert_not_called()


# ── EventWatcher.poll ─────────────────────────────────────────────────────────

def test_poll_returns_new_events():
    fake_events = [
        {"url": "https://a.com", "title": "Stripe news", "date": "2026-01-01", "source": "rss"},
    ]

    with patch("storytelling_bot.watcher.event_watcher._fetch_rss_events", return_value=fake_events):
        with patch("storytelling_bot.watcher.event_watcher._fetch_gdelt_events", return_value=[]):
            with patch("storytelling_bot.watcher.event_watcher._send_slack_alert") as mock_slack:
                watcher = EventWatcher("stripe")
                new = watcher.poll()

    assert len(new) == 1
    mock_slack.assert_called_once()


def test_poll_deduplicates_repeated_events():
    fake_events = [
        {"url": "https://a.com", "title": "Stripe news", "date": "2026-01-01", "source": "rss"},
    ]

    with patch("storytelling_bot.watcher.event_watcher._fetch_rss_events", return_value=fake_events):
        with patch("storytelling_bot.watcher.event_watcher._fetch_gdelt_events", return_value=[]):
            with patch("storytelling_bot.watcher.event_watcher._send_slack_alert"):
                watcher = EventWatcher("stripe")
                new1 = watcher.poll()
                new2 = watcher.poll()

    assert len(new1) == 1
    assert len(new2) == 0  # already seen


def test_poll_returns_empty_when_no_events():
    with patch("storytelling_bot.watcher.event_watcher._fetch_rss_events", return_value=[]):
        with patch("storytelling_bot.watcher.event_watcher._fetch_gdelt_events", return_value=[]):
            with patch("storytelling_bot.watcher.event_watcher._send_slack_alert") as mock_slack:
                watcher = EventWatcher("stripe")
                new = watcher.poll()

    assert new == []
    mock_slack.assert_not_called()


def test_check_red_flags_filters_flagged_events():
    watcher = EventWatcher("stripe")
    events = [
        {"title": "Stripe raises funding", "summary": "Series D announced"},
        {"title": "Founder placed on OFAC SDN list", "summary": "Sanctions enforcement"},
        {"title": "New product launch", "summary": "Payments API"},
    ]
    flagged = watcher.check_red_flags(events)
    assert len(flagged) == 1
    assert "OFAC" in flagged[0]["title"]
