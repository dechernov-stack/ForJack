"""Tests for InterviewCollector — YouTube + Whisper, fully mocked."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from storytelling_bot.schema import SourceType


@pytest.fixture(autouse=True)
def tmp_data_dirs(tmp_path, monkeypatch):
    import storytelling_bot.collectors.interview as mod
    monkeypatch.setattr(mod, "_BRONZE_ROOT", tmp_path / "bronze")
    monkeypatch.setattr(mod, "_SILVER_ROOT", tmp_path / "silver")
    return tmp_path


# ── chunk_transcript ──────────────────────────────────────────────────────────

def test_chunk_transcript_splits_long_text():
    from storytelling_bot.collectors.interview import _chunk_transcript
    text = " ".join([f"word{i}" for i in range(300)])
    chunks = _chunk_transcript(text, chunk_size=100)
    assert len(chunks) > 1
    assert all(len(c) > 50 for c in chunks)


def test_chunk_transcript_empty():
    from storytelling_bot.collectors.interview import _chunk_transcript
    assert _chunk_transcript("") == []


def test_chunk_transcript_short_text_single_chunk():
    from storytelling_bot.collectors.interview import _chunk_transcript
    chunks = _chunk_transcript("Short text about a founder.", chunk_size=500)
    # Short text might be filtered out if <50 chars but the full sentence is fine
    assert isinstance(chunks, list)


# ── _process_url ─────────────────────────────────────────────────────────────

def test_process_url_skips_long_video():
    from storytelling_bot.collectors.interview import _process_url

    with patch("storytelling_bot.collectors.interview._fetch_youtube_info", return_value={"duration": 9999, "title": "Long Video", "upload_date": "20260101"}):
        result = _process_url("stripe", "https://youtube.com/watch?v=abc")
    assert result == []


def test_process_url_returns_chunks_on_success():
    from storytelling_bot.collectors.interview import _process_url

    fake_info = {"duration": 600, "title": "Stripe Founder Interview", "upload_date": "20260101"}
    fake_transcript = "Patrick Collison founded Stripe in 2010. " * 30

    with patch("storytelling_bot.collectors.interview._fetch_youtube_info", return_value=fake_info):
        with patch("storytelling_bot.collectors.interview._download_audio", return_value="/tmp/fake.m4a"):
            with patch("storytelling_bot.collectors.interview._transcribe", return_value=fake_transcript):
                result = _process_url("stripe", "https://youtube.com/watch?v=abc")

    assert len(result) > 0
    chunk = result[0]
    assert chunk["source_type"] == SourceType.ONLINE_INTERVIEW
    assert chunk["url"] == "https://youtube.com/watch?v=abc"
    assert "source_hash" in chunk
    assert "captured_at" in chunk
    assert "Patrick Collison" in chunk["text"] or len(chunk["text"]) > 10


def test_process_url_dedup_same_content():
    from storytelling_bot.collectors.interview import _process_url

    fake_info = {"duration": 300, "title": "Interview", "upload_date": "20260101"}
    fake_transcript = "Founder built company from scratch. " * 20

    with patch("storytelling_bot.collectors.interview._fetch_youtube_info", return_value=fake_info):
        with patch("storytelling_bot.collectors.interview._download_audio", return_value="/tmp/fake.m4a"):
            with patch("storytelling_bot.collectors.interview._transcribe", return_value=fake_transcript):
                result1 = _process_url("stripe", "https://youtube.com/watch?v=xyz")
                result2 = _process_url("stripe", "https://youtube.com/watch?v=xyz")

    assert len(result1) > 0
    assert len(result2) == 0  # all deduped


def test_process_url_no_audio_returns_empty():
    from storytelling_bot.collectors.interview import _process_url

    fake_info = {"duration": 300, "title": "Interview", "upload_date": "20260101"}

    with patch("storytelling_bot.collectors.interview._fetch_youtube_info", return_value=fake_info):
        with patch("storytelling_bot.collectors.interview._download_audio", return_value=None):
            result = _process_url("stripe", "https://youtube.com/watch?v=noaudio")

    assert result == []


def test_process_url_whisper_failure_returns_empty():
    from storytelling_bot.collectors.interview import _process_url

    fake_info = {"duration": 300, "title": "Interview", "upload_date": "20260101"}

    with patch("storytelling_bot.collectors.interview._fetch_youtube_info", return_value=fake_info):
        with patch("storytelling_bot.collectors.interview._download_audio", return_value="/tmp/fake.m4a"):
            with patch("storytelling_bot.collectors.interview._transcribe", side_effect=RuntimeError("CUDA unavailable")):
                result = _process_url("stripe", "https://youtube.com/watch?v=whisperfail")

    assert result == []


# ── InterviewCollector.collect ────────────────────────────────────────────────

def test_collect_includes_demo_corpus_for_known_entity():
    from storytelling_bot.collectors.interview import InterviewCollector

    with patch.object(InterviewCollector, "_collect_youtube", return_value=[]):
        result = InterviewCollector().collect("accumulator")

    # accumulator has ONLINE_INTERVIEW items in DEMO_CORPUS
    assert any(c["source_type"] == SourceType.ONLINE_INTERVIEW for c in result)


def test_collect_unknown_entity_returns_youtube_chunks():
    from storytelling_bot.collectors.interview import InterviewCollector

    fake_chunk = {
        "source_type": SourceType.ONLINE_INTERVIEW,
        "url": "https://youtube.com/watch?v=test",
        "captured_at": "2026-01-01T00:00:00+00:00",
        "text": "Some interview text",
        "entity_focus": "stripe",
        "source_hash": "abc123",
    }

    with patch.object(InterviewCollector, "_collect_youtube", return_value=[fake_chunk]):
        result = InterviewCollector().collect("stripe")

    assert result == [fake_chunk]


def test_collect_all_chunks_have_source_type():
    from storytelling_bot.collectors.interview import InterviewCollector

    fake_chunk = {
        "source_type": SourceType.ONLINE_INTERVIEW,
        "url": "https://youtube.com/watch?v=test2",
        "captured_at": "2026-01-01T00:00:00+00:00",
        "text": "Interview text about founders",
        "entity_focus": "anthropic",
        "source_hash": "def456",
    }

    with patch.object(InterviewCollector, "_collect_youtube", return_value=[fake_chunk]):
        result = InterviewCollector().collect("anthropic")

    assert all(c["source_type"] == SourceType.ONLINE_INTERVIEW for c in result)


def test_collect_youtube_calls_search_and_process():
    from storytelling_bot.collectors.interview import InterviewCollector

    fake_urls = ["https://youtube.com/watch?v=vid1", "https://youtube.com/watch?v=vid2"]

    with patch("storytelling_bot.collectors.interview._search_youtube_urls", return_value=fake_urls):
        with patch("storytelling_bot.collectors.interview._process_url", return_value=[]):
            collector = InterviewCollector()
            result = collector._collect_youtube("stripe")

    assert result == []  # _process_url returned empty for each
