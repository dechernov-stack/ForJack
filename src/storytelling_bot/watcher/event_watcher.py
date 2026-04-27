"""EventWatcher — monitors RSS feeds and GDELT for entity mentions.

Sends alert via Slack webhook (mock when SLACK_WEBHOOK_URL not set).
Deduplicates events by URL + date so alerts are not repeated.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

try:
    import feedparser
except ImportError:
    feedparser = None  # type: ignore[assignment]

log = logging.getLogger(__name__)

_STATE_DIR = Path("data/watcher")
_GDELT_URL = "https://api.gdeltproject.org/api/v2/doc/doc"

# Default RSS feeds to monitor for entity news
_DEFAULT_RSS_FEEDS = [
    "https://feeds.bloomberg.com/technology/news.rss",
    "https://techcrunch.com/feed/",
    "https://news.crunchbase.com/feed/",
    "https://venturebeat.com/feed/",
]


# ── deduplication ─────────────────────────────────────────────────────────────

def _event_id(url: str, date: str) -> str:
    return hashlib.sha256(f"{url}::{date}".encode()).hexdigest()[:16]


def _load_seen(entity_id: str) -> set[str]:
    path = _STATE_DIR / entity_id / "seen.json"
    if path.exists():
        try:
            return set(json.loads(path.read_text()))
        except Exception:
            return set()
    return set()


def _save_seen(entity_id: str, seen: set[str]) -> None:
    path = _STATE_DIR / entity_id / "seen.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sorted(seen)), encoding="utf-8")


# ── Slack alert ───────────────────────────────────────────────────────────────

def _send_slack_alert(entity_id: str, events: List[Dict[str, Any]]) -> None:
    """Post alert to Slack. Logs mock message when SLACK_WEBHOOK_URL not set."""
    webhook_url = os.environ.get("SLACK_WEBHOOK_URL", "")
    if not events:
        return

    lines = [f"*[EventWatcher]* {len(events)} new event(s) for *{entity_id}*:"]
    for ev in events[:5]:
        lines.append(f"• <{ev['url']}|{ev['title'][:80]}> ({ev['date']})")

    payload = {"text": "\n".join(lines)}

    if not webhook_url or webhook_url == "mock":
        log.info("[MOCK SLACK ALERT] %s", payload["text"])
        return

    try:
        resp = httpx.post(webhook_url, json=payload, timeout=10)
        if resp.status_code != 200:
            log.warning("Slack webhook returned %d", resp.status_code)
    except Exception as e:
        log.warning("Slack alert failed: %s", e)


# ── RSS fetching ──────────────────────────────────────────────────────────────

def _fetch_rss_events(entity_id: str, feeds: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """Fetch RSS feeds and filter entries that mention entity_id."""
    if feedparser is None:
        log.warning("feedparser not installed — skipping RSS")
        return []

    feeds = feeds or _DEFAULT_RSS_FEEDS
    name = entity_id.replace("-", " ").lower()
    events = []

    for feed_url in feeds:
        try:
            parsed = feedparser.parse(feed_url)
            for entry in parsed.entries:
                title = (entry.get("title") or "").strip()
                summary = (entry.get("summary") or entry.get("description") or "").strip()
                link = entry.get("link") or feed_url
                pub_date = entry.get("published", "")

                # Only keep entries that mention the entity
                combined = (title + " " + summary).lower()
                if name not in combined and entity_id.lower() not in combined:
                    continue

                events.append({
                    "source": "rss",
                    "url": link,
                    "title": title,
                    "summary": summary[:200],
                    "date": pub_date[:10] if pub_date else datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                })
        except Exception as e:
            log.warning("RSS fetch failed for %s: %s", feed_url, e)

    return events


# ── GDELT fetching ────────────────────────────────────────────────────────────

def _fetch_gdelt_events(entity_id: str, days: int = 1) -> List[Dict[str, Any]]:
    """Fetch GDELT articles mentioning entity in the last N days."""
    name = entity_id.replace("-", " ")
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)

    params = {
        "query": f'"{name}"',
        "mode": "ArtList",
        "maxrecords": 10,
        "startdatetime": start.strftime("%Y%m%d%H%M%S"),
        "enddatetime": end.strftime("%Y%m%d%H%M%S"),
        "format": "json",
    }
    try:
        resp = httpx.get(_GDELT_URL, params=params, timeout=15)
        if resp.status_code != 200:
            return []
        data = resp.json()
    except Exception as e:
        log.warning("GDELT watcher fetch failed: %s", e)
        return []

    events = []
    for art in data.get("articles") or []:
        url = art.get("url", "")
        title = (art.get("title") or "").strip()
        seendate = art.get("seendate", "")
        if not url or not title:
            continue
        date = seendate[:8] if len(seendate) >= 8 else datetime.now(timezone.utc).strftime("%Y%m%d")
        date_fmt = f"{date[:4]}-{date[4:6]}-{date[6:8]}" if len(date) == 8 else date
        events.append({
            "source": "gdelt",
            "url": url,
            "title": title,
            "date": date_fmt,
            "tone": art.get("tone", ""),
        })
    return events


# ── Public watcher class ──────────────────────────────────────────────────────

class EventWatcher:
    """Polls RSS + GDELT for an entity and sends Slack alerts for new events."""

    def __init__(
        self,
        entity_id: str,
        rss_feeds: Optional[List[str]] = None,
        alert_on_red_flag: bool = True,
    ) -> None:
        self.entity_id = entity_id
        self.rss_feeds = rss_feeds
        self.alert_on_red_flag = alert_on_red_flag

    def poll(self, gdelt_days: int = 1) -> List[Dict[str, Any]]:
        """
        Poll all sources. Return list of NEW events (not seen before).
        Sends Slack alert if new events found.
        """
        seen = _load_seen(self.entity_id)
        all_events = []
        all_events.extend(_fetch_rss_events(self.entity_id, self.rss_feeds))
        all_events.extend(_fetch_gdelt_events(self.entity_id, days=gdelt_days))

        new_events = []
        for ev in all_events:
            eid = _event_id(ev["url"], ev.get("date", ""))
            if eid not in seen:
                seen.add(eid)
                new_events.append(ev)

        _save_seen(self.entity_id, seen)

        if new_events:
            _send_slack_alert(self.entity_id, new_events)

        log.info(
            "EventWatcher[%s]: %d total events, %d new",
            self.entity_id, len(all_events), len(new_events),
        )
        return new_events

    def check_red_flags(self, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Filter events that may contain red flag signals (keyword-based)."""
        from storytelling_bot.sanctions.checker import _check_keyword_rules  # noqa: PLC0415
        flagged = []
        for ev in events:
            text = ev.get("title", "") + " " + ev.get("summary", "")
            if _check_keyword_rules(text):
                flagged.append(ev)
        return flagged
