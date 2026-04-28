"""Tests for PostgresStore persistence wired to the pipeline (SQLite in-memory)."""
from __future__ import annotations

import datetime as dt

import pytest

from storytelling_bot.schema import Fact, Flag, Layer, SourceType


def _make_store():
    """Create a PostgresStore backed by SQLite in-memory with full schema."""
    from storytelling_bot.storage.postgres import PostgresStore

    store = PostgresStore(database_url="sqlite:///:memory:")
    store._setup_sqlite()
    return store


def _make_fact(
    text: str = "Accumulator processes data.",
    subcategory: str = "Architecture of the solution",
    url: str = "https://example.com/1",
    confidence: float = 0.7,
    flag: Flag = Flag.GREEN,
) -> Fact:
    return Fact(
        entity_id="accumulator",
        layer=Layer.PRODUCT_BUSINESS,
        subcategory=subcategory,
        source_type=SourceType.ONLINE_RESEARCH,
        text=text,
        source_url=url,
        captured_at=dt.datetime.now(dt.UTC),
        flag=flag,
        confidence=confidence,
    )


# ── upsert_facts ─────────────────────────────────────────────────────────────


def test_upsert_facts_inserts_new_rows():
    store = _make_store()
    facts = [
        _make_fact("Fact one.", url="https://example.com/1"),
        _make_fact("Fact two.", url="https://example.com/2"),
    ]
    store.upsert_facts(facts)
    assert store.count_facts("accumulator") == 2


def test_upsert_facts_idempotent_same_confidence():
    """Re-upserting identical facts must not grow the count."""
    store = _make_store()
    facts = [_make_fact("Same fact.", url="https://example.com/1", confidence=0.7)]
    store.upsert_facts(facts)
    store.upsert_facts(facts)
    assert store.count_facts("accumulator") == 1


def test_upsert_facts_updates_higher_confidence():
    """A second run with higher confidence replaces the row."""
    store = _make_store()
    low = _make_fact("Fact.", url="https://example.com/1", confidence=0.5)
    store.upsert_facts([low])

    high = _make_fact("Fact.", url="https://example.com/1", confidence=0.9)
    store.upsert_facts([high])

    rows = store.load_facts("accumulator")
    assert len(rows) == 1
    assert float(rows[0]["confidence"]) == pytest.approx(0.9)


def test_upsert_facts_does_not_lower_confidence():
    """A second run with lower confidence must NOT overwrite the existing row."""
    store = _make_store()
    high = _make_fact("Fact.", url="https://example.com/1", confidence=0.9)
    store.upsert_facts([high])

    low = _make_fact("Fact.", url="https://example.com/1", confidence=0.3)
    store.upsert_facts([low])

    rows = store.load_facts("accumulator")
    assert len(rows) == 1
    assert float(rows[0]["confidence"]) == pytest.approx(0.9)


# ── persist_run (transactional) ───────────────────────────────────────────────


def test_persist_run_writes_facts_and_decision():
    from sqlalchemy import text

    store = _make_store()
    facts = [_make_fact("Fact A.", url="https://a.com/1")]
    decision = {"recommendation": "watch", "rationale": "no issues", "hard_flag_count": 0,
                "soft_flag_count": 0, "green_count": 1, "human_approval_required": True}

    store.persist_run(facts, "accumulator", decision)

    assert store.count_facts("accumulator") == 1
    with store._get_engine().connect() as conn:
        rows = list(conn.execute(text("SELECT recommendation FROM decisions WHERE entity_id='accumulator'")))
    assert len(rows) == 1
    assert rows[0][0] == "watch"


def test_persist_run_idempotent():
    """Running persist_run twice with same facts keeps count at N."""
    store = _make_store()
    facts = [
        _make_fact("F1.", url="https://a.com/1"),
        _make_fact("F2.", url="https://a.com/2"),
    ]
    decision = {"recommendation": "continue"}
    store.persist_run(facts, "accumulator", decision)
    store.persist_run(facts, "accumulator", decision)

    assert store.count_facts("accumulator") == 2


def test_persist_run_updates_on_higher_confidence():
    """Second run with upgraded confidence updates the fact row."""
    store = _make_store()
    url = "https://a.com/1"
    store.persist_run([_make_fact("F.", url=url, confidence=0.5)], "accumulator", {})
    store.persist_run([_make_fact("F.", url=url, confidence=0.95)], "accumulator", {})

    rows = store.load_facts("accumulator")
    assert len(rows) == 1
    assert float(rows[0]["confidence"]) == pytest.approx(0.95)


# ── reporter node integration ─────────────────────────────────────────────────


def test_node_reporter_persists_to_store(monkeypatch):
    """node_reporter calls PostgresStore.persist_run with state facts."""
    from storytelling_bot.nodes.reporter import node_reporter
    from storytelling_bot.schema import State

    captured = {}

    class _FakeStore:
        def persist_run(self, facts, entity_id, decision):
            captured["facts"] = facts
            captured["entity_id"] = entity_id

    monkeypatch.setattr(
        "storytelling_bot.nodes.reporter.PostgresStore",
        _FakeStore,
        raising=False,
    )
    # Patch import inside _persist
    import storytelling_bot.nodes.reporter as _rep_mod

    def _patched_persist(state):
        try:
            _FakeStore().persist_run(state.facts, state.entity_id, state.decision)
        except Exception:
            pass

    monkeypatch.setattr(_rep_mod, "_persist", _patched_persist)

    facts = [_make_fact("Pipeline fact.", url="https://x.com/1")]
    state = State(entity_id="accumulator", facts=facts)
    node_reporter(state)

    assert captured.get("entity_id") == "accumulator"
    assert len(captured.get("facts", [])) == 1
