"""RuntimeSolver for node-scoped multi-step execution."""

from __future__ import annotations

from rtv2.solver.models import SolverResult, StepResult, StepStatusSignal
from rtv2.solver.react_step import ReActStepInput, ReActStepRunner
from rtv2.state.models import RunContext
from rtv2.task_graph.models import NodePatch, NodeStatus, TaskGraphNode, TaskGraphPatch, TaskGraphState


class RuntimeSolver:
    """Solve a single active node through a bounded multi-step loop."""

    def __init__(
        self,
        *,
        react_step_runner: ReActStepRunner,
        max_steps_per_node: int = 20,
    ) -> None:
        if max_steps_per_node <= 0:
            raise ValueError("max_steps_per_node must be positive")
        self.react_step_runner = react_step_runner
        self.max_steps_per_node = max_steps_per_node

    def solve_current_node(
        self,
        *,
        context: RunContext,
        node: TaskGraphNode,
        build_step_prompt,
        create_step_id,
    ) -> SolverResult:
        """Run the minimal node-scoped solve loop for the selected node."""

        if node.node_status is NodeStatus.PENDING:
            return SolverResult(
                final_step_result=self._advance_pending_node(context.domain_state.task_graph_state, node),
                final_node_status=NodeStatus.READY if self._can_promote_pending_node(context.domain_state.task_graph_state, node) else None,
                step_count=0,
            )

        current_node = node
        final_step_result: StepResult | None = None
        step_count = 0
        running_transition_patch: TaskGraphPatch | None = None

        if current_node.node_status is NodeStatus.READY:
            running_transition_patch = TaskGraphPatch(
                node_updates=[NodePatch(
                    node_id=current_node.node_id,
                    node_status=NodeStatus.RUNNING,
                )]
            )
            final_step_result = StepResult(
                patch=running_transition_patch
            )
            current_node = self._materialize_node_status(current_node, NodeStatus.RUNNING)

        if current_node.node_status is not NodeStatus.RUNNING:
            return SolverResult(
                final_step_result=final_step_result,
                final_node_status=current_node.node_status,
                step_count=step_count,
            )

        while step_count < self.max_steps_per_node:
            step_count += 1
            react_output = self.react_step_runner.run_step(
                ReActStepInput(
                    step_prompt=build_step_prompt(context, current_node),
                    task_id=context.run_identity.task_id,
                    run_id=context.run_identity.run_id,
                    step_id=create_step_id(),
                    node_id=current_node.node_id,
                )
            )
            final_step_result = self._materialize_running_node_step_result(
                current_node,
                react_output.step_result,
            )
            if final_step_result is None:
                return SolverResult(
                    final_step_result=None,
                    final_node_status=current_node.node_status,
                    step_count=step_count,
                )

            signal = final_step_result.status_signal
            if signal is StepStatusSignal.PROGRESSED:
                continue
            if signal is StepStatusSignal.READY_FOR_COMPLETION:
                final_step_result = self._merge_with_running_transition(
                    running_transition_patch,
                    final_step_result,
                )
                return SolverResult(
                    final_step_result=final_step_result,
                    final_node_status=NodeStatus.COMPLETED,
                    step_count=step_count,
                )
            if signal is StepStatusSignal.BLOCKED:
                final_step_result = self._merge_with_running_transition(
                    running_transition_patch,
                    final_step_result,
                )
                return SolverResult(
                    final_step_result=final_step_result,
                    final_node_status=NodeStatus.BLOCKED,
                    step_count=step_count,
                )
            if signal is StepStatusSignal.FAILED:
                final_step_result = self._merge_with_running_transition(
                    running_transition_patch,
                    final_step_result,
                )
                return SolverResult(
                    final_step_result=final_step_result,
                    final_node_status=NodeStatus.FAILED,
                    step_count=step_count,
                )

        terminal_step_result = StepResult(
                status_signal=StepStatusSignal.BLOCKED,
                reason="solver step limit reached",
                patch=TaskGraphPatch(
                    node_updates=[NodePatch(
                        node_id=current_node.node_id,
                        node_status=NodeStatus.BLOCKED,
                        block_reason="solver step limit reached",
                    )]
                ),
            )
        terminal_step_result = self._merge_with_running_transition(
            running_transition_patch,
            terminal_step_result,
        )
        return SolverResult(
            final_step_result=terminal_step_result,
            final_node_status=NodeStatus.BLOCKED,
            step_count=step_count,
        )

    @staticmethod
    def _merge_with_running_transition(
        running_transition_patch: TaskGraphPatch | None,
        step_result: StepResult | None,
    ) -> StepResult | None:
        if running_transition_patch is None or step_result is None:
            return step_result
        if step_result.patch is None:
            step_result.patch = TaskGraphPatch(
                node_updates=list(running_transition_patch.node_updates),
            )
            return step_result

        step_result.patch = TaskGraphPatch(
            node_updates=list(running_transition_patch.node_updates) + list(step_result.patch.node_updates),
            new_nodes=list(step_result.patch.new_nodes),
            active_node_id=step_result.patch.active_node_id,
            graph_status=step_result.patch.graph_status,
        )
        return step_result

    @staticmethod
    def _can_promote_pending_node(graph_state: TaskGraphState, node: TaskGraphNode) -> bool:
        for dependency_id in node.dependencies:
            dependency_node = RuntimeSolver._find_node(graph_state, dependency_id)
            if dependency_node is None:
                raise ValueError(f"Node dependency not found: {dependency_id}")
            if dependency_node.node_status is not NodeStatus.COMPLETED:
                return False
        return True

    def _advance_pending_node(
        self,
        graph_state: TaskGraphState,
        node: TaskGraphNode,
    ) -> StepResult | None:
        if not self._can_promote_pending_node(graph_state, node):
            return None
        return StepResult(
            patch=TaskGraphPatch(
                node_updates=[NodePatch(
                    node_id=node.node_id,
                    node_status=NodeStatus.READY,
                )]
            )
        )

    @staticmethod
    def _materialize_running_node_step_result(
        node: TaskGraphNode,
        step_result: StepResult | None,
    ) -> StepResult | None:
        if step_result is None or step_result.patch is not None:
            return step_result

        if step_result.status_signal is StepStatusSignal.READY_FOR_COMPLETION:
            step_result.patch = TaskGraphPatch(
                node_updates=[NodePatch(
                    node_id=node.node_id,
                    node_status=NodeStatus.COMPLETED,
                )]
            )
            return step_result

        if step_result.status_signal is StepStatusSignal.BLOCKED:
            step_result.patch = TaskGraphPatch(
                node_updates=[NodePatch(
                    node_id=node.node_id,
                    node_status=NodeStatus.BLOCKED,
                    block_reason=step_result.reason,
                )]
            )
            return step_result

        if step_result.status_signal is StepStatusSignal.FAILED:
            step_result.patch = TaskGraphPatch(
                node_updates=[NodePatch(
                    node_id=node.node_id,
                    node_status=NodeStatus.FAILED,
                    failure_reason=step_result.reason,
                )]
            )
            return step_result

        return step_result

    @staticmethod
    def _materialize_node_status(node: TaskGraphNode, node_status: NodeStatus) -> TaskGraphNode:
        return TaskGraphNode(
            node_id=node.node_id,
            graph_id=node.graph_id,
            name=node.name,
            kind=node.kind,
            description=node.description,
            node_status=node_status,
            owner=node.owner,
            dependencies=list(node.dependencies),
            order=node.order,
            artifacts=list(node.artifacts),
            evidence=list(node.evidence),
            notes=list(node.notes),
            block_reason=node.block_reason,
            failure_reason=node.failure_reason,
        )

    @staticmethod
    def _find_node(graph_state: TaskGraphState, node_id: str) -> TaskGraphNode | None:
        for node in graph_state.nodes:
            if node.node_id == node_id:
                return node
        return None
