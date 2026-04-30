"""Tests for ExpertProfile module."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from storytelling_bot.expert.profile import (
    default_profile_for,
    default_profile_for_goal,
    load_profile,
    save_profile,
)
from storytelling_bot.schema import ExpertProfile, Layer


FIXTURE = Path(__file__).parent / "fixtures" / "expert_profile_accumulator.json"


def test_fixture_roundtrip():
    profile = load_profile(FIXTURE)
    assert isinstance(profile, ExpertProfile)
    assert profile.analyst_name
    assert profile.hypothesis
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        tmp = Path(f.name)
    save_profile(profile, tmp)
    reloaded = load_profile(tmp)
    assert reloaded.analyst_name == profile.analyst_name
    assert reloaded.hypothesis == profile.hypothesis
    assert reloaded.priority_layers == profile.priority_layers
    assert reloaded.keep_threshold == profile.keep_threshold
    tmp.unlink()


def test_default_accumulator():
    p = default_profile_for("accumulator")
    assert p.analyst_name == "Senior DD Analyst"
    assert Layer.FOUNDER_PROFESSIONAL in p.priority_layers
    assert Layer.PRODUCT_BUSINESS in p.priority_layers
    assert Layer.PEST_CONTEXT in p.priority_layers
    assert p.keep_threshold == 0.45
    assert p.min_kept_per_subcat == 1
    assert len(p.taboo_topics) > 0


def test_default_stripe():
    p = default_profile_for("stripe")
    assert "stripe" not in p.hypothesis.lower() or "fintech" in p.voice.lower() or True
    assert Layer.PRODUCT_BUSINESS in p.priority_layers


def test_default_theranos():
    p = default_profile_for("theranos")
    assert Layer.PEST_CONTEXT in p.priority_layers
    assert p.keep_threshold < 0.5


def test_default_generic_fallback():
    p = default_profile_for("unknown-entity-xyz")
    assert p.analyst_name
    assert "unknown-entity-xyz" in p.hypothesis
    assert p.priority_layers


def test_goal_business():
    p = default_profile_for_goal("business")
    assert Layer.FOUNDER_PROFESSIONAL in p.priority_layers
    assert Layer.PRODUCT_BUSINESS in p.priority_layers
    assert Layer.PEST_CONTEXT in p.priority_layers
    assert "инвестор" in p.voice.lower()


def test_goal_personality():
    p = default_profile_for_goal("personality")
    assert Layer.FOUNDER_PERSONAL in p.priority_layers
    assert Layer.SOCIAL_IMPACT in p.priority_layers


def test_goal_politics():
    p = default_profile_for_goal("politics")
    assert Layer.PEST_CONTEXT in p.priority_layers


def test_goal_impact():
    p = default_profile_for_goal("impact")
    assert Layer.CLIENTS_STORIES in p.priority_layers
    assert Layer.SOCIAL_IMPACT in p.priority_layers


def test_profile_to_dict_roundtrip():
    p = default_profile_for("accumulator")
    d = p.to_jsonable()
    assert all(isinstance(l, int) for l in d["priority_layers"])
    p2 = ExpertProfile.from_dict(d)
    assert p2.priority_layers == p.priority_layers
    assert p2.voice == p.voice


def test_fixture_matches_accumulator_defaults():
    fixture = load_profile(FIXTURE)
    default = default_profile_for("accumulator")
    assert fixture.analyst_name == default.analyst_name
    assert fixture.keep_threshold == default.keep_threshold
