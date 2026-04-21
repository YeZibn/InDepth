from typing import Any, Callable, Dict, List

from app.core.todo import TodoService


_todo_service = TodoService()


def finalize_active_todo_context(current_context: Dict[str, Any], runtime_state: str) -> Dict[str, Any]:
    return _todo_service.finalize_context(current_context=current_context, runtime_state=runtime_state)


def update_active_todo_context(
    current_context: Dict[str, Any],
    executions: List[Dict[str, Any]],
) -> Dict[str, Any]:
    return _todo_service.apply_executions(current_context=current_context, executions=executions)


def restore_active_todo_context_from_history(history: List[Dict[str, Any]]) -> Dict[str, Any]:
    return _todo_service.restore_context_from_history(history=history)


def tool_requires_todo_binding(tool_name: str, exempt_tools: set[str]) -> bool:
    return _todo_service.tool_requires_todo_binding(tool_name=tool_name, exempt_tools=exempt_tools)


def maybe_emit_todo_binding_warning(
    tool_name: str,
    task_id: str,
    run_id: str,
    todo_context: Dict[str, Any],
    guard_mode: str,
    exempt_tools: set[str],
    emit_event: Callable[..., Dict[str, Any]],
) -> None:
    if not _todo_service.should_emit_binding_warning(
        tool_name=tool_name,
        current_context=todo_context,
        guard_mode=guard_mode,
        exempt_tools=exempt_tools,
    ):
        return
    ctx = todo_context if isinstance(todo_context, dict) else {}
    todo_id = str(ctx.get("todo_id", "") or "").strip()
    emit_event(
        task_id=task_id,
        run_id=run_id,
        actor="main",
        role="general",
        event_type="todo_binding_missing_warning",
        status="error",
        payload={
            "todo_id": todo_id,
            "tool": tool_name,
            "execution_phase": str(ctx.get("execution_phase", "") or ""),
            "guard_mode": guard_mode,
        },
    )
