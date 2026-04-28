"""Tool integration hooks for runtime-v2."""

from rtv2.tools.decorator import tool
from rtv2.tools.executor import LocalToolExecutor
from rtv2.tools.models import ToolCall, ToolHook, ToolResult, ToolSpec
from rtv2.tools.registry import ToolRegistry

__all__ = [
    "LocalToolExecutor",
    "ToolCall",
    "ToolHook",
    "ToolRegistry",
    "ToolResult",
    "ToolSpec",
    "tool",
]
