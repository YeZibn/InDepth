import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from rtv2.host.interfaces import StartRunIdentity
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
from rtv2.solver.react_step import ReActStepOutput
from rtv2.solver.models import StepResult, StepStatusSignal
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


def create_orchestrator(react_step_runner=None) -> RuntimeOrchestrator:
    db_dir = tempfile.mkdtemp()
    return RuntimeOrchestrator(
        graph_store=InMemoryTaskGraphStore(),
        react_step_runner=react_step_runner,
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

    def test_initialize_minimal_graph_returns_step_result_for_empty_graph(self):
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

        step_result = orchestrator.initialize_minimal_graph(context)

        self.assertIsNotNone(step_result)
        self.assertIsNotNone(step_result.patch)
        self.assertEqual(len(step_result.patch.new_nodes), 1)
        initial_node = step_result.patch.new_nodes[0]
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
        self.assertEqual(step_result.patch.active_node_id, "node-1")
        self.assertIsNone(step_result.patch.graph_status)

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

        step_result = orchestrator.advance_node_minimally(context, pending_node)

        self.assertIsNotNone(step_result)
        self.assertEqual(step_result.status_signal, StepStatusSignal.PROGRESSED)
        self.assertIsNotNone(step_result.patch)
        self.assertEqual(step_result.patch.node_updates[0].node_id, "node-2")
        self.assertEqual(step_result.patch.node_updates[0].node_status, NodeStatus.READY)

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

        step_result = orchestrator.advance_node_minimally(context, ready_node)

        self.assertIsNotNone(step_result)
        self.assertEqual(step_result.status_signal, StepStatusSignal.PROGRESSED)
        self.assertIsNotNone(step_result.patch)
        self.assertEqual(step_result.patch.node_updates[0].node_status, NodeStatus.RUNNING)

    def test_advance_node_minimally_runs_react_step_for_running_node(self):
        react_runner = FakeReActStepRunner(
            ReActStepOutput(
                thought="inspect current progress",
                action="continue execution",
                observation="work is complete",
                step_result=StepResult(
                    status_signal=StepStatusSignal.READY_FOR_COMPLETION,
                    reason="node reached completion",
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

        step_result = orchestrator.advance_node_minimally(context, running_node)

        self.assertIsNotNone(step_result)
        self.assertEqual(step_result.status_signal, StepStatusSignal.READY_FOR_COMPLETION)
        self.assertEqual(step_result.reason, "node reached completion")
        self.assertIsNotNone(step_result.patch)
        self.assertEqual(step_result.patch.node_updates[0].node_status, NodeStatus.COMPLETED)
        self.assertEqual(len(react_runner.inputs), 1)
        self.assertIn("## Base Prompt", react_runner.inputs[0].step_prompt)
        self.assertIn("## Phase Prompt", react_runner.inputs[0].step_prompt)
        self.assertIn("## Dynamic Injection", react_runner.inputs[0].step_prompt)
        self.assertIn("User input: Running node.", react_runner.inputs[0].step_prompt)
        self.assertIn("## Run run-1", react_runner.inputs[0].step_prompt)
        self.assertIn("Active node id: node-1", react_runner.inputs[0].step_prompt)
        self.assertIn("Active node status: running", react_runner.inputs[0].step_prompt)

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
        self.assertEqual(executed.runtime_state.active_node_id, "node-1")
        self.assertEqual(executed.domain_state.task_graph_state.version, 2)

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

        self.assertEqual(len(provider.calls), 2)
        self.assertEqual(provider.calls[0]["tools"][0]["name"], "echo_text")
        self.assertEqual(provider.calls[1]["tools"], [])
        self.assertEqual(
            executed.domain_state.task_graph_state.nodes[0].node_status,
            NodeStatus.COMPLETED,
        )
        self.assertEqual(executed.runtime_state.active_node_id, "node-1")

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

    def test_advance_node_minimally_materializes_failed_signal_without_patch(self):
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

        step_result = orchestrator.advance_node_minimally(context, running_node)

        self.assertIsNotNone(step_result)
        self.assertEqual(step_result.status_signal, StepStatusSignal.FAILED)
        self.assertIsNotNone(step_result.patch)
        self.assertEqual(step_result.patch.node_updates[0].node_status, NodeStatus.FAILED)
        self.assertEqual(step_result.patch.node_updates[0].failure_reason, "tool execution failed")


if __name__ == "__main__":
    unittest.main()
