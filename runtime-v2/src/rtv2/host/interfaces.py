"""RuntimeHost-facing host identity structures for runtime-v2."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class RuntimeHostState:
    """Minimal host binding snapshot exposed to outer callers."""

    session_id: str
    current_task_id: str = ""
    active_run_id: str = ""


@dataclass(slots=True)
class HostTaskRef:
    """Minimal task reference returned by start_task-like host operations."""

    task_id: str


@dataclass(slots=True)
class StartRunIdentity:
    """Minimal host-owned identity payload used to start a new run."""

    session_id: str
    task_id: str
    run_id: str
    user_input: str
