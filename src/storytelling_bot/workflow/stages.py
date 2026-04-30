"""Stage enum for storytelling case state machine."""
from __future__ import annotations

from enum import StrEnum


class Stage(StrEnum):
    DRAFT = "draft"
    IDENTIFIED = "identified"
    COLLECTED = "collected"
    MONITORING = "monitoring"
    PAUSED = "paused"
    TERMINATED = "terminated"


VALID_TRANSITIONS: dict[Stage, set[Stage]] = {
    Stage.DRAFT: {Stage.IDENTIFIED},
    Stage.IDENTIFIED: {Stage.COLLECTED, Stage.DRAFT},
    Stage.COLLECTED: {Stage.MONITORING, Stage.IDENTIFIED},
    Stage.MONITORING: {Stage.PAUSED, Stage.TERMINATED, Stage.COLLECTED},
    Stage.PAUSED: {Stage.MONITORING, Stage.TERMINATED},
    Stage.TERMINATED: set(),
}
