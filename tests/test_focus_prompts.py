"""Tests: focus prompts produce different kept-sets on same fact batch."""
from __future__ import annotations

from storytelling_bot.expert.profile import default_profile_for_goal
from storytelling_bot.schema import Layer
from storytelling_bot.workflow.focus_prompts import FOCUS_PROMPTS, apply_focus


def test_focus_prompts_keys_present():
    assert "business-pulse" in FOCUS_PROMPTS
    assert "red-flag-watch" in FOCUS_PROMPTS
    assert "personal-shift" in FOCUS_PROMPTS
    assert "policy-shift" in FOCUS_PROMPTS
    assert "quotes-only" in FOCUS_PROMPTS


def test_apply_focus_business_pulse_lowers_threshold():
    profile = default_profile_for_goal("business")
    original_threshold = profile.keep_threshold
    patched = apply_focus(profile, "business-pulse")
    assert patched.keep_threshold < original_threshold


def test_apply_focus_adds_boost_layers_to_priority():
    profile = default_profile_for_goal("personality")
    patched = apply_focus(profile, "business-pulse")
    assert Layer.PRODUCT_BUSINESS in patched.priority_layers
    assert Layer.PEST_CONTEXT in patched.priority_layers


def test_apply_focus_does_not_mutate_original():
    profile = default_profile_for_goal("business")
    original_threshold = profile.keep_threshold
    _ = apply_focus(profile, "business-pulse")
    assert profile.keep_threshold == original_threshold


def test_apply_focus_quotes_only_no_threshold_change():
    profile = default_profile_for_goal("business")
    patched = apply_focus(profile, "quotes-only")
    assert patched.keep_threshold == profile.keep_threshold


def test_apply_focus_different_modes_different_priorities():
    profile = default_profile_for_goal("business")
    pulse = apply_focus(profile, "business-pulse")
    personal = apply_focus(profile, "personal-shift")
    assert pulse.priority_layers != personal.priority_layers


def test_default_profile_for_goal_business_priority_layers():
    """15.2 DoD: business preset → priority_layers includes layers 2, 6, 8."""
    profile = default_profile_for_goal("business")
    layer_values = [lay.value for lay in profile.priority_layers]
    assert 2 in layer_values
    assert 6 in layer_values
    assert 8 in layer_values


def test_default_profile_for_goal_business_voice():
    profile = default_profile_for_goal("business")
    assert "инвесторский" in profile.voice.lower()


def test_default_profile_for_goal_personality_layers():
    profile = default_profile_for_goal("personality")
    layer_values = [lay.value for lay in profile.priority_layers]
    assert 1 in layer_values  # FOUNDER_PERSONAL
    assert 7 in layer_values  # SOCIAL_IMPACT
