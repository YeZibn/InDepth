"""Prompting models for runtime-v2."""

from __future__ import annotations

from dataclasses import dataclass, field

from rtv2.state.models import RunPhase


@dataclass(slots=True)
class ExecutionNodePromptContext:
    """Minimal dynamic node/task view consumed by the execution prompt."""

    user_input: str
    goal: str = ""
    active_node_id: str = ""
    active_node_name: str = ""
    active_node_description: str = ""
    active_node_status: str = ""
    dependency_summaries: list[str] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ExecutionPromptInput:
    """Formal input consumed by the execution prompt assembler."""

    phase: RunPhase
    node_context: ExecutionNodePromptContext
    runtime_memory_text: str = ""
    tool_capability_text: str = ""
    finalize_return_input: str = ""


@dataclass(slots=True)
class ExecutionPrompt:
    """Three-block execution prompt output for runtime-v2."""

    base_prompt: str
    phase_prompt: str
    dynamic_injection: str


@dataclass(slots=True)
class PreparePromptInput:
    """Formal input consumed by prepare-phase prompt assembly."""

    user_input: str
    current_goal: str = ""
    graph_snapshot_text: str = ""
    runtime_memory_text: str = ""
    capability_text: str = ""
    finalize_return_input: str = ""
