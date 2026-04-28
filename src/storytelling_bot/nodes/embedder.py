"""Embedder node — compute embeddings and write facts to VectorStore."""
from __future__ import annotations

import logging

from storytelling_bot.llm import get_llm_client
from storytelling_bot.schema import State
from storytelling_bot.storage.vector_store import VectorStore

log = logging.getLogger(__name__)


def embed_facts(state: State) -> dict:
    """Embed all facts in state and upsert into Qdrant. Best-effort."""
    if not state.facts:
        return {}

    llm = get_llm_client()
    vs = VectorStore()

    texts = [f.text for f in state.facts]
    try:
        vectors = llm.embed(texts)
    except Exception:
        log.exception("embed() failed — skipping vector storage for this run")
        return {}

    n_written = 0
    for fact, vector in zip(state.facts, vectors):
        try:
            vs.upsert_fact(fact.to_jsonable(), vector)
            n_written += 1
        except Exception:
            log.warning("VectorStore upsert failed for fact: %s", fact.text[:60])

    log.info("Embedded %d/%d facts → VectorStore", n_written, len(state.facts))
    return {}
