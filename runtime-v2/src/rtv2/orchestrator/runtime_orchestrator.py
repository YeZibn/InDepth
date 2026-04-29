"""RuntimeOrchestrator skeleton module."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

from rtv2.finalize import FinalizeGenerationResult, Handoff, RuntimeVerifier, VerificationResultStatus
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
from rtv2.model import GenerationConfig, HttpChatModelProvider, ModelOutput, ModelProvider
from rtv2.prompting import (
    ExecutionNodePromptContext,
    ExecutionPrompt,
    ExecutionPromptAssembler,
    ExecutionPromptInput,
    FinalizePromptInput,
    PreparePromptInput,
)
from rtv2.skills import LocalSkillLoader, SkillRegistry, SkillStatus, build_skill_tools
from rtv2.solver import ReActStepRunner, RuntimeSolver
from rtv2.solver.models import SolverResult, StepResult, StepStatusSignal
from rtv2.state.models import (
    DomainState,
    PrepareResult,
    RunContext,
    RunIdentity,
    RunLifecycle,
    RunPhase,
    RuntimeState,
)
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
        planner_model_provider: ModelProvider | None = None,
        planner_generation_config: GenerationConfig | None = None,
        finalize_model_provider: ModelProvider | None = None,
        finalize_generation_config: GenerationConfig | None = None,
        runtime_verifier: RuntimeVerifier | None = None,
        verifier_model_provider: ModelProvider | None = None,
        verifier_generation_config: GenerationConfig | None = None,
        runtime_solver: RuntimeSolver | None = None,
    ) -> None:
        self.graph_store = graph_store
        self.skill_loader = skill_loader or LocalSkillLoader()
        self.skill_registry = skill_registry
        self.tool_registry = tool_registry
        self._load_and_enable_skills(skill_paths or [])
        self.memory_store = memory_store or SQLiteRuntimeMemoryStore()
        self.memory_processor = memory_processor or RuntimeMemoryProcessor(memory_store=self.memory_store)
        self.prompt_assembler = prompt_assembler or ExecutionPromptAssembler()
        self.planner_model_provider = planner_model_provider or HttpChatModelProvider(
            default_config=GenerationConfig(temperature=0.1, max_tokens=1200)
        )
        self.planner_generation_config = planner_generation_config or GenerationConfig(
            temperature=0.1,
            max_tokens=1200,
        )
        self.finalize_model_provider = finalize_model_provider or HttpChatModelProvider(
            default_config=GenerationConfig(temperature=0.1, max_tokens=1200)
        )
        self.finalize_generation_config = finalize_generation_config or GenerationConfig(
            temperature=0.1,
            max_tokens=1200,
        )
        self.react_step_runner = react_step_runner or ReActStepRunner(
            tool_registry=tool_registry,
            memory_store=self.memory_store,
        )
        self.runtime_verifier = runtime_verifier or RuntimeVerifier(
            model_provider=verifier_model_provider,
            generation_config=verifier_generation_config,
            max_rounds=20,
        )
        self.runtime_solver = runtime_solver or RuntimeSolver(
            react_step_runner=self.react_step_runner,
            max_steps_per_node=20,
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
        """Run the prepare-phase planner and advance into execute."""

        if context.run_lifecycle.current_phase is not RunPhase.PREPARE:
            raise ValueError("Prepare phase requires current_phase=PREPARE")

        if context.domain_state.task_graph_state.nodes:
            raise ValueError("Prepare phase currently only supports empty-graph initialization")

        self._append_run_user_input_entry(context)
        try:
            planner_output = self._run_prepare_planner(context)
            prepare_result = self._normalize_prepare_payload(context, planner_output)
            if prepare_result.patch is None:
                raise ValueError("Prepare planner did not produce a graph patch")
        except RuntimeError:
            prepare_result = self._build_prepare_fallback_result(context)

        context.run_identity.goal = prepare_result.goal
        context.runtime_state.prepare_result = prepare_result
        self._apply_graph_patch(context, prepare_result.patch)
        self._append_prepare_result_entry(context, prepare_result)
        context.run_lifecycle.current_phase = RunPhase.EXECUTE
        return context

    def run_execute_phase(self, context: RunContext) -> RunContext:
        """Advance the context from execute into finalize."""

        if context.run_lifecycle.current_phase is not RunPhase.EXECUTE:
            raise ValueError("Execute phase requires current_phase=EXECUTE")

        while True:
            selected_node = self.select_active_node(context)
            if selected_node is None:
                self._finalize_execute_graph_status(context)
                break

            context.runtime_state.active_node_id = selected_node.node_id
            solver_result = self.runtime_solver.solve_current_node(
                context=context,
                node=selected_node,
                build_step_prompt=self.build_react_step_prompt,
                create_step_id=self._create_step_id,
            )
            self._apply_solver_result(context, solver_result)

        context.run_lifecycle.current_phase = RunPhase.FINALIZE
        context.run_lifecycle.result_status = "completed"
        context.run_lifecycle.stop_reason = "execute_finished"
        return context

    def run_finalize_phase(self, context: RunContext) -> HostRunResult:
        """Finalize a completed context into a host-facing run result."""

        if context.run_lifecycle.current_phase is not RunPhase.FINALIZE:
            raise ValueError("Finalize phase requires current_phase=FINALIZE")

        graph_state = context.domain_state.task_graph_state
        if not graph_state.nodes or any(node.node_status is not NodeStatus.COMPLETED for node in graph_state.nodes):
            raise ValueError("Finalize phase requires all graph nodes to be completed")

        finalize_result = self._run_finalize_generator(context)
        handoff = Handoff(
            goal=context.run_identity.goal,
            user_input=context.run_identity.user_input,
            graph_summary=finalize_result.graph_summary,
            final_output=finalize_result.final_output,
        )
        verification_result = self.runtime_verifier.verify(handoff)

        if verification_result.result_status is VerificationResultStatus.PASS:
            context.run_lifecycle.result_status = "pass"
            context.run_lifecycle.stop_reason = "finalize_passed"
            return HostRunResult(
                task_id=context.run_identity.task_id,
                run_id=context.run_identity.run_id,
                runtime_state="completed",
                output_text=handoff.final_output,
            )

        context.run_lifecycle.result_status = "fail"
        context.run_lifecycle.stop_reason = "final_verification_failed"
        return HostRunResult(
            task_id=context.run_identity.task_id,
            run_id=context.run_identity.run_id,
            runtime_state="failed",
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
            if node.node_status in {NodeStatus.READY, NodeStatus.RUNNING}:
                return node

        if graph_state.active_node_id:
            node = self._find_node(graph_state, graph_state.active_node_id)
            if node is None:
                raise ValueError("task_graph_state.active_node_id points to a missing node")
            if node.node_status in {NodeStatus.READY, NodeStatus.RUNNING}:
                return node

        for node in graph_state.nodes:
            if node.node_status in {NodeStatus.READY, NodeStatus.RUNNING}:
                return node

        return None

    def _apply_step_result(self, context: RunContext, step_result: StepResult | None) -> None:
        """Consume the current minimal step result and write back its graph patch."""

        patch = step_result.patch if step_result is not None else None
        if patch is None:
            return

        self._apply_graph_patch(context, patch)

    def _apply_graph_patch(self, context: RunContext, patch: TaskGraphPatch) -> None:
        """Apply a graph patch and synchronize runtime active-node mirrors."""

        self.graph_store.save_graph(context.domain_state.task_graph_state)
        updated_graph = self.graph_store.apply_patch(
            context.domain_state.task_graph_state.graph_id,
            patch,
        )
        context.domain_state.task_graph_state = updated_graph
        if patch.active_node_id is not None:
            context.runtime_state.active_node_id = patch.active_node_id

    def _apply_solver_result(self, context: RunContext, solver_result: SolverResult) -> None:
        """Consume the current node-scoped solve result and write back its patch."""

        self._apply_step_result(context, solver_result.final_step_result)
        self._refresh_runtime_active_node(context)

    def _refresh_runtime_active_node(self, context: RunContext) -> None:
        selected_node = self.select_active_node(context)
        if selected_node is None:
            context.runtime_state.active_node_id = ""
            context.domain_state.task_graph_state.active_node_id = ""
            return
        context.runtime_state.active_node_id = selected_node.node_id
        context.domain_state.task_graph_state.active_node_id = selected_node.node_id

    def _finalize_execute_graph_status(self, context: RunContext) -> None:
        graph_state = context.domain_state.task_graph_state
        if graph_state.nodes and all(node.node_status is NodeStatus.COMPLETED for node in graph_state.nodes):
            if graph_state.graph_status is not TaskGraphStatus.COMPLETED:
                self._apply_graph_patch(
                    context,
                    TaskGraphPatch(graph_status=TaskGraphStatus.COMPLETED, active_node_id=""),
                )
            return
        if graph_state.graph_status is not TaskGraphStatus.BLOCKED:
            self._apply_graph_patch(
                context,
                TaskGraphPatch(graph_status=TaskGraphStatus.BLOCKED, active_node_id=""),
            )

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

    def build_prepare_prompt(self, context: RunContext) -> ExecutionPrompt:
        """Build the three-block prepare prompt for planner-side execution."""

        prompt_context = self.memory_processor.build_prompt_context_text(
            RuntimeMemoryProcessorInput(
                task_id=context.run_identity.task_id,
                run_id=context.run_identity.run_id,
                current_phase=context.run_lifecycle.current_phase.value,
                active_node_id=context.runtime_state.active_node_id,
                user_input=context.run_identity.user_input,
                compression_state=context.runtime_state.compression_state,
            )
        )
        return self.prompt_assembler.build_prepare_prompt(
            PreparePromptInput(
                user_input=context.run_identity.user_input,
                current_goal=context.run_identity.goal,
                graph_snapshot_text=self._build_graph_snapshot_text(context.domain_state.task_graph_state),
                runtime_memory_text=prompt_context.prompt_context_text,
                capability_text=self._build_tool_capability_text(),
                finalize_return_input=self._build_finalize_return_input_text(context),
            )
        )

    def build_finalize_prompt(self, context: RunContext) -> ExecutionPrompt:
        """Build the three-block finalize prompt for closeout generation."""

        prompt_context = self.memory_processor.build_prompt_context_text(
            RuntimeMemoryProcessorInput(
                task_id=context.run_identity.task_id,
                run_id=context.run_identity.run_id,
                current_phase=context.run_lifecycle.current_phase.value,
                active_node_id=context.runtime_state.active_node_id,
                user_input=context.run_identity.user_input,
                compression_state=context.runtime_state.compression_state,
            )
        )
        return self.prompt_assembler.build_finalize_prompt(
            FinalizePromptInput(
                user_input=context.run_identity.user_input,
                goal=context.run_identity.goal,
                graph_snapshot_text=self._build_graph_snapshot_text(context.domain_state.task_graph_state),
                runtime_memory_text=prompt_context.prompt_context_text,
                capability_text=self._build_tool_capability_text(),
            )
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
    def _build_graph_snapshot_text(graph_state: TaskGraphState) -> str:
        if not graph_state.nodes:
            return "(empty graph)"

        lines = [
            f"Graph id: {graph_state.graph_id}",
            f"Graph status: {graph_state.graph_status.value}",
            f"Active node id: {graph_state.active_node_id or '(empty)'}",
            "Nodes:",
        ]
        for node in graph_state.nodes:
            dependency_text = ", ".join(node.dependencies) if node.dependencies else "(none)"
            lines.append(
                f"- {node.node_id} | {node.name or '(empty)'} | {node.kind or '(empty)'} | "
                f"{node.node_status.value} | deps={dependency_text}"
            )
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

    def _append_prepare_result_entry(self, context: RunContext, prepare_result: PrepareResult) -> None:
        patch = prepare_result.patch
        if patch is None:
            return

        self.memory_store.append_entry(
            RuntimeMemoryEntry(
                entry_id=f"entry-{uuid4()}",
                task_id=context.run_identity.task_id,
                run_id=context.run_identity.run_id,
                step_id="prepare",
                node_id="",
                entry_type=RuntimeMemoryEntryType.CONTEXT,
                role=RuntimeMemoryRole.SYSTEM,
                content="\n".join(
                    [
                        f"goal: {prepare_result.goal}",
                        f"graph_change_summary: added {len(patch.new_nodes)} nodes; active node = {patch.active_node_id or '(empty)'}",
                    ]
                ),
                created_at=datetime.now(timezone.utc).isoformat(),
            )
        )

    def _run_prepare_planner(self, context: RunContext) -> ModelOutput:
        prepare_prompt = self.build_prepare_prompt(context)
        rendered_prompt = self.render_execution_prompt(prepare_prompt)
        return self.planner_model_provider.generate(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are the runtime-v2 prepare planner. "
                        "Return valid JSON only and do not call tools."
                    ),
                },
                {
                    "role": "user",
                    "content": rendered_prompt,
                },
            ],
            tools=[],
            config=self.planner_generation_config,
        )

    def _run_finalize_generator(self, context: RunContext) -> FinalizeGenerationResult:
        finalize_prompt = self.build_finalize_prompt(context)
        rendered_prompt = self.render_execution_prompt(finalize_prompt)
        model_output = self.finalize_model_provider.generate(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are the runtime-v2 finalize generator. "
                        "Return valid JSON only and do not call tools."
                    ),
                },
                {
                    "role": "user",
                    "content": rendered_prompt,
                },
            ],
            tools=[],
            config=self.finalize_generation_config,
        )
        payload = self._load_prepare_payload(model_output.content)
        final_output = str(payload.get("final_output", "") or "").strip()
        graph_summary = str(payload.get("graph_summary", "") or "").strip()
        if not final_output:
            raise ValueError("Finalize generator output must contain non-empty final_output")
        if not graph_summary:
            raise ValueError("Finalize generator output must contain non-empty graph_summary")
        return FinalizeGenerationResult(
            final_output=final_output,
            graph_summary=graph_summary,
        )

    def _build_prepare_fallback_result(self, context: RunContext) -> PrepareResult:
        goal = context.run_identity.goal.strip() or context.run_identity.user_input.strip()
        if not goal:
            raise RuntimeError("Prepare fallback requires a non-empty goal or user input")

        node_id = self._create_node_id()
        patch = TaskGraphPatch(
            new_nodes=[
                TaskGraphNode(
                    node_id=node_id,
                    graph_id=context.domain_state.task_graph_state.graph_id,
                    name="Handle current request",
                    kind="execution",
                    description=goal,
                    node_status=NodeStatus.READY,
                    owner="main",
                    order=1,
                )
            ],
            active_node_id=node_id,
        )
        return PrepareResult(
            goal=goal,
            patch=patch,
        )

    def _normalize_prepare_payload(self, context: RunContext, planner_output: ModelOutput) -> PrepareResult:
        payload = self._load_prepare_payload(planner_output.content)
        if context.domain_state.task_graph_state.nodes:
            raise ValueError("Prepare payload normalization currently supports empty graphs only")

        goal = str(payload.get("goal", "") or "").strip()
        if not goal:
            raise ValueError("Prepare payload must contain a non-empty goal")

        raw_nodes = payload.get("nodes")
        if not isinstance(raw_nodes, list) or not raw_nodes:
            raise ValueError("Prepare payload must contain a non-empty nodes list")

        active_node_ref = str(payload.get("active_node_ref", "") or "").strip()
        if not active_node_ref:
            raise ValueError("Prepare payload must contain active_node_ref")

        normalized_nodes: list[tuple[str, TaskGraphNode]] = []
        ref_to_node_id: dict[str, str] = {}
        seen_refs: set[str] = set()

        for raw_node in raw_nodes:
            if not isinstance(raw_node, dict):
                raise ValueError("Each prepare node must be an object")

            ref = str(raw_node.get("ref", "") or "").strip()
            if not ref:
                raise ValueError("Prepare node ref is required")
            if ref in seen_refs:
                raise ValueError(f"Duplicate prepare node ref: {ref}")
            seen_refs.add(ref)

            name = str(raw_node.get("name", "") or "").strip()
            kind = str(raw_node.get("kind", "") or "").strip()
            description = str(raw_node.get("description", "") or "").strip()
            if not name:
                raise ValueError(f"Prepare node name is required for ref: {ref}")
            if not kind:
                raise ValueError(f"Prepare node kind is required for ref: {ref}")
            if not description:
                raise ValueError(f"Prepare node description is required for ref: {ref}")

            raw_status = str(raw_node.get("node_status", "") or "").strip().lower()
            if raw_status not in {NodeStatus.PENDING.value, NodeStatus.READY.value}:
                raise ValueError(
                    f"Prepare node_status must be pending or ready for ref: {ref}"
                )
            node_status = NodeStatus(raw_status)

            owner = str(raw_node.get("owner", "") or "").strip() or "main"
            raw_order = raw_node.get("order", 0)
            if not isinstance(raw_order, int) or raw_order <= 0:
                raise ValueError(f"Prepare node order must be a positive integer for ref: {ref}")

            raw_dependencies = raw_node.get("dependencies", [])
            if not isinstance(raw_dependencies, list):
                raise ValueError(f"Prepare node dependencies must be a list for ref: {ref}")
            dependencies = []
            for dependency in raw_dependencies:
                dependency_ref = str(dependency or "").strip()
                if not dependency_ref:
                    raise ValueError(f"Prepare node dependency ref is required for ref: {ref}")
                dependencies.append(dependency_ref)

            node_id = self._create_node_id()
            ref_to_node_id[ref] = node_id
            normalized_nodes.append(
                (
                    ref,
                    TaskGraphNode(
                        node_id=node_id,
                        graph_id=context.domain_state.task_graph_state.graph_id,
                        name=name,
                        kind=kind,
                        description=description,
                        node_status=node_status,
                        owner=owner,
                        dependencies=dependencies,
                        order=raw_order,
                    ),
                )
            )

        if active_node_ref not in ref_to_node_id:
            raise ValueError("active_node_ref must point to one of the planned nodes")

        final_nodes: list[TaskGraphNode] = []
        for ref, node in normalized_nodes:
            mapped_dependencies: list[str] = []
            for dependency_ref in node.dependencies:
                dependency_node_id = ref_to_node_id.get(dependency_ref)
                if dependency_node_id is None:
                    raise ValueError(
                        f"Prepare node dependency ref not found: {dependency_ref} for ref: {ref}"
                    )
                mapped_dependencies.append(dependency_node_id)
            node.dependencies = mapped_dependencies
            final_nodes.append(node)

        active_node_id = ref_to_node_id[active_node_ref]
        active_node = self._find_node(
            TaskGraphState(
                graph_id=context.domain_state.task_graph_state.graph_id,
                nodes=final_nodes,
                active_node_id=active_node_id,
            ),
            active_node_id,
        )
        if active_node is None or active_node.node_status is not NodeStatus.READY:
            raise ValueError("active_node_ref must point to a ready node")

        return PrepareResult(
            goal=goal,
            patch=TaskGraphPatch(
                new_nodes=final_nodes,
                active_node_id=active_node_id,
            ),
        )

    @staticmethod
    def _load_prepare_payload(raw_text: str) -> dict[str, object]:
        text = raw_text.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines).strip()
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError("Prepare planner output was not valid JSON") from exc
        if not isinstance(payload, dict):
            raise ValueError("Prepare planner output must be a JSON object")
        return payload
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
