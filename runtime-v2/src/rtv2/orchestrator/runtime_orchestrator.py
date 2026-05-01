"""RuntimeOrchestrator skeleton module."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

from rtv2.finalize import (
    FinalizeGenerationResult,
    FinalizeReflexion,
    Handoff,
    RunReflexionAction,
    RunReflexionInput,
    RuntimeVerifier,
    VerificationResultStatus,
)
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
    NodeReflexionPromptInput,
    PreparePromptInput,
    RunReflexionPromptInput,
)
from rtv2.skills import LocalSkillLoader, SkillRegistry, SkillStatus, build_skill_tools
from rtv2.solver import CompletionCheckInput, CompletionEvaluator, ReActStepRunner, RuntimeReflexion, RuntimeSolver
from rtv2.solver.models import SolverControlSignal, SolverResult, StepResult, StepStatusSignal
from rtv2.state.models import (
    DomainState,
    PrepareFailure,
    PrepareFailureType,
    PrepareResult,
    RunContext,
    RunIdentity,
    RunLifecycle,
    RunPhase,
    RequestReplan,
    RequestReplanSource,
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
        finalize_reflexion: FinalizeReflexion | None = None,
        verifier_model_provider: ModelProvider | None = None,
        verifier_generation_config: GenerationConfig | None = None,
        completion_evaluator: CompletionEvaluator | None = None,
        completion_evaluator_model_provider: ModelProvider | None = None,
        completion_evaluator_generation_config: GenerationConfig | None = None,
        runtime_reflexion: RuntimeReflexion | None = None,
        reflexion_model_provider: ModelProvider | None = None,
        reflexion_generation_config: GenerationConfig | None = None,
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
        self.finalize_reflexion = finalize_reflexion or FinalizeReflexion(
            model_provider=reflexion_model_provider,
            generation_config=reflexion_generation_config,
            max_rounds=10,
        )
        self.completion_evaluator = completion_evaluator or CompletionEvaluator(
            model_provider=completion_evaluator_model_provider,
            generation_config=completion_evaluator_generation_config,
            max_rounds=10,
        )
        self.runtime_reflexion = runtime_reflexion or RuntimeReflexion(
            model_provider=reflexion_model_provider,
            generation_config=reflexion_generation_config,
            max_rounds=10,
        )
        self.runtime_solver = runtime_solver or RuntimeSolver(
            react_step_runner=self.react_step_runner,
            completion_evaluator=self.completion_evaluator,
            runtime_reflexion=self.runtime_reflexion,
            memory_store=self.memory_store,
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

        self._append_run_user_input_entry(context)
        is_replan = context.runtime_state.request_replan is not None
        try:
            planner_output = self._run_prepare_planner(context)
            prepare_result = self._normalize_prepare_payload(context, planner_output)
            if prepare_result.patch is None:
                raise self._build_prepare_error(
                    PrepareFailureType.PLANNER_CONTRACT_ERROR,
                    "Prepare planner did not produce a graph patch",
                )
            if self._is_noop_prepare_patch(context, prepare_result.patch):
                raise self._build_prepare_error(
                    PrepareFailureType.PLANNER_NOOP_PATCH,
                    "Prepare planner patch did not introduce any effective graph change",
                )
        except (RuntimeError, AssertionError) as exc:
            if is_replan:
                context.runtime_state.prepare_failure = self._to_prepare_failure(
                    PrepareFailureType.PLANNER_MODEL_ERROR,
                    str(exc) or "Prepare planner model call failed",
                )
                raise
            prepare_result = self._build_prepare_fallback_result(context)
        except PreparePhaseError as exc:
            context.runtime_state.prepare_failure = self._to_prepare_failure(exc.failure_type, str(exc))
            raise

        context.run_identity.goal = prepare_result.goal
        context.runtime_state.prepare_result = prepare_result
        context.runtime_state.prepare_failure = None
        self._apply_graph_patch(context, prepare_result.patch)
        self._append_prepare_result_entry(context, prepare_result)
        context.runtime_state.request_replan = None
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
                build_completion_check_input=self.build_completion_check_input,
                build_reflexion_prompt=self.build_node_reflexion_prompt,
                create_step_id=self._create_step_id,
            )
            self._apply_solver_result(context, solver_result)
            if solver_result.control_signal is SolverControlSignal.REQUEST_REPLAN:
                self._store_request_replan(
                    context,
                    RequestReplan(
                        source=RequestReplanSource.NODE_REFLEXION,
                        node_id=selected_node.node_id,
                        reason=(
                            (solver_result.final_step_result.reason if solver_result.final_step_result is not None else "")
                            or "Node reflexion requested replan."
                        ),
                        created_at=datetime.now(timezone.utc).isoformat(),
                    ),
                )
                context.run_lifecycle.current_phase = RunPhase.PREPARE
                context = self.run_prepare_phase(context)
                continue

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

        context.runtime_state.finalize_return_input = self._build_finalize_return_input(verification_result)
        run_reflexion_input = RunReflexionInput(
            trigger_type="final_verification_fail",
            latest_summary=verification_result.summary,
            issues=verification_result.issues,
        )
        run_reflexion_result = self.finalize_reflexion.reflect(
            run_reflexion_input,
            self.build_run_reflexion_prompt(context, run_reflexion_input),
        )
        if run_reflexion_result.action is RunReflexionAction.REQUEST_REPLAN:
            self._store_request_replan(
                context,
                RequestReplan(
                    source=RequestReplanSource.RUN_REFLEXION,
                    node_id="",
                    reason=run_reflexion_result.summary,
                    created_at=datetime.now(timezone.utc).isoformat(),
                ),
            )
            context.run_lifecycle.current_phase = RunPhase.PREPARE
            context = self.run_prepare_phase(context)
            context = self.run_execute_phase(context)
            return self.run_finalize_phase(context)

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
                request_replan_text=self._build_request_replan_text(context),
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

    def build_node_reflexion_prompt(self, context: RunContext, reflexion_input) -> str:
        prompt_context = self.memory_processor.build_prompt_context_text(
            RuntimeMemoryProcessorInput(
                task_id=context.run_identity.task_id,
                run_id=context.run_identity.run_id,
                current_phase=context.run_lifecycle.current_phase.value,
                active_node_id=reflexion_input.node_id,
                user_input=context.run_identity.user_input,
                compression_state=context.runtime_state.compression_state,
            )
        )
        prompt = self.prompt_assembler.build_node_reflexion_prompt(
            NodeReflexionPromptInput(
                node_id=reflexion_input.node_id,
                node_name=reflexion_input.node_name,
                trigger_type=reflexion_input.trigger_type,
                latest_summary=reflexion_input.latest_summary,
                issues=list(reflexion_input.issues),
                runtime_memory_text=prompt_context.prompt_context_text,
            )
        )
        return self.render_execution_prompt(prompt)

    def build_run_reflexion_prompt(self, context: RunContext, reflexion_input: RunReflexionInput) -> str:
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
        prompt = self.prompt_assembler.build_run_reflexion_prompt(
            RunReflexionPromptInput(
                trigger_type=reflexion_input.trigger_type,
                latest_summary=reflexion_input.latest_summary,
                issues=list(reflexion_input.issues),
                runtime_memory_text=prompt_context.prompt_context_text,
            )
        )
        return self.render_execution_prompt(prompt)

    def build_completion_check_input(
        self,
        context: RunContext,
        node: TaskGraphNode,
        step_result: StepResult,
    ) -> CompletionCheckInput:
        if not hasattr(self.react_step_runner, "model_provider") or not hasattr(self.react_step_runner, "generation_config"):
            return CompletionCheckInput(
                node_id=node.node_id,
                node_name=node.name,
                node_kind=node.kind,
                node_description=node.description,
                completion_summary=step_result.reason or "Current node appears ready for completion.",
                completion_evidence=[],
                completion_notes=[],
                completion_reason=step_result.reason or "The latest step signaled ready_for_completion.",
            )

        rendered_prompt = self.build_react_step_prompt(context, node)
        try:
            model_output = self.react_step_runner.model_provider.generate(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are the current actor preparing a completion package for node-level evaluation. "
                            "Do not call tools. Return valid JSON only. "
                            "Required top-level keys: completion_summary, completion_evidence, completion_notes, completion_reason."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"{rendered_prompt}\n\n"
                            "Latest completion signal summary:\n"
                            f"{step_result.reason or '(empty)'}"
                        ),
                    },
                ],
                tools=[],
                config=self.react_step_runner.generation_config,
            )
        except AssertionError:
            return CompletionCheckInput(
                node_id=node.node_id,
                node_name=node.name,
                node_kind=node.kind,
                node_description=node.description,
                completion_summary=step_result.reason or "Current node appears ready for completion.",
                completion_evidence=[],
                completion_notes=[],
                completion_reason=step_result.reason or "The latest step signaled ready_for_completion.",
            )
        payload = self._load_prepare_payload(model_output.content)
        completion_summary = str(payload.get("completion_summary", "") or "").strip()
        completion_reason = str(payload.get("completion_reason", "") or "").strip()
        raw_evidence = payload.get("completion_evidence", [])
        raw_notes = payload.get("completion_notes", [])
        if not completion_summary:
            raise ValueError("Completion summary builder must return non-empty completion_summary")
        if not completion_reason:
            raise ValueError("Completion summary builder must return non-empty completion_reason")
        if not isinstance(raw_evidence, list):
            raise ValueError("Completion summary builder completion_evidence must be a list")
        if not isinstance(raw_notes, list):
            raise ValueError("Completion summary builder completion_notes must be a list")
        completion_evidence = [str(item or "").strip() for item in raw_evidence if str(item or "").strip()]
        completion_notes = [str(item or "").strip() for item in raw_notes if str(item or "").strip()]
        return CompletionCheckInput(
            node_id=node.node_id,
            node_name=node.name,
            node_kind=node.kind,
            node_description=node.description,
            completion_summary=completion_summary,
            completion_evidence=completion_evidence,
            completion_notes=completion_notes,
            completion_reason=completion_reason,
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
    def _build_request_replan_text(context: RunContext) -> str:
        request_replan = context.runtime_state.request_replan
        if request_replan is None:
            return ""
        return "\n".join(
            [
                f"Source: {request_replan.source.value}",
                f"Node id: {request_replan.node_id or '(empty)'}",
                f"Reason: {request_replan.reason or '(empty)'}",
                f"Created at: {request_replan.created_at or '(empty)'}",
            ]
        )

    @staticmethod
    def _build_finalize_return_input(verification_result) -> object:
        from rtv2.state.models import FinalizeReturnInput

        return FinalizeReturnInput(
            verification_summary=verification_result.summary,
            verification_issues=list(verification_result.issues),
        )

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
        try:
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
        except AssertionError as exc:
            raise RuntimeError(str(exc) or "Prepare planner model call failed") from exc

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

        node_id = self._create_node_id_for_graph(context.domain_state.task_graph_state)
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
            graph_status=TaskGraphStatus.ACTIVE,
        )
        return PrepareResult(
            goal=goal,
            patch=patch,
        )

    def _normalize_prepare_payload(self, context: RunContext, planner_output: ModelOutput) -> PrepareResult:
        payload = self._load_prepare_payload(planner_output.content)
        graph_state = context.domain_state.task_graph_state
        is_replan = context.runtime_state.request_replan is not None

        goal = str(payload.get("goal", "") or "").strip()
        if not goal:
            raise self._build_prepare_error(
                PrepareFailureType.PLANNER_CONTRACT_ERROR,
                "Prepare payload must contain a non-empty goal",
            )

        raw_nodes = payload.get("nodes")
        if not isinstance(raw_nodes, list) or not raw_nodes:
            raise self._build_prepare_error(
                PrepareFailureType.PLANNER_CONTRACT_ERROR,
                "Prepare payload must contain a non-empty nodes list",
            )

        active_node_ref = str(payload.get("active_node_ref", "") or "").strip()
        if not active_node_ref:
            raise self._build_prepare_error(
                PrepareFailureType.PLANNER_CONTRACT_ERROR,
                "Prepare payload must contain active_node_ref",
            )

        existing_node_map = {node.node_id: node for node in graph_state.nodes}
        normalized_nodes: list[tuple[str, TaskGraphNode]] = []
        node_updates: list[NodePatch] = []
        ref_to_node_id: dict[str, str] = {}
        seen_refs: set[str] = set()
        seen_update_ids: set[str] = set()

        for raw_node in raw_nodes:
            if not isinstance(raw_node, dict):
                raise self._build_prepare_error(
                    PrepareFailureType.PLANNER_CONTRACT_ERROR,
                    "Each prepare node must be an object",
                )

            action = str(raw_node.get("action", "") or "").strip().lower()
            if not action:
                action = "update" if is_replan and str(raw_node.get("node_id", "") or "").strip() else "create"

            if action == "create":
                ref = str(raw_node.get("ref", "") or "").strip()
                if not ref:
                    raise self._build_prepare_error(
                        PrepareFailureType.PLANNER_CONTRACT_ERROR,
                        "Prepare node ref is required",
                    )
                if ref in seen_refs:
                    raise self._build_prepare_error(
                        PrepareFailureType.PLANNER_CONTRACT_ERROR,
                        f"Duplicate prepare node ref: {ref}",
                    )
                seen_refs.add(ref)

                name = str(raw_node.get("name", "") or "").strip()
                kind = str(raw_node.get("kind", "") or "").strip()
                description = str(raw_node.get("description", "") or "").strip()
                if not name:
                    raise self._build_prepare_error(
                        PrepareFailureType.PLANNER_CONTRACT_ERROR,
                        f"Prepare node name is required for ref: {ref}",
                    )
                if not kind:
                    raise self._build_prepare_error(
                        PrepareFailureType.PLANNER_CONTRACT_ERROR,
                        f"Prepare node kind is required for ref: {ref}",
                    )
                if not description:
                    raise self._build_prepare_error(
                        PrepareFailureType.PLANNER_CONTRACT_ERROR,
                        f"Prepare node description is required for ref: {ref}",
                    )

                raw_status = str(raw_node.get("node_status", "") or "").strip().lower()
                if raw_status not in {NodeStatus.PENDING.value, NodeStatus.READY.value}:
                    raise self._build_prepare_error(
                        PrepareFailureType.PLANNER_CONTRACT_ERROR,
                        f"Prepare node_status must be pending or ready for ref: {ref}",
                    )
                node_status = NodeStatus(raw_status)

                owner = str(raw_node.get("owner", "") or "").strip() or "main"
                raw_order = raw_node.get("order", 0)
                if not isinstance(raw_order, int) or raw_order <= 0:
                    raise self._build_prepare_error(
                        PrepareFailureType.PLANNER_CONTRACT_ERROR,
                        f"Prepare node order must be a positive integer for ref: {ref}",
                    )

                raw_dependencies = raw_node.get("dependencies", [])
                if not isinstance(raw_dependencies, list):
                    raise self._build_prepare_error(
                        PrepareFailureType.PLANNER_CONTRACT_ERROR,
                        f"Prepare node dependencies must be a list for ref: {ref}",
                    )
                dependencies = []
                for dependency in raw_dependencies:
                    dependency_ref = str(dependency or "").strip()
                    if not dependency_ref:
                        raise self._build_prepare_error(
                            PrepareFailureType.PLANNER_CONTRACT_ERROR,
                            f"Prepare node dependency ref is required for ref: {ref}",
                        )
                    dependencies.append(dependency_ref)

                node_id = self._create_node_id_for_graph(graph_state, ref_to_node_id.values())
                ref_to_node_id[ref] = node_id
                normalized_nodes.append(
                    (
                        ref,
                        TaskGraphNode(
                            node_id=node_id,
                            graph_id=graph_state.graph_id,
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
                continue

            if action == "update":
                node_id = str(raw_node.get("node_id", "") or "").strip()
                if not is_replan:
                    raise self._build_prepare_error(
                        PrepareFailureType.PLANNER_GRAPH_SEMANTIC_ERROR,
                        "Prepare update action is only allowed during replan",
                    )
                if not node_id:
                    raise self._build_prepare_error(
                        PrepareFailureType.PLANNER_CONTRACT_ERROR,
                        "Prepare update node_id is required",
                    )
                if node_id in seen_update_ids:
                    raise self._build_prepare_error(
                        PrepareFailureType.PLANNER_CONTRACT_ERROR,
                        f"Duplicate prepare update node_id: {node_id}",
                    )
                seen_update_ids.add(node_id)
                existing_node = existing_node_map.get(node_id)
                if existing_node is None:
                    raise self._build_prepare_error(
                        PrepareFailureType.PLANNER_GRAPH_SEMANTIC_ERROR,
                        f"Prepare update node_id not found: {node_id}",
                    )
                if existing_node.node_status in {
                    NodeStatus.COMPLETED,
                    NodeStatus.FAILED,
                    NodeStatus.BLOCKED,
                    NodeStatus.ABANDONED,
                }:
                    raise self._build_prepare_error(
                        PrepareFailureType.PLANNER_GRAPH_SEMANTIC_ERROR,
                        f"Prepare update cannot modify terminal node: {node_id}",
                    )

                raw_status = raw_node.get("node_status")
                node_status = None
                if raw_status is not None:
                    status_text = str(raw_status or "").strip().lower()
                    if status_text not in {NodeStatus.PENDING.value, NodeStatus.READY.value}:
                        raise self._build_prepare_error(
                            PrepareFailureType.PLANNER_CONTRACT_ERROR,
                            f"Prepare update node_status must be pending or ready for node_id: {node_id}",
                        )
                    node_status = NodeStatus(status_text)

                raw_dependencies = raw_node.get("dependencies")
                dependencies = None
                if raw_dependencies is not None:
                    if not isinstance(raw_dependencies, list):
                        raise self._build_prepare_error(
                            PrepareFailureType.PLANNER_CONTRACT_ERROR,
                            f"Prepare update dependencies must be a list for node_id: {node_id}",
                        )
                    dependencies = []
                    for dependency in raw_dependencies:
                        dependency_ref = str(dependency or "").strip()
                        if not dependency_ref:
                            raise self._build_prepare_error(
                                PrepareFailureType.PLANNER_CONTRACT_ERROR,
                                f"Prepare update dependency ref is required for node_id: {node_id}",
                            )
                        dependencies.append(dependency_ref)

                node_updates.append(
                    NodePatch(
                        node_id=node_id,
                        name=self._optional_prepare_string(raw_node.get("name")),
                        description=self._optional_prepare_string(raw_node.get("description")),
                        node_status=node_status,
                        owner=self._optional_prepare_string(raw_node.get("owner")),
                        dependencies=dependencies,
                    )
                )
                continue

            raise self._build_prepare_error(
                PrepareFailureType.PLANNER_CONTRACT_ERROR,
                f"Unsupported prepare node action: {action}",
            )

        if active_node_ref not in ref_to_node_id and active_node_ref not in existing_node_map:
            raise self._build_prepare_error(
                PrepareFailureType.PLANNER_CONTRACT_ERROR,
                "active_node_ref must point to a planned create ref or existing node_id",
            )

        final_nodes: list[TaskGraphNode] = []
        for ref, node in normalized_nodes:
            mapped_dependencies: list[str] = []
            for dependency_ref in node.dependencies:
                dependency_node_id = ref_to_node_id.get(dependency_ref) or (
                    dependency_ref if dependency_ref in existing_node_map else None
                )
                if dependency_node_id is None:
                    raise self._build_prepare_error(
                        PrepareFailureType.PLANNER_GRAPH_SEMANTIC_ERROR,
                        f"Prepare node dependency ref not found: {dependency_ref} for ref: {ref}",
                    )
                mapped_dependencies.append(dependency_node_id)
            node.dependencies = mapped_dependencies
            final_nodes.append(node)

        for node_update in node_updates:
            if node_update.dependencies is not None:
                mapped_dependencies: list[str] = []
                for dependency_ref in node_update.dependencies:
                    dependency_node_id = ref_to_node_id.get(dependency_ref) or (
                        dependency_ref if dependency_ref in existing_node_map else None
                    )
                    if dependency_node_id is None:
                        raise self._build_prepare_error(
                            PrepareFailureType.PLANNER_GRAPH_SEMANTIC_ERROR,
                            f"Prepare update dependency ref not found: {dependency_ref} for node_id: {node_update.node_id}",
                        )
                    mapped_dependencies.append(dependency_node_id)
                node_update.dependencies = mapped_dependencies

        active_node_id = ref_to_node_id.get(active_node_ref, active_node_ref)
        active_node = self._resolve_prepare_active_node(graph_state, final_nodes, node_updates, active_node_id)
        if active_node is None or active_node.node_status is not NodeStatus.READY:
            raise self._build_prepare_error(
                PrepareFailureType.PLANNER_GRAPH_SEMANTIC_ERROR,
                "active_node_ref must point to a ready node after prepare normalization",
            )

        return PrepareResult(
            goal=goal,
            patch=TaskGraphPatch(
                node_updates=node_updates,
                new_nodes=final_nodes,
                active_node_id=active_node_id,
                graph_status=TaskGraphStatus.ACTIVE,
            ),
        )

    @staticmethod
    def _store_request_replan(context: RunContext, request_replan: RequestReplan) -> None:
        context.runtime_state.request_replan = request_replan

    def _create_node_id_for_graph(
        self,
        graph_state: TaskGraphState,
        pending_node_ids=None,
    ) -> str:
        existing_ids = {node.node_id for node in graph_state.nodes}
        if pending_node_ids is not None:
            existing_ids.update(str(node_id) for node_id in pending_node_ids)
        while True:
            node_id = self._create_node_id()
            if node_id not in existing_ids:
                return node_id

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
            raise PreparePhaseError(
                PrepareFailureType.PLANNER_PAYLOAD_PARSE_ERROR,
                "Prepare planner output was not valid JSON",
            ) from exc
        if not isinstance(payload, dict):
            raise PreparePhaseError(
                PrepareFailureType.PLANNER_PAYLOAD_PARSE_ERROR,
                "Prepare planner output must be a JSON object",
            )
        return payload

    @staticmethod
    def _optional_prepare_string(value: object) -> str | None:
        if value is None:
            return None
        text = str(value or "").strip()
        return text or ""

    @staticmethod
    def _build_prepare_error(failure_type: PrepareFailureType, message: str) -> "PreparePhaseError":
        return PreparePhaseError(failure_type, message)

    @staticmethod
    def _to_prepare_failure(failure_type: PrepareFailureType, message: str) -> PrepareFailure:
        return PrepareFailure(
            failure_type=failure_type,
            message=message,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

    @staticmethod
    def _is_noop_prepare_patch(context: RunContext, patch: TaskGraphPatch) -> bool:
        graph_state = context.domain_state.task_graph_state
        if patch.new_nodes:
            return False
        for node_update in patch.node_updates:
            existing_node = next((node for node in graph_state.nodes if node.node_id == node_update.node_id), None)
            if existing_node is None:
                return False
            if node_update.name is not None and node_update.name != existing_node.name:
                return False
            if node_update.description is not None and node_update.description != existing_node.description:
                return False
            if node_update.node_status is not None and node_update.node_status != existing_node.node_status:
                return False
            if node_update.owner is not None and node_update.owner != existing_node.owner:
                return False
            if node_update.dependencies is not None and list(node_update.dependencies) != list(existing_node.dependencies):
                return False
        if patch.active_node_id is not None and patch.active_node_id != graph_state.active_node_id:
            return False
        if patch.graph_status is not None and patch.graph_status != graph_state.graph_status:
            return False
        return True

    @staticmethod
    def _resolve_prepare_active_node(
        graph_state: TaskGraphState,
        new_nodes: list[TaskGraphNode],
        node_updates: list[NodePatch],
        active_node_id: str,
    ) -> TaskGraphNode | None:
        for node in new_nodes:
            if node.node_id == active_node_id:
                return node

        existing_node = next((node for node in graph_state.nodes if node.node_id == active_node_id), None)
        if existing_node is None:
            return None

        for patch in node_updates:
            if patch.node_id == active_node_id:
                status = patch.node_status or existing_node.node_status
                return TaskGraphNode(
                    node_id=existing_node.node_id,
                    graph_id=existing_node.graph_id,
                    name=patch.name if patch.name is not None else existing_node.name,
                    kind=existing_node.kind,
                    description=patch.description if patch.description is not None else existing_node.description,
                    node_status=status,
                    owner=patch.owner if patch.owner is not None else existing_node.owner,
                    dependencies=patch.dependencies if patch.dependencies is not None else list(existing_node.dependencies),
                    order=existing_node.order,
                )
        return existing_node

    @staticmethod
    def _find_node(graph_state: TaskGraphState, node_id: str) -> TaskGraphNode | None:
        for node in graph_state.nodes:
            if node.node_id == node_id:
                return node
        return None


class PreparePhaseError(ValueError):
    """Structured error raised during prepare normalization and validation."""

    def __init__(self, failure_type: PrepareFailureType, message: str) -> None:
        super().__init__(message)
        self.failure_type = failure_type
