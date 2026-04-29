import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from rtv2.host.interfaces import StartRunIdentity
from rtv2.finalize import (
    RunReflexionAction,
    RunReflexionResult,
    RuntimeVerifier,
    VerificationResult,
    VerificationResultStatus,
)
from rtv2.judge import JudgeResultStatus
from rtv2.memory import (
    RuntimeMemoryEntry,
    RuntimeMemoryEntryType,
    RuntimeMemoryQuery,
    RuntimeMemoryRole,
    SQLiteRuntimeMemoryStore,
)
from rtv2.orchestrator.runtime_orchestrator import RuntimeOrchestrator
from rtv2.skills import RuntimeSkill, SkillManifest, SkillRegistry, SkillStatus
from rtv2.model.base import ModelOutput
from rtv2.solver import RuntimeSolver
from rtv2.solver.react_step import ReActStepOutput
from rtv2.solver.models import (
    CompletionCheckResult,
    ReflexionAction,
    ReflexionResult,
    SolverControlSignal,
    StepResult,
    StepStatusSignal,
)
from rtv2.state.models import RunPhase
from rtv2.task_graph.models import NodePatch, NodeStatus, TaskGraphNode, TaskGraphPatch, TaskGraphStatus
from rtv2.task_graph.store import InMemoryTaskGraphStore
from rtv2.tools import ToolRegistry, tool


class FakeReActStepRunner:
    def __init__(self, output: ReActStepOutput | None = None) -> None:
        self.output = output or ReActStepOutput(
            thought="",
            action="",
            observation="",
            step_result=StepResult(),
        )
        self.inputs = []

    def run_step(self, step_input):
        self.inputs.append(step_input)
        return self.output


class SequenceReActStepRunner:
    def __init__(self, outputs) -> None:
        self.outputs = list(outputs)
        self.inputs = []

    def run_step(self, step_input):
        self.inputs.append(step_input)
        if not self.outputs:
            raise AssertionError("No fake react outputs left")
        return self.outputs.pop(0)


class StubRuntimeVerifier:
    def __init__(self, result: VerificationResult | None = None) -> None:
        self.result = result or VerificationResult(
            result_status=VerificationResultStatus.PASS,
            summary="verified",
            issues=[],
        )
        self.handoffs = []

    def verify(self, handoff):
        self.handoffs.append(handoff)
        return self.result


class SequenceRuntimeVerifier:
    def __init__(self, results) -> None:
        self.results = list(results)
        self.handoffs = []

    def verify(self, handoff):
        self.handoffs.append(handoff)
        if not self.results:
            raise AssertionError("No verifier results left")
        return self.results.pop(0)


class StubCompletionEvaluator:
    def __init__(self, result: CompletionCheckResult | None = None) -> None:
        self.result = result or CompletionCheckResult(
            result_status=JudgeResultStatus.PASS,
            summary="completion verified",
            issues=[],
        )
        self.inputs = []

    def evaluate(self, input):
        self.inputs.append(input)
        return self.result


class StubRuntimeReflexion:
    def __init__(self, result: ReflexionResult | None = None) -> None:
        self.result = result or ReflexionResult(
            summary="mark current node failed",
            next_attempt_hint="stop the current node",
            action=ReflexionAction.MARK_FAILED,
        )
        self.inputs = []

    def reflect(self, input, prompt_text=""):
        self.inputs.append(input)
        return self.result


class StubFinalizeReflexion:
    def __init__(self, result: RunReflexionResult | None = None) -> None:
        self.result = result or RunReflexionResult(
            summary="finish failed",
            action=RunReflexionAction.FINISH_FAILED,
        )
        self.inputs = []

    def reflect(self, input, prompt_text=""):
        self.inputs.append(input)
        return self.result


def create_orchestrator(
    react_step_runner=None,
    planner_model_provider=None,
    finalize_model_provider=None,
    runtime_verifier=None,
    finalize_reflexion=None,
    completion_evaluator=None,
    runtime_reflexion=None,
) -> RuntimeOrchestrator:
    db_dir = tempfile.mkdtemp()
    return RuntimeOrchestrator(
        graph_store=InMemoryTaskGraphStore(),
        react_step_runner=react_step_runner or FakeReActStepRunner(
            ReActStepOutput(
                thought="complete node",
                action="finish",
                observation="done",
                step_result=StepResult(
                    status_signal=StepStatusSignal.READY_FOR_COMPLETION,
                    reason="default fake completion",
                ),
            )
        ),
        planner_model_provider=planner_model_provider,
        finalize_model_provider=finalize_model_provider or SequenceModelProvider(
            [
                ModelOutput(
                    content='{"final_output":"Final answer.","graph_summary":"All graph nodes completed."}'
                )
            ]
        ),
        runtime_verifier=runtime_verifier or StubRuntimeVerifier(),
        finalize_reflexion=finalize_reflexion or StubFinalizeReflexion(),
        completion_evaluator=completion_evaluator or StubCompletionEvaluator(),
        runtime_reflexion=runtime_reflexion or StubRuntimeReflexion(),
        memory_store=SQLiteRuntimeMemoryStore(db_file=str(Path(db_dir) / "runtime_memory.db")),
    )


class SequenceModelProvider:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls = []

    def generate(self, messages, tools, config=None):
        self.calls.append({"messages": messages, "tools": tools, "config": config})
        if not self.outputs:
            raise AssertionError("No fake model outputs left")
        return self.outputs.pop(0)


@tool(
    name="echo_text",
    description="Echo text.",
    parameters={
        "type": "object",
        "properties": {
            "text": {"type": "string"},
        },
        "required": ["text"],
    },
)
def echo_text(text: str) -> str:
    return f"echo:{text}"


class RuntimeOrchestratorTests(unittest.TestCase):
    def create_memory_store(self) -> SQLiteRuntimeMemoryStore:
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        return SQLiteRuntimeMemoryStore(db_file=str(Path(tmpdir.name) / "runtime_memory.db"))

    def create_skill_dir(
        self,
        root: Path,
        *,
        folder_name: str,
        description: str = "Use this skill when needed.",
    ) -> Path:
        skill_dir = root / folder_name
        skill_dir.mkdir(parents=True, exist_ok=False)
        (skill_dir / "SKILL.md").write_text(
            "\n".join(
                [
                    "---",
                    f"name: {folder_name}",
                    f"description: {description}",
                    "---",
                    "",
                    "# Skill Body",
                    "Detailed instructions.",
                ]
            ),
            encoding="utf-8",
        )
        refs_dir = skill_dir / "references"
        refs_dir.mkdir()
        (refs_dir / "guide.md").write_text("guide", encoding="utf-8")
        return skill_dir

    def test_explicit_react_step_runner_takes_priority_over_tool_registry_auto_wiring(self):
        registry = ToolRegistry()
        registry.register(echo_text)
        explicit_runner = FakeReActStepRunner()

        orchestrator = RuntimeOrchestrator(
            graph_store=InMemoryTaskGraphStore(),
            react_step_runner=explicit_runner,
            tool_registry=registry,
            memory_store=self.create_memory_store(),
        )

        self.assertIs(orchestrator.react_step_runner, explicit_runner)

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
        orchestrator = create_orchestrator(
            planner_model_provider=SequenceModelProvider(
                [
                    ModelOutput(
                        content=(
                            '{"goal":"Run orchestrator chain.","active_node_ref":"plan_node_1","nodes":'
                            '[{"ref":"plan_node_1","name":"Handle request","kind":"execution",'
                            '"description":"Run orchestrator chain.","node_status":"ready",'
                            '"owner":"main","dependencies":[],"order":1}]}'
                        )
                    )
                ]
            )
        )

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
        self.assertEqual(run_result.output_text, "Final answer.")

    def test_prepare_execute_finalize_methods_advance_minimal_state(self):
        planner = SequenceModelProvider(
            [
                ModelOutput(
                    content=(
                        '{"goal":"Phase transition test.","active_node_ref":"plan_node_1","nodes":'
                        '[{"ref":"plan_node_1","name":"Handle request","kind":"execution",'
                        '"description":"Phase transition test.","node_status":"ready",'
                        '"owner":"main","dependencies":[],"order":1}]}'
                    )
                )
            ]
        )
        orchestrator = create_orchestrator(planner_model_provider=planner)
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
        self.assertEqual(prepared.run_identity.goal, "Phase transition test.")
        self.assertEqual(len(prepared.domain_state.task_graph_state.nodes), 1)
        self.assertTrue(prepared.runtime_state.active_node_id)
        self.assertEqual(len(planner.calls), 1)
        self.assertEqual(planner.calls[0]["tools"], [])

        executed = orchestrator.run_execute_phase(prepared)
        self.assertEqual(executed.run_lifecycle.current_phase, RunPhase.FINALIZE)
        self.assertEqual(executed.run_lifecycle.result_status, "completed")
        self.assertEqual(executed.run_lifecycle.stop_reason, "execute_finished")

        finalized = orchestrator.run_finalize_phase(executed)
        self.assertEqual(finalized.runtime_state, "completed")
        self.assertEqual(finalized.output_text, "Final answer.")
        self.assertEqual(executed.run_lifecycle.result_status, "pass")
        self.assertEqual(executed.run_lifecycle.stop_reason, "finalize_passed")

    def test_prepare_phase_runs_planner_and_writes_goal_graph_and_memory(self):
        planner = SequenceModelProvider(
            [
                ModelOutput(
                    content=(
                        '{"goal":"Plan runtime implementation.","active_node_ref":"plan_node_2","nodes":'
                        '[{"ref":"plan_node_1","name":"Review context","kind":"analysis",'
                        '"description":"Review the current runtime state.","node_status":"pending",'
                        '"owner":"","dependencies":[],"order":1},'
                        '{"ref":"plan_node_2","name":"Implement prepare phase","kind":"execution",'
                        '"description":"Implement the initial prepare planner.","node_status":"ready",'
                        '"owner":"main","dependencies":["plan_node_1"],"order":2}]}'
                    )
                )
            ]
        )
        orchestrator = create_orchestrator(planner_model_provider=planner)
        context = orchestrator.build_initial_context(
            StartRunIdentity(
                session_id="sess-1",
                task_id="task-1",
                run_id="run-1",
                user_input="Implement prepare phase.",
            )
        )

        prepared = orchestrator.run_prepare_phase(context)

        self.assertEqual(prepared.run_identity.goal, "Plan runtime implementation.")
        self.assertIsNotNone(prepared.runtime_state.prepare_result)
        self.assertEqual(prepared.run_lifecycle.current_phase, RunPhase.EXECUTE)
        self.assertEqual(len(prepared.domain_state.task_graph_state.nodes), 2)
        first_node, second_node = prepared.domain_state.task_graph_state.nodes
        self.assertEqual(first_node.owner, "main")
        self.assertEqual(second_node.dependencies, [first_node.node_id])
        self.assertEqual(prepared.domain_state.task_graph_state.active_node_id, second_node.node_id)
        self.assertEqual(prepared.runtime_state.active_node_id, second_node.node_id)

        entries = orchestrator.memory_store.list_entries_for_run(task_id="task-1", run_id="run-1")
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0].content, "Implement prepare phase.")
        self.assertIn("goal: Plan runtime implementation.", entries[1].content)
        self.assertIn("graph_change_summary: added 2 nodes", entries[1].content)

    def test_prepare_phase_rejects_invalid_planner_payload(self):
        planner = SequenceModelProvider([ModelOutput(content='{"goal":"","nodes":[]}')])
        orchestrator = create_orchestrator(planner_model_provider=planner)
        context = orchestrator.build_initial_context(
            StartRunIdentity(
                session_id="sess-1",
                task_id="task-1",
                run_id="run-1",
                user_input="Implement prepare phase.",
            )
        )

        with self.assertRaises(ValueError):
            orchestrator.run_prepare_phase(context)

    def test_prepare_phase_rejects_non_empty_graph_for_first_version(self):
        planner = SequenceModelProvider(
            [
                ModelOutput(
                    content=(
                        '{"goal":"Plan runtime implementation.","active_node_ref":"plan_node_1","nodes":'
                        '[{"ref":"plan_node_1","name":"Implement prepare phase","kind":"execution",'
                        '"description":"Implement the initial prepare planner.","node_status":"ready",'
                        '"owner":"main","dependencies":[],"order":1}]}'
                    )
                )
            ]
        )
        orchestrator = create_orchestrator(planner_model_provider=planner)
        context = orchestrator.build_initial_context(
            StartRunIdentity(
                session_id="sess-1",
                task_id="task-1",
                run_id="run-1",
                user_input="Implement prepare phase.",
            )
        )
        context.domain_state.task_graph_state.nodes.append(
            TaskGraphNode(
                node_id="node-existing",
                graph_id=context.domain_state.task_graph_state.graph_id,
                name="Existing",
                kind="execution",
                description="Existing node.",
                node_status=NodeStatus.READY,
            )
        )

        with self.assertRaises(ValueError):
            orchestrator.run_prepare_phase(context)

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

    def test_finalize_phase_requires_all_graph_nodes_completed(self):
        orchestrator = create_orchestrator()
        context = orchestrator.build_initial_context(
            StartRunIdentity(
                session_id="sess-1",
                task_id="task-1",
                run_id="run-1",
                user_input="Finalize validation.",
            )
        )
        context.run_lifecycle.current_phase = RunPhase.FINALIZE
        context.domain_state.task_graph_state.nodes = [
            TaskGraphNode(
                node_id="node-1",
                graph_id=context.domain_state.task_graph_state.graph_id,
                name="Incomplete node",
                kind="execution",
                description="Still running",
                node_status=NodeStatus.RUNNING,
            )
        ]

        with self.assertRaises(ValueError):
            orchestrator.run_finalize_phase(context)

    def test_finalize_phase_returns_failed_host_result_when_verifier_fails(self):
        finalize_model_provider = SequenceModelProvider(
            [ModelOutput(content='{"final_output":"Candidate output.","graph_summary":"Completed graph."}')]
        )
        runtime_verifier = StubRuntimeVerifier(
            VerificationResult(
                result_status=VerificationResultStatus.FAIL,
                summary="missing evidence",
                issues=["missing evidence"],
            )
        )
        orchestrator = create_orchestrator(
            finalize_model_provider=finalize_model_provider,
            runtime_verifier=runtime_verifier,
        )
        context = orchestrator.build_initial_context(
            StartRunIdentity(
                session_id="sess-1",
                task_id="task-1",
                run_id="run-1",
                user_input="Finalize failure flow.",
            )
        )
        context.run_identity.goal = "Finalize failure flow."
        context.run_lifecycle.current_phase = RunPhase.FINALIZE
        context.domain_state.task_graph_state.nodes = [
            TaskGraphNode(
                node_id="node-1",
                graph_id=context.domain_state.task_graph_state.graph_id,
                name="Done node",
                kind="execution",
                description="Finished work",
                node_status=NodeStatus.COMPLETED,
            )
        ]

        result = orchestrator.run_finalize_phase(context)

        self.assertEqual(result.runtime_state, "failed")
        self.assertEqual(result.output_text, "")
        self.assertEqual(context.run_lifecycle.result_status, "fail")
        self.assertEqual(context.run_lifecycle.stop_reason, "final_verification_failed")
        self.assertEqual(runtime_verifier.handoffs[0].final_output, "Candidate output.")

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

    def test_runtime_solver_promotes_pending_node_when_dependencies_completed(self):
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

        solver_result = orchestrator.runtime_solver.solve_current_node(
            context=context,
            node=pending_node,
            build_step_prompt=orchestrator.build_react_step_prompt,
            build_completion_check_input=orchestrator.build_completion_check_input,
            create_step_id=orchestrator._create_step_id,
        )

        self.assertIsNotNone(solver_result.final_step_result)
        self.assertEqual(solver_result.final_node_status, NodeStatus.READY)
        self.assertEqual(solver_result.step_count, 0)
        self.assertEqual(solver_result.final_step_result.patch.node_updates[0].node_id, "node-2")
        self.assertEqual(solver_result.final_step_result.patch.node_updates[0].node_status, NodeStatus.READY)

    def test_runtime_solver_keeps_pending_node_when_dependencies_not_completed(self):
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

        solver_result = orchestrator.runtime_solver.solve_current_node(
            context=context,
            node=pending_node,
            build_step_prompt=orchestrator.build_react_step_prompt,
            build_completion_check_input=orchestrator.build_completion_check_input,
            create_step_id=orchestrator._create_step_id,
        )
        self.assertIsNone(solver_result.final_step_result)
        self.assertIsNone(solver_result.final_node_status)
        self.assertEqual(solver_result.step_count, 0)

    def test_runtime_solver_raises_when_dependency_is_missing(self):
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
            orchestrator.runtime_solver.solve_current_node(
                context=context,
                node=pending_node,
                build_step_prompt=orchestrator.build_react_step_prompt,
                build_completion_check_input=orchestrator.build_completion_check_input,
                create_step_id=orchestrator._create_step_id,
            )

    def test_runtime_solver_promotes_ready_and_runs_until_completion(self):
        react_runner = FakeReActStepRunner(
            ReActStepOutput(
                thought="inspect current progress",
                action="continue execution",
                observation="work is complete",
                step_result=StepResult(
                    status_signal=StepStatusSignal.READY_FOR_COMPLETION,
                    reason="node reached completion",
                ),
            )
        )
        evaluator = StubCompletionEvaluator(
            CompletionCheckResult(
                result_status=JudgeResultStatus.PASS,
                summary="good enough",
                issues=[],
            )
        )
        orchestrator = create_orchestrator(react_step_runner=react_runner, completion_evaluator=evaluator)
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
        context.run_lifecycle.current_phase = RunPhase.EXECUTE

        solver_result = orchestrator.runtime_solver.solve_current_node(
            context=context,
            node=ready_node,
            build_step_prompt=orchestrator.build_react_step_prompt,
            build_completion_check_input=orchestrator.build_completion_check_input,
            create_step_id=orchestrator._create_step_id,
        )

        self.assertIsNotNone(solver_result.final_step_result)
        self.assertEqual(solver_result.final_node_status, NodeStatus.COMPLETED)
        self.assertEqual(solver_result.step_count, 1)
        self.assertEqual(solver_result.final_step_result.status_signal, StepStatusSignal.READY_FOR_COMPLETION)
        self.assertEqual(solver_result.final_step_result.reason, "node reached completion")
        self.assertIsNotNone(solver_result.final_step_result.patch)
        self.assertEqual(solver_result.final_step_result.patch.node_updates[0].node_status, NodeStatus.RUNNING)
        self.assertEqual(solver_result.final_step_result.patch.node_updates[-1].node_status, NodeStatus.COMPLETED)
        self.assertEqual(len(react_runner.inputs), 1)
        self.assertEqual(len(evaluator.inputs), 1)
        self.assertIn("## Base Prompt", react_runner.inputs[0].step_prompt)
        self.assertIn("## Phase Prompt", react_runner.inputs[0].step_prompt)
        self.assertIn("## Dynamic Injection", react_runner.inputs[0].step_prompt)
        self.assertIn("User input: Ready node.", react_runner.inputs[0].step_prompt)
        self.assertIn("## Run run-1", react_runner.inputs[0].step_prompt)
        self.assertIn("Active node id: node-1", react_runner.inputs[0].step_prompt)
        self.assertIn("Active node status: running", react_runner.inputs[0].step_prompt)

    def test_runtime_solver_returns_current_status_for_non_progressing_statuses(self):
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
            solver_result = orchestrator.runtime_solver.solve_current_node(
                context=context,
                node=node,
                build_step_prompt=orchestrator.build_react_step_prompt,
                build_completion_check_input=orchestrator.build_completion_check_input,
                create_step_id=orchestrator._create_step_id,
            )
            self.assertIsNone(solver_result.final_step_result)
            self.assertEqual(solver_result.final_node_status, status)

    def test_runtime_solver_runs_reflexion_when_completion_evaluator_fails(self):
        react_runner = FakeReActStepRunner(
            ReActStepOutput(
                thought="work complete",
                action="finish",
                observation="candidate complete",
                step_result=StepResult(
                    status_signal=StepStatusSignal.READY_FOR_COMPLETION,
                    reason="candidate ready",
                ),
            )
        )
        evaluator = StubCompletionEvaluator(
            CompletionCheckResult(
                result_status=JudgeResultStatus.FAIL,
                summary="missing validation",
                issues=["missing validation"],
            )
        )
        reflexion = StubRuntimeReflexion(
            ReflexionResult(
                summary="block until validation is available",
                next_attempt_hint="collect missing validation first",
                action=ReflexionAction.MARK_BLOCKED,
            )
        )
        orchestrator = create_orchestrator(
            react_step_runner=react_runner,
            completion_evaluator=evaluator,
            runtime_reflexion=reflexion,
        )
        context = orchestrator.build_initial_context(
            StartRunIdentity(
                session_id="sess-1",
                task_id="task-1",
                run_id="run-1",
                user_input="Evaluator fail.",
            )
        )
        ready_node = TaskGraphNode(
            node_id="node-1",
            graph_id=context.domain_state.task_graph_state.graph_id,
            name="Ready",
            kind="execution",
            node_status=NodeStatus.READY,
        )
        context.run_lifecycle.current_phase = RunPhase.EXECUTE

        solver_result = orchestrator.runtime_solver.solve_current_node(
            context=context,
            node=ready_node,
            build_step_prompt=orchestrator.build_react_step_prompt,
            build_completion_check_input=orchestrator.build_completion_check_input,
            create_step_id=orchestrator._create_step_id,
        )

        self.assertEqual(solver_result.final_node_status, NodeStatus.BLOCKED)
        self.assertEqual(len(reflexion.inputs), 1)
        entries = orchestrator.memory_store.list_entries(RuntimeMemoryQuery(task_id="task-1", run_id="run-1"))
        self.assertTrue(any(entry.entry_type is RuntimeMemoryEntryType.REFLEXION for entry in entries))

    def test_runtime_solver_returns_control_signal_when_reflexion_requests_replan(self):
        react_runner = FakeReActStepRunner(
            ReActStepOutput(
                thought="cannot proceed",
                action="fail",
                observation="stuck",
                step_result=StepResult(
                    status_signal=StepStatusSignal.FAILED,
                    reason="cannot proceed",
                ),
            )
        )
        reflexion = StubRuntimeReflexion(
            ReflexionResult(
                summary="request replan",
                next_attempt_hint="rebuild the plan around this failure",
                action=ReflexionAction.REQUEST_REPLAN,
            )
        )
        orchestrator = create_orchestrator(
            react_step_runner=react_runner,
            runtime_reflexion=reflexion,
        )
        context = orchestrator.build_initial_context(
            StartRunIdentity(
                session_id="sess-1",
                task_id="task-1",
                run_id="run-1",
                user_input="Request replan.",
            )
        )
        node = TaskGraphNode(
            node_id="node-1",
            graph_id=context.domain_state.task_graph_state.graph_id,
            name="Running",
            kind="execution",
            node_status=NodeStatus.RUNNING,
        )
        context.run_lifecycle.current_phase = RunPhase.EXECUTE

        solver_result = orchestrator.runtime_solver.solve_current_node(
            context=context,
            node=node,
            build_step_prompt=orchestrator.build_react_step_prompt,
            build_completion_check_input=orchestrator.build_completion_check_input,
            create_step_id=orchestrator._create_step_id,
        )

        self.assertEqual(solver_result.control_signal, SolverControlSignal.REQUEST_REPLAN)

    def test_run_execute_phase_aligns_runtime_active_node_when_node_is_selected(self):
        react_runner = FakeReActStepRunner(
            ReActStepOutput(
                thought="done",
                action="complete",
                observation="done",
                step_result=StepResult(
                    status_signal=StepStatusSignal.READY_FOR_COMPLETION,
                    reason="done",
                ),
            )
        )
        orchestrator = create_orchestrator(react_step_runner=react_runner)
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

        self.assertEqual(executed.runtime_state.active_node_id, "")
        self.assertEqual(executed.run_lifecycle.current_phase, RunPhase.FINALIZE)
        self.assertEqual(
            executed.domain_state.task_graph_state.nodes[0].node_status,
            NodeStatus.COMPLETED,
        )
        self.assertEqual(executed.domain_state.task_graph_state.graph_status, TaskGraphStatus.COMPLETED)

    def test_run_execute_phase_applies_node_advancement_patch_back_to_graph(self):
        react_runner = FakeReActStepRunner(
            ReActStepOutput(
                thought="done",
                action="complete",
                observation="done",
                step_result=StepResult(
                    status_signal=StepStatusSignal.READY_FOR_COMPLETION,
                    reason="done",
                ),
            )
        )
        orchestrator = create_orchestrator(react_step_runner=react_runner)
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
            NodeStatus.COMPLETED,
        )
        self.assertEqual(executed.runtime_state.active_node_id, "")
        self.assertEqual(executed.domain_state.task_graph_state.graph_status, TaskGraphStatus.COMPLETED)

    def test_run_execute_phase_consumes_step_result_from_react_runner(self):
        react_runner = FakeReActStepRunner(
            ReActStepOutput(
                thought="finish the node",
                action="return completion patch",
                observation="node can be completed",
                step_result=StepResult(
                    status_signal=StepStatusSignal.READY_FOR_COMPLETION,
                    reason="react step finished current node",
                    patch=TaskGraphPatch(
                        node_updates=[NodePatch(
                            node_id="node-1",
                            node_status=NodeStatus.COMPLETED,
                        )]
                    ),
                ),
            )
        )
        orchestrator = create_orchestrator(react_step_runner=react_runner)
        context = orchestrator.build_initial_context(
            StartRunIdentity(
                session_id="sess-1",
                task_id="task-1",
                run_id="run-1",
                user_input="Run one react step.",
            )
        )
        context.run_lifecycle.current_phase = RunPhase.EXECUTE
        context.domain_state.task_graph_state.nodes = [
            TaskGraphNode(
                node_id="node-1",
                graph_id=context.domain_state.task_graph_state.graph_id,
                name="Running",
                kind="execution",
                description="Process the current user request.",
                node_status=NodeStatus.RUNNING,
            )
        ]

        executed = orchestrator.run_execute_phase(context)

        self.assertEqual(len(react_runner.inputs), 1)
        self.assertEqual(executed.run_lifecycle.current_phase, RunPhase.FINALIZE)
        self.assertEqual(
            executed.domain_state.task_graph_state.nodes[0].node_status,
            NodeStatus.COMPLETED,
        )
        self.assertEqual(executed.runtime_state.active_node_id, "")
        self.assertEqual(executed.domain_state.task_graph_state.graph_status, TaskGraphStatus.COMPLETED)

    def test_run_execute_phase_auto_wires_tool_aware_react_runner_from_tool_registry(self):
        registry = ToolRegistry()
        registry.register(echo_text)
        provider = SequenceModelProvider([
            ModelOutput(
                content='{"thought":"need tool","action":"call tool","observation":"","tool_call":{"tool_name":"echo_text","arguments":{"text":"hello"}}}',
                raw={},
            ),
            ModelOutput(
                content='{"thought":"tool done","action":"complete node","observation":"echo:hello","status_signal":"ready_for_completion","reason":"tool provided enough information"}',
                raw={},
            ),
        ])
        orchestrator = RuntimeOrchestrator(
            graph_store=InMemoryTaskGraphStore(),
            tool_registry=registry,
            completion_evaluator=StubCompletionEvaluator(),
            runtime_reflexion=StubRuntimeReflexion(),
            memory_store=self.create_memory_store(),
        )
        orchestrator.react_step_runner.model_provider = provider
        context = orchestrator.build_initial_context(
            StartRunIdentity(
                session_id="sess-1",
                task_id="task-1",
                run_id="run-1",
                user_input="Run tool-aware react step.",
            )
        )
        context.run_lifecycle.current_phase = RunPhase.EXECUTE
        context.domain_state.task_graph_state.nodes = [
            TaskGraphNode(
                node_id="node-1",
                graph_id=context.domain_state.task_graph_state.graph_id,
                name="Running",
                kind="execution",
                description="Process the current user request.",
                node_status=NodeStatus.RUNNING,
            )
        ]

        executed = orchestrator.run_execute_phase(context)

        self.assertEqual(len(provider.calls), 3)
        self.assertEqual(provider.calls[0]["tools"][0]["name"], "echo_text")
        self.assertEqual(provider.calls[1]["tools"], [])
        self.assertEqual(provider.calls[2]["tools"], [])
        self.assertEqual(
            executed.domain_state.task_graph_state.nodes[0].node_status,
            NodeStatus.COMPLETED,
        )
        self.assertEqual(executed.runtime_state.active_node_id, "")

    def test_run_execute_phase_replans_back_to_prepare_and_returns_to_execute(self):
        planner_provider = SequenceModelProvider([
            ModelOutput(
                content=(
                    '{"goal":"Replanned goal.","active_node_ref":"plan_node_2","nodes":'
                    '[{"ref":"plan_node_2","name":"Retry through replanning","kind":"execution",'
                    '"description":"Retry after replan.","node_status":"ready",'
                    '"owner":"main","dependencies":[],"order":1}]}'
                ),
                raw={},
            ),
        ])
        reflexion = StubRuntimeReflexion(
            ReflexionResult(
                summary="Need a replan.",
                next_attempt_hint="Go back to prepare.",
                action=ReflexionAction.REQUEST_REPLAN,
            )
        )
        orchestrator = create_orchestrator(
            planner_model_provider=planner_provider,
            runtime_reflexion=reflexion,
            react_step_runner=SequenceReActStepRunner(
                [
                    ReActStepOutput(
                        thought="fail node",
                        action="stop",
                        observation="failed",
                        step_result=StepResult(
                            status_signal=StepStatusSignal.FAILED,
                            reason="current node cannot continue",
                        ),
                    ),
                    ReActStepOutput(
                        thought="complete node",
                        action="finish",
                        observation="done",
                        step_result=StepResult(
                            status_signal=StepStatusSignal.READY_FOR_COMPLETION,
                            reason="replanned node completed",
                        ),
                    ),
                ]
            ),
        )
        context = orchestrator.build_initial_context(
            StartRunIdentity(
                session_id="sess-1",
                task_id="task-1",
                run_id="run-1",
                user_input="Replan this task.",
            )
        )
        context.run_identity.goal = "Old goal"
        context.run_lifecycle.current_phase = RunPhase.EXECUTE
        context.domain_state.task_graph_state.nodes = [
            TaskGraphNode(
                node_id="node-1",
                graph_id=context.domain_state.task_graph_state.graph_id,
                name="Failing",
                kind="execution",
                description="Current path is exhausted.",
                node_status=NodeStatus.RUNNING,
            )
        ]
        orchestrator.graph_store.save_graph(context.domain_state.task_graph_state)

        executed = orchestrator.run_execute_phase(context)

        self.assertEqual(executed.run_lifecycle.current_phase, RunPhase.FINALIZE)
        self.assertEqual(executed.run_identity.goal, "Replanned goal.")
        self.assertIsNone(executed.runtime_state.request_replan)
        self.assertTrue(any(node.name == "Retry through replanning" for node in executed.domain_state.task_graph_state.nodes))

    def test_run_finalize_phase_verification_fail_can_request_replan(self):
        planner_provider = SequenceModelProvider([
            ModelOutput(
                content=(
                    '{"goal":"Replanned final goal.","active_node_ref":"plan_node_3","nodes":'
                    '[{"ref":"plan_node_3","name":"Retry after verification fail","kind":"execution",'
                    '"description":"Retry after final verification fail.","node_status":"ready",'
                    '"owner":"main","dependencies":[],"order":1}]}'
                ),
                raw={},
            ),
        ])
        finalize_provider = SequenceModelProvider([
            ModelOutput(
                content='{"final_output":"First final answer.","graph_summary":"Initial completed graph."}',
                raw={},
            ),
            ModelOutput(
                content='{"final_output":"Second final answer.","graph_summary":"Replanned completed graph."}',
                raw={},
            ),
        ])
        verifier = SequenceRuntimeVerifier([
            VerificationResult(
                result_status=VerificationResultStatus.FAIL,
                summary="Missing required detail.",
                issues=["required detail missing"],
            ),
            VerificationResult(
                result_status=VerificationResultStatus.PASS,
                summary="Looks good now.",
                issues=[],
            ),
        ])
        finalize_reflexion = StubFinalizeReflexion(
            RunReflexionResult(
                summary="Need to replan after verification fail.",
                action=RunReflexionAction.REQUEST_REPLAN,
            )
        )
        orchestrator = create_orchestrator(
            planner_model_provider=planner_provider,
            finalize_model_provider=finalize_provider,
            runtime_verifier=verifier,
            finalize_reflexion=finalize_reflexion,
        )
        context = orchestrator.build_initial_context(
            StartRunIdentity(
                session_id="sess-1",
                task_id="task-1",
                run_id="run-1",
                user_input="Finalize with replan.",
            )
        )
        context.run_identity.goal = "Initial goal"
        context.run_lifecycle.current_phase = RunPhase.FINALIZE
        context.domain_state.task_graph_state.nodes = [
            TaskGraphNode(
                node_id="node-1",
                graph_id=context.domain_state.task_graph_state.graph_id,
                name="Completed node",
                kind="execution",
                description="Done.",
                node_status=NodeStatus.COMPLETED,
            )
        ]
        orchestrator.graph_store.save_graph(context.domain_state.task_graph_state)
        orchestrator.react_step_runner = FakeReActStepRunner()

        result = orchestrator.run_finalize_phase(context)

        self.assertEqual(result.runtime_state, "completed")
        self.assertEqual(result.output_text, "Second final answer.")

    def test_build_react_step_prompt_reads_task_level_runtime_memory_across_runs(self):
        memory_store = self.create_memory_store()
        memory_store.append_entry(
            RuntimeMemoryEntry(
                entry_id="entry-1",
                task_id="task-1",
                run_id="run-1",
                step_id="run-start",
                node_id="",
                entry_type=RuntimeMemoryEntryType.CONTEXT,
                role=RuntimeMemoryRole.USER,
                content="Previous run input.",
                created_at="2026-04-28T22:00:00+08:00",
            )
        )
        orchestrator = RuntimeOrchestrator(
            graph_store=InMemoryTaskGraphStore(),
            memory_store=memory_store,
        )
        context = orchestrator.build_initial_context(
            StartRunIdentity(
                session_id="sess-1",
                task_id="task-1",
                run_id="run-2",
                user_input="Current run input.",
            )
        )
        node = TaskGraphNode(
            node_id="node-1",
            graph_id=context.domain_state.task_graph_state.graph_id,
            name="Running",
            kind="execution",
            description="Process the current request.",
            node_status=NodeStatus.RUNNING,
        )
        context.run_lifecycle.current_phase = RunPhase.EXECUTE

        prompt = orchestrator.build_react_step_prompt(context, node)

        self.assertIn("## Base Prompt", prompt)
        self.assertIn("## Phase Prompt", prompt)
        self.assertIn("## Dynamic Injection", prompt)
        self.assertIn("## Run run-1", prompt)
        self.assertIn("Previous run input.", prompt)
        self.assertIn("## Run run-2", prompt)
        self.assertIn("Current run input.", prompt)
        entries = memory_store.list_entries(RuntimeMemoryQuery(task_id="task-1", run_id="run-2"))
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].content, "Current run input.")

    def test_build_execution_prompt_includes_tool_summary_and_dependency_summaries(self):
        registry = ToolRegistry()
        registry.register(echo_text)
        orchestrator = RuntimeOrchestrator(
            graph_store=InMemoryTaskGraphStore(),
            tool_registry=registry,
            memory_store=self.create_memory_store(),
        )
        context = orchestrator.build_initial_context(
            StartRunIdentity(
                session_id="sess-1",
                task_id="task-1",
                run_id="run-1",
                user_input="Inspect node context.",
            )
        )
        dependency = TaskGraphNode(
            node_id="node-1",
            graph_id=context.domain_state.task_graph_state.graph_id,
            name="Dependency",
            kind="execution",
            node_status=NodeStatus.COMPLETED,
        )
        node = TaskGraphNode(
            node_id="node-2",
            graph_id=context.domain_state.task_graph_state.graph_id,
            name="Running",
            kind="execution",
            description="Process the current request.",
            node_status=NodeStatus.RUNNING,
            dependencies=["node-1"],
        )
        context.domain_state.task_graph_state.nodes = [dependency, node]
        context.run_lifecycle.current_phase = RunPhase.EXECUTE

        prompt = orchestrator.build_execution_prompt(context, node)

        self.assertIn("- echo_text: Echo text.", prompt.dynamic_injection)
        self.assertIn("node-1 | Dependency | completed", prompt.dynamic_injection)
        self.assertIn("Active node id: node-2", prompt.dynamic_injection)

    def test_build_execution_prompt_includes_enabled_skill_summaries_in_capability_text(self):
        skill_registry = SkillRegistry()
        skill_registry.register(
            RuntimeSkill(
                manifest=SkillManifest(
                    name="ppt-skill",
                    description="Use this skill when creating or editing presentation materials.",
                ),
                source_path="/tmp/ppt-skill",
                instructions="presentation details",
                status=SkillStatus.ENABLED,
            )
        )
        orchestrator = RuntimeOrchestrator(
            graph_store=InMemoryTaskGraphStore(),
            skill_registry=skill_registry,
            memory_store=self.create_memory_store(),
        )
        context = orchestrator.build_initial_context(
            StartRunIdentity(
                session_id="sess-1",
                task_id="task-1",
                run_id="run-1",
                user_input="Use a skill.",
            )
        )
        context.run_lifecycle.current_phase = RunPhase.EXECUTE
        node = TaskGraphNode(
            node_id="node-1",
            graph_id=context.domain_state.task_graph_state.graph_id,
            name="Running",
            kind="execution",
            description="Do the current task.",
            node_status=NodeStatus.RUNNING,
        )

        prompt = orchestrator.build_execution_prompt(context, node)

        self.assertIn(
            "- ppt-skill: Use this skill when creating or editing presentation materials.",
            prompt.dynamic_injection,
        )

    def test_build_execution_prompt_ignores_disabled_skills(self):
        skill_registry = SkillRegistry()
        skill_registry.register(
            RuntimeSkill(
                manifest=SkillManifest(
                    name="ppt-skill",
                    description="Use this skill when creating or editing presentation materials.",
                ),
                source_path="/tmp/ppt-skill",
                instructions="presentation details",
                status=SkillStatus.DISABLED,
            )
        )
        orchestrator = RuntimeOrchestrator(
            graph_store=InMemoryTaskGraphStore(),
            skill_registry=skill_registry,
            memory_store=self.create_memory_store(),
        )
        context = orchestrator.build_initial_context(
            StartRunIdentity(
                session_id="sess-1",
                task_id="task-1",
                run_id="run-1",
                user_input="Use a skill.",
            )
        )
        context.run_lifecycle.current_phase = RunPhase.EXECUTE
        node = TaskGraphNode(
            node_id="node-1",
            graph_id=context.domain_state.task_graph_state.graph_id,
            name="Running",
            kind="execution",
            description="Do the current task.",
            node_status=NodeStatus.RUNNING,
        )

        prompt = orchestrator.build_execution_prompt(context, node)

        self.assertNotIn("ppt-skill", prompt.dynamic_injection)

    def test_orchestrator_auto_loads_enabled_skills_from_skill_paths(self):
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        skill_dir = self.create_skill_dir(Path(tmpdir.name), folder_name="demo-skill")
        orchestrator = RuntimeOrchestrator(
            graph_store=InMemoryTaskGraphStore(),
            skill_paths=[str(skill_dir)],
            memory_store=self.create_memory_store(),
        )
        context = orchestrator.build_initial_context(
            StartRunIdentity(
                session_id="sess-1",
                task_id="task-1",
                run_id="run-1",
                user_input="Use auto-loaded skill.",
            )
        )
        context.run_lifecycle.current_phase = RunPhase.EXECUTE
        node = TaskGraphNode(
            node_id="node-1",
            graph_id=context.domain_state.task_graph_state.graph_id,
            name="Running",
            kind="execution",
            description="Do the current task.",
            node_status=NodeStatus.RUNNING,
        )

        prompt = orchestrator.build_execution_prompt(context, node)

        self.assertIsNotNone(orchestrator.skill_registry)
        self.assertEqual(
            [skill.manifest.name for skill in orchestrator.skill_registry.list_enabled()],
            ["demo-skill"],
        )
        self.assertIn("- demo-skill: Use this skill when needed.", prompt.dynamic_injection)

    def test_orchestrator_auto_registers_skill_tools_from_skill_paths(self):
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        skill_dir = self.create_skill_dir(Path(tmpdir.name), folder_name="demo-skill")
        orchestrator = RuntimeOrchestrator(
            graph_store=InMemoryTaskGraphStore(),
            skill_paths=[str(skill_dir)],
            memory_store=self.create_memory_store(),
        )

        self.assertIsNotNone(orchestrator.tool_registry)
        tool_names = [schema["name"] for schema in orchestrator.tool_registry.list_tool_schemas()]
        self.assertIn("get_skill_instructions", tool_names)
        self.assertIn("get_skill_reference", tool_names)
        self.assertIn("get_skill_script", tool_names)
        self.assertIn("get_skill_asset", tool_names)

    def test_runtime_solver_materializes_failed_signal_without_patch(self):
        react_runner = FakeReActStepRunner(
            ReActStepOutput(
                thought="tool failed",
                action="stop current node",
                observation="failure observed",
                step_result=StepResult(
                    status_signal=StepStatusSignal.FAILED,
                    reason="tool execution failed",
                ),
            )
        )
        orchestrator = create_orchestrator(react_step_runner=react_runner)
        context = orchestrator.build_initial_context(
            StartRunIdentity(
                session_id="sess-1",
                task_id="task-1",
                run_id="run-1",
                user_input="Running node failure.",
            )
        )
        running_node = TaskGraphNode(
            node_id="node-1",
            graph_id=context.domain_state.task_graph_state.graph_id,
            name="Running",
            kind="execution",
            node_status=NodeStatus.RUNNING,
        )
        context.run_lifecycle.current_phase = RunPhase.EXECUTE

        solver_result = orchestrator.runtime_solver.solve_current_node(
            context=context,
            node=running_node,
            build_step_prompt=orchestrator.build_react_step_prompt,
            build_completion_check_input=orchestrator.build_completion_check_input,
            create_step_id=orchestrator._create_step_id,
        )

        self.assertIsNotNone(solver_result.final_step_result)
        self.assertEqual(solver_result.final_node_status, NodeStatus.FAILED)
        self.assertEqual(solver_result.final_step_result.status_signal, StepStatusSignal.FAILED)
        self.assertIsNotNone(solver_result.final_step_result.patch)
        self.assertEqual(solver_result.final_step_result.patch.node_updates[0].node_status, NodeStatus.FAILED)
        self.assertEqual(solver_result.final_step_result.patch.node_updates[0].failure_reason, "tool execution failed")

    def test_runtime_solver_blocks_when_step_limit_is_reached(self):
        react_runner = FakeReActStepRunner(
            ReActStepOutput(
                thought="continue",
                action="keep going",
                observation="progress continues",
                step_result=StepResult(status_signal=StepStatusSignal.PROGRESSED),
            )
        )
        solver = RuntimeSolver(
            react_step_runner=react_runner,
            completion_evaluator=StubCompletionEvaluator(),
            runtime_reflexion=StubRuntimeReflexion(),
            memory_store=None,
            max_steps_per_node=2,
        )
        orchestrator = create_orchestrator(react_step_runner=react_runner)
        context = orchestrator.build_initial_context(
            StartRunIdentity(
                session_id="sess-1",
                task_id="task-1",
                run_id="run-1",
                user_input="Long running node.",
            )
        )
        context.run_lifecycle.current_phase = RunPhase.EXECUTE
        running_node = TaskGraphNode(
            node_id="node-1",
            graph_id=context.domain_state.task_graph_state.graph_id,
            name="Running",
            kind="execution",
            node_status=NodeStatus.RUNNING,
        )

        solver_result = solver.solve_current_node(
            context=context,
            node=running_node,
            build_step_prompt=orchestrator.build_react_step_prompt,
            build_completion_check_input=orchestrator.build_completion_check_input,
            create_step_id=orchestrator._create_step_id,
        )

        self.assertEqual(solver_result.final_node_status, NodeStatus.BLOCKED)
        self.assertEqual(solver_result.step_count, 2)
        self.assertEqual(solver_result.final_step_result.reason, "solver step limit reached")
        self.assertEqual(
            solver_result.final_step_result.patch.node_updates[0].block_reason,
            "solver step limit reached",
        )


if __name__ == "__main__":
    unittest.main()
