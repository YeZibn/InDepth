"""Task graph store interfaces for runtime-v2."""

from __future__ import annotations

from copy import deepcopy
from typing import Protocol

from rtv2.task_graph.models import NodePatch, NodeStatus, ResultRef, TaskGraphNode, TaskGraphPatch, TaskGraphState


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


class InMemoryTaskGraphStore:
    """In-memory graph store used for local runtime wiring and tests."""

    _ALLOWED_STATUS_TRANSITIONS: dict[NodeStatus, set[NodeStatus]] = {
        NodeStatus.PENDING: {NodeStatus.READY},
        NodeStatus.READY: {NodeStatus.RUNNING},
        NodeStatus.RUNNING: {NodeStatus.COMPLETED, NodeStatus.BLOCKED, NodeStatus.FAILED},
        NodeStatus.BLOCKED: {NodeStatus.READY},
    }

    def __init__(self) -> None:
        self._graphs: dict[str, TaskGraphState] = {}

    def get_graph(self, graph_id: str) -> TaskGraphState | None:
        graph = self._graphs.get(graph_id)
        return deepcopy(graph) if graph is not None else None

    def save_graph(self, graph: TaskGraphState) -> None:
        self._graphs[graph.graph_id] = deepcopy(graph)

    def apply_patch(self, graph_id: str, patch: TaskGraphPatch) -> TaskGraphState:
        current_graph = self._graphs.get(graph_id)
        if current_graph is None:
            raise KeyError(f"Task graph not found: {graph_id}")

        updated_graph = deepcopy(current_graph)
        updated_nodes = deepcopy(updated_graph.nodes)
        node_index = {node.node_id: index for index, node in enumerate(updated_nodes)}

        for node_patch in patch.node_updates:
            if node_patch.node_id not in node_index:
                raise KeyError(f"Task graph node not found: {node_patch.node_id}")
            current_node = updated_nodes[node_index[node_patch.node_id]]
            self._validate_node_patch(current_node, node_patch)
            self._apply_node_patch(current_node, node_patch)

        for new_node in patch.new_nodes:
            if new_node.node_id in node_index:
                raise ValueError(f"Duplicate task graph node id: {new_node.node_id}")
            self._validate_new_node(new_node)
            updated_nodes.append(deepcopy(new_node))
            node_index[new_node.node_id] = len(updated_nodes) - 1

        updated_graph.nodes = updated_nodes

        if patch.active_node_id is not None:
            if patch.active_node_id and patch.active_node_id not in node_index:
                raise KeyError(f"Active task graph node not found: {patch.active_node_id}")
            updated_graph.active_node_id = patch.active_node_id

        if patch.graph_status is not None:
            updated_graph.graph_status = patch.graph_status

        updated_graph.version += 1
        self._graphs[graph_id] = deepcopy(updated_graph)
        return deepcopy(updated_graph)

    def get_node(self, graph_id: str, node_id: str) -> TaskGraphNode | None:
        graph = self._graphs.get(graph_id)
        if graph is None:
            return None
        for node in graph.nodes:
            if node.node_id == node_id:
                return deepcopy(node)
        return None

    def get_active_node(self, graph_id: str) -> TaskGraphNode | None:
        graph = self._graphs.get(graph_id)
        if graph is None or not graph.active_node_id:
            return None
        return self.get_node(graph_id, graph.active_node_id)

    def list_nodes(self, graph_id: str) -> list[TaskGraphNode]:
        graph = self._graphs.get(graph_id)
        if graph is None:
            return []
        return deepcopy(graph.nodes)

    @staticmethod
    def _apply_node_patch(node: TaskGraphNode, patch: NodePatch) -> None:
        if patch.node_status is not None:
            node.node_status = patch.node_status
        if patch.owner is not None:
            node.owner = patch.owner
        if patch.dependencies is not None:
            node.dependencies = list(patch.dependencies)
        if patch.order is not None:
            node.order = patch.order
        if patch.artifacts is not None:
            InMemoryTaskGraphStore._merge_result_refs(node.artifacts, patch.artifacts)
        if patch.evidence is not None:
            InMemoryTaskGraphStore._merge_result_refs(node.evidence, patch.evidence)
        if patch.notes is not None:
            InMemoryTaskGraphStore._merge_notes(node.notes, patch.notes)
        if patch.block_reason is not None:
            node.block_reason = patch.block_reason
        if patch.failure_reason is not None:
            node.failure_reason = patch.failure_reason

    @staticmethod
    def _merge_notes(target: list[str], incoming: list[str]) -> None:
        for note in incoming:
            if note:
                target.append(note)

    @staticmethod
    def _merge_result_refs(target: list[ResultRef], incoming: list[ResultRef]) -> None:
        existing_ids = {item.ref_id for item in target}
        for item in incoming:
            if item.ref_id not in existing_ids:
                target.append(deepcopy(item))
                existing_ids.add(item.ref_id)

    @staticmethod
    def _validate_node_patch(node: TaskGraphNode, patch: NodePatch) -> None:
        if patch.node_status is NodeStatus.BLOCKED and not patch.block_reason:
            raise ValueError("Blocked node patch requires block_reason")
        if patch.node_status is NodeStatus.FAILED and not patch.failure_reason:
            raise ValueError("Failed node patch requires failure_reason")

        InMemoryTaskGraphStore._validate_status_transition(node.node_status, patch.node_status)
        InMemoryTaskGraphStore._validate_result_refs(patch.artifacts)
        InMemoryTaskGraphStore._validate_result_refs(patch.evidence)

    @staticmethod
    def _validate_new_node(node: TaskGraphNode) -> None:
        if node.node_status is NodeStatus.BLOCKED and not node.block_reason:
            raise ValueError("Blocked node requires block_reason")
        if node.node_status is NodeStatus.FAILED and not node.failure_reason:
            raise ValueError("Failed node requires failure_reason")

        InMemoryTaskGraphStore._validate_result_refs(node.artifacts)
        InMemoryTaskGraphStore._validate_result_refs(node.evidence)

    @staticmethod
    def _validate_result_refs(refs: list[ResultRef] | None) -> None:
        if refs is None:
            return

        for item in refs:
            if not item.ref_id:
                raise ValueError("ResultRef requires non-empty ref_id")

    @classmethod
    def _validate_status_transition(
        cls,
        current_status: NodeStatus,
        next_status: NodeStatus | None,
    ) -> None:
        if next_status is None or next_status is current_status:
            return

        allowed_next = cls._ALLOWED_STATUS_TRANSITIONS.get(current_status, set())
        if next_status not in allowed_next:
            raise ValueError(
                f"Illegal node status transition: {current_status.value} -> {next_status.value}"
            )
