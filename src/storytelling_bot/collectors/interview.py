"""InterviewCollector — YouTube download + faster-whisper (CPU) transcription."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from storytelling_bot.collectors.base import DEMO_CORPUS
from storytelling_bot.collectors.lake import upload_bronze as _minio_bronze
from storytelling_bot.collectors.lake import upload_silver as _minio_silver
from storytelling_bot.schema import SourceType

log = logging.getLogger(__name__)

_BRONZE_ROOT = Path("data/bronze")
_SILVER_ROOT = Path("data/silver")

# Whisper model size: tiny for speed on CPU (override with WHISPER_MODEL env var)
_WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "tiny")

# Max video length in seconds to attempt transcription (avoid huge downloads)
_MAX_DURATION_SEC = int(os.environ.get("WHISPER_MAX_DURATION", "1800"))  # 30 min


# ── helpers ──────────────────────────────────────────────────────────────────

def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _write_bronze(entity_id: str, sha: str, raw: dict[str, Any]) -> bool:
    path = _BRONZE_ROOT / entity_id / "interview" / f"{sha}.json"
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
    _minio_bronze(entity_id, "interview", sha, raw)
    return True


def _write_silver(entity_id: str, sha: str, record: dict[str, Any]) -> None:
    path = _SILVER_ROOT / entity_id / "interview" / f"{sha}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    _minio_silver(entity_id, "interview", sha, record)


# ── YouTube metadata & audio ──────────────────────────────────────────────────

def _fetch_youtube_info(url: str) -> dict[str, Any] | None:
    """Return yt-dlp info dict without downloading (flat extraction)."""
    try:
        import yt_dlp
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "extract_flat": False,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            return ydl.extract_info(url, download=False)
    except Exception as e:
        log.warning("yt-dlp info failed for %s: %s", url, e)
        return None


def _download_audio(url: str, out_dir: str) -> str | None:
    """Download best audio to out_dir, return path to m4a/webm/opus file."""
    try:
        import yt_dlp
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "format": "bestaudio[ext=m4a]/bestaudio/best",
            "outtmpl": os.path.join(out_dir, "%(id)s.%(ext)s"),
            "postprocessors": [],  # no ffmpeg required
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if info:
                filename = ydl.prepare_filename(info)
                if os.path.exists(filename):
                    return filename
                # Try with actual ext
                for f in Path(out_dir).iterdir():
                    if info.get("id", "") in f.name:
                        return str(f)
    except Exception as e:
        log.warning("yt-dlp download failed for %s: %s", url, e)
    return None


# ── Whisper transcription ─────────────────────────────────────────────────────

def _transcribe(audio_path: str) -> str:
    """Transcribe audio file via faster-whisper (CPU). Returns full text."""
    from faster_whisper import WhisperModel
    model = WhisperModel(_WHISPER_MODEL, device="cpu", compute_type="int8")
    segments, _ = model.transcribe(audio_path, beam_size=1)
    return " ".join(seg.text.strip() for seg in segments)


# ── YouTube search ────────────────────────────────────────────────────────────

def _search_youtube_urls(entity_id: str, max_results: int = 5) -> list[str]:
    """Search YouTube for entity interviews. Returns list of video URLs."""
    try:
        import yt_dlp
        query = f"{entity_id.replace('-', ' ')} founder interview"
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": True,
            "playlistend": max_results,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            result = ydl.extract_info(f"ytsearch{max_results}:{query}", download=False)
            entries = result.get("entries", []) if result else []
            return [
                f"https://www.youtube.com/watch?v={e['id']}"
                for e in entries
                if e and e.get("id")
            ]
    except Exception as e:
        log.warning("YouTube search failed for %s: %s", entity_id, e)
        return []


# ── Chunk text into Fact-sized pieces ────────────────────────────────────────

def _chunk_transcript(text: str, chunk_size: int = 500) -> list[str]:
    """Split long transcript into overlapping chunks (~500 chars each)."""
    words = text.split()
    if not words:
        return []
    chunks, current = [], []
    for word in words:
        current.append(word)
        joined = " ".join(current)
        if len(joined) >= chunk_size:
            chunks.append(joined.strip())
            current = current[-20:]  # 20-word overlap
    if current:
        chunks.append(" ".join(current).strip())
    return [c for c in chunks if len(c) > 50]


# ── Main collection logic ─────────────────────────────────────────────────────

def _process_url(entity_id: str, url: str) -> list[dict[str, Any]]:
    """Fetch, transcribe, chunk one YouTube video. Returns Silver chunks."""
    info = _fetch_youtube_info(url)
    if not info:
        return []

    duration = info.get("duration") or 0
    if duration > _MAX_DURATION_SEC:
        log.info("Skipping %s — duration %ds > max %ds", url, duration, _MAX_DURATION_SEC)
        return []

    title = info.get("title", "")
    upload_date = info.get("upload_date", "")  # YYYYMMDD
    captured_at = (
        f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:]}T00:00:00+00:00"
        if upload_date and len(upload_date) == 8
        else _now_iso()
    )

    with tempfile.TemporaryDirectory() as tmp:
        audio_path = _download_audio(url, tmp)
        if not audio_path:
            return []
        try:
            transcript = _transcribe(audio_path)
        except Exception as e:
            log.warning("Whisper failed for %s: %s", url, e)
            return []

    if not transcript.strip():
        return []

    chunks_text = _chunk_transcript(transcript)
    results = []

    for i, chunk in enumerate(chunks_text):
        raw = {"source": "youtube", "url": url, "title": title, "chunk_index": i, "text": chunk}
        sha = _sha256(json.dumps(raw, sort_keys=True))
        is_new = _write_bronze(entity_id, sha, raw)
        if not is_new:
            continue  # dedup

        record = {
            "source_type": SourceType.ONLINE_INTERVIEW,
            "url": url,
            "captured_at": captured_at,
            "text": chunk,
            "entity_focus": entity_id,
            "source_hash": sha,
            "metadata": {"title": title, "chunk_index": i},
        }
        _write_silver(entity_id, sha, record)
        results.append(record)

    return results


# ── Public collector class ────────────────────────────────────────────────────

class InterviewCollector:
    source_type = SourceType.ONLINE_INTERVIEW

    def collect(self, entity_id: str) -> list[dict[str, Any]]:
        # First return any demo corpus items (for known entities like accumulator)
        demo = DEMO_CORPUS.get(entity_id, [])
        demo_chunks = [c for c in demo if c["source_type"] == self.source_type]

        # Then try real YouTube collection
        yt_chunks = self._collect_youtube(entity_id)

        return demo_chunks + yt_chunks

    def _collect_youtube(self, entity_id: str) -> list[dict[str, Any]]:
        urls = _search_youtube_urls(entity_id, max_results=3)
        if not urls:
            return []

        results = []
        for url in urls:
            try:
                chunks = _process_url(entity_id, url)
                results.extend(chunks)
            except Exception as e:
                log.warning("Failed processing %s: %s", url, e)
        return results
