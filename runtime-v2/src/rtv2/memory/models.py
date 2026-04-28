"""Runtime memory models for runtime-v2."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from rtv2.task_graph.models import ResultRef


class RuntimeMemoryEntryType(StrEnum):
    """Top-level runtime memory entry kinds."""

    CONTEXT = "context"
    REFLEXION = "reflexion"


class RuntimeMemoryRole(StrEnum):
    """Minimal runtime memory speaker/source roles."""

    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"
    SYSTEM = "system"


class ReflexionTrigger(StrEnum):
    """Minimal trigger reasons for reflexion entries."""

    COMPLETION_FAILED = "completion_failed"
    BLOCKED = "blocked"
    FAILED = "failed"


class ReplanSignal(StrEnum):
    """Minimal replan signals retained in runtime memory."""

    NONE = "none"
    SUGGESTED = "suggested"


@dataclass(slots=True)
class RuntimeMemoryEntry:
    """Unified runtime memory entry persisted for short-term context."""

    entry_id: str
    task_id: str
    run_id: str
    step_id: str
    node_id: str
    entry_type: RuntimeMemoryEntryType
    role: RuntimeMemoryRole
    content: str
    tool_name: str = ""
    tool_call_id: str = ""
    related_result_refs: list[ResultRef] = field(default_factory=list)
    reflexion_trigger: ReflexionTrigger | None = None
    reflexion_reason: str = ""
    next_try_hint: str = ""
    replan_signal: ReplanSignal = ReplanSignal.NONE
    created_at: str = ""
    seq: int | None = None

    def __post_init__(self) -> None:
        if not self.entry_id.strip():
            raise ValueError("entry_id is required")
        if not self.task_id.strip():
            raise ValueError("task_id is required")
        if not self.run_id.strip():
            raise ValueError("run_id is required")
        if not self.step_id.strip():
            raise ValueError("step_id is required")
        if not self.content.strip():
            raise ValueError("content is required")
        if not self.created_at.strip():
            raise ValueError("created_at is required")
        if self.seq is not None and self.seq <= 0:
            raise ValueError("seq must be positive when provided")

        if self.entry_type is RuntimeMemoryEntryType.REFLEXION:
            if self.reflexion_trigger is None:
                raise ValueError("reflexion_trigger is required for reflexion entries")
            if not self.reflexion_reason.strip():
                raise ValueError("reflexion_reason is required for reflexion entries")
        else:
            if self.reflexion_trigger is not None:
                raise ValueError("reflexion_trigger is only allowed for reflexion entries")
            if self.reflexion_reason.strip():
                raise ValueError("reflexion_reason is only allowed for reflexion entries")
            if self.next_try_hint.strip():
                raise ValueError("next_try_hint is only allowed for reflexion entries")
            if self.replan_signal is not ReplanSignal.NONE:
                raise ValueError("replan_signal is only allowed for reflexion entries")


@dataclass(slots=True)
class RuntimeMemoryQuery:
    """Minimal filter object for runtime memory reads."""

    task_id: str = ""
    run_id: str = ""
    step_id: str = ""
    node_id: str = ""
    entry_type: RuntimeMemoryEntryType | None = None
    tool_name: str = ""
    limit: int | None = None

    def __post_init__(self) -> None:
        if self.limit is not None and self.limit <= 0:
            raise ValueError("limit must be positive when provided")


@dataclass(slots=True)
class RuntimeMemoryProcessorInput:
    """Input contract for runtime memory prompt-context processing."""

    task_id: str
    run_id: str
    current_phase: str
    active_node_id: str = ""
    user_input: str = ""
    compression_state: object | None = None


@dataclass(slots=True)
class RuntimeMemoryProcessorOutput:
    """Output contract for runtime memory prompt-context processing."""

    prompt_context_text: str
