"""ArchivalCollector — Wayback Machine CDX API + snapshot text extraction."""
from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from storytelling_bot.collectors.base import DEMO_CORPUS
from storytelling_bot.collectors.lake import upload_bronze as _minio_bronze
from storytelling_bot.collectors.lake import upload_silver as _minio_silver
from storytelling_bot.schema import SourceType

log = logging.getLogger(__name__)

_BRONZE_ROOT = Path("data/bronze")
_SILVER_ROOT = Path("data/silver")

# Wayback CDX API — returns list of captures for a URL prefix
_CDX_URL = "https://web.archive.org/cdx/search/cdx"
# Wayback content API — fetch snapshot text
_WB_BASE = "https://web.archive.org/web"

_MAX_SNAPSHOTS = 10  # per entity search


# ── helpers ──────────────────────────────────────────────────────────────────

def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _write_bronze(entity_id: str, sha: str, raw: dict[str, Any]) -> bool:
    path = _BRONZE_ROOT / entity_id / "wayback" / f"{sha}.json"
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
    _minio_bronze(entity_id, "wayback", sha, raw)
    return True


def _write_silver(entity_id: str, sha: str, record: dict[str, Any]) -> None:
    path = _SILVER_ROOT / entity_id / "wayback" / f"{sha}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    _minio_silver(entity_id, "wayback", sha, record)


def _strip_html(html: str) -> str:
    """Very light HTML → text: strip tags, collapse whitespace."""
    text = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()[:3000]  # cap at 3k chars


# ── CDX search ───────────────────────────────────────────────────────────────

class _WaybackRateLimit(Exception):
    pass


@retry(
    retry=retry_if_exception_type(_WaybackRateLimit),
    wait=wait_exponential(multiplier=2, min=4, max=60),
    stop=stop_after_attempt(3),
    reraise=True,
)
def _cdx_search(url_prefix: str, from_year: str = "2010", to_year: str = "2024") -> list[dict]:
    """Query CDX API for captures of url_prefix. Returns list of capture dicts."""
    params = {
        "url": url_prefix,
        "output": "json",
        "fl": "timestamp,original,statuscode,digest",
        "limit": str(_MAX_SNAPSHOTS),
        "from": f"{from_year}0101",
        "to": f"{to_year}1231",
        "filter": "statuscode:200",
        "collapse": "digest",  # deduplicate identical content
    }
    try:
        resp = httpx.get(_CDX_URL, params=params, timeout=15)
    except Exception as e:
        log.warning("CDX request failed: %s", e)
        return []

    if resp.status_code == 429:
        raise _WaybackRateLimit("Wayback CDX 429")
    if resp.status_code != 200:
        log.warning("CDX returned %d for %s", resp.status_code, url_prefix)
        return []

    try:
        rows = resp.json()
    except Exception:
        return []

    if not rows or len(rows) < 2:
        return []

    # First row is headers
    headers = rows[0]
    return [dict(zip(headers, row)) for row in rows[1:]]


# ── snapshot fetch ────────────────────────────────────────────────────────────

@retry(
    retry=retry_if_exception_type(_WaybackRateLimit),
    wait=wait_exponential(multiplier=2, min=4, max=60),
    stop=stop_after_attempt(2),
    reraise=False,
)
def _fetch_snapshot_text(timestamp: str, original_url: str) -> str | None:
    """Fetch Wayback snapshot and extract plain text (≤3000 chars)."""
    wb_url = f"{_WB_BASE}/{timestamp}if_/{original_url}"
    try:
        resp = httpx.get(wb_url, timeout=20, follow_redirects=True)
    except Exception as e:
        log.warning("Snapshot fetch failed %s: %s", wb_url, e)
        return None

    if resp.status_code == 429:
        raise _WaybackRateLimit("Wayback snapshot 429")
    if resp.status_code != 200:
        return None

    ct = resp.headers.get("content-type", "")
    if "text" not in ct and "html" not in ct:
        return None

    return _strip_html(resp.text)


# ── entity → URL candidates ───────────────────────────────────────────────────

def _build_url_candidates(entity_id: str) -> list[str]:
    """Generate URL prefixes to search in Wayback for a given entity."""
    name = entity_id.replace("-", "").lower()
    slug = entity_id.replace(" ", "-").lower()
    return [
        f"https://{name}.com/*",
        f"https://www.{name}.com/*",
        f"https://techcrunch.com/*{slug}*",
        f"https://crunchbase.com/organization/{slug}",
    ]


# ── main collection ───────────────────────────────────────────────────────────

def _collect_wayback(entity_id: str) -> list[dict[str, Any]]:
    candidates = _build_url_candidates(entity_id)
    results: list[dict[str, Any]] = []

    for url_pattern in candidates:
        try:
            captures = _cdx_search(url_pattern)
        except _WaybackRateLimit:
            log.warning("Wayback rate limit exceeded for %s — stopping", entity_id)
            break
        except Exception as e:
            log.warning("CDX error for %s: %s", url_pattern, e)
            continue

        for cap in captures[:3]:  # max 3 snapshots per URL pattern
            ts = cap.get("timestamp", "")
            orig = cap.get("original", "")
            if not ts or not orig:
                continue

            text = _fetch_snapshot_text(ts, orig)
            if not text or len(text) < 100:
                continue

            # Format event_date from CDX timestamp YYYYMMDDHHMMSS
            event_date = None
            if len(ts) >= 8:
                try:
                    event_date = f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}"
                except Exception:
                    pass

            raw = {"source": "wayback", "timestamp": ts, "original_url": orig, "text": text[:500]}
            sha = _sha256(json.dumps(raw, sort_keys=True))
            is_new = _write_bronze(entity_id, sha, raw)
            if not is_new:
                continue

            captured_at = (
                f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}T{ts[8:10]}:{ts[10:12]}:{ts[12:14]}+00:00"
                if len(ts) >= 14
                else _now_iso()
            )
            record: dict[str, Any] = {
                "source_type": SourceType.ARCHIVAL,
                "url": f"{_WB_BASE}/{ts}/{orig}",
                "captured_at": captured_at,
                "text": text,
                "entity_focus": entity_id,
                "source_hash": sha,
            }
            if event_date:
                record["event_date"] = event_date
            _write_silver(entity_id, sha, record)
            results.append(record)

    log.info("Wayback collected %d chunks for %s", len(results), entity_id)
    return results


# ── Public collector ──────────────────────────────────────────────────────────

class ArchivalCollector:
    source_type = SourceType.ARCHIVAL

    def collect(self, entity_id: str) -> list[dict[str, Any]]:
        demo = DEMO_CORPUS.get(entity_id, [])
        demo_chunks = [c for c in demo if c["source_type"] == self.source_type]
        live = _collect_wayback(entity_id)
        return demo_chunks + live
