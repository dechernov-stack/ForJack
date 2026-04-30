"""Tests for QuoteDecomposer: transcript → Fact list."""
from __future__ import annotations

from pathlib import Path

import pytest

from storytelling_bot.nodes.quote_decomposer import decompose_chunk, decompose_transcript
from storytelling_bot.schema import Fact, Layer

TRANSCRIPT_FIXTURE = Path(__file__).parent / "fixtures" / "liberman_podcast_transcript.txt"


def test_decompose_chunk_returns_facts():
    chunk = (
        "Мы основали Sibilant Interactive в 2005 году. "
        "Это был первый настоящий продукт компании. "
        "Архитектура решения строилась вокруг peer-сети."
    )
    facts = decompose_chunk(chunk, chunk_id=0, source_url="https://example.com/video", entity_name="David Liberman")
    assert len(facts) >= 1
    assert all(isinstance(f, Fact) for f in facts)


def test_decompose_chunk_sets_source_url():
    chunk = "Клиенты Libermans Co — это люди второго круга предпринимателей. Их challenge — рост."
    facts = decompose_chunk(chunk, chunk_id=2, source_url="https://youtube.com/watch?v=abc")
    for f in facts:
        assert "https://youtube.com/watch?v=abc" in f.source_url
        assert "chunk=2" in f.source_url


def test_decompose_chunk_has_metadata_tone():
    chunk = "Страх не добиться результата всегда был рядом. Но мечта о своём бизнесе была сильнее."
    facts = decompose_chunk(chunk, chunk_id=0, source_url="url://x")
    for f in facts:
        assert "tone" in f.metadata
        assert "chunk_id" in f.metadata


def test_decompose_chunk_text_max_500():
    long_sentence = "а" * 600
    facts = decompose_chunk(long_sentence + ". дополнение.", chunk_id=0, source_url="u://x")
    for f in facts:
        assert len(f.text) <= 500


def test_decompose_transcript_multiple_layers():
    transcript = TRANSCRIPT_FIXTURE.read_text(encoding="utf-8") if TRANSCRIPT_FIXTURE.exists() else (
        "Мы выросли в Москве в семье учёных. Детство сформировало наши ценности и мечты. "
        "Продукт Libermans Co — это инвестиционная экосистема. Архитектура строится вокруг peer-сети. "
        "Рынок AR-технологий только формировался в 2016 году. Регуляторная среда становится сложнее. "
        "Клиенты — люди второго круга. Момент выбора происходит, когда клиент один не может идти дальше. "
        "Карьера началась с Sibilant Interactive в 2005. Путь к экспертизе занял 10 лет. "
        "Наш социальный импакт — создание нового класса предпринимателей в России."
    )
    facts = decompose_transcript(
        transcript,
        source_url="https://youtube.com/watch?v=test",
        entity_name="David Liberman",
    )
    assert len(facts) >= 10
    layers_seen = {f.layer for f in facts}
    assert len(layers_seen) >= 4


def test_decompose_transcript_all_facts_have_layer():
    transcript = "Детство прошло в Москве. Карьера началась рано. Продукт стал успешным. Рынок вырос."
    facts = decompose_transcript(transcript, source_url="u://x")
    for f in facts:
        assert isinstance(f.layer, Layer)
        assert f.layer in list(Layer)


@pytest.mark.skipif(not TRANSCRIPT_FIXTURE.exists(), reason="fixture not found")
def test_fixture_transcript_10_plus_facts():
    transcript = TRANSCRIPT_FIXTURE.read_text(encoding="utf-8")
    facts = decompose_transcript(
        transcript,
        source_url="https://youtube.com/watch?v=liberman_podcast",
        entity_name="Liberman brothers",
    )
    assert len(facts) >= 10
    layers_seen = {f.layer for f in facts}
    assert len(layers_seen) >= 4


@pytest.mark.skipif(not TRANSCRIPT_FIXTURE.exists(), reason="fixture not found")
def test_fixture_citations_are_substrings_of_transcript():
    """Faithfulness: each fact.text must appear (approx) in the original transcript."""
    transcript = TRANSCRIPT_FIXTURE.read_text(encoding="utf-8")
    facts = decompose_transcript(transcript, source_url="u://x")
    # normalize newlines before checking (chunking may split mid-line)
    transcript_norm = " ".join(transcript.lower().split())
    for f in facts:
        words = f.text.lower().split()
        if len(words) >= 2:
            snippet = " ".join(words[:2])
            assert snippet in transcript_norm, f"Snippet not in transcript: {snippet!r}"
