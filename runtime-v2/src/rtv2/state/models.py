"""State model entrypoints for runtime-v2."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class RunPhase(StrEnum):
    PREPARE = "prepare"
    EXECUTE = "execute"
    FINALIZE = "finalize"


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
