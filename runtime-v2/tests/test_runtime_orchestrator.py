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


class RuntimeOrchestratorTests(unittest.TestCase):
    def test_build_initial_context_creates_minimal_formal_run_context(self):
        orchestrator = RuntimeOrchestrator()

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
        orchestrator = RuntimeOrchestrator()

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
        orchestrator = RuntimeOrchestrator()

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
        orchestrator = RuntimeOrchestrator()
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
        orchestrator = RuntimeOrchestrator()
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
        orchestrator = RuntimeOrchestrator()
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
        orchestrator = RuntimeOrchestrator()
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
        orchestrator = RuntimeOrchestrator()
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
        orchestrator = RuntimeOrchestrator()
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
        orchestrator = RuntimeOrchestrator()
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
        orchestrator = RuntimeOrchestrator()
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


if __name__ == "__main__":
    unittest.main()
