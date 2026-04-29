"""Decision engine unit tests — refactored for modular package."""
from __future__ import annotations

import datetime as dt

from storytelling_bot.nodes.decision_engine import node_decision_engine
from storytelling_bot.schema import Fact, Flag, Layer, SourceType, State


def make_fact(
    flag: Flag,
    layer: Layer = Layer.PRODUCT_BUSINESS,
    red_cat: str | None = None,
    conf: float = 0.7,
) -> Fact:
    return Fact(
        entity_id="test",
        layer=layer,
        subcategory="Architecture of the solution",
        source_type=SourceType.ONLINE_RESEARCH,
        text="…",
        source_url="https://example.test",
        captured_at=dt.datetime.now(dt.UTC),
        flag=flag,
        red_flag_category=red_cat,
        confidence=conf,
    )


def _decide(facts: list[Fact]) -> str:
    state = State(entity_id="test", facts=facts)
    result = node_decision_engine(state)
    merged = State(**{**state.model_dump(), **result})
    return merged.decision["recommendation"]


def test_terminate_when_two_hard_flags():
    assert _decide([
        make_fact(Flag.RED, red_cat="hard:sanctions", conf=0.95),
        make_fact(Flag.RED, red_cat="hard:fraud", conf=0.92),
    ]) == "terminate"


def test_terminate_when_high_conf_sanctions():
    assert _decide([make_fact(Flag.RED, red_cat="hard:sanctions", conf=0.92)]) == "terminate"


def test_pause_on_one_hard():
    assert _decide([make_fact(Flag.RED, red_cat="hard:sec_enforcement", conf=0.7)]) == "pause"


def test_pause_on_four_soft():
    assert _decide([
        make_fact(Flag.RED, red_cat="soft:toxic_communication"),
        make_fact(Flag.RED, red_cat="soft:exec_exodus"),
        make_fact(Flag.RED, red_cat="soft:investor_lawsuit"),
        make_fact(Flag.RED, red_cat="soft:deadpool_pattern"),
    ]) == "pause"


def test_continue_when_clean_with_green():
    assert _decide([
        make_fact(Flag.GREEN, layer=Layer.FOUNDER_PERSONAL),
        make_fact(Flag.GREEN, layer=Layer.FOUNDER_PROFESSIONAL),
        make_fact(Flag.GREEN, layer=Layer.PRODUCT_BUSINESS),
        make_fact(Flag.GREEN, layer=Layer.FOUNDER_PERSONAL),
        make_fact(Flag.GREEN, layer=Layer.PRODUCT_BUSINESS),
    ]) == "continue"


def test_watch_default_uncertain():
    assert _decide([make_fact(Flag.GREEN), make_fact(Flag.GREY)]) == "watch"


def test_human_approval_required():
    state = State(entity_id="test", facts=[make_fact(Flag.GREEN)])
    result = node_decision_engine(state)
    assert result["decision"]["human_approval_required"] is True
