"""ResearchCollector — Tavily + GDELT + SEC EDGAR with Bronze/Silver persistence."""
from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

try:
    from tavily import TavilyClient
except ImportError:
    TavilyClient = None  # type: ignore[assignment,misc]

from storytelling_bot.collectors.base import DEMO_CORPUS
from storytelling_bot.collectors.lake import upload_bronze as _minio_bronze
from storytelling_bot.collectors.lake import upload_silver as _minio_silver
from storytelling_bot.schema import SourceType

log = logging.getLogger(__name__)

_BRONZE_ROOT = Path("data/bronze")
_SILVER_ROOT = Path("data/silver")

# ── helpers ─────────────────────────────────────────────────────────────────

def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _write_bronze(entity_id: str, source: str, raw: dict[str, Any]) -> str | None:
    """Persist raw dict to Bronze. Returns sha if new, None if duplicate."""
    content = json.dumps(raw, ensure_ascii=False, sort_keys=True)
    sha = _sha256(content)
    path = _BRONZE_ROOT / entity_id / source / f"{sha}.json"
    if path.exists():
        return None  # duplicate
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    _minio_bronze(entity_id, source, sha, raw)
    return sha


def _write_silver(entity_id: str, source: str, sha: str, record: dict[str, Any]) -> None:
    path = _SILVER_ROOT / entity_id / source / f"{sha}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    _minio_silver(entity_id, source, sha, record)


def _normalize(entity_id: str, source: str, url: str, text: str, captured_at: str) -> dict[str, Any]:
    return {
        "source_type": SourceType.ONLINE_RESEARCH,
        "url": url,
        "captured_at": captured_at,
        "text": text,
        "entity_focus": entity_id,
        "source_hash": _sha256(text),
    }


# ── Wikipedia alias fallback ─────────────────────────────────────────────────

def _get_aliases(entity_id: str) -> list[str]:
    """Fetch redirects from Wikipedia as aliases. Non-fatal on error."""
    try:
        name = entity_id.replace("-", " ").title()
        url = "https://en.wikipedia.org/w/api.php"
        resp = httpx.get(
            url,
            params={"action": "query", "titles": name, "redirects": 1, "format": "json"},
            timeout=10,
        )
        data = resp.json()
        redirects = data.get("query", {}).get("redirects", [])
        return [r["to"] for r in redirects[:3]]
    except Exception:
        return []


# ── Tavily ───────────────────────────────────────────────────────────────────

class _TavilyRateLimit(Exception):
    pass


@retry(
    retry=retry_if_exception_type(_TavilyRateLimit),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    stop=stop_after_attempt(4),
    reraise=True,
)
def _tavily_search(client, query: str, max_results: int = 10) -> list[dict]:
    try:
        result = client.search(query=query, max_results=max_results, search_depth="basic")
        return result.get("results", [])
    except Exception as e:
        msg = str(e).lower()
        if "429" in msg or "rate" in msg or "quota" in msg:
            raise _TavilyRateLimit(str(e))
        log.warning("Tavily error for %r: %s", query, e)
        return []


def _collect_tavily(entity_id: str) -> list[dict[str, Any]]:
    if TavilyClient is None:
        log.warning("tavily-python not installed — skipping Tavily")
        return []
    api_key = os.environ.get("TAVILY_API_KEY", "")
    if not api_key:
        log.warning("TAVILY_API_KEY not set — skipping Tavily")
        return []

    client = TavilyClient(api_key=api_key)

    aliases = _get_aliases(entity_id)
    queries = [entity_id.replace("-", " "), *aliases[:2]]

    chunks = []
    seen_urls: set[str] = set()

    from storytelling_bot import langfuse_ctx
    with langfuse_ctx.span("collector.research.tavily", input_data={"entity_id": entity_id, "queries": queries}):
        for q in queries:
            for item in _tavily_search(client, q):
                url = item.get("url", "")
                content = (item.get("content") or item.get("raw_content") or "").strip()
                if not content or url in seen_urls:
                    continue
                seen_urls.add(url)

                raw = {"source": "tavily", "query": q, "url": url, "content": content}
                sha = _write_bronze(entity_id, "tavily", raw)
                if sha is None:
                    continue  # duplicate

                record = _normalize(entity_id, "tavily", url, content, _now_iso())
                _write_silver(entity_id, "tavily", sha, record)
                chunks.append(record)

    log.info("Tavily collected %d chunks for %s", len(chunks), entity_id)
    return chunks


# ── GDELT ────────────────────────────────────────────────────────────────────

def _collect_gdelt(entity_id: str) -> list[dict[str, Any]]:
    from storytelling_bot import langfuse_ctx
    name = entity_id.replace("-", " ")
    end = datetime.now(UTC)
    start = end - timedelta(days=30)
    query = f'"{name}"'

    url = "https://api.gdeltproject.org/api/v2/doc/doc"
    params = {
        "query": query,
        "mode": "ArtList",
        "maxrecords": 25,
        "startdatetime": start.strftime("%Y%m%d%H%M%S"),
        "enddatetime": end.strftime("%Y%m%d%H%M%S"),
        "format": "json",
    }

    with langfuse_ctx.span("collector.research.gdelt", input_data={"entity_id": entity_id, "query": query}):
        try:
            resp = httpx.get(url, params=params, timeout=20)
            if resp.status_code != 200:
                log.warning("GDELT returned %d for %s", resp.status_code, entity_id)
                return []
            data = resp.json()
        except Exception as e:
            log.warning("GDELT fetch failed for %s: %s", entity_id, e)
            return []

        articles = data.get("articles") or []
        chunks = []

        for art in articles:
            art_url = art.get("url", "")
            title = (art.get("title") or "").strip()
            if not title or not art_url:
                continue

            tone = art.get("tone", "")
            seendate = art.get("seendate", "")
            text = f"{title}. [tone={tone}, date={seendate}]"

            raw = {"source": "gdelt", "url": art_url, "title": title, "tone": tone, "seendate": seendate}
            sha = _write_bronze(entity_id, "gdelt", raw)
            if sha is None:
                continue

            record = _normalize(entity_id, "gdelt", art_url, text, _now_iso())
            _write_silver(entity_id, "gdelt", sha, record)
            chunks.append(record)

    log.info("GDELT collected %d chunks for %s", len(chunks), entity_id)
    return chunks


# ── SEC EDGAR ────────────────────────────────────────────────────────────────

def _collect_sec(entity_id: str) -> list[dict[str, Any]]:
    """Try SEC EDGAR. Silently returns [] for private companies (no CIK found)."""
    dl_dir = Path("data/bronze") / entity_id / "sec_raw"
    dl_dir.mkdir(parents=True, exist_ok=True)

    name = entity_id.replace("-", " ").title()
    # First check if CIK exists for this entity
    cik_url = f"https://efts.sec.gov/LATEST/search-index?q=%22{name.replace(' ', '+')}%22&dateRange=custom&startdt=2010-01-01&forms=D"
    try:
        resp = httpx.get(cik_url, timeout=10, headers={"User-Agent": "storytelling-bot de.chernov@gmail.com"})
        data = resp.json()
        hits = data.get("hits", {}).get("hits", [])
        if not hits:
            log.info("SEC: no filings found for %s — likely private", name)
            return []
    except Exception:
        return []

    chunks = []
    for hit in hits[:10]:
        src = hit.get("_source", {})
        form_type = src.get("form_type", "D")
        filed_at = src.get("file_date", _now_iso()[:10])
        entity_name = src.get("display_names", [name])[0] if src.get("display_names") else name
        text = f"{entity_name} filed {form_type} with SEC on {filed_at}."

        raw = {"source": "sec", "form_type": form_type, "filed_at": filed_at, "entity": entity_name}
        sha = _write_bronze(entity_id, "sec", raw)
        if sha is None:
            continue

        sec_url = f"https://efts.sec.gov/LATEST/search-index?q=%22{name}%22&forms={form_type}"
        record = _normalize(entity_id, "sec", sec_url, text, filed_at + "T00:00:00+00:00")
        _write_silver(entity_id, "sec", sha, record)
        chunks.append(record)

    log.info("SEC collected %d chunks for %s", len(chunks), entity_id)
    return chunks


# ── Main collector ───────────────────────────────────────────────────────────

class ResearchCollector:
    source_type = SourceType.ONLINE_RESEARCH

    def collect(self, entity_id: str) -> list[dict[str, Any]]:
        # Always include demo corpus items for known entities
        demo = DEMO_CORPUS.get(entity_id, [])
        demo_chunks = [c for c in demo if c["source_type"] == self.source_type]

        live: list[dict[str, Any]] = []
        live.extend(_collect_tavily(entity_id))
        live.extend(_collect_gdelt(entity_id))
        live.extend(_collect_sec(entity_id))

        return demo_chunks + live
