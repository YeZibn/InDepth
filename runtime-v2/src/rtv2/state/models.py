"""State model entrypoints for runtime-v2."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


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
class RuntimeState:
    """Runtime control state shared across the main execution chain."""

    active_node_id: str = ""
    compression_state: CompressionState | None = None
    external_signal_state: ExternalSignalState | None = None
    finalize_return_input: FinalizeReturnInput | None = None
