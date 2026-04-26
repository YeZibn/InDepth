"""Task graph store interfaces for runtime-v2."""

from __future__ import annotations

from typing import Protocol

from rtv2.task_graph.models import TaskGraphNode, TaskGraphPatch, TaskGraphState


class TaskGraphStore(Protocol):
    """Minimal task graph read/write boundary without scheduling behavior."""

    def get_graph(self, graph_id: str) -> TaskGraphState | None:
        """Return the current graph snapshot or None when the graph is missing."""

    def save_graph(self, graph: TaskGraphState) -> None:
        """Persist a full graph snapshot."""

    def apply_patch(self, graph_id: str, patch: TaskGraphPatch) -> TaskGraphState:
        """Apply a graph patch and return the updated graph snapshot."""

    def get_node(self, graph_id: str, node_id: str) -> TaskGraphNode | None:
        """Return a single node by id or None when the node is missing."""

    def get_active_node(self, graph_id: str) -> TaskGraphNode | None:
        """Return the graph's active node or None when there is no active node."""

    def list_nodes(self, graph_id: str) -> list[TaskGraphNode]:
        """Return the nodes currently attached to a graph."""
