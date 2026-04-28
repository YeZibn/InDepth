"""Minimal tool decorator for runtime-v2."""

from __future__ import annotations

from collections.abc import Callable

from rtv2.tools.models import ToolHook, ToolSpec


def tool(
    *,
    name: str,
    description: str,
    parameters: dict[str, object] | None = None,
    hooks: list[ToolHook] | None = None,
) -> Callable[[Callable[..., object]], ToolSpec]:
    """Declare a local tool as a directly-registrable spec."""

    def decorator(fn: Callable[..., object]) -> ToolSpec:
        return ToolSpec(
            name=name,
            description=description,
            parameters=parameters or {"type": "object", "properties": {}, "required": []},
            handler=fn,
            hooks=list(hooks or []),
        )

    return decorator
