"""Minimal tool protocol models for runtime-v2."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, TypeAlias


ToolHandler: TypeAlias = Callable[..., object]
NextToolHandler: TypeAlias = Callable[[dict[str, object]], object]
ToolHook: TypeAlias = Callable[[str, dict[str, object], NextToolHandler], object]


@dataclass(slots=True)
class ToolSpec:
    """Minimal local tool declaration."""

    name: str
    description: str
    parameters: dict[str, object]
    handler: ToolHandler
    hooks: list[ToolHook] = field(default_factory=list)


@dataclass(slots=True)
class ToolCall:
    """Single tool call intent emitted from a runtime step."""

    tool_name: str
    arguments: dict[str, object]


@dataclass(slots=True)
class ToolResult:
    """Unified local tool execution result."""

    tool_name: str
    success: bool
    output_text: str
    error: str = ""
