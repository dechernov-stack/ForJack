"""Tests for ExpertCritic node."""
from __future__ import annotations

import datetime as dt

from storytelling_bot.expert.critic import (
    _challenges_hypothesis,
    _formulate_thesis,
    _hypothesis_keywords,
    _is_taboo,
    _make_expert_note,
    _score_narrative,
    _score_relevance,
    _signature,
    node_expert_critic,
)
from storytelling_bot.schema import (
    ExpertProfile,
    Fact,
    FactScore,
    Flag,
    Layer,
    SourceType,
    State,
)


def _fact(**kw) -> Fact:
    defaults = dict(
        entity_id="test",
        layer=Layer.FOUNDER_PROFESSIONAL,
        subcategory="Path to expertise",
        source_type=SourceType.ONLINE_RESEARCH,
        text="Дэйв основал компанию в 2010 году.",
        source_url="https://example.com",
        captured_at=dt.datetime(2024, 1, 1),
        flag=Flag.GREY,
        confidence=0.7,
    )
    defaults.update(kw)
    return Fact(**defaults)


def _profile(**kw) -> ExpertProfile:
    defaults = dict(
        analyst_name="Test Analyst",
        role="DD Lead",
        hypothesis="Команда способна построить платформу опираясь на track record.",
        priority_layers=[Layer.FOUNDER_PROFESSIONAL, Layer.PRODUCT_BUSINESS],
        priority_subcategories=[(Layer.FOUNDER_PROFESSIONAL.value, "Path to expertise")],
        taboo_topics=["личн", "семейн"],
        voice="аналитический",
        keep_threshold=0.45,
        min_kept_per_subcat=1,
    )
    defaults.update(kw)
    return ExpertProfile(**defaults)


# ── helpers ────────────────────────────────────────────────────────────────────

def test_hypothesis_keywords_extracts_tokens():
    kw = _hypothesis_keywords("Команда Accumulator способна построить платформу.")
    assert "команда" in kw
    assert "accumulator" in kw
    assert "платформу" in kw


def test_hypothesis_keywords_excludes_stopwords():
    kw = _hypothesis_keywords("которая способ between против опираясь")
    for stop in ["которая", "способ", "between", "против", "опираясь"]:
        assert stop not in kw


def test_signature_normalizes_whitespace():
    assert _signature("  foo   bar  ") == "foo bar"


def test_signature_truncates_to_80():
    long = "a" * 200
    assert len(_signature(long)) == 80


# ── scoring ────────────────────────────────────────────────────────────────────

def test_score_relevance_priority_layer_boost():
    p = _profile()
    f = _fact(layer=Layer.FOUNDER_PROFESSIONAL)
    hyp_kw = _hypothesis_keywords(p.hypothesis)
    score = _score_relevance(f, p, hyp_kw)
    assert score >= 0.30


def test_score_relevance_red_flag_boost():
    p = _profile(priority_layers=[])
    f = _fact(flag=Flag.RED, layer=Layer.PEST_CONTEXT)
    score = _score_relevance(f, p, [])
    assert score >= 0.20


def test_score_narrative_quote_boost():
    f = _fact(text='Он сказал: «Мы построили лучший продукт в мире»')
    assert _score_narrative(f) >= 0.40


def test_score_narrative_numbers_boost():
    f = _fact(text="Компания привлекла $46M при оценке $140M в 2023 году.")
    assert _score_narrative(f) >= 0.20


def test_score_narrative_interview_boost():
    f = _fact(source_type=SourceType.OFFLINE_INTERVIEW)
    assert _score_narrative(f) >= 0.15


def test_score_narrative_event_date_boost():
    f = _fact(event_date=dt.date(2023, 6, 1))
    assert _score_narrative(f) >= 0.10


# ── challenges / taboo ─────────────────────────────────────────────────────────

def test_challenges_hypothesis_red_flag():
    p = _profile()
    f = _fact(flag=Flag.RED)
    assert _challenges_hypothesis(f, p) is True


def test_challenges_hypothesis_contrarian_text():
    p = _profile()
    f = _fact(text="Компания потерял всех клиентов в 2022.")
    assert _challenges_hypothesis(f, p) is True


def test_challenges_hypothesis_normal_fact():
    p = _profile()
    f = _fact(text="Дэйв работает в компании с 2010 года.")
    assert _challenges_hypothesis(f, p) is False


def test_is_taboo_detects_keyword():
    p = _profile(taboo_topics=["личн"])
    f = _fact(text="Его личная жизнь остаётся закрытой.")
    assert _is_taboo(f, p) is True


def test_is_taboo_no_match():
    p = _profile(taboo_topics=["личн"])
    f = _fact(text="Компания основана в 2015 году.")
    assert _is_taboo(f, p) is False


def test_is_taboo_empty_list():
    p = _profile(taboo_topics=[])
    f = _fact(text="Его личная жизнь остаётся закрытой.")
    assert _is_taboo(f, p) is False


# ── expert note ────────────────────────────────────────────────────────────────

def test_make_expert_note_drop_low_relevance():
    p = _profile()
    f = _fact()
    s = FactScore(fact_idx=0, relevance=0.1, narrative_value=0.5, novelty=1.0,
                  challenges_hypothesis=False, keep=False)
    note = _make_expert_note(f, s, p)
    assert "приоритет" in note


def test_make_expert_note_keep_challenges():
    p = _profile()
    f = _fact(flag=Flag.RED)
    s = FactScore(fact_idx=0, relevance=0.7, narrative_value=0.5, novelty=1.0,
                  challenges_hypothesis=True, keep=True)
    note = _make_expert_note(f, s, p)
    assert "гипотезу" in note


def test_make_expert_note_keep_default():
    p = _profile()
    f = _fact()
    s = FactScore(fact_idx=0, relevance=0.7, narrative_value=0.5, novelty=1.0,
                  challenges_hypothesis=False, keep=True)
    note = _make_expert_note(f, s, p)
    assert "опорный факт" in note


# ── formulate thesis ───────────────────────────────────────────────────────────

def test_formulate_thesis_pest_context():
    p = _profile()
    f = _fact(layer=Layer.PEST_CONTEXT, text="Рынок вырос на $110B в 2025.")
    thesis = _formulate_thesis(Layer.PEST_CONTEXT, "Historical moment", [f], p)
    assert len(thesis) > 20


def test_formulate_thesis_founder_professional():
    p = _profile()
    f = _fact(layer=Layer.FOUNDER_PROFESSIONAL, text="10 лет опыта в венчуре.")
    thesis = _formulate_thesis(Layer.FOUNDER_PROFESSIONAL, "Path to expertise", [f], p)
    assert len(thesis) > 20


def test_formulate_thesis_fallback():
    p = _profile()
    f = _fact(layer=Layer.CLIENTS_STORIES, subcategory="Moment of choice & trust")
    thesis = _formulate_thesis(Layer.CLIENTS_STORIES, "Moment of choice & trust", [f], p)
    assert len(thesis) > 10


# ── node_expert_critic ─────────────────────────────────────────────────────────

def _make_state(facts, profile=None) -> State:
    return State(
        entity_id="test",
        facts=facts,
        expert_profile=profile,
    )


def test_node_critic_scores_all_facts():
    facts = [_fact(), _fact(text="Другой факт про компанию в 2020 году.")]
    state = _make_state(facts, _profile())
    out = node_expert_critic(state)
    assert len(out.fact_scores) == len(facts)


def test_node_critic_deduplication():
    same_text = "Компания основана в 2015 году и привлекла первый раунд."
    facts = [_fact(text=same_text), _fact(text=same_text)]
    state = _make_state(facts, _profile())
    out = node_expert_critic(state)
    novelties = [s.novelty for s in out.fact_scores]
    assert novelties[0] == 1.0
    assert novelties[1] == 0.0


def test_node_critic_taboo_dropped():
    p = _profile(taboo_topics=["личн"])
    f = _fact(text="Его личная жизнь: развод и скандал в 2022.")
    state = _make_state([f], p)
    out = node_expert_critic(state)
    assert out.fact_scores[0].keep is False


def test_node_critic_red_flag_always_kept():
    p = _profile(keep_threshold=0.99)
    f = _fact(flag=Flag.RED, text="Компания потерял все средства клиентов.")
    state = _make_state([f], p)
    out = node_expert_critic(state)
    assert out.fact_scores[0].keep is True


def test_node_critic_theses_generated():
    facts = [
        _fact(layer=Layer.FOUNDER_PROFESSIONAL, subcategory="Path to expertise"),
        _fact(layer=Layer.PRODUCT_BUSINESS, subcategory="Architecture of the solution",
              text="Платформа использует Rule 506(b) и Section 3(c)(1)."),
    ]
    state = _make_state(facts, _profile())
    out = node_expert_critic(state)
    assert len(out.theses) > 0


def test_node_critic_min_kept_per_subcat_enforced():
    p = _profile(
        keep_threshold=0.99,
        priority_subcategories=[(Layer.FOUNDER_PROFESSIONAL.value, "Path to expertise")],
        min_kept_per_subcat=1,
        taboo_topics=[],
    )
    f = _fact(layer=Layer.FOUNDER_PROFESSIONAL, subcategory="Path to expertise",
              text="Дэйв работает в компании.", confidence=0.1)
    state = _make_state([f], p)
    out = node_expert_critic(state)
    assert out.fact_scores[0].keep is True
    assert "принудительно" in out.fact_scores[0].expert_note


def test_node_critic_uses_default_profile_when_none():
    facts = [_fact()]
    state = _make_state(facts, profile=None)
    out = node_expert_critic(state)
    assert out.expert_profile is not None
    assert len(out.fact_scores) == 1


def test_node_critic_profile_set_on_state():
    p = _profile()
    state = _make_state([_fact()], p)
    out = node_expert_critic(state)
    assert out.expert_profile is p
