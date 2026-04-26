import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from rtv2.host.runtime_host import RuntimeHost
from rtv2.orchestrator.runtime_orchestrator import RuntimeOrchestrator
from rtv2.task_graph.store import InMemoryTaskGraphStore


class StubHostIdGenerator:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def create_session_id(self) -> str:
        self.calls.append("session")
        return "sess-1"

    def create_task_id(self) -> str:
        self.calls.append("task")
        return "task-1"

    def create_run_id(self) -> str:
        self.calls.append("run")
        return "run-1"


class RuntimeHostTests(unittest.TestCase):
    def test_runtime_host_keeps_core_dependencies_and_initial_host_state(self):
        graph_store = InMemoryTaskGraphStore()
        orchestrator = RuntimeOrchestrator()
        id_generator = StubHostIdGenerator()

        host = RuntimeHost(
            graph_store=graph_store,
            orchestrator=orchestrator,
            id_generator=id_generator,
        )

        self.assertIs(host.graph_store, graph_store)
        self.assertIs(host.orchestrator, orchestrator)
        self.assertIs(host.id_generator, id_generator)
        self.assertEqual(host.host_state.session_id, "sess-1")
        self.assertEqual(host.host_state.current_task_id, "")
        self.assertEqual(host.host_state.active_run_id, "")
        self.assertEqual(id_generator.calls, ["session"])

    def test_get_host_state_returns_snapshot_copy(self):
        host = RuntimeHost(
            graph_store=InMemoryTaskGraphStore(),
            orchestrator=RuntimeOrchestrator(),
            id_generator=StubHostIdGenerator(),
        )
        host.host_state.current_task_id = "task-2"
        host.host_state.active_run_id = "run-2"

        snapshot = host.get_host_state()
        snapshot.current_task_id = "mutated"
        snapshot.active_run_id = "mutated-run"

        self.assertEqual(snapshot.session_id, "sess-1")
        self.assertEqual(host.host_state.current_task_id, "task-2")
        self.assertEqual(host.host_state.active_run_id, "run-2")


if __name__ == "__main__":
    unittest.main()
