"""Tests for Case state machine: valid/invalid transitions, audit trail."""
from __future__ import annotations

import pytest

from storytelling_bot.workflow.case import Case, CaseTransitionError
from storytelling_bot.workflow.stages import Stage


def _draft_case(**kwargs) -> Case:
    return Case(title="Test case", goal="business", created_by="analyst@firm.com", **kwargs)


# ── valid transitions ──────────────────────────────────────────────────────────

def test_draft_to_identified():
    case = _draft_case(entity_card_ids=["card-1"])
    updated = case.confirm_identification(analyst_email="analyst@firm.com")
    assert updated.stage == Stage.IDENTIFIED
    assert updated.confirmed_by == "analyst@firm.com"
    assert len(updated.transitions) == 1
    assert updated.transitions[0].from_stage == Stage.DRAFT
    assert updated.transitions[0].to_stage == Stage.IDENTIFIED


def test_identified_to_collected():
    case = _draft_case(
        entity_card_ids=["card-1"],
        expert_profile_id="profile-1",
        stage=Stage.IDENTIFIED,
        confirmed_by="analyst@firm.com",
    )
    updated = case.run_initial_collection(analyst_email="analyst@firm.com", depth="2y")
    assert updated.stage == Stage.COLLECTED
    assert updated.depth == "2y"


def test_collected_to_monitoring():
    case = _draft_case(stage=Stage.COLLECTED)
    updated = case.start_monitoring(actor="analyst@firm.com", mode="business-pulse")
    assert updated.stage == Stage.MONITORING
    assert updated.monitor_mode == "business-pulse"


def test_monitoring_to_paused():
    case = _draft_case(stage=Stage.MONITORING)
    updated = case.pause(actor="analyst@firm.com")
    assert updated.stage == Stage.PAUSED


def test_paused_to_monitoring():
    case = _draft_case(stage=Stage.PAUSED)
    updated = case.resume(actor="analyst@firm.com")
    assert updated.stage == Stage.MONITORING


def test_monitoring_to_terminated():
    case = _draft_case(stage=Stage.MONITORING)
    updated = case.terminate(actor="senior@firm.com", rationale="hard:sanctions confirmed by legal")
    assert updated.stage == Stage.TERMINATED


# ── invalid transitions ────────────────────────────────────────────────────────

def test_draft_to_collected_invalid():
    case = _draft_case()
    with pytest.raises(CaseTransitionError, match="Invalid transition"):
        case.move_to(Stage.COLLECTED, actor="analyst@firm.com")


def test_draft_to_monitoring_invalid():
    case = _draft_case()
    with pytest.raises(CaseTransitionError):
        case.move_to(Stage.MONITORING, actor="analyst@firm.com")


def test_terminated_is_final():
    case = _draft_case(stage=Stage.TERMINATED)
    with pytest.raises(CaseTransitionError):
        case.move_to(Stage.MONITORING, actor="analyst@firm.com")


def test_terminate_requires_rationale():
    case = _draft_case(stage=Stage.MONITORING)
    with pytest.raises(CaseTransitionError, match="rationale"):
        case.terminate(actor="senior@firm.com", rationale="")


# ── preconditions ──────────────────────────────────────────────────────────────

def test_confirm_identification_requires_entity_cards():
    case = _draft_case()
    with pytest.raises(CaseTransitionError, match="entity_card_ids"):
        case.confirm_identification(analyst_email="analyst@firm.com")


def test_run_collection_requires_expert_profile():
    case = _draft_case(entity_card_ids=["c1"], stage=Stage.IDENTIFIED)
    with pytest.raises(CaseTransitionError, match="expert_profile_id"):
        case.run_initial_collection(analyst_email="analyst@firm.com", depth="1y")


# ── audit trail ───────────────────────────────────────────────────────────────

def test_audit_trail_grows_on_each_transition():
    case = _draft_case(entity_card_ids=["c1"], expert_profile_id="p1")
    case = case.confirm_identification(analyst_email="analyst@firm.com")
    case = case.run_initial_collection(analyst_email="analyst@firm.com", depth="1y")
    case = case.start_monitoring(actor="analyst@firm.com")
    case = case.pause(actor="analyst@firm.com")
    assert len(case.transitions) == 4


def test_transition_immutability():
    """move_to returns a new Case; original is unchanged."""
    original = _draft_case(entity_card_ids=["c1"])
    updated = original.confirm_identification(analyst_email="analyst@firm.com")
    assert original.stage == Stage.DRAFT
    assert updated.stage == Stage.IDENTIFIED
