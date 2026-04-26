"""Task graph state models for runtime-v2."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class TaskGraphStatus(StrEnum):
    ACTIVE = "active"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


class NodeStatus(StrEnum):
    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    BLOCKED = "blocked"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    ABANDONED = "abandoned"


@dataclass(slots=True)
class TaskGraphNode:
    """Minimal formal execution node in a task graph."""

    node_id: str
    graph_id: str
    name: str
    kind: str
    description: str = ""
    node_status: NodeStatus = NodeStatus.PENDING
    owner: str = ""
    dependencies: list[str] = field(default_factory=list)
    order: int = 0
    artifacts: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    block_reason: str = ""
    failure_reason: str = ""


@dataclass(slots=True)
class NodePatch:
    """Minimal field-level node patch for runtime-updatable node fields."""

    node_id: str
    node_status: NodeStatus | None = None
    owner: str | None = None
    dependencies: list[str] | None = None
    order: int | None = None
    artifacts: list[str] | None = None
    evidence: list[str] | None = None
    notes: list[str] | None = None
    block_reason: str | None = None
    failure_reason: str | None = None


@dataclass(slots=True)
class TaskGraphPatch:
    """Minimal formal graph patch produced by a step result."""

    node_updates: list[NodePatch] = field(default_factory=list)
    new_nodes: list[TaskGraphNode] = field(default_factory=list)
    active_node_id: str | None = None
    graph_status: TaskGraphStatus | None = None


@dataclass(slots=True)
class TaskGraphState:
    """Minimal formal task graph state."""

    graph_id: str
    nodes: list[TaskGraphNode] = field(default_factory=list)
    active_node_id: str = ""
    graph_status: TaskGraphStatus = TaskGraphStatus.ACTIVE
    version: int = 1
