"""Qdrant vector store — semantic search over facts."""
from __future__ import annotations

import hashlib
import logging
import os
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

_COLLECTION = "facts"
_VECTOR_SIZE = 1536  # text-embedding-3-small / ada-002 dimension


def _text_to_id(text: str) -> int:
    """Stable int ID from text hash (Qdrant requires uint64)."""
    return int(hashlib.sha256(text.encode()).hexdigest()[:16], 16)


class VectorStore:
    """Qdrant-backed semantic search for facts."""

    def __init__(self, host: Optional[str] = None, port: int = 6333) -> None:
        self._host = host or os.environ.get("QDRANT_HOST", "localhost")
        self._port = int(os.environ.get("QDRANT_PORT", str(port)))
        self._client = None

    def _get_client(self):
        if self._client is None:
            from qdrant_client import QdrantClient  # noqa: PLC0415
            from qdrant_client.models import Distance, VectorParams  # noqa: PLC0415
            self._client = QdrantClient(host=self._host, port=self._port)
            try:
                self._client.get_collection(_COLLECTION)
            except Exception:
                self._client.create_collection(
                    collection_name=_COLLECTION,
                    vectors_config=VectorParams(size=_VECTOR_SIZE, distance=Distance.COSINE),
                )
                log.info("VectorStore: created collection %s", _COLLECTION)
        return self._client

    def upsert_fact(self, fact_dict: Dict[str, Any], vector: List[float]) -> None:
        """Upsert a fact with its embedding vector."""
        from qdrant_client.models import PointStruct  # noqa: PLC0415
        client = self._get_client()
        point_id = _text_to_id(fact_dict.get("text", ""))
        payload = {k: v for k, v in fact_dict.items() if k != "vector"}
        client.upsert(
            collection_name=_COLLECTION,
            points=[PointStruct(id=point_id, vector=vector, payload=payload)],
        )

    def search(self, query_vector: List[float], limit: int = 10) -> List[Dict[str, Any]]:
        """Search facts by semantic similarity."""
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

    def count(self) -> int:
        """Return total number of indexed facts."""
        try:
            info = self._get_client().get_collection(_COLLECTION)
            return info.points_count or 0
        except Exception:
            return 0
