"""Tests for embedding node, VectorStore wiring, and semantic dedup."""
from __future__ import annotations

import datetime as dt
from unittest.mock import MagicMock, patch

from storytelling_bot.schema import Fact, Flag, Layer, SourceType

# ── helpers ───────────────────────────────────────────────────────────────────


def _make_fact(text: str = "Stripe processes payments.", url: str = "https://a.com/1") -> Fact:
    return Fact(
        entity_id="accumulator",
        layer=Layer.PRODUCT_BUSINESS,
        subcategory="Architecture of the solution",
        source_type=SourceType.ONLINE_RESEARCH,
        text=text,
        source_url=url,
        captured_at=dt.datetime.now(dt.UTC),
        flag=Flag.GREEN,
        confidence=0.8,
    )


def _mock_vs():
    vs = MagicMock()
    vs.search_with_filter.return_value = []
    vs.count.return_value = 0
    return vs


# ── MockClient.embed ──────────────────────────────────────────────────────────


def test_mock_embed_returns_1024_dim_vectors():
    from storytelling_bot.llm.mock import MockClient
    vecs = MockClient().embed(["hello", "world"])
    assert len(vecs) == 2
    assert all(len(v) == 1024 for v in vecs)


def test_mock_embed_deterministic():
    from storytelling_bot.llm.mock import MockClient
    mc = MockClient()
    v1 = mc.embed(["same text"])[0]
    v2 = mc.embed(["same text"])[0]
    assert v1 == v2


def test_mock_embed_normalized():
    import math

    from storytelling_bot.llm.mock import MockClient
    v = MockClient().embed(["test"])[0]
    mag = math.sqrt(sum(x * x for x in v))
    assert abs(mag - 1.0) < 1e-6


def test_mock_embed_different_texts_differ():
    from storytelling_bot.llm.mock import MockClient
    mc = MockClient()
    v1 = mc.embed(["hello world"])[0]
    v2 = mc.embed(["completely different text about sanctions"])[0]
    assert v1 != v2


# ── embed_facts node ─────────────────────────────────────────────────────────


def test_embed_facts_calls_upsert_for_each_fact():
    from storytelling_bot.nodes.embedder import embed_facts
    from storytelling_bot.schema import State

    mock_vs_instance = _mock_vs()
    facts = [_make_fact("F1.", "https://a.com/1"), _make_fact("F2.", "https://a.com/2")]
    state = State(entity_id="accumulator", facts=facts)

    with patch("storytelling_bot.nodes.embedder.VectorStore", return_value=mock_vs_instance), \
         patch("storytelling_bot.nodes.embedder.get_llm_client") as mock_llm:
        mock_llm.return_value.embed.return_value = [[0.1] * 1024, [0.2] * 1024]
        embed_facts(state)

    assert mock_vs_instance.upsert_fact.call_count == 2


def test_embed_facts_empty_state_is_noop():
    from storytelling_bot.nodes.embedder import embed_facts
    from storytelling_bot.schema import State

    mock_vs_instance = _mock_vs()
    state = State(entity_id="accumulator", facts=[])

    with patch("storytelling_bot.nodes.embedder.VectorStore", return_value=mock_vs_instance):
        result = embed_facts(state)

    mock_vs_instance.upsert_fact.assert_not_called()
    assert result == {}


def test_embed_facts_survives_qdrant_error():
    from storytelling_bot.nodes.embedder import embed_facts
    from storytelling_bot.schema import State

    mock_vs_instance = _mock_vs()
    mock_vs_instance.upsert_fact.side_effect = Exception("Qdrant unavailable")
    state = State(entity_id="accumulator", facts=[_make_fact()])

    with patch("storytelling_bot.nodes.embedder.VectorStore", return_value=mock_vs_instance), \
         patch("storytelling_bot.nodes.embedder.get_llm_client") as mock_llm:
        mock_llm.return_value.embed.return_value = [[0.1] * 1024]
        result = embed_facts(state)  # must not raise

    assert result == {}


# ── semantic dedup in classifier ─────────────────────────────────────────────


def test_classifier_skips_near_duplicate():
    """When Qdrant returns a near-match, the fact is skipped."""
    from storytelling_bot.nodes.classifier import node_layer_classifier
    from storytelling_bot.schema import State

    raw_chunk = {
        "text": "Stripe processes trillions of dollars annually.",
        "source_type": "online_research",
        "url": "https://example.com/1",
        "captured_at": "2024-01-01T00:00:00",
        "entity_focus": "accumulator",
    }
    state = State(entity_id="accumulator", raw_chunks=[raw_chunk])

    near_duplicate_result = [{"text": "Stripe processes payments.", "_score": 0.95}]

    with patch("storytelling_bot.nodes.classifier.VectorStore") as MockVS, \
         patch("storytelling_bot.nodes.classifier.get_llm_client") as mock_llm:
        mock_vs_instance = MagicMock()
        mock_vs_instance.search_with_filter.return_value = near_duplicate_result
        MockVS.return_value = mock_vs_instance

        from storytelling_bot.llm.mock import MockClient
        mc = MockClient()
        mock_llm.return_value = mc
        # Patch embed on mock_llm instance to return a vector and trigger the VS search
        mock_llm.return_value.embed = MagicMock(return_value=[[0.1] * 1024])

        result = node_layer_classifier(state)

    assert result["facts"] == []


def test_classifier_keeps_fact_when_no_duplicate():
    """When Qdrant returns empty, the fact is retained."""
    from storytelling_bot.nodes.classifier import node_layer_classifier
    from storytelling_bot.schema import State

    raw_chunk = {
        "text": "Stripe processes trillions of dollars annually.",
        "source_type": "online_research",
        "url": "https://example.com/1",
        "captured_at": "2024-01-01T00:00:00",
        "entity_focus": "accumulator",
    }
    state = State(entity_id="accumulator", raw_chunks=[raw_chunk])

    with patch("storytelling_bot.nodes.classifier.VectorStore") as MockVS, \
         patch("storytelling_bot.nodes.classifier.get_llm_client") as mock_llm:
        mock_vs_instance = MagicMock()
        mock_vs_instance.search_with_filter.return_value = []
        MockVS.return_value = mock_vs_instance

        from storytelling_bot.llm.mock import MockClient
        mc = MockClient()
        mock_llm.return_value = mc
        mock_llm.return_value.embed = MagicMock(return_value=[[0.1] * 1024])

        result = node_layer_classifier(state)

    assert len(result["facts"]) == 1


# ── VectorStore.search_with_filter ───────────────────────────────────────────


def test_vector_store_search_with_filter():
    from storytelling_bot.storage.vector_store import VectorStore

    mock_client = MagicMock()
    mock_hit = MagicMock()
    mock_hit.payload = {"text": "Stripe fact", "entity_id": "stripe"}
    mock_hit.score = 0.95
    mock_client.search.return_value = [mock_hit]

    vs = VectorStore()
    vs._client = mock_client

    results = vs.search_with_filter([0.1] * 1024, entity_id="stripe", limit=5, min_score=0.9)
    assert len(results) == 1
    assert results[0]["entity_id"] == "stripe"

    # Verify qdrant filter was built
    call_kwargs = mock_client.search.call_args[1]
    assert call_kwargs["query_filter"] is not None


def test_vector_store_search_with_filter_no_entity():
    from storytelling_bot.storage.vector_store import VectorStore

    mock_client = MagicMock()
    mock_client.search.return_value = []

    vs = VectorStore()
    vs._client = mock_client

    vs.search_with_filter([0.1] * 1024, entity_id=None, limit=5)

    call_kwargs = mock_client.search.call_args[1]
    assert call_kwargs["query_filter"] is None


# ── graph has embed node ──────────────────────────────────────────────────────


def test_graph_contains_embed_node():
    from storytelling_bot.graph import build_graph
    wrapper = build_graph()
    nodes = list(wrapper._compiled.get_graph().nodes.keys())
    assert "embed" in nodes
