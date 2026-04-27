import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from rtv2.host.interfaces import StartRunIdentity
from rtv2.orchestrator.runtime_orchestrator import RuntimeOrchestrator
from rtv2.state.models import RunPhase
from rtv2.task_graph.models import NodeStatus, TaskGraphNode, TaskGraphStatus
from rtv2.task_graph.store import InMemoryTaskGraphStore


def create_orchestrator() -> RuntimeOrchestrator:
    return RuntimeOrchestrator(graph_store=InMemoryTaskGraphStore())


class RuntimeOrchestratorTests(unittest.TestCase):
    def test_build_initial_context_creates_minimal_formal_run_context(self):
        orchestrator = create_orchestrator()

        context = orchestrator.build_initial_context(
            StartRunIdentity(
                session_id="sess-1",
                task_id="task-1",
                run_id="run-1",
                user_input="Continue orchestrator work.",
            )
        )

        self.assertEqual(context.run_identity.session_id, "sess-1")
        self.assertEqual(context.run_identity.task_id, "task-1")
        self.assertEqual(context.run_identity.run_id, "run-1")
        self.assertEqual(context.run_identity.user_input, "Continue orchestrator work.")
        self.assertEqual(context.run_lifecycle.lifecycle_state, "running")
        self.assertEqual(context.run_lifecycle.current_phase, RunPhase.PREPARE)
        self.assertEqual(context.runtime_state.active_node_id, "")
        self.assertEqual(context.domain_state.task_graph_state.graph_id, "graph-1")
        self.assertEqual(context.domain_state.task_graph_state.nodes, [])
        self.assertEqual(context.domain_state.task_graph_state.active_node_id, "")
        self.assertEqual(
            context.domain_state.task_graph_state.graph_status,
            TaskGraphStatus.ACTIVE,
        )
        self.assertEqual(context.domain_state.task_graph_state.version, 1)
        self.assertIsNone(context.domain_state.verification_state)

    def test_build_initial_context_generates_distinct_graph_ids(self):
        orchestrator = create_orchestrator()

        first_context = orchestrator.build_initial_context(
            StartRunIdentity(
                session_id="sess-1",
                task_id="task-1",
                run_id="run-1",
                user_input="First run.",
            )
        )
        second_context = orchestrator.build_initial_context(
            StartRunIdentity(
                session_id="sess-1",
                task_id="task-1",
                run_id="run-2",
                user_input="Second run.",
            )
        )

        self.assertEqual(first_context.domain_state.task_graph_state.graph_id, "graph-1")
        self.assertEqual(second_context.domain_state.task_graph_state.graph_id, "graph-2")

    def test_run_advances_through_minimal_phase_chain_and_returns_host_result(self):
        orchestrator = create_orchestrator()

        run_result = orchestrator.run(
            StartRunIdentity(
                session_id="sess-1",
                task_id="task-1",
                run_id="run-1",
                user_input="Run orchestrator chain.",
            )
        )

        self.assertEqual(run_result.task_id, "task-1")
        self.assertEqual(run_result.run_id, "run-1")
        self.assertEqual(run_result.runtime_state, "completed")
        self.assertEqual(run_result.output_text, "")

    def test_prepare_execute_finalize_methods_advance_minimal_state(self):
        orchestrator = create_orchestrator()
        context = orchestrator.build_initial_context(
            StartRunIdentity(
                session_id="sess-1",
                task_id="task-1",
                run_id="run-1",
                user_input="Phase transition test.",
            )
        )

        prepared = orchestrator.run_prepare_phase(context)
        self.assertEqual(prepared.run_lifecycle.current_phase, RunPhase.EXECUTE)

        executed = orchestrator.run_execute_phase(prepared)
        self.assertEqual(executed.run_lifecycle.current_phase, RunPhase.FINALIZE)
        self.assertEqual(executed.run_lifecycle.result_status, "completed")
        self.assertEqual(executed.run_lifecycle.stop_reason, "execute_finished")

        finalized = orchestrator.run_finalize_phase(executed)
        self.assertEqual(finalized.runtime_state, "completed")
        self.assertEqual(finalized.output_text, "")

    def test_phase_methods_raise_when_called_out_of_order(self):
        orchestrator = create_orchestrator()
        context = orchestrator.build_initial_context(
            StartRunIdentity(
                session_id="sess-1",
                task_id="task-1",
                run_id="run-1",
                user_input="Out of order test.",
            )
        )

        with self.assertRaises(ValueError):
            orchestrator.run_execute_phase(context)

        with self.assertRaises(ValueError):
            orchestrator.run_finalize_phase(context)

    def test_select_active_node_prefers_runtime_state_active_node(self):
        orchestrator = create_orchestrator()
        context = orchestrator.build_initial_context(
            StartRunIdentity(
                session_id="sess-1",
                task_id="task-1",
                run_id="run-1",
                user_input="Select runtime node.",
            )
        )
        context.domain_state.task_graph_state.nodes = [
            TaskGraphNode(
                node_id="node-1",
                graph_id=context.domain_state.task_graph_state.graph_id,
                name="A",
                kind="analysis",
                node_status=NodeStatus.READY,
            ),
            TaskGraphNode(
                node_id="node-2",
                graph_id=context.domain_state.task_graph_state.graph_id,
                name="B",
                kind="execution",
                node_status=NodeStatus.RUNNING,
            ),
        ]
        context.runtime_state.active_node_id = "node-2"
        context.domain_state.task_graph_state.active_node_id = "node-1"

        selected = orchestrator.select_active_node(context)

        self.assertIsNotNone(selected)
        self.assertEqual(selected.node_id, "node-2")

    def test_select_active_node_falls_back_to_graph_active_node(self):
        orchestrator = create_orchestrator()
        context = orchestrator.build_initial_context(
            StartRunIdentity(
                session_id="sess-1",
                task_id="task-1",
                run_id="run-1",
                user_input="Select graph node.",
            )
        )
        context.domain_state.task_graph_state.nodes = [
            TaskGraphNode(
                node_id="node-1",
                graph_id=context.domain_state.task_graph_state.graph_id,
                name="A",
                kind="analysis",
                node_status=NodeStatus.READY,
            )
        ]
        context.domain_state.task_graph_state.active_node_id = "node-1"

        selected = orchestrator.select_active_node(context)

        self.assertIsNotNone(selected)
        self.assertEqual(selected.node_id, "node-1")

    def test_select_active_node_falls_back_to_first_ready_or_running_node(self):
        orchestrator = create_orchestrator()
        context = orchestrator.build_initial_context(
            StartRunIdentity(
                session_id="sess-1",
                task_id="task-1",
                run_id="run-1",
                user_input="Select ready node.",
            )
        )
        context.domain_state.task_graph_state.nodes = [
            TaskGraphNode(
                node_id="node-1",
                graph_id=context.domain_state.task_graph_state.graph_id,
                name="Pending",
                kind="analysis",
                node_status=NodeStatus.PENDING,
            ),
            TaskGraphNode(
                node_id="node-2",
                graph_id=context.domain_state.task_graph_state.graph_id,
                name="Ready",
                kind="execution",
                node_status=NodeStatus.READY,
            ),
        ]

        selected = orchestrator.select_active_node(context)

        self.assertIsNotNone(selected)
        self.assertEqual(selected.node_id, "node-2")

    def test_select_active_node_returns_none_when_no_executable_node_exists(self):
        orchestrator = create_orchestrator()
        context = orchestrator.build_initial_context(
            StartRunIdentity(
                session_id="sess-1",
                task_id="task-1",
                run_id="run-1",
                user_input="No executable node.",
            )
        )
        context.domain_state.task_graph_state.nodes = [
            TaskGraphNode(
                node_id="node-1",
                graph_id=context.domain_state.task_graph_state.graph_id,
                name="Pending",
                kind="analysis",
                node_status=NodeStatus.PENDING,
            )
        ]

        self.assertIsNone(orchestrator.select_active_node(context))

    def test_select_active_node_raises_when_runtime_active_node_is_missing(self):
        orchestrator = create_orchestrator()
        context = orchestrator.build_initial_context(
            StartRunIdentity(
                session_id="sess-1",
                task_id="task-1",
                run_id="run-1",
                user_input="Missing runtime node.",
            )
        )
        context.runtime_state.active_node_id = "missing"

        with self.assertRaises(ValueError):
            orchestrator.select_active_node(context)

    def test_select_active_node_raises_when_graph_active_node_is_missing(self):
        orchestrator = create_orchestrator()
        context = orchestrator.build_initial_context(
            StartRunIdentity(
                session_id="sess-1",
                task_id="task-1",
                run_id="run-1",
                user_input="Missing graph node.",
            )
        )
        context.domain_state.task_graph_state.active_node_id = "missing"

        with self.assertRaises(ValueError):
            orchestrator.select_active_node(context)

    def test_initialize_minimal_graph_returns_patch_for_empty_graph(self):
        orchestrator = create_orchestrator()
        context = orchestrator.build_initial_context(
            StartRunIdentity(
                session_id="sess-1",
                task_id="task-1",
                run_id="run-1",
                user_input="Handle this request.",
            )
        )
        context.domain_state.task_graph_state.active_node_id = "stale-node"

        patch = orchestrator.initialize_minimal_graph(context)

        self.assertIsNotNone(patch)
        self.assertEqual(len(patch.new_nodes), 1)
        initial_node = patch.new_nodes[0]
        self.assertEqual(initial_node.node_id, "node-1")
        self.assertEqual(initial_node.graph_id, context.domain_state.task_graph_state.graph_id)
        self.assertEqual(initial_node.name, "Handle user request")
        self.assertEqual(initial_node.kind, "execution")
        self.assertEqual(initial_node.description, "Handle this request.")
        self.assertEqual(initial_node.node_status, NodeStatus.READY)
        self.assertEqual(initial_node.owner, "main")
        self.assertEqual(initial_node.dependencies, [])
        self.assertEqual(initial_node.order, 1)
        self.assertEqual(initial_node.artifacts, [])
        self.assertEqual(initial_node.evidence, [])
        self.assertEqual(initial_node.notes, [])
        self.assertEqual(initial_node.block_reason, "")
        self.assertEqual(initial_node.failure_reason, "")
        self.assertEqual(patch.active_node_id, "node-1")
        self.assertIsNone(patch.graph_status)

    def test_initialize_minimal_graph_returns_none_when_graph_is_not_empty(self):
        orchestrator = create_orchestrator()
        context = orchestrator.build_initial_context(
            StartRunIdentity(
                session_id="sess-1",
                task_id="task-1",
                run_id="run-1",
                user_input="Existing node test.",
            )
        )
        context.domain_state.task_graph_state.nodes = [
            TaskGraphNode(
                node_id="node-existing",
                graph_id=context.domain_state.task_graph_state.graph_id,
                name="Existing",
                kind="execution",
                node_status=NodeStatus.READY,
            )
        ]

        self.assertIsNone(orchestrator.initialize_minimal_graph(context))

    def test_advance_node_minimally_promotes_pending_node_when_dependencies_completed(self):
        orchestrator = create_orchestrator()
        context = orchestrator.build_initial_context(
            StartRunIdentity(
                session_id="sess-1",
                task_id="task-1",
                run_id="run-1",
                user_input="Advance pending node.",
            )
        )
        dependency = TaskGraphNode(
            node_id="node-1",
            graph_id=context.domain_state.task_graph_state.graph_id,
            name="Dependency",
            kind="execution",
            node_status=NodeStatus.COMPLETED,
        )
        pending_node = TaskGraphNode(
            node_id="node-2",
            graph_id=context.domain_state.task_graph_state.graph_id,
            name="Pending",
            kind="execution",
            node_status=NodeStatus.PENDING,
            dependencies=["node-1"],
        )
        context.domain_state.task_graph_state.nodes = [dependency, pending_node]

        patch = orchestrator.advance_node_minimally(context, pending_node)

        self.assertIsNotNone(patch)
        self.assertEqual(patch.node_updates[0].node_id, "node-2")
        self.assertEqual(patch.node_updates[0].node_status, NodeStatus.READY)

    def test_advance_node_minimally_keeps_pending_node_when_dependencies_not_completed(self):
        orchestrator = create_orchestrator()
        context = orchestrator.build_initial_context(
            StartRunIdentity(
                session_id="sess-1",
                task_id="task-1",
                run_id="run-1",
                user_input="Keep pending node.",
            )
        )
        dependency = TaskGraphNode(
            node_id="node-1",
            graph_id=context.domain_state.task_graph_state.graph_id,
            name="Dependency",
            kind="execution",
            node_status=NodeStatus.READY,
        )
        pending_node = TaskGraphNode(
            node_id="node-2",
            graph_id=context.domain_state.task_graph_state.graph_id,
            name="Pending",
            kind="execution",
            node_status=NodeStatus.PENDING,
            dependencies=["node-1"],
        )
        context.domain_state.task_graph_state.nodes = [dependency, pending_node]

        self.assertIsNone(orchestrator.advance_node_minimally(context, pending_node))

    def test_advance_node_minimally_raises_when_dependency_is_missing(self):
        orchestrator = create_orchestrator()
        context = orchestrator.build_initial_context(
            StartRunIdentity(
                session_id="sess-1",
                task_id="task-1",
                run_id="run-1",
                user_input="Missing dependency.",
            )
        )
        pending_node = TaskGraphNode(
            node_id="node-1",
            graph_id=context.domain_state.task_graph_state.graph_id,
            name="Pending",
            kind="execution",
            node_status=NodeStatus.PENDING,
            dependencies=["missing"],
        )
        context.domain_state.task_graph_state.nodes = [pending_node]

        with self.assertRaises(ValueError):
            orchestrator.advance_node_minimally(context, pending_node)

    def test_advance_node_minimally_promotes_ready_to_running(self):
        orchestrator = create_orchestrator()
        context = orchestrator.build_initial_context(
            StartRunIdentity(
                session_id="sess-1",
                task_id="task-1",
                run_id="run-1",
                user_input="Ready node.",
            )
        )
        ready_node = TaskGraphNode(
            node_id="node-1",
            graph_id=context.domain_state.task_graph_state.graph_id,
            name="Ready",
            kind="execution",
            node_status=NodeStatus.READY,
        )

        patch = orchestrator.advance_node_minimally(context, ready_node)

        self.assertIsNotNone(patch)
        self.assertEqual(patch.node_updates[0].node_status, NodeStatus.RUNNING)

    def test_advance_node_minimally_promotes_running_to_completed(self):
        orchestrator = create_orchestrator()
        context = orchestrator.build_initial_context(
            StartRunIdentity(
                session_id="sess-1",
                task_id="task-1",
                run_id="run-1",
                user_input="Running node.",
            )
        )
        running_node = TaskGraphNode(
            node_id="node-1",
            graph_id=context.domain_state.task_graph_state.graph_id,
            name="Running",
            kind="execution",
            node_status=NodeStatus.RUNNING,
        )

        patch = orchestrator.advance_node_minimally(context, running_node)

        self.assertIsNotNone(patch)
        self.assertEqual(patch.node_updates[0].node_status, NodeStatus.COMPLETED)

    def test_advance_node_minimally_returns_none_for_non_progressing_statuses(self):
        orchestrator = create_orchestrator()
        context = orchestrator.build_initial_context(
            StartRunIdentity(
                session_id="sess-1",
                task_id="task-1",
                run_id="run-1",
                user_input="Static statuses.",
            )
        )

        for status in (
            NodeStatus.BLOCKED,
            NodeStatus.PAUSED,
            NodeStatus.FAILED,
            NodeStatus.ABANDONED,
            NodeStatus.COMPLETED,
        ):
            node = TaskGraphNode(
                node_id=f"node-{status.value}",
                graph_id=context.domain_state.task_graph_state.graph_id,
                name=status.value,
                kind="execution",
                node_status=status,
            )
            self.assertIsNone(orchestrator.advance_node_minimally(context, node))

    def test_run_execute_phase_aligns_runtime_active_node_when_node_is_selected(self):
        orchestrator = create_orchestrator()
        context = orchestrator.build_initial_context(
            StartRunIdentity(
                session_id="sess-1",
                task_id="task-1",
                run_id="run-1",
                user_input="Execute selected node.",
            )
        )
        context.run_lifecycle.current_phase = RunPhase.EXECUTE
        ready_node = TaskGraphNode(
            node_id="node-1",
            graph_id=context.domain_state.task_graph_state.graph_id,
            name="Ready",
            kind="execution",
            node_status=NodeStatus.READY,
        )
        context.domain_state.task_graph_state.nodes = [ready_node]

        executed = orchestrator.run_execute_phase(context)

        self.assertEqual(executed.runtime_state.active_node_id, "node-1")
        self.assertEqual(executed.run_lifecycle.current_phase, RunPhase.FINALIZE)
        self.assertEqual(
            executed.domain_state.task_graph_state.nodes[0].node_status,
            NodeStatus.RUNNING,
        )
        self.assertEqual(executed.domain_state.task_graph_state.version, 2)

    def test_run_execute_phase_applies_initialization_patch_back_to_graph(self):
        orchestrator = create_orchestrator()
        context = orchestrator.build_initial_context(
            StartRunIdentity(
                session_id="sess-1",
                task_id="task-1",
                run_id="run-1",
                user_input="Initialize graph.",
            )
        )
        context.run_lifecycle.current_phase = RunPhase.EXECUTE

        executed = orchestrator.run_execute_phase(context)

        self.assertEqual(len(executed.domain_state.task_graph_state.nodes), 1)
        self.assertEqual(executed.domain_state.task_graph_state.active_node_id, "node-1")
        self.assertEqual(executed.runtime_state.active_node_id, "node-1")
        self.assertEqual(executed.domain_state.task_graph_state.version, 2)

    def test_run_execute_phase_applies_node_advancement_patch_back_to_graph(self):
        orchestrator = create_orchestrator()
        context = orchestrator.build_initial_context(
            StartRunIdentity(
                session_id="sess-1",
                task_id="task-1",
                run_id="run-1",
                user_input="Advance node in graph.",
            )
        )
        context.run_lifecycle.current_phase = RunPhase.EXECUTE
        ready_node = TaskGraphNode(
            node_id="node-1",
            graph_id=context.domain_state.task_graph_state.graph_id,
            name="Ready",
            kind="execution",
            node_status=NodeStatus.READY,
        )
        context.domain_state.task_graph_state.nodes = [ready_node]

        executed = orchestrator.run_execute_phase(context)

        self.assertEqual(len(executed.domain_state.task_graph_state.nodes), 1)
        self.assertEqual(
            executed.domain_state.task_graph_state.nodes[0].node_status,
            NodeStatus.RUNNING,
        )
        self.assertEqual(executed.runtime_state.active_node_id, "node-1")
        self.assertEqual(executed.domain_state.task_graph_state.version, 2)


if __name__ == "__main__":
    unittest.main()
