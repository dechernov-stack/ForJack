"""Case model + state machine + transition guards."""
from __future__ import annotations

import datetime as dt
import functools
import logging
from typing import Any, Callable

from pydantic import BaseModel, Field

from storytelling_bot.workflow.stages import Stage, VALID_TRANSITIONS

log = logging.getLogger(__name__)


class CaseTransitionError(ValueError):
    pass


class CaseTransition(BaseModel):
    from_stage: Stage | None
    to_stage: Stage
    actor: str
    rationale: str = ""
    created_at: dt.datetime = Field(default_factory=lambda: dt.datetime.now(dt.UTC))


class Case(BaseModel):
    id: str = ""
    title: str
    goal: str
    stage: Stage = Stage.DRAFT
    entity_query: str = ""
    entity_card_ids: list[str] = []
    expert_profile_id: str | None = None
    depth: str | None = None
    last_report_id: str | None = None
    created_by: str = ""
    confirmed_by: str | None = None
    monitor_mode: str | None = None
    transitions: list[CaseTransition] = []
    metadata: dict[str, Any] = {}
    created_at: dt.datetime = Field(default_factory=lambda: dt.datetime.now(dt.UTC))
    transitioned_at: dt.datetime = Field(default_factory=lambda: dt.datetime.now(dt.UTC))

    def move_to(self, to: Stage, *, actor: str, rationale: str = "") -> "Case":
        allowed = VALID_TRANSITIONS.get(self.stage, set())
        if to not in allowed:
            raise CaseTransitionError(
                f"Invalid transition {self.stage!r} → {to!r}. "
                f"Allowed: {[s.value for s in allowed]}"
            )
        transition = CaseTransition(
            from_stage=self.stage,
            to_stage=to,
            actor=actor,
            rationale=rationale,
        )
        now = dt.datetime.now(dt.UTC)
        return self.model_copy(update={
            "stage": to,
            "transitioned_at": now,
            "transitions": [*self.transitions, transition],
        })

    def confirm_identification(self, *, analyst_email: str) -> "Case":
        """Transition draft → identified after analyst confirms EntityCards."""
        if not self.entity_card_ids:
            raise CaseTransitionError("entity_card_ids must be set before confirming identification")
        updated = self.move_to(Stage.IDENTIFIED, actor=analyst_email, rationale="analyst confirmed EntityCards")
        return updated.model_copy(update={"confirmed_by": analyst_email})

    def run_initial_collection(self, *, analyst_email: str, depth: str) -> "Case":
        """Transition identified → collected."""
        if not self.expert_profile_id:
            raise CaseTransitionError("expert_profile_id required before collection")
        updated = self.move_to(Stage.COLLECTED, actor=analyst_email, rationale=f"initial collection depth={depth}")
        return updated.model_copy(update={"depth": depth})

    def start_monitoring(self, *, actor: str, mode: str = "business-pulse") -> "Case":
        """Transition collected → monitoring."""
        updated = self.move_to(Stage.MONITORING, actor=actor, rationale=f"monitor mode={mode}")
        return updated.model_copy(update={"monitor_mode": mode})

    def pause(self, *, actor: str, rationale: str = "") -> "Case":
        return self.move_to(Stage.PAUSED, actor=actor, rationale=rationale or "paused by analyst")

    def terminate(self, *, actor: str, rationale: str) -> "Case":
        if not rationale:
            raise CaseTransitionError("rationale is required for termination")
        return self.move_to(Stage.TERMINATED, actor=actor, rationale=rationale)

    def resume(self, *, actor: str) -> "Case":
        return self.move_to(Stage.MONITORING, actor=actor, rationale="resumed from pause")


def transition(from_: Stage, to: Stage, requires: list[str] | None = None):
    """Decorator that validates preconditions before a case transition."""
    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(case: Case, **kwargs) -> Case:
            if case.stage != from_:
                raise CaseTransitionError(
                    f"{fn.__name__}: expected stage {from_!r}, got {case.stage!r}"
                )
            for req in (requires or []):
                if not getattr(case, req, None):
                    raise CaseTransitionError(
                        f"{fn.__name__}: precondition '{req}' not satisfied"
                    )
            return fn(case, **kwargs)
        return wrapper
    return decorator
