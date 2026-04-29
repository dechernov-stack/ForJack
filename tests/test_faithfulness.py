"""Faithfulness evaluation — every synthesized claim must be covered by a source fact.

Runs with LLM_PROVIDER=anthropic. Skipped when ANTHROPIC_API_KEY is not set.
"""
from __future__ import annotations

import os
import re

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_API_KEY") in ("", "FILL_ME_IN", "sk-ant-..."),
    reason="ANTHROPIC_API_KEY not configured",
)


def _claim_covered(claim: str, fact_texts: list[str]) -> bool:
    claim_words = set(re.findall(r"\w+", claim.lower()))
    for ft in fact_texts:
        fact_words = set(re.findall(r"\w+", ft.lower()))
        overlap = claim_words & fact_words
        # At least 40% of claim words should be in the fact
        if len(claim_words) > 0 and len(overlap) / len(claim_words) >= 0.40:
            return True
    return False


def test_synthesizer_faithfulness():
    """All claims in synthesis must be grounded in provided facts."""
    import datetime as dt

    from storytelling_bot.llm.claude import AnthropicClient
    from storytelling_bot.schema import Fact, Flag, Layer, SourceType

    client = AnthropicClient()
    sample_facts = [
        Fact(
            entity_id="test", layer=Layer.PRODUCT_BUSINESS,
            subcategory="Architecture of the solution",
            source_type=SourceType.ONLINE_RESEARCH,
            text="Accumulator Fund I зарегистрирован в SEC под Rule 506(b). AUM более $60M.",
            source_url="https://sec.gov/test",
            captured_at=dt.datetime.now(dt.UTC),
            flag=Flag.GREEN, confidence=0.9,
        ),
        Fact(
            entity_id="test", layer=Layer.PRODUCT_BUSINESS,
            subcategory="Evolution",
            source_type=SourceType.ONLINE_RESEARCH,
            text="В 2024 году Accumulator привлёк $46M при оценке $140M.",
            source_url="https://crunchbase.com/test",
            captured_at=dt.datetime.now(dt.UTC),
            flag=Flag.GREEN, confidence=0.9,
        ),
    ]

    narrative = client.synthesize_layer(Layer.PRODUCT_BUSINESS, sample_facts)
    assert narrative and narrative != "(нет данных)", "Synthesis returned empty"

    fact_texts = [f.text for f in sample_facts]
    # Split narrative into sentences / claims
    sentences = [s.strip() for s in re.split(r"[.!?]", narrative) if len(s.strip()) > 15]

    uncovered = [s for s in sentences if not _claim_covered(s, fact_texts)]
    assert len(uncovered) == 0, (
        f"Faithfulness violation — {len(uncovered)}/{len(sentences)} claims not grounded:\n"
        + "\n".join(f"  - {s}" for s in uncovered)
    )


def test_classify_fact_returns_valid_layer():
    from storytelling_bot.llm.claude import AnthropicClient
    from storytelling_bot.schema import Layer

    client = AnthropicClient()
    layer, sub, conf = client.classify_fact(
        "SEC Rule 506(b) — регуляторная база для фондов частного рынка в США."
    )
    assert layer in Layer
    assert conf > 0.0
    assert isinstance(sub, str) and len(sub) > 0


def test_judge_hard_flag():
    from storytelling_bot.llm.claude import AnthropicClient

    client = AnthropicClient()
    result = client.judge_red_flag(
        "The founder was placed on the OFAC sanctions list in 2023 for financial crimes."
    )
    assert result is not None, "Expected hard:sanctions flag"
    cat, conf = result
    assert "sanctions" in cat or "criminal" in cat or "fraud" in cat
    assert conf >= 0.85
