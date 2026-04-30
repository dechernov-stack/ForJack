"""Graph node: resolve_entity — runs before collectors."""
from __future__ import annotations

import logging
import os
from pathlib import Path

from storytelling_bot.schema import State

log = logging.getLogger(__name__)


def node_resolve_entity(state: State) -> dict:
    """
    Resolves entity_query → entity_cards + entity_relations.
    Skipped when entity_cards already set (e.g. loaded from JSON).
    """
    if state.entity_cards:
        log.info("EntityCards already set (%d), skipping resolver", len(state.entity_cards))
        return {}

    query = state.entity_query or state.entity_id
    providers_env = os.environ.get("RESOLVER_PROVIDERS", "")
    providers = [p.strip() for p in providers_env.split(",") if p.strip()] or None

    mock_dir_env = os.environ.get("RESOLVER_MOCK_DIR", "")
    mock_dir = Path(mock_dir_env) if mock_dir_env else None

    if not providers and not mock_dir:
        log.info("RESOLVER_PROVIDERS not set — skipping entity resolution")
        return {}

    try:
        from storytelling_bot.resolver.card import resolve
        cards = resolve(query=query, providers=providers, mock_dir=mock_dir, use_tavily=False)
        log.info("EntityResolver: %d cards for '%s'", len(cards), query)
        uncertain = [c for c in cards if c.uncertain]
        if uncertain:
            log.warning("Low-consensus cards: %s — review before proceeding",
                        [c.canonical_name for c in uncertain])
        return {"entity_cards": cards}
    except Exception as exc:
        log.error("EntityResolver failed: %s", exc)
        return {"errors": [*state.errors, f"EntityResolver: {exc}"]}
