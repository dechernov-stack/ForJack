"""Audio pipeline: URL → transcript → quote facts."""
from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path

from storytelling_bot.nodes.quote_decomposer import decompose_transcript
from storytelling_bot.schema import Fact

log = logging.getLogger(__name__)


def transcribe_url(url: str, *, device: str | None = None) -> str:
    """Download audio from URL and transcribe with faster-whisper.

    Returns empty string if yt-dlp or faster-whisper are not installed.
    """
    try:
        import yt_dlp
    except ImportError:
        log.warning("yt_dlp not installed — skipping transcription for %s", url)
        return ""

    try:
        from faster_whisper import WhisperModel
    except ImportError:
        log.warning("faster_whisper not installed — skipping transcription for %s", url)
        return ""

    model_size = os.environ.get("WHISPER_MODEL", "base")
    whisper_device = device or os.environ.get("WHISPER_DEVICE", "cpu")

    with tempfile.TemporaryDirectory() as tmp:
        audio_path = str(Path(tmp) / "audio.%(ext)s")
        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": audio_path,
            "quiet": True,
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
            }],
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
        except Exception as exc:
            log.error("yt_dlp download failed for %s: %s", url, exc)
            return ""

        mp3_files = list(Path(tmp).glob("*.mp3"))
        if not mp3_files:
            log.error("No audio file found after yt-dlp for %s", url)
            return ""

        model = WhisperModel(model_size, device=whisper_device)
        segments, _ = model.transcribe(str(mp3_files[0]))
        return " ".join(seg.text.strip() for seg in segments)


def run(
    url: str,
    *,
    entity_name: str = "",
    event_date: str = "",
    expert_profile=None,
    entity_card=None,
    transcript: str | None = None,
) -> list[Fact]:
    """Full audio pipeline: URL → transcript → Fact[].

    Pass `transcript` directly to skip yt-dlp/Whisper (for testing).
    """
    if transcript is None:
        transcript = transcribe_url(url)
    if not transcript:
        log.warning("Empty transcript for %s — returning 0 facts", url)
        return []

    log.info("AudioPipeline: %d chars transcript from %s", len(transcript), url)
    facts = decompose_transcript(
        transcript,
        source_url=url,
        event_date=event_date,
        entity_name=entity_name,
        expert_profile=expert_profile,
    )
    log.info("AudioPipeline: %d quote-facts extracted", len(facts))
    return facts
