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
        self.task_counter = 0
        self.run_counter = 0

    def create_session_id(self) -> str:
        self.calls.append("session")
        return "sess-1"

    def create_task_id(self) -> str:
        self.calls.append("task")
        self.task_counter += 1
        return f"task-{self.task_counter}"

    def create_run_id(self) -> str:
        self.calls.append("run")
        self.run_counter += 1
        return f"run-{self.run_counter}"


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

    def test_start_task_generates_new_task_id_and_clears_active_run_id(self):
        id_generator = StubHostIdGenerator()
        host = RuntimeHost(
            graph_store=InMemoryTaskGraphStore(),
            orchestrator=RuntimeOrchestrator(),
            id_generator=id_generator,
        )
        host.host_state.active_run_id = "run-9"

        task_ref = host.start_task(label="Implement host task flow")

        self.assertEqual(task_ref.task_id, "task-1")
        self.assertEqual(host.host_state.session_id, "sess-1")
        self.assertEqual(host.host_state.current_task_id, "task-1")
        self.assertEqual(host.host_state.active_run_id, "")
        self.assertEqual(id_generator.calls, ["session", "task"])

    def test_start_task_allows_repeated_explicit_task_switches(self):
        host = RuntimeHost(
            graph_store=InMemoryTaskGraphStore(),
            orchestrator=RuntimeOrchestrator(),
            id_generator=StubHostIdGenerator(),
        )

        first_task = host.start_task()
        second_task = host.start_task(label="Another task")

        self.assertEqual(first_task.task_id, "task-1")
        self.assertEqual(second_task.task_id, "task-2")
        self.assertEqual(host.host_state.current_task_id, "task-2")
        self.assertEqual(host.host_state.active_run_id, "")

    def test_submit_user_input_auto_creates_default_task_and_active_run(self):
        id_generator = StubHostIdGenerator()
        host = RuntimeHost(
            graph_store=InMemoryTaskGraphStore(),
            orchestrator=RuntimeOrchestrator(),
            id_generator=id_generator,
        )

        run_result = host.submit_user_input("Continue runtime-v2 host implementation.")

        self.assertEqual(run_result.task_id, "task-1")
        self.assertEqual(run_result.run_id, "run-1")
        self.assertEqual(run_result.runtime_state, "stub")
        self.assertEqual(run_result.output_text, "")
        self.assertEqual(host.host_state.current_task_id, "task-1")
        self.assertEqual(host.host_state.active_run_id, "run-1")
        self.assertEqual(id_generator.calls, ["session", "task", "run"])

    def test_submit_user_input_reuses_existing_task_and_generates_new_run(self):
        id_generator = StubHostIdGenerator()
        host = RuntimeHost(
            graph_store=InMemoryTaskGraphStore(),
            orchestrator=RuntimeOrchestrator(),
            id_generator=id_generator,
        )
        host.start_task(label="Host task")

        first_result = host.submit_user_input("First input")
        second_result = host.submit_user_input("Second input")

        self.assertEqual(first_result.task_id, "task-1")
        self.assertEqual(second_result.task_id, "task-1")
        self.assertEqual(first_result.run_id, "run-1")
        self.assertEqual(second_result.run_id, "run-2")
        self.assertEqual(host.host_state.current_task_id, "task-1")
        self.assertEqual(host.host_state.active_run_id, "run-2")
        self.assertEqual(id_generator.calls, ["session", "task", "run", "run"])


if __name__ == "__main__":
    unittest.main()
