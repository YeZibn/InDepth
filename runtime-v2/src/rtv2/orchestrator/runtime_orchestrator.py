"""RuntimeOrchestrator skeleton module."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from rtv2.host.interfaces import HostRunResult, StartRunIdentity
from rtv2.memory import (
    RuntimeMemoryEntry,
    RuntimeMemoryEntryType,
    RuntimeMemoryProcessor,
    RuntimeMemoryProcessorInput,
    RuntimeMemoryQuery,
    RuntimeMemoryRole,
    RuntimeMemoryStore,
    SQLiteRuntimeMemoryStore,
)
from rtv2.prompting import (
    ExecutionNodePromptContext,
    ExecutionPrompt,
    ExecutionPromptAssembler,
    ExecutionPromptInput,
)
from rtv2.skills import LocalSkillLoader, SkillRegistry, SkillStatus, build_skill_tools
from rtv2.solver import ReActStepInput, ReActStepRunner
from rtv2.solver.models import StepResult, StepStatusSignal
from rtv2.state.models import DomainState, RunContext, RunIdentity, RunLifecycle, RunPhase, RuntimeState
from rtv2.task_graph.store import TaskGraphStore
from rtv2.tools import ToolRegistry
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

    def __init__(
        self,
        *,
        graph_store: TaskGraphStore,
        react_step_runner: ReActStepRunner | None = None,
        tool_registry: ToolRegistry | None = None,
        skill_registry: SkillRegistry | None = None,
        skill_loader: LocalSkillLoader | None = None,
        skill_paths: list[str] | None = None,
        memory_store: RuntimeMemoryStore | None = None,
        memory_processor: RuntimeMemoryProcessor | None = None,
        prompt_assembler: ExecutionPromptAssembler | None = None,
    ) -> None:
        self.graph_store = graph_store
        self.skill_loader = skill_loader or LocalSkillLoader()
        self.skill_registry = skill_registry
        self.tool_registry = tool_registry
        self._load_and_enable_skills(skill_paths or [])
        self.memory_store = memory_store or SQLiteRuntimeMemoryStore()
        self.memory_processor = memory_processor or RuntimeMemoryProcessor(memory_store=self.memory_store)
        self.prompt_assembler = prompt_assembler or ExecutionPromptAssembler()
        self.react_step_runner = react_step_runner or ReActStepRunner(
            tool_registry=tool_registry,
            memory_store=self.memory_store,
        )
        self._graph_counter = 0
        self._node_counter = 0
        self._step_counter = 0

    def _load_and_enable_skills(self, skill_paths: list[str]) -> None:
        if not skill_paths:
            return

        if self.skill_registry is None:
            self.skill_registry = SkillRegistry()

        for skill_path in skill_paths:
            for skill in self.skill_loader.load(skill_path):
                self.skill_registry.register(skill)
                self.skill_registry.enable(skill.manifest.name)

        if self.tool_registry is None:
            self.tool_registry = ToolRegistry()
        for spec in build_skill_tools(self.skill_registry):
            self.tool_registry.register(spec)

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
            step_result = self.initialize_minimal_graph(context)
        else:
            context.runtime_state.active_node_id = selected_node.node_id
            step_result = self.advance_node_minimally(context, selected_node)

        self._apply_step_result(context, step_result)

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

    def _create_step_id(self) -> str:
        """Create a step id inside the orchestrator boundary."""

        self._step_counter += 1
        return f"step-{self._step_counter}"

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

    def initialize_minimal_graph(self, context: RunContext) -> StepResult | None:
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
        return StepResult(
            patch=TaskGraphPatch(
                new_nodes=[initial_node],
                active_node_id=initial_node.node_id,
            )
        )

    def advance_node_minimally(
        self,
        context: RunContext,
        node: TaskGraphNode,
    ) -> StepResult | None:
        """Return the minimal node status transition step result for the selected node."""

        if node.node_status is NodeStatus.PENDING:
            return self._advance_pending_node(context, node)
        if node.node_status is NodeStatus.READY:
            return StepResult(
                patch=TaskGraphPatch(
                    node_updates=[NodePatch(
                        node_id=node.node_id,
                        node_status=NodeStatus.RUNNING,
                    )]
                )
            )
        if node.node_status is NodeStatus.RUNNING:
            step_id = self._create_step_id()
            react_output = self.react_step_runner.run_step(
                ReActStepInput(
                    step_prompt=self.build_react_step_prompt(context, node),
                    task_id=context.run_identity.task_id,
                    run_id=context.run_identity.run_id,
                    step_id=step_id,
                    node_id=node.node_id,
                )
            )
            return self._materialize_running_node_step_result(node, react_output.step_result)
        return None

    def _advance_pending_node(
        self,
        context: RunContext,
        node: TaskGraphNode,
    ) -> StepResult | None:
        graph_state = context.domain_state.task_graph_state

        for dependency_id in node.dependencies:
            dependency_node = self._find_node(graph_state, dependency_id)
            if dependency_node is None:
                raise ValueError(f"Node dependency not found: {dependency_id}")
            if dependency_node.node_status is not NodeStatus.COMPLETED:
                return None

        return StepResult(
            patch=TaskGraphPatch(
                node_updates=[NodePatch(
                    node_id=node.node_id,
                    node_status=NodeStatus.READY,
                )]
            )
        )

    def _apply_step_result(self, context: RunContext, step_result: StepResult | None) -> None:
        """Consume the current minimal step result and write back its graph patch."""

        patch = step_result.patch if step_result is not None else None
        if patch is None:
            return

        self.graph_store.save_graph(context.domain_state.task_graph_state)
        updated_graph = self.graph_store.apply_patch(
            context.domain_state.task_graph_state.graph_id,
            patch,
        )
        context.domain_state.task_graph_state = updated_graph
        if patch.active_node_id is not None:
            context.runtime_state.active_node_id = patch.active_node_id

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

    def build_react_step_prompt(self, context: RunContext, node: TaskGraphNode) -> str:
        """Render the formal execution prompt blocks into the current step prompt string."""

        execution_prompt = self.build_execution_prompt(context, node)
        return self.render_execution_prompt(execution_prompt)

    def build_execution_prompt(self, context: RunContext, node: TaskGraphNode) -> ExecutionPrompt:
        """Build the three-block execution prompt for the current node."""

        self._append_run_user_input_entry(context)
        prompt_context = self.memory_processor.build_prompt_context_text(
            RuntimeMemoryProcessorInput(
                task_id=context.run_identity.task_id,
                run_id=context.run_identity.run_id,
                current_phase=context.run_lifecycle.current_phase.value,
                active_node_id=node.node_id,
                user_input=context.run_identity.user_input,
                compression_state=context.runtime_state.compression_state,
            )
        )
        return self.prompt_assembler.build_execution_prompt(
            ExecutionPromptInput(
                phase=context.run_lifecycle.current_phase,
                node_context=self._build_execution_node_prompt_context(context, node),
                runtime_memory_text=prompt_context.prompt_context_text,
                tool_capability_text=self._build_tool_capability_text(),
                finalize_return_input=self._build_finalize_return_input_text(context),
            )
        )

    @staticmethod
    def render_execution_prompt(execution_prompt: ExecutionPrompt) -> str:
        """Render the three formal prompt blocks into the current single-string step prompt."""

        return "\n\n".join(
            [
                "## Base Prompt",
                execution_prompt.base_prompt,
                "## Phase Prompt",
                execution_prompt.phase_prompt,
                "## Dynamic Injection",
                execution_prompt.dynamic_injection,
            ]
        )

    def _build_execution_node_prompt_context(
        self,
        context: RunContext,
        node: TaskGraphNode,
    ) -> ExecutionNodePromptContext:
        return ExecutionNodePromptContext(
            user_input=context.run_identity.user_input,
            goal=context.run_identity.goal,
            active_node_id=node.node_id,
            active_node_name=node.name,
            active_node_description=node.description,
            active_node_status=node.node_status.value,
            dependency_summaries=self._build_dependency_summaries(
                context.domain_state.task_graph_state,
                node,
            ),
            artifacts=self._render_result_refs(node.artifacts),
            evidence=self._render_result_refs(node.evidence),
            notes=list(node.notes),
        )

    def _build_dependency_summaries(
        self,
        graph_state: TaskGraphState,
        node: TaskGraphNode,
    ) -> list[str]:
        summaries: list[str] = []
        for dependency_id in node.dependencies:
            dependency_node = self._find_node(graph_state, dependency_id)
            if dependency_node is None:
                summaries.append(f"{dependency_id} | (missing) | unknown")
                continue
            summaries.append(
                f"{dependency_node.node_id} | {dependency_node.name or '(empty)'} | {dependency_node.node_status.value}"
            )
        return summaries

    def _build_tool_capability_text(self) -> str:
        lines: list[str] = []

        if self.tool_registry is not None:
            for schema in self.tool_registry.list_tool_schemas():
                name = str(schema.get("name", "") or "").strip() or "(unnamed)"
                description = str(schema.get("description", "") or "").strip() or "(no description)"
                lines.append(f"- {name}: {description}")

        if self.skill_registry is not None:
            for skill in self.skill_registry.list_enabled():
                if skill.status is not SkillStatus.ENABLED:
                    continue
                lines.append(f"- {skill.manifest.name}: {skill.manifest.description}")

        if not lines:
            return "(no tools available)"
        return "\n".join(lines)

    @staticmethod
    def _build_finalize_return_input_text(context: RunContext) -> str:
        finalize_return_input = context.runtime_state.finalize_return_input
        if finalize_return_input is None:
            return ""

        lines = [
            f"Verification summary: {finalize_return_input.verification_summary or '(empty)'}",
            "Verification issues:",
        ]
        if finalize_return_input.verification_issues:
            lines.extend(f"- {issue}" for issue in finalize_return_input.verification_issues)
        else:
            lines.append("(empty)")
        return "\n".join(lines)

    @staticmethod
    def _render_result_refs(result_refs: list) -> list[str]:
        rendered: list[str] = []
        for result_ref in result_refs:
            title = result_ref.title or "(untitled)"
            rendered.append(f"{result_ref.ref_id} | {result_ref.ref_type} | {title}")
        return rendered

    def _append_run_user_input_entry(self, context: RunContext) -> None:
        existing_entries = self.memory_store.list_entries(
            RuntimeMemoryQuery(
                task_id=context.run_identity.task_id,
                run_id=context.run_identity.run_id,
                step_id="run-start",
                node_id="",
            )
        )
        if existing_entries:
            return
        self.memory_store.append_entry(
            RuntimeMemoryEntry(
                entry_id=f"entry-{uuid4()}",
                task_id=context.run_identity.task_id,
                run_id=context.run_identity.run_id,
                step_id="run-start",
                node_id="",
                entry_type=RuntimeMemoryEntryType.CONTEXT,
                role=RuntimeMemoryRole.USER,
                content=context.run_identity.user_input,
                created_at=datetime.now(timezone.utc).isoformat(),
            )
        )

    @staticmethod
    def _find_node(graph_state: TaskGraphState, node_id: str) -> TaskGraphNode | None:
        for node in graph_state.nodes:
            if node.node_id == node_id:
                return node
        return None
