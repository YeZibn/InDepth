"""State model entrypoints for runtime-v2."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from rtv2.task_graph.models import TaskGraphPatch


class RunPhase(StrEnum):
    PREPARE = "prepare"
    EXECUTE = "execute"
    FINALIZE = "finalize"


class BudgetStatus(StrEnum):
    HEALTHY = "healthy"
    TIGHT = "tight"
    EXCEEDED = "exceeded"


class SignalSourceType(StrEnum):
    USER = "user"
    VERIFICATION = "verification"
    SUBAGENT = "subagent"
    TOOL = "tool"


class VerificationStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class RequestReplanSource(StrEnum):
    NODE_REFLEXION = "node_reflexion"
    RUN_REFLEXION = "run_reflexion"


@dataclass(slots=True)
class RunIdentity:
    """Stable host/runtime identity for a single run instance."""

    session_id: str
    task_id: str
    run_id: str
    user_input: str
    goal: str = ""


@dataclass(slots=True)
class RunLifecycle:
    """Minimal lifecycle control state for a single run."""

    lifecycle_state: str
    current_phase: RunPhase
    result_status: str = ""
    stop_reason: str = ""


@dataclass(slots=True)
class CompressionState:
    """Minimal runtime compression status for the current step window."""

    compressed: bool
    compressed_context_ref: str = ""
    budget_status: BudgetStatus | None = None
    context_usage_ratio: float | None = None


@dataclass(slots=True)
class SignalRef:
    """Reference to an external signal waiting to be consumed."""

    signal_id: str
    source_type: SignalSourceType
    ref: str
    arrived_at: str


@dataclass(slots=True)
class ExternalSignalState:
    """Pending external inputs that can resume or redirect execution."""

    pending_user_reply: SignalRef | None = None
    pending_verification_result: SignalRef | None = None
    pending_subagent_result: SignalRef | None = None
    pending_async_tool_result: SignalRef | None = None


@dataclass(slots=True)
class FinalizeReturnInput:
    """Execute-phase return input produced by failed final verification."""

    verification_summary: str
    verification_issues: list[str]


@dataclass(slots=True)
class PrepareResult:
    """Minimal formal prepare-phase result retained after planner normalization."""

    goal: str
    patch: TaskGraphPatch | None = None


@dataclass(slots=True)
class RequestReplan:
    """Minimal structured request used to route control back to prepare."""

    source: RequestReplanSource
    node_id: str
    reason: str
    created_at: str


@dataclass(slots=True)
class RuntimeState:
    """Runtime control state shared across the main execution chain."""

    active_node_id: str = ""
    prepare_result: PrepareResult | None = None
    compression_state: CompressionState | None = None
    external_signal_state: ExternalSignalState | None = None
    finalize_return_input: FinalizeReturnInput | None = None
    request_replan: RequestReplan | None = None


@dataclass(slots=True)
class VerificationState:
    """Lightweight verification state retained during final verification flow."""

    verification_status: VerificationStatus | None = None
    latest_result_ref: str = ""


@dataclass(slots=True)
class DomainState:
    """Domain-facing runtime state hung off the minimal RunContext."""

    task_graph_state: Any
    verification_state: VerificationState | None = None


@dataclass(slots=True)
class RunContext:
    """Minimal formal runtime context shared across the main execution chain."""

    run_identity: RunIdentity
    run_lifecycle: RunLifecycle
    runtime_state: RuntimeState
    domain_state: DomainState
