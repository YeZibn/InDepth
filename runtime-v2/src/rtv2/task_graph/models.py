"""Task graph state models for runtime-v2."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class TaskGraphStatus(StrEnum):
    ACTIVE = "active"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


@dataclass(slots=True)
class TaskGraphState:
    """Minimal formal task graph state."""

    graph_id: str
    nodes: list[Any] = field(default_factory=list)
    active_node_id: str = ""
    graph_status: TaskGraphStatus = TaskGraphStatus.ACTIVE
    version: int = 1
