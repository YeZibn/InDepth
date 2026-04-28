"""Minimal local tool executor for runtime-v2."""

from __future__ import annotations

import json

from rtv2.tools.models import NextToolHandler, ToolCall, ToolResult, ToolSpec
from rtv2.tools.registry import ToolRegistry


class LocalToolExecutor:
    """Resolve, validate, execute, and normalize a single local tool call."""

    def __init__(self, *, tool_registry: ToolRegistry) -> None:
        self.tool_registry = tool_registry

    def execute(self, tool_call: ToolCall) -> ToolResult:
        spec = self.tool_registry.get(tool_call.tool_name)
        if spec is None:
            return ToolResult(
                tool_name=tool_call.tool_name,
                success=False,
                output_text="",
                error=f"Unknown tool: {tool_call.tool_name}",
            )

        arguments = tool_call.arguments
        if not isinstance(arguments, dict):
            return ToolResult(
                tool_name=tool_call.tool_name,
                success=False,
                output_text="",
                error=f"Tool arguments for {tool_call.tool_name} must be a dict",
            )

        missing_required = self._find_missing_required(spec, arguments)
        if missing_required:
            missing_text = ", ".join(missing_required)
            return ToolResult(
                tool_name=tool_call.tool_name,
                success=False,
                output_text="",
                error=f"Tool arguments missing required fields: {missing_text}",
            )

        try:
            raw_result = self._run_tool(spec, dict(arguments))
        except Exception as exc:
            return ToolResult(
                tool_name=tool_call.tool_name,
                success=False,
                output_text="",
                error=str(exc),
            )

        return ToolResult(
            tool_name=tool_call.tool_name,
            success=True,
            output_text=self._to_output_text(raw_result),
        )

    def _run_tool(self, spec: ToolSpec, arguments: dict[str, object]) -> object:
        def base_handler(current_arguments: dict[str, object]) -> object:
            return spec.handler(**current_arguments)

        handler: NextToolHandler = base_handler
        for hook in reversed(spec.hooks):
            previous_handler = handler

            def make_wrapped(current_hook, next_handler):
                def wrapped(current_arguments: dict[str, object]) -> object:
                    return current_hook(spec.name, current_arguments, next_handler)

                return wrapped

            handler = make_wrapped(hook, previous_handler)
        return handler(arguments)

    @staticmethod
    def _find_missing_required(spec: ToolSpec, arguments: dict[str, object]) -> list[str]:
        required = spec.parameters.get("required", [])
        if not isinstance(required, list):
            return []
        return [field for field in required if not str(field) in arguments]

    @staticmethod
    def _to_output_text(result: object) -> str:
        if result is None:
            return ""
        if isinstance(result, str):
            return result
        try:
            return json.dumps(result, ensure_ascii=False)
        except TypeError:
            return str(result)
