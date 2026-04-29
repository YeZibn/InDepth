"""Prompt assembler skeleton for runtime-v2."""

from __future__ import annotations

from rtv2.prompting.models import ExecutionPrompt, ExecutionPromptInput, FinalizePromptInput, PreparePromptInput
from rtv2.state.models import RunPhase


class ExecutionPromptAssembler:
    """Assemble the three formal execution prompt blocks."""

    def build_prepare_prompt(self, prompt_input: PreparePromptInput) -> ExecutionPrompt:
        """Build the formal prompt blocks for prepare-phase planning."""

        return ExecutionPrompt(
            base_prompt=self._build_base_prompt(),
            phase_prompt=self._build_prepare_phase_prompt(),
            dynamic_injection=self._build_prepare_dynamic_injection(prompt_input),
        )

    def build_finalize_prompt(self, prompt_input: FinalizePromptInput) -> ExecutionPrompt:
        """Build the formal prompt blocks for finalize-phase generation."""

        return ExecutionPrompt(
            base_prompt=self._build_base_prompt(),
            phase_prompt=self._build_finalize_phase_prompt(),
            dynamic_injection=self._build_finalize_dynamic_injection(prompt_input),
        )

    def build_execution_prompt(self, prompt_input: ExecutionPromptInput) -> ExecutionPrompt:
        """Build the formal prompt blocks for the current execution context."""

        return ExecutionPrompt(
            base_prompt=self._build_base_prompt(),
            phase_prompt=self._build_phase_prompt(prompt_input.phase),
            dynamic_injection=self._build_dynamic_injection(prompt_input),
        )

    @staticmethod
    def _build_base_prompt() -> str:
        return "\n".join(
            [
                "You are the main runtime-v2 agent executor.",
                "Follow the formal runtime contract and stay truthful.",
                "Use tools only when they are necessary to advance the current node.",
                "Ground your progress in the active node and the provided dynamic context.",
            ]
        )

    def _build_phase_prompt(self, phase: RunPhase) -> str:
        if phase is RunPhase.EXECUTE:
            return self._build_execute_phase_prompt()
        if phase is RunPhase.PREPARE:
            return self._build_prepare_phase_prompt()
        if phase is RunPhase.FINALIZE:
            return self._build_finalize_phase_prompt()
        raise ValueError(f"Unsupported phase for execution prompt assembly: {phase}")

    @staticmethod
    def _build_execute_phase_prompt() -> str:
        return "\n".join(
            [
                "Current phase: execute.",
                "Work inside the solver context and advance the current node only.",
                "You may use a lightweight ReAct style when needed.",
                "If a tool is needed, decide based on the current node objective and available capabilities.",
                "Your output must stay compatible with the current step execution contract.",
            ]
        )

    @staticmethod
    def _build_prepare_phase_prompt() -> str:
        return "\n".join(
            [
                "Current phase: prepare.",
                "You are acting as the runtime-v2 planner for the current run.",
                "Your job is to refine the run goal and produce the first executable task-graph plan.",
                "Do not execute any node and do not simulate tool results.",
                "Return JSON only.",
                "Required top-level keys: goal, active_node_ref, nodes.",
                "Each node must contain: ref, name, kind, description, node_status, owner, dependencies, order.",
                "Allowed node_status values for new nodes: pending, ready.",
                "active_node_ref must point to one ready node.",
            ]
        )

    @staticmethod
    def _build_finalize_phase_prompt() -> str:
        return "\n".join(
            [
                "Current phase: finalize.",
                "You are acting as the runtime-v2 finalize generator.",
                "Use the provided context to produce the final delivery text and a concise graph summary.",
                "Do not call tools and do not invent missing work.",
                "Return JSON only.",
                "Required top-level keys: final_output, graph_summary.",
            ]
        )

    def _build_dynamic_injection(self, prompt_input: ExecutionPromptInput) -> str:
        node_context = prompt_input.node_context
        lines = [
            "## Current Task Context",
            f"User input: {node_context.user_input or '(empty)'}",
            f"Goal: {node_context.goal or '(empty)'}",
            f"Active node id: {node_context.active_node_id or '(empty)'}",
            f"Active node name: {node_context.active_node_name or '(empty)'}",
            "Active node description:",
            node_context.active_node_description or "(empty)",
            f"Active node status: {node_context.active_node_status or '(empty)'}",
            "Dependencies:",
            self._render_list(node_context.dependency_summaries),
            "Artifacts:",
            self._render_list(node_context.artifacts),
            "Evidence:",
            self._render_list(node_context.evidence),
            "Notes:",
            self._render_list(node_context.notes),
            "## Runtime Memory",
            prompt_input.runtime_memory_text or "(empty)",
            "## Tool Capability Summary",
            prompt_input.tool_capability_text or "(empty)",
        ]
        if prompt_input.finalize_return_input.strip():
            lines.extend(
                [
                    "## Finalize Return Input",
                    prompt_input.finalize_return_input,
                ]
            )
        return "\n".join(lines)

    def _build_prepare_dynamic_injection(self, prompt_input: PreparePromptInput) -> str:
        lines = [
            "## Current Task Context",
            f"User input: {prompt_input.user_input or '(empty)'}",
            f"Current goal: {prompt_input.current_goal or '(empty)'}",
            "## Current Graph Snapshot",
            prompt_input.graph_snapshot_text or "(empty)",
            "## Runtime Memory",
            prompt_input.runtime_memory_text or "(empty)",
            "## Capability Summary",
            prompt_input.capability_text or "(empty)",
        ]
        if prompt_input.finalize_return_input.strip():
            lines.extend(
                [
                    "## Finalize Return Input",
                    prompt_input.finalize_return_input,
                ]
            )
        return "\n".join(lines)

    def _build_finalize_dynamic_injection(self, prompt_input: FinalizePromptInput) -> str:
        return "\n".join(
            [
                "## Current Task Context",
                f"User input: {prompt_input.user_input or '(empty)'}",
                f"Goal: {prompt_input.goal or '(empty)'}",
                "## Current Graph Snapshot",
                prompt_input.graph_snapshot_text or "(empty)",
                "## Runtime Memory",
                prompt_input.runtime_memory_text or "(empty)",
                "## Capability Summary",
                prompt_input.capability_text or "(empty)",
            ]
        )

    @staticmethod
    def _render_list(items: list[str]) -> str:
        if not items:
            return "(empty)"
        return "\n".join(f"- {item}" for item in items)
