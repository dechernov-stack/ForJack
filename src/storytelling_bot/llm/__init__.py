"""LLM client factory."""
from __future__ import annotations

import os

from storytelling_bot.llm.base import LLMClient
from storytelling_bot.llm.mock import MockClient


def get_llm_client() -> LLMClient:
    provider = os.environ.get("LLM_PROVIDER", "").lower()
    if not provider:
        # Auto-detect: use anthropic if key is set
        provider = "anthropic" if os.environ.get("ANTHROPIC_API_KEY") else "mock"
    if provider == "anthropic":
        from storytelling_bot.llm.claude import AnthropicClient
        return AnthropicClient()  # type: ignore[return-value]
    return MockClient()  # type: ignore[return-value]


__all__ = ["LLMClient", "MockClient", "get_llm_client"]
