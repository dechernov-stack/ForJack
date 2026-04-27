"""End-to-end pipeline tests.

Task 10: Anthropic as primary target, Theranos as regression.
Both run with LLM_PROVIDER=mock (fast, no real API calls).
The real-API results are verified via the JSON reports already generated.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from storytelling_bot.graph import build_graph
from storytelling_bot.schema import Flag, State


# ── Mock pipeline: both entities ──────────────────────────────────────────────

def _run_entity(entity_id: str) -> State:
    """Run full LangGraph pipeline with mock LLM."""
    os.environ["LLM_PROVIDER"] = "mock"
    state = State(entity_id=entity_id)
    graph = build_graph()
    return graph.run(state)


def test_anthropic_pipeline_produces_facts():
    """Anthropic pipeline: must collect facts, make a decision, no auto-terminate."""
    from storytelling_bot.collectors.base import DEMO_CORPUS
    from storytelling_bot.schema import SourceType

    original = DEMO_CORPUS.get("anthropic", [])
    DEMO_CORPUS["anthropic"] = [
        {
            "source_type": SourceType.ONLINE_RESEARCH,
            "url": "https://anthropic.com/about",
            "captured_at": "2026-01-01",
            "text": "Anthropic is an AI safety company founded in 2021 by Dario Amodei and Daniela Amodei.",
            "entity_focus": "anthropic",
        },
        {
            "source_type": SourceType.ONLINE_RESEARCH,
            "url": "https://techcrunch.com/anthropic",
            "captured_at": "2026-02-01",
            "text": "Anthropic raised $7.3B in funding from Google and Amazon. The company focuses on AI safety research.",
            "entity_focus": "anthropic",
        },
    ]
    try:
        final = _run_entity("anthropic")
        assert len(final.facts) > 0, "Expected facts for anthropic"
        assert final.decision.get("recommendation") in ("continue", "watch", "pause")
        assert final.decision.get("human_approval_required") is True
    finally:
        DEMO_CORPUS["anthropic"] = original


def test_theranos_pipeline_terminates():
    """Theranos pipeline (mock): decision must be terminate or pause due to fraud keywords."""
    # Load theranos demo fact with fraud keywords into DEMO_CORPUS temporarily
    from storytelling_bot.collectors.base import DEMO_CORPUS
    from storytelling_bot.schema import SourceType

    original = DEMO_CORPUS.get("theranos", [])
    DEMO_CORPUS["theranos"] = [
        {
            "source_type": SourceType.ONLINE_RESEARCH,
            "url": "https://sec.gov/theranos-fraud",
            "captured_at": "2018-03-01",
            "text": "Elizabeth Holmes convicted of criminal fraud. SEC enforcement action confirmed.",
            "entity_focus": "theranos",
        },
        {
            "source_type": SourceType.ONLINE_RESEARCH,
            "url": "https://doj.gov/theranos-indictment",
            "captured_at": "2018-06-01",
            "text": "Criminal indictment filed against Theranos founder for wire fraud Ponzi scheme.",
            "entity_focus": "theranos",
        },
    ]
    try:
        final = _run_entity("theranos")
        red_facts = [f for f in final.facts if f.flag == Flag.RED]
        assert len(red_facts) >= 1, "Expected at least 1 red flag for theranos"
        assert final.decision.get("recommendation") in ("terminate", "pause")
    finally:
        DEMO_CORPUS["theranos"] = original


def test_pipeline_human_approval_always_required():
    """Human approval must be required regardless of entity or decision."""
    final = _run_entity("accumulator")
    assert final.decision.get("human_approval_required") is True


def test_pipeline_all_facts_have_provenance():
    """Every fact must have source_url and captured_at."""
    final = _run_entity("accumulator")
    for fact in final.facts:
        assert fact.source_url, f"Missing source_url: {fact.text[:50]}"
        assert fact.captured_at, f"Missing captured_at: {fact.text[:50]}"


def test_pipeline_metrics_populated():
    """Metrics must include fact_count, coverage_pct, decision fields."""
    final = _run_entity("accumulator")
    assert "fact_count" in final.metrics
    assert "coverage_pct" in final.metrics
    assert final.metrics["fact_count"] == len(final.facts)


# ── Verify real-API reports (generated in Task 10 setup) ─────────────────────

_REPORTS_DIR = Path(__file__).parent.parent / "reports"


@pytest.mark.skipif(
    not (_REPORTS_DIR / "anthropic.json").exists(),
    reason="anthropic.json report not generated yet",
)
def test_anthropic_report_no_red_flags():
    """Pre-generated Anthropic report must have no red flags."""
    with open(_REPORTS_DIR / "anthropic.json") as f:
        data = json.load(f)
    facts = data.get("facts", [])
    red_count = sum(1 for f in facts if f["flag"] == "red")
    assert red_count == 0, f"Unexpected red flags in Anthropic report: {red_count}"
    assert len(facts) >= 5, "Expected at least 5 facts in Anthropic report"


@pytest.mark.skipif(
    not (_REPORTS_DIR / "theranos.json").exists(),
    reason="theranos.json report not generated yet",
)
def test_theranos_report_terminates():
    """Pre-generated Theranos report must have red flags and terminate decision."""
    with open(_REPORTS_DIR / "theranos.json") as f:
        data = json.load(f)
    facts = data.get("facts", [])
    red_count = sum(1 for f in facts if f["flag"] == "red")
    decision = data.get("decision", {})
    assert red_count >= 3, f"Expected ≥3 red flags for Theranos, got {red_count}"
    assert decision.get("recommendation") == "terminate", (
        f"Expected 'terminate' for Theranos, got {decision.get('recommendation')}"
    )
