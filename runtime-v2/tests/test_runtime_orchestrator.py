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
from rtv2.task_graph.models import TaskGraphStatus


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


if __name__ == "__main__":
    unittest.main()
