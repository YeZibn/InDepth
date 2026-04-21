from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class TodoBindingState(StrEnum):
    BOUND = "bound"
    CLOSED = "closed"


class TodoExecutionPhase(StrEnum):
    PLANNING = "planning"
    EXECUTING = "executing"
    FINALIZING = "finalizing"


class TodoSubtaskStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in-progress"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    FAILED = "failed"
    PARTIAL = "partial"
    AWAITING_INPUT = "awaiting_input"
    TIMED_OUT = "timed_out"
    ABANDONED = "abandoned"


@dataclass(slots=True)
class TodoContext:
    """Runtime-facing lightweight execution context for an active todo."""

    todo_id: str = ""
    active_subtask_id: str | None = None
    active_subtask_number: int | None = None
    execution_phase: TodoExecutionPhase = TodoExecutionPhase.PLANNING
    binding_required: bool = False
    binding_state: TodoBindingState = TodoBindingState.BOUND
    todo_bound_at: str = ""

    @property
    def is_bound(self) -> bool:
        return bool(self.todo_id) and self.binding_state == TodoBindingState.BOUND

    @property
    def has_active_subtask(self) -> bool:
        return self.active_subtask_number is not None


@dataclass(slots=True)
class TodoSubtask:
    """Stable domain model for a single subtask."""

    subtask_id: str
    number: int
    name: str
    description: str
    status: TodoSubtaskStatus = TodoSubtaskStatus.PENDING
    priority: str = "medium"
    dependencies: list[int] = field(default_factory=list)
    split_rationale: str = ""
    acceptance_criteria: list[str] = field(default_factory=list)
    kind: str = ""
    owner: str = ""
    origin_subtask_id: str = ""
    origin_subtask_number: int | None = None


@dataclass(slots=True)
class TodoSnapshot:
    """Full structured todo snapshot for services and repositories."""

    todo_id: str
    task_name: str
    context: str
    split_reason: str
    status: str = ""
    subtasks: list[TodoSubtask] = field(default_factory=list)
    filepath: str = ""
    metadata: dict[str, str] = field(default_factory=dict)

    @property
    def subtask_ids(self) -> list[str]:
        return [item.subtask_id for item in self.subtasks]

