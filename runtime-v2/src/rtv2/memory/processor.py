"""Runtime memory prompt-context processor for runtime-v2."""

from __future__ import annotations

from rtv2.memory.models import (
    RuntimeMemoryEntry,
    RuntimeMemoryEntryType,
    RuntimeMemoryProcessorInput,
    RuntimeMemoryProcessorOutput,
)
from rtv2.memory.store import RuntimeMemoryStore


class RuntimeMemoryProcessor:
    """Build task-level prompt context text from persisted runtime memory."""

    def __init__(self, *, memory_store: RuntimeMemoryStore) -> None:
        self.memory_store = memory_store

    def build_prompt_context_text(
        self,
        input: RuntimeMemoryProcessorInput,
    ) -> RuntimeMemoryProcessorOutput:
        entries = self.memory_store.list_entries_for_run(task_id=input.task_id, run_id=input.run_id)
        if input.task_id:
            task_entries = self.memory_store.list_entries_for_task(task_id=input.task_id)
        else:
            task_entries = entries

        lines = [
            "Runtime Context Anchor:",
            f"- task_id: {input.task_id}",
            f"- run_id: {input.run_id}",
            f"- current_phase: {input.current_phase}",
            f"- active_node_id: {input.active_node_id}",
            f"- user_input: {input.user_input}",
            "",
            "Runtime Memory Timeline:",
        ]
        if not task_entries:
            lines.append("(no runtime memory entries)")
            return RuntimeMemoryProcessorOutput(prompt_context_text="\n".join(lines))

        current_run_id = ""
        for entry in task_entries:
            if entry.run_id != current_run_id:
                current_run_id = entry.run_id
                lines.append("")
                lines.append(f"## Run {current_run_id}")
            lines.append(self._render_entry(entry))

        return RuntimeMemoryProcessorOutput(prompt_context_text="\n".join(lines))

    @staticmethod
    def _render_entry(entry: RuntimeMemoryEntry) -> str:
        prefix = (
            f"[seq={entry.seq or ''}]"
            f"[step={entry.step_id}]"
            f"[node={entry.node_id}]"
            f"[role={entry.role.value}]"
        )
        if entry.entry_type is RuntimeMemoryEntryType.REFLEXION:
            return (
                f"{prefix}[reflexion]"
                f"[trigger={entry.reflexion_trigger.value if entry.reflexion_trigger else ''}] "
                f"{entry.content} | reason={entry.reflexion_reason} | "
                f"next_try_hint={entry.next_try_hint} | replan_signal={entry.replan_signal.value}"
            )

        if entry.tool_name:
            return (
                f"{prefix}[tool={entry.tool_name}]"
                f"[tool_call_id={entry.tool_call_id}] {entry.content}"
            )
        return f"{prefix} {entry.content}"
