"""Mock collector tests."""
from __future__ import annotations

from storytelling_bot.collectors.archival import ArchivalCollector
from storytelling_bot.collectors.interview import InterviewCollector
from storytelling_bot.collectors.research import ResearchCollector
from storytelling_bot.graph import build_graph
from storytelling_bot.schema import SourceType, State


def test_interview_collector_returns_chunks():
    chunks = InterviewCollector().collect("accumulator")
    assert len(chunks) > 0
    assert all(c["source_type"] == SourceType.ONLINE_INTERVIEW for c in chunks)


def test_research_collector_returns_chunks():
    chunks = ResearchCollector().collect("accumulator")
    assert len(chunks) > 0
    assert all(c["source_type"] == SourceType.ONLINE_RESEARCH for c in chunks)


def test_archival_collector_returns_chunks():
    chunks = ArchivalCollector().collect("accumulator")
    assert len(chunks) > 0
    assert all(c["source_type"] == SourceType.ARCHIVAL for c in chunks)


def test_unknown_entity_returns_empty():
    assert InterviewCollector().collect("nonexistent_xyz") == []
    assert ResearchCollector().collect("nonexistent_xyz") == []


def test_all_facts_have_provenance():
    state = State(entity_id="accumulator")
    final = build_graph().run(state)
    for f in final.facts:
        assert f.source_url, f"Fact without provenance: {f.text[:50]}"


def test_full_pipeline_produces_decision():
    state = State(entity_id="accumulator")
    final = build_graph().run(state)
    assert final.decision["recommendation"] in {"continue", "watch", "pause", "terminate"}
    assert final.metrics["fact_count"] > 0


def test_human_approval_flag():
    state = State(entity_id="accumulator")
    final = build_graph().run(state)
    assert final.decision.get("human_approval_required") is True
