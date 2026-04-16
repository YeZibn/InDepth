import inspect
import types
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Union, get_args, get_origin


@dataclass
class ToolFunction:
    name: str
    description: str
    entrypoint: Callable[..., Any]
    parameters: Dict[str, Any]
    stop_after_tool_call: bool = False
    requires_confirmation: bool = False
    cache_results: bool = False
    strict: bool = False


def _infer_parameters(fn: Callable[..., Any]) -> Dict[str, Any]:
    def _annotation_to_schema(annotation: Any) -> Dict[str, Any]:
        if annotation is inspect.Parameter.empty:
            return {"type": "string"}
        if annotation in (int, "int"):
            return {"type": "integer"}
        if annotation in (float, "float"):
            return {"type": "number"}
        if annotation in (bool, "bool"):
            return {"type": "boolean"}
        if annotation in (dict, Dict, "dict"):
            return {"type": "object"}
        if annotation in (list, List, "list"):
            return {"type": "array", "items": {"type": "string"}}

        origin = get_origin(annotation)
        if origin in (list, List):
            args = get_args(annotation)
            item_annotation = args[0] if args else str
            return {"type": "array", "items": _annotation_to_schema(item_annotation)}
        if origin in (dict, Dict):
            return {"type": "object"}
        if origin in (Union, types.UnionType):
            nested = [a for a in get_args(annotation) if a is not type(None)]
            if len(nested) == 1:
                return _annotation_to_schema(nested[0])
        return {"type": "string"}

    sig = inspect.signature(fn)
    properties: Dict[str, Any] = {}
    required: List[str] = []
    for param_name, param in sig.parameters.items():
        if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            continue
        properties[param_name] = _annotation_to_schema(param.annotation)
        if param.default is inspect.Parameter.empty:
            required.append(param_name)
    return {
        "type": "object",
        "properties": properties,
        "required": required,
    }


def _apply_hooks(
    fn_name: str,
    fn: Callable[..., Any],
    tool_hooks: Optional[List[Callable[..., Any]]],
) -> Callable[..., Any]:
    if not tool_hooks:
        return fn
    wrapped = fn
    for hook in reversed(tool_hooks):
        prev_fn = wrapped

        def _make(h: Callable[..., Any], p: Callable[..., Any]) -> Callable[..., Any]:
            def _wrapped(**kwargs: Any) -> Any:
                return h(fn_name, p, kwargs)

            return _wrapped

        wrapped = _make(hook, prev_fn)
    return wrapped


def tool(
    name: str,
    description: str,
    stop_after_tool_call: bool = False,
    requires_confirmation: bool = False,
    cache_results: bool = False,
    strict: bool = False,
    parameters: Optional[Dict[str, Any]] = None,
    tool_hooks: Optional[List[Callable[..., Any]]] = None,
):
    def decorator(fn: Callable[..., Any]) -> ToolFunction:
        wrapped = _apply_hooks(name, fn, tool_hooks)
        return ToolFunction(
            name=name,
            description=description,
            entrypoint=wrapped,
            parameters=parameters if parameters is not None else _infer_parameters(fn),
            stop_after_tool_call=stop_after_tool_call,
            requires_confirmation=requires_confirmation,
            cache_results=cache_results,
            strict=strict,
        )

    return decorator
