"""RuntimeOrchestrator skeleton module."""

from __future__ import annotations

from rtv2.host.interfaces import HostRunResult, StartRunIdentity
from rtv2.state.models import DomainState, RunContext, RunIdentity, RunLifecycle, RunPhase, RuntimeState
from rtv2.task_graph.models import (
    NodePatch,
    NodeStatus,
    TaskGraphNode,
    TaskGraphPatch,
    TaskGraphState,
    TaskGraphStatus,
)


class RuntimeOrchestrator:
    """Minimal runtime control skeleton for the main execution chain."""

    def __init__(self) -> None:
        self._graph_counter = 0
        self._node_counter = 0

    def build_initial_context(self, start_run_identity: StartRunIdentity) -> RunContext:
        """Build the minimal formal run context for a new run."""

        graph_id = self._create_graph_id()
        return RunContext(
            run_identity=RunIdentity(
                session_id=start_run_identity.session_id,
                task_id=start_run_identity.task_id,
                run_id=start_run_identity.run_id,
                user_input=start_run_identity.user_input,
            ),
            run_lifecycle=RunLifecycle(
                lifecycle_state="running",
                current_phase=RunPhase.PREPARE,
            ),
            runtime_state=RuntimeState(),
            domain_state=DomainState(
                task_graph_state=TaskGraphState(
                    graph_id=graph_id,
                    nodes=[],
                    active_node_id="",
                    graph_status=TaskGraphStatus.ACTIVE,
                    version=1,
                )
            ),
        )

    def run(self, start_run_identity: StartRunIdentity) -> HostRunResult:
        """Run the minimal prepare -> execute -> finalize skeleton."""

        context = self.build_initial_context(start_run_identity)
        context = self.run_prepare_phase(context)
        context = self.run_execute_phase(context)
        return self.run_finalize_phase(context)

    def run_prepare_phase(self, context: RunContext) -> RunContext:
        """Advance the context from prepare into execute."""

        if context.run_lifecycle.current_phase is not RunPhase.PREPARE:
            raise ValueError("Prepare phase requires current_phase=PREPARE")

        context.run_lifecycle.current_phase = RunPhase.EXECUTE
        return context

    def run_execute_phase(self, context: RunContext) -> RunContext:
        """Advance the context from execute into finalize."""

        if context.run_lifecycle.current_phase is not RunPhase.EXECUTE:
            raise ValueError("Execute phase requires current_phase=EXECUTE")

        selected_node = self.select_active_node(context)
        if selected_node is None:
            self.initialize_minimal_graph(context)
        else:
            context.runtime_state.active_node_id = selected_node.node_id
            self.advance_node_minimally(context, selected_node)
        context.run_lifecycle.current_phase = RunPhase.FINALIZE
        context.run_lifecycle.result_status = "completed"
        context.run_lifecycle.stop_reason = "execute_finished"
        return context

    def run_finalize_phase(self, context: RunContext) -> HostRunResult:
        """Finalize a completed context into a host-facing run result."""

        if context.run_lifecycle.current_phase is not RunPhase.FINALIZE:
            raise ValueError("Finalize phase requires current_phase=FINALIZE")

        return HostRunResult(
            task_id=context.run_identity.task_id,
            run_id=context.run_identity.run_id,
            runtime_state="completed",
            output_text="",
        )

    def _create_graph_id(self) -> str:
        """Create a graph id inside the orchestrator boundary."""

        self._graph_counter += 1
        return f"graph-{self._graph_counter}"

    def _create_node_id(self) -> str:
        """Create a node id inside the orchestrator boundary."""

        self._node_counter += 1
        return f"node-{self._node_counter}"

    def select_active_node(self, context: RunContext) -> TaskGraphNode | None:
        """Select the current executable node using minimal rule-based priority."""

        graph_state = context.domain_state.task_graph_state

        if context.runtime_state.active_node_id:
            node = self._find_node(graph_state, context.runtime_state.active_node_id)
            if node is None:
                raise ValueError("runtime_state.active_node_id points to a missing node")
            return node

        if graph_state.active_node_id:
            node = self._find_node(graph_state, graph_state.active_node_id)
            if node is None:
                raise ValueError("task_graph_state.active_node_id points to a missing node")
            return node

        for node in graph_state.nodes:
            if node.node_status in {NodeStatus.READY, NodeStatus.RUNNING}:
                return node

        return None

    def initialize_minimal_graph(self, context: RunContext) -> TaskGraphPatch | None:
        """Create the first executable node when the current graph is empty."""

        graph_state = context.domain_state.task_graph_state
        if graph_state.nodes:
            return None

        initial_node = TaskGraphNode(
            node_id=self._create_node_id(),
            graph_id=graph_state.graph_id,
            name="Handle user request",
            kind="execution",
            description=context.run_identity.user_input,
            node_status=NodeStatus.READY,
            owner="main",
            dependencies=[],
            order=1,
        )
        return TaskGraphPatch(
            new_nodes=[initial_node],
            active_node_id=initial_node.node_id,
        )

    def advance_node_minimally(
        self,
        context: RunContext,
        node: TaskGraphNode,
    ) -> TaskGraphPatch | None:
        """Return the minimal node status transition patch for the selected node."""

        if node.node_status is NodeStatus.PENDING:
            return self._advance_pending_node(context, node)
        if node.node_status is NodeStatus.READY:
            return TaskGraphPatch(
                node_updates=[NodePatch(
                    node_id=node.node_id,
                    node_status=NodeStatus.RUNNING,
                )]
            )
        if node.node_status is NodeStatus.RUNNING:
            return TaskGraphPatch(
                node_updates=[NodePatch(
                    node_id=node.node_id,
                    node_status=NodeStatus.COMPLETED,
                )]
            )
        return None

    def _advance_pending_node(
        self,
        context: RunContext,
        node: TaskGraphNode,
    ) -> TaskGraphPatch | None:
        graph_state = context.domain_state.task_graph_state

        for dependency_id in node.dependencies:
            dependency_node = self._find_node(graph_state, dependency_id)
            if dependency_node is None:
                raise ValueError(f"Node dependency not found: {dependency_id}")
            if dependency_node.node_status is not NodeStatus.COMPLETED:
                return None

        return TaskGraphPatch(
            node_updates=[NodePatch(
                node_id=node.node_id,
                node_status=NodeStatus.READY,
            )]
        )

    @staticmethod
    def _find_node(graph_state: TaskGraphState, node_id: str) -> TaskGraphNode | None:
        for node in graph_state.nodes:
            if node.node_id == node_id:
                return node
        return None
