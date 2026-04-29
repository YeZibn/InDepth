"""Solver result models for runtime-v2."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from rtv2.judge import JudgeResultStatus
from rtv2.task_graph.models import NodeStatus
from rtv2.task_graph.models import ResultRef, TaskGraphPatch


class StepStatusSignal(StrEnum):
    """Minimal local progress signal returned from actor-side execution."""

    PROGRESSED = "progressed"
    READY_FOR_COMPLETION = "ready_for_completion"
    BLOCKED = "blocked"
    FAILED = "failed"


class ReflexionAction(StrEnum):
    """Next-action choices suggested by reflexion."""

    RETRY_CURRENT_NODE = "retry_current_node"
    MARK_BLOCKED = "mark_blocked"
    MARK_FAILED = "mark_failed"
    REQUEST_REPLAN = "request_replan"


class SolverControlSignal(StrEnum):
    """Solver-level control signal returned to higher layers."""

    NONE = "none"
    REQUEST_REPLAN = "request_replan"


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


@dataclass(slots=True)
class CompletionCheckInput:
    """Completion package produced before node completion evaluation."""

    node_id: str
    node_name: str
    node_kind: str
    node_description: str
    completion_summary: str
    completion_evidence: list[str] = field(default_factory=list)
    completion_notes: list[str] = field(default_factory=list)
    completion_reason: str = ""


@dataclass(slots=True)
class CompletionCheckResult:
    """Verdict returned by completion evaluation."""

    result_status: JudgeResultStatus
    summary: str
    issues: list[str]


@dataclass(slots=True)
class ReflexionInput:
    """Minimal input consumed by reflexion."""

    node_id: str
    node_name: str
    trigger_type: str
    latest_summary: str
    issues: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ReflexionResult:
    """Minimal reflexion output used by solver and memory."""

    summary: str
    next_attempt_hint: str
    action: ReflexionAction


@dataclass(slots=True)
class SolverResult:
    """Final node-scoped solve result returned from RuntimeSolver to ExecutePhase."""

    final_step_result: StepResult | None = None
    final_node_status: NodeStatus | None = None
    step_count: int = 0
    control_signal: SolverControlSignal = SolverControlSignal.NONE

    def __post_init__(self) -> None:
        if self.step_count < 0:
            raise ValueError("step_count must be non-negative")
