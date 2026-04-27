"""AnthropicClient — real Claude LLM calls. Implemented in Task 3."""
from __future__ import annotations

import os
from typing import TYPE_CHECKING, Optional, Tuple

if TYPE_CHECKING:
    from storytelling_bot.schema import Fact, Layer


class AnthropicClient:
    """Stub — full implementation in Task 3."""

    def __init__(self) -> None:
        self._model = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")
        self._client = None

    def _get_client(self):
        if self._client is None:
            import anthropic
            self._client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        return self._client

    def classify_fact(self, text: str) -> Tuple["Layer", str, float]:
        raise NotImplementedError("Implement in Task 3")

    def synthesize_layer(self, layer: "Layer", facts: "list[Fact]") -> str:
        raise NotImplementedError("Implement in Task 3")

    def judge_red_flag(self, text: str) -> Optional[Tuple[str, float]]:
        raise NotImplementedError("Implement in Task 3")

    def classify_green(self, text: str) -> bool:
        raise NotImplementedError("Implement in Task 3")
