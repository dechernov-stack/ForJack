"""Tests for PostgresStore (SQLite in-memory), MinIOStore, VectorStore — all mocked."""
from __future__ import annotations

import datetime as dt
import json
from unittest.mock import MagicMock

from storytelling_bot.schema import Fact, Flag, Layer, SourceType

# ── helpers ──────────────────────────────────────────────────────────────────

def _make_fact(text: str = "Test fact about Stripe.", flag: Flag = Flag.GREEN) -> Fact:
    return Fact(
        entity_id="stripe",
        layer=Layer.PRODUCT_BUSINESS,
        subcategory="Architecture of the solution",
        source_type=SourceType.ONLINE_RESEARCH,
        text=text,
        source_url="https://example.com",
        captured_at=dt.datetime.now(dt.UTC),
        flag=flag,
        confidence=0.9,
    )


# ── PostgresStore (SQLite in-memory) ─────────────────────────────────────────

def test_postgres_store_save_and_load_facts():
    """PostgresStore works with SQLite in-memory (same SQLAlchemy Core API)."""
    from storytelling_bot.storage.postgres import PostgresStore

    store = PostgresStore(database_url="sqlite:///:memory:")
    # SQLite doesn't have TIMESTAMPTZ/JSONB → patch DDL for testing
    from sqlalchemy import create_engine, text
    engine = create_engine("sqlite:///:memory:")
    store._engine = engine
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS facts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_id TEXT NOT NULL,
                layer INTEGER NOT NULL,
                subcategory TEXT NOT NULL,
                source_type TEXT NOT NULL,
                source_url TEXT NOT NULL,
                source_hash TEXT,
                text TEXT NOT NULL,
                flag TEXT NOT NULL DEFAULT 'grey',
                confidence REAL NOT NULL DEFAULT 0.5,
                captured_at TEXT NOT NULL,
                event_date TEXT,
                red_flag_category TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """))
        conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_facts_key "
            "ON facts (entity_id, layer, subcategory, source_url)"
        ))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_id TEXT NOT NULL,
                recommendation TEXT NOT NULL,
                rationale TEXT,
                human_approval_required INTEGER NOT NULL DEFAULT 1,
                hard_flag_count INTEGER NOT NULL DEFAULT 0,
                soft_flag_count INTEGER NOT NULL DEFAULT 0,
                green_count INTEGER NOT NULL DEFAULT 0,
                payload TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """))
        conn.commit()

    facts = [
        _make_fact("Stripe processes trillions."),
        Fact(
            entity_id="stripe",
            layer=Layer.PRODUCT_BUSINESS,
            subcategory="Architecture of the solution",
            source_type=SourceType.ONLINE_RESEARCH,
            text="Stripe went public in 2021.",
            source_url="https://example.com/2",
            captured_at=dt.datetime.now(dt.UTC),
            flag=Flag.GREEN,
            confidence=0.9,
        ),
    ]
    store.save_facts(facts)

    loaded = store.load_facts("stripe")
    assert len(loaded) == 2
    assert all(r["entity_id"] == "stripe" for r in loaded)


def test_postgres_store_save_decision_sqlite():
    from sqlalchemy import create_engine, text

    from storytelling_bot.storage.postgres import PostgresStore

    store = PostgresStore(database_url="sqlite:///:memory:")
    engine = create_engine("sqlite:///:memory:")
    store._engine = engine
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_id TEXT NOT NULL,
                recommendation TEXT NOT NULL,
                rationale TEXT,
                human_approval_required INTEGER NOT NULL DEFAULT 1,
                hard_flag_count INTEGER NOT NULL DEFAULT 0,
                soft_flag_count INTEGER NOT NULL DEFAULT 0,
                green_count INTEGER NOT NULL DEFAULT 0,
                payload TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """))
        conn.commit()

    decision = {
        "recommendation": "continue",
        "rationale": "No red flags",
        "human_approval_required": True,
        "hard_flag_count": 0,
        "soft_flag_count": 0,
        "green_count": 3,
    }
    store.save_decision("stripe", decision)

    with engine.connect() as conn:
        result = list(conn.execute(text("SELECT * FROM decisions WHERE entity_id='stripe'")))
    assert len(result) == 1
    assert result[0][2] == "continue"  # recommendation column


# ── MinIOStore (mocked boto3) ─────────────────────────────────────────────────

def test_minio_upload_bronze():
    from storytelling_bot.storage.minio_store import MinIOStore

    mock_client = MagicMock()
    store = MinIOStore()
    store._client = mock_client

    key = store.upload_bronze("stripe", "tavily", "abc123", {"text": "hello"})
    assert key == "stripe/tavily/abc123.json"
    mock_client.put_object.assert_called_once()
    call_kwargs = mock_client.put_object.call_args[1]
    assert call_kwargs["Bucket"] == "bronze"
    assert call_kwargs["Key"] == key


def test_minio_upload_silver():
    from storytelling_bot.storage.minio_store import MinIOStore

    mock_client = MagicMock()
    store = MinIOStore()
    store._client = mock_client

    record = {"source_type": "online_research", "text": "fact text"}
    key = store.upload_silver("stripe", "gdelt", "sha256hex", record)
    assert key == "stripe/gdelt/sha256hex.json"
    mock_client.put_object.assert_called_once()


def test_minio_download_silver():
    from storytelling_bot.storage.minio_store import MinIOStore

    mock_client = MagicMock()
    expected = {"text": "some fact", "flag": "green"}
    mock_client.get_object.return_value = {
        "Body": MagicMock(read=MagicMock(return_value=json.dumps(expected).encode()))
    }
    store = MinIOStore()
    store._client = mock_client

    result = store.download_silver("stripe/gdelt/sha256hex.json")
    assert result == expected


def test_minio_list_silver():
    from storytelling_bot.storage.minio_store import MinIOStore

    mock_client = MagicMock()
    mock_paginator = MagicMock()
    mock_client.get_paginator.return_value = mock_paginator
    mock_paginator.paginate.return_value = [
        {"Contents": [{"Key": "stripe/tavily/abc.json"}, {"Key": "stripe/gdelt/def.json"}]}
    ]
    store = MinIOStore()
    store._client = mock_client

    keys = store.list_silver("stripe")
    assert len(keys) == 2


def test_minio_download_failure_returns_none():
    from storytelling_bot.storage.minio_store import MinIOStore

    mock_client = MagicMock()
    mock_client.get_object.side_effect = Exception("NoSuchKey")
    store = MinIOStore()
    store._client = mock_client

    result = store.download_silver("nonexistent/key.json")
    assert result is None


# ── VectorStore (mocked qdrant-client) ───────────────────────────────────────

def test_vector_store_upsert():
    from storytelling_bot.storage.vector_store import VectorStore

    mock_client = MagicMock()
    store = VectorStore()
    store._client = mock_client

    fact_dict = {"entity_id": "stripe", "text": "Stripe processes payments.", "flag": "green"}
    vector = [0.1] * 1536
    store.upsert_fact(fact_dict, vector)

    mock_client.upsert.assert_called_once()
    call_kwargs = mock_client.upsert.call_args[1]
    assert call_kwargs["collection_name"] == "facts"
    points = call_kwargs["points"]
    assert len(points) == 1


def test_vector_store_search():

    from storytelling_bot.storage.vector_store import VectorStore

    mock_client = MagicMock()
    mock_hit = MagicMock()
    mock_hit.payload = {"text": "Stripe fact", "flag": "green"}
    mock_hit.score = 0.95
    mock_client.search.return_value = [mock_hit]

    store = VectorStore()
    store._client = mock_client

    results = store.search([0.1] * 1536, limit=5)
    assert len(results) == 1
    assert results[0]["text"] == "Stripe fact"
    assert results[0]["_score"] == 0.95


def test_vector_store_count():
    from storytelling_bot.storage.vector_store import VectorStore

    mock_client = MagicMock()
    mock_client.get_collection.return_value = MagicMock(points_count=42)
    store = VectorStore()
    store._client = mock_client

    assert store.count() == 42
