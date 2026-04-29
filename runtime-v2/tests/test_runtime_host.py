import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from rtv2.memory import SQLiteRuntimeMemoryStore
from rtv2.host.runtime_host import RuntimeHost
from rtv2.finalize import VerificationResult, VerificationResultStatus
from rtv2.judge import JudgeResultStatus
from rtv2.model.base import ModelOutput
from rtv2.orchestrator.runtime_orchestrator import RuntimeOrchestrator
from rtv2.solver.models import CompletionCheckResult, ReflexionAction, ReflexionResult, StepResult, StepStatusSignal
from rtv2.solver.react_step import ReActStepOutput
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


class SequenceModelProvider:
    def __init__(self, outputs) -> None:
        self.outputs = list(outputs)

    def generate(self, messages, tools, config=None):
        if not self.outputs:
            raise AssertionError("No fake model outputs left")
        return self.outputs.pop(0)


class FakeReActStepRunner:
    def __init__(self) -> None:
        self.inputs = []

    def run_step(self, step_input):
        self.inputs.append(step_input)
        return ReActStepOutput(
            thought="complete node",
            action="finish",
            observation="done",
            step_result=StepResult(
                status_signal=StepStatusSignal.READY_FOR_COMPLETION,
                reason="default host test completion",
            ),
        )


class StubRuntimeVerifier:
    def verify(self, handoff):
        return VerificationResult(
            result_status=VerificationResultStatus.PASS,
            summary="verified",
            issues=[],
        )


class StubCompletionEvaluator:
    def evaluate(self, input):
        return CompletionCheckResult(
            result_status=JudgeResultStatus.PASS,
            summary="complete",
            issues=[],
        )


class StubRuntimeReflexion:
    def reflect(self, input):
        return ReflexionResult(
            summary="retry current node",
            next_attempt_hint="continue",
            action=ReflexionAction.RETRY_CURRENT_NODE,
        )


def create_runtime_host(id_generator: StubHostIdGenerator | None = None) -> RuntimeHost:
    graph_store = InMemoryTaskGraphStore()
    db_dir = tempfile.mkdtemp()
    return RuntimeHost(
        graph_store=graph_store,
        orchestrator=RuntimeOrchestrator(
            graph_store=graph_store,
            planner_model_provider=SequenceModelProvider(
                [
                    ModelOutput(
                        content=(
                            '{"goal":"Handle current request.","active_node_ref":"plan_node_1","nodes":'
                            '[{"ref":"plan_node_1","name":"Handle request","kind":"execution",'
                            '"description":"Handle current request.","node_status":"ready",'
                            '"owner":"main","dependencies":[],"order":1}]}'
                        )
                    )
                ]
                * 8
            ),
            finalize_model_provider=SequenceModelProvider(
                [
                    ModelOutput(
                        content='{"final_output":"Host final answer.","graph_summary":"Completed graph."}'
                    )
                ]
                * 8
            ),
            runtime_verifier=StubRuntimeVerifier(),
            completion_evaluator=StubCompletionEvaluator(),
            runtime_reflexion=StubRuntimeReflexion(),
            react_step_runner=FakeReActStepRunner(),
            memory_store=SQLiteRuntimeMemoryStore(db_file=str(Path(db_dir) / "runtime_memory.db")),
        ),
        id_generator=id_generator or StubHostIdGenerator(),
    )


class RuntimeHostTests(unittest.TestCase):
    def test_runtime_host_keeps_core_dependencies_and_initial_host_state(self):
        graph_store = InMemoryTaskGraphStore()
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        orchestrator = RuntimeOrchestrator(
            graph_store=graph_store,
            memory_store=SQLiteRuntimeMemoryStore(db_file=str(Path(tmpdir.name) / "runtime_memory.db")),
        )
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
        host = create_runtime_host()
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
        host = create_runtime_host(id_generator)
        host.host_state.active_run_id = "run-9"

        task_ref = host.start_task(label="Implement host task flow")

        self.assertEqual(task_ref.task_id, "task-1")
        self.assertEqual(host.host_state.session_id, "sess-1")
        self.assertEqual(host.host_state.current_task_id, "task-1")
        self.assertEqual(host.host_state.active_run_id, "")
        self.assertEqual(id_generator.calls, ["session", "task"])

    def test_start_task_allows_repeated_explicit_task_switches(self):
        host = create_runtime_host()

        first_task = host.start_task()
        second_task = host.start_task(label="Another task")

        self.assertEqual(first_task.task_id, "task-1")
        self.assertEqual(second_task.task_id, "task-2")
        self.assertEqual(host.host_state.current_task_id, "task-2")
        self.assertEqual(host.host_state.active_run_id, "")

    def test_submit_user_input_auto_creates_default_task_and_active_run(self):
        id_generator = StubHostIdGenerator()
        host = create_runtime_host(id_generator)

        run_result = host.submit_user_input("Continue runtime-v2 host implementation.")

        self.assertEqual(run_result.task_id, "task-1")
        self.assertEqual(run_result.run_id, "run-1")
        self.assertEqual(run_result.runtime_state, "completed")
        self.assertEqual(run_result.output_text, "Host final answer.")
        self.assertEqual(host.host_state.current_task_id, "task-1")
        self.assertEqual(host.host_state.active_run_id, "run-1")
        self.assertEqual(id_generator.calls, ["session", "task", "run"])

    def test_submit_user_input_reuses_existing_task_and_generates_new_run(self):
        id_generator = StubHostIdGenerator()
        host = create_runtime_host(id_generator)
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
