"""Qdrant vector store — semantic search over facts."""
from __future__ import annotations

import hashlib
import logging
import os
from typing import Any

log = logging.getLogger(__name__)

_COLLECTION = "facts"
_VECTOR_SIZE = 1024  # voyage-3 / mock hash-based dimension


def _text_to_id(text: str) -> int:
    """Stable int ID from text hash (Qdrant requires uint64)."""
    return int(hashlib.sha256(text.encode()).hexdigest()[:16], 16)


class VectorStore:
    """Qdrant-backed semantic search for facts."""

    def __init__(self, host: str | None = None, port: int = 6333) -> None:
        self._host = host or os.environ.get("QDRANT_HOST", "localhost")
        self._port = int(os.environ.get("QDRANT_PORT", str(port)))
        self._client = None

    def _get_client(self):
        if self._client is None:
            from qdrant_client import QdrantClient
            from qdrant_client.models import Distance, VectorParams
            self._client = QdrantClient(host=self._host, port=self._port)
            try:
                self._client.get_collection(_COLLECTION)
            except Exception:
                self._client.create_collection(
                    collection_name=_COLLECTION,
                    vectors_config=VectorParams(size=_VECTOR_SIZE, distance=Distance.COSINE),
                )
                log.info("VectorStore: created collection %s (dim=%d)", _COLLECTION, _VECTOR_SIZE)
        return self._client

    def upsert_fact(self, fact_dict: dict[str, Any], vector: list[float]) -> None:
        """Upsert a fact with its embedding vector."""
        from qdrant_client.models import PointStruct
        client = self._get_client()
        point_id = _text_to_id(fact_dict.get("text", ""))
        payload = {k: v for k, v in fact_dict.items() if k != "vector"}
        client.upsert(
            collection_name=_COLLECTION,
            points=[PointStruct(id=point_id, vector=vector, payload=payload)],
        )

    def search(self, query_vector: list[float], limit: int = 10) -> list[dict[str, Any]]:
        """Search facts by semantic similarity (no entity filter)."""
        client = self._get_client()
        results = client.search(
            collection_name=_COLLECTION,
            query_vector=query_vector,
            limit=limit,
        )
        return [
            {**hit.payload, "_score": hit.score}
            for hit in results
            if hit.payload
        ]

    def search_with_filter(
        self,
        query_vector: list[float],
        entity_id: str | None = None,
        limit: int = 10,
        min_score: float = 0.0,
    ) -> list[dict[str, Any]]:
        """Search with optional entity_id payload filter and minimum score threshold."""
        from qdrant_client.models import FieldCondition, Filter, MatchValue
        client = self._get_client()
        query_filter = None
        if entity_id:
            query_filter = Filter(
                must=[FieldCondition(key="entity_id", match=MatchValue(value=entity_id))]
            )
        results = client.search(
            collection_name=_COLLECTION,
            query_vector=query_vector,
            query_filter=query_filter,
            limit=limit,
            score_threshold=min_score if min_score > 0.0 else None,
        )
        return [
            {**hit.payload, "_score": hit.score}
            for hit in results
            if hit.payload
        ]

    def count(self) -> int:
        """Return total number of indexed facts."""
        try:
            info = self._get_client().get_collection(_COLLECTION)
            return info.points_count or 0
        except Exception:
            return 0
