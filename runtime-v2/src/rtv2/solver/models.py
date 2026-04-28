"""Solver result models for runtime-v2."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from rtv2.task_graph.models import ResultRef, TaskGraphPatch


class StepStatusSignal(StrEnum):
    """Minimal local progress signal returned from actor-side execution."""

    PROGRESSED = "progressed"
    READY_FOR_COMPLETION = "ready_for_completion"
    BLOCKED = "blocked"
    FAILED = "failed"


@dataclass(slots=True)
class StepResult:
    """Minimal structured handoff object from actor-side execution to solver."""

    result_refs: list[ResultRef] = field(default_factory=list)
    status_signal: StepStatusSignal = StepStatusSignal.PROGRESSED
    reason: str = ""
    patch: TaskGraphPatch | None = None

    def __post_init__(self) -> None:
        if self.status_signal is not StepStatusSignal.PROGRESSED and not self.reason.strip():
            raise ValueError("reason is required when status_signal is not progressed")
