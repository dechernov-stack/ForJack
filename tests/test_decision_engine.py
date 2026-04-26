"""Юнит-тесты decision engine.

В скелете повторно используются функции из storytelling_bot.py.
Когда Claude Code разнесёт код по модулям (см. CLAUDE_TASKS.md шаг 2),
эти тесты переедут в tests/test_nodes_decision_engine.py с импортами
из storytelling_bot.nodes.decision_engine.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

# Делаем доступным storytelling_bot.py из корня репо
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import storytelling_bot as bot  # noqa: E402


def make_fact(flag: bot.Flag, layer: bot.Layer = bot.Layer.PRODUCT_BUSINESS,
              red_cat: str | None = None, conf: float = 0.7) -> bot.Fact:
    return bot.Fact(
        entity_id="test",
        layer=layer,
        subcategory="Architecture of the solution",
        source_type=bot.SourceType.ONLINE_RESEARCH,
        text="…",
        source_url="https://example.test",
        captured_at=dt.datetime.utcnow(),
        flag=flag,
        red_flag_category=red_cat,
        confidence=conf,
    )


def test_terminate_when_two_hard_flags():
    state = bot.State(entity_id="test")
    state.facts = [
        make_fact(bot.Flag.RED, red_cat="hard:sanctions", conf=0.95),
        make_fact(bot.Flag.RED, red_cat="hard:fraud", conf=0.92),
    ]
    bot.node_decision_engine(state)
    assert state.decision["recommendation"] == "terminate"


def test_terminate_when_high_conf_sanctions():
    state = bot.State(entity_id="test")
    state.facts = [make_fact(bot.Flag.RED, red_cat="hard:sanctions", conf=0.92)]
    bot.node_decision_engine(state)
    assert state.decision["recommendation"] == "terminate"


def test_pause_on_one_hard():
    state = bot.State(entity_id="test")
    state.facts = [make_fact(bot.Flag.RED, red_cat="hard:sec_enforcement", conf=0.7)]
    bot.node_decision_engine(state)
    assert state.decision["recommendation"] == "pause"


def test_pause_on_four_soft():
    state = bot.State(entity_id="test")
    state.facts = [
        make_fact(bot.Flag.RED, red_cat="soft:toxic_communication", conf=0.7),
        make_fact(bot.Flag.RED, red_cat="soft:exec_exodus", conf=0.7),
        make_fact(bot.Flag.RED, red_cat="soft:investor_lawsuit", conf=0.7),
        make_fact(bot.Flag.RED, red_cat="soft:deadpool_pattern", conf=0.7),
    ]
    bot.node_decision_engine(state)
    assert state.decision["recommendation"] == "pause"


def test_continue_when_clean_with_green():
    state = bot.State(entity_id="test")
    state.facts = [
        make_fact(bot.Flag.GREEN, layer=bot.Layer.FOUNDER_PERSONAL),
        make_fact(bot.Flag.GREEN, layer=bot.Layer.FOUNDER_PROFESSIONAL),
        make_fact(bot.Flag.GREEN, layer=bot.Layer.PRODUCT_BUSINESS),
        make_fact(bot.Flag.GREEN, layer=bot.Layer.FOUNDER_PERSONAL),
        make_fact(bot.Flag.GREEN, layer=bot.Layer.PRODUCT_BUSINESS),
    ]
    bot.node_decision_engine(state)
    assert state.decision["recommendation"] == "continue"


def test_watch_default_uncertain():
    state = bot.State(entity_id="test")
    state.facts = [make_fact(bot.Flag.GREEN), make_fact(bot.Flag.GREY)]
    bot.node_decision_engine(state)
    assert state.decision["recommendation"] == "watch"


def test_classifier_picks_product_layer():
    layer, sub, _ = bot.llm_classify(
        "Equity pooling под Rule 506(b), Fund I и Fund II, AUM $60M"
    )
    assert layer == bot.Layer.PRODUCT_BUSINESS


def test_red_flag_judge_detects_hard():
    res = bot.llm_judge_red_flag("Persona under OFAC sanctions list since 2022")
    assert res is not None
    cat, conf = res
    assert cat == "hard:sanctions" and conf >= 0.9


def test_red_flag_judge_detects_soft():
    res = bot.llm_judge_red_flag("По данным портала, executives ушли (массовый исход)")
    assert res is not None
    cat, _ = res
    assert cat.startswith("soft:")


def test_full_pipeline_runs():
    state = bot.State(entity_id="accumulator")
    final = bot.build_graph().run(state)
    assert final.decision["recommendation"] in {"continue", "watch", "pause", "terminate"}
    assert final.metrics["fact_count"] > 0
    # каждый факт должен иметь источник
    for f in final.facts:
        assert f.source_url, "fact without provenance"
