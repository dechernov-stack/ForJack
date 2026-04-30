"""EntityResolver — orchestrates providers → reconcile → verify."""
from __future__ import annotations

import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from storytelling_bot.resolver.providers import build_user_prompt, get_provider, parse_provider_answer
from storytelling_bot.resolver.reconcile import reconcile
from storytelling_bot.resolver.verifier import verify_with_tavily
from storytelling_bot.schema import EntityCard

log = logging.getLogger(__name__)

_DEFAULT_PROVIDERS = os.environ.get("RESOLVER_PROVIDERS", "claude,gpt,deepseek").split(",")


def resolve(
    query: str,
    providers: list[str] | None = None,
    mock_dir: Path | None = None,
    use_tavily: bool = False,
) -> list[EntityCard]:
    """
    Run multi-LLM entity resolution.
    Returns list[EntityCard] sorted by canonical_name.
    """
    provider_names = providers or _DEFAULT_PROVIDERS
    user_prompt = build_user_prompt(query)

    fns = {name: get_provider(name, mock_dir) for name in provider_names}

    raw_outputs: dict[str, Any] = {}
    with ThreadPoolExecutor(max_workers=len(fns)) as pool:
        futures = {pool.submit(fn, user_prompt): name for name, fn in fns.items()}
        for future in as_completed(futures):
            name = futures[future]
            try:
                raw = future.result()
                raw_outputs[name] = parse_provider_answer(name, raw)
                log.info("Provider %s → %d entities", name, len(raw_outputs[name].get("entities", [])))
            except Exception as exc:
                log.warning("Provider %s failed: %s", name, exc)
                raw_outputs[name] = {"entities": [], "uncertainty_note": str(exc)}

    cards = reconcile(raw_outputs)

    if use_tavily:
        for card in cards:
            verify_with_tavily(card)

    return cards
