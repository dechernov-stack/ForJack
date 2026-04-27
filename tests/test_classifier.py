"""Classifier and flag detector tests."""
from __future__ import annotations

from storytelling_bot.llm.mock import MockClient
from storytelling_bot.schema import Layer


def test_classifier_picks_product_layer():
    client = MockClient()
    layer, _sub, conf = client.classify_fact(
        "Equity pooling под Rule 506(b), Fund I и Fund II, AUM $60M"
    )
    assert layer == Layer.PRODUCT_BUSINESS
    assert conf > 0.5


def test_red_flag_judge_detects_hard():
    client = MockClient()
    res = client.judge_red_flag("Persona under OFAC sanctions list since 2022")
    assert res is not None
    cat, conf = res
    assert cat == "hard:sanctions"
    assert conf >= 0.9


def test_red_flag_judge_detects_soft():
    client = MockClient()
    res = client.judge_red_flag("По данным портала, executives ушли (массовый исход)")
    assert res is not None
    cat, _ = res
    assert cat.startswith("soft:")


def test_red_flag_returns_none_for_clean():
    client = MockClient()
    assert client.judge_red_flag("Компания привлекла $46M от ведущих инвесторов.") is None


def test_green_classify():
    client = MockClient()
    assert client.classify_green("масштаб 1500 городов, Fortune 500")
    assert not client.classify_green("обычный нейтральный текст")


def test_founder_professional_layer():
    client = MockClient()
    layer, _, _ = client.classify_fact("Gett под руководством Вайзера привлёк $1B инвестиций")
    assert layer == Layer.FOUNDER_PROFESSIONAL


def test_pest_context_layer():
    client = MockClient()
    layer, _, _ = client.classify_fact("SEC enforcement action, NSMIA Jobs Act regulations 1996")
    assert layer == Layer.PEST_CONTEXT
