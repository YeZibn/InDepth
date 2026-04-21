import json
from typing import Any, Callable, Dict, List


def finalize_active_todo_context(current_context: Dict[str, Any], runtime_state: str) -> Dict[str, Any]:
    ctx = dict(current_context or {})
    if not ctx:
        return {}
    if runtime_state == "completed":
        ctx["binding_state"] = "closed"
        ctx["binding_required"] = False
        ctx["execution_phase"] = "finalizing"
        ctx["active_subtask_number"] = None
        ctx["active_subtask_id"] = None
    return ctx


def update_active_todo_context(
    current_context: Dict[str, Any],
    executions: List[Dict[str, Any]],
) -> Dict[str, Any]:
    next_context = dict(current_context or {})
    for execution in executions:
        tool = str(execution.get("tool", "")).strip()
        args = execution.get("args", {}) if isinstance(execution.get("args"), dict) else {}
        payload = execution.get("payload", {}) if isinstance(execution.get("payload"), dict) else {}
        if tool == "plan_task" and execution.get("success"):
            mode = str(payload.get("mode", "") or "").strip()
            active_todo_id = str(payload.get("active_todo_id", "") or "").strip()
            execution_result = payload.get("execution_result", {}) if isinstance(payload.get("execution_result"), dict) else {}
            if mode == "create":
                todo_id = str(execution_result.get("todo_id", "") or "").strip()
                if todo_id:
                    next_context = {
                        "todo_id": todo_id,
                        "active_subtask_id": None,
                        "active_subtask_number": None,
                        "execution_phase": "planning",
                        "binding_required": True,
                        "binding_state": "bound",
                        "todo_bound_at": execution_result.get("todo_bound_at", ""),
                    }
            elif mode == "update" and active_todo_id:
                next_context = {
                    "todo_id": active_todo_id,
                    "active_subtask_id": None,
                    "active_subtask_number": None,
                    "execution_phase": "planning",
                    "binding_required": True,
                    "binding_state": "bound",
                    "todo_bound_at": next_context.get("todo_bound_at", ""),
                }
        elif tool == "update_task_status":
            todo_id = str(args.get("todo_id", payload.get("todo_id", ""))).strip()
            subtask_number = args.get("subtask_number")
            if todo_id and subtask_number is not None:
                status = str(args.get("status", "") or "").strip()
                active_number = int(subtask_number)
                active_subtask_id = str(payload.get("subtask_id", "") or "").strip() or None
                if status in {"completed", "abandoned", "pending"}:
                    active_number = None
                    active_subtask_id = None
                phase = "executing" if status == "in-progress" else "planning"
                if status in {"blocked", "awaiting_input", "timed_out"}:
                    phase = "planning"
                binding_state = "closed" if payload.get("all_completed") else "bound"
                next_context = {
                    "todo_id": todo_id,
                    "active_subtask_id": active_subtask_id,
                    "active_subtask_number": active_number,
                    "execution_phase": phase,
                    "binding_required": True,
                    "binding_state": binding_state,
                    "todo_bound_at": next_context.get("todo_bound_at", ""),
                }
        elif tool == "update_subtask":
            todo_id = str(args.get("todo_id", payload.get("todo_id", ""))).strip()
            subtask_number = payload.get("subtask_number") or args.get("subtask_number")
            subtask_id = str(payload.get("subtask_id", "") or args.get("subtask_id", "")).strip()
            if todo_id and subtask_number is not None:
                next_context = {
                    "todo_id": todo_id,
                    "active_subtask_id": subtask_id or None,
                    "active_subtask_number": int(subtask_number),
                    "execution_phase": str(next_context.get("execution_phase", "planning") or "planning"),
                    "binding_required": True,
                    "binding_state": str(next_context.get("binding_state", "bound") or "bound"),
                    "todo_bound_at": next_context.get("todo_bound_at", ""),
                }
        elif tool == "reopen_subtask":
            todo_id = str(args.get("todo_id", payload.get("todo_id", ""))).strip()
            subtask_number = payload.get("subtask_number") or args.get("subtask_number")
            subtask_id = str(payload.get("subtask_id", "") or args.get("subtask_id", "")).strip()
            if todo_id and subtask_number is not None:
                next_context = {
                    "todo_id": todo_id,
                    "active_subtask_id": subtask_id or None,
                    "active_subtask_number": int(subtask_number),
                    "execution_phase": "executing",
                    "binding_required": True,
                    "binding_state": "bound",
                    "todo_bound_at": next_context.get("todo_bound_at", ""),
                }
        elif tool == "get_next_task":
            todo_id = str(args.get("todo_id", "")).strip()
            next_task = payload.get("next_task", {}) if isinstance(payload, dict) else {}
            number = next_task.get("number")
            if todo_id and number:
                next_context = {
                    "todo_id": todo_id,
                    "active_subtask_id": str(next_task.get("subtask_id", "") or "").strip() or None,
                    "active_subtask_number": int(number),
                    "execution_phase": "planning",
                    "binding_required": True,
                    "binding_state": str(next_context.get("binding_state", "bound") or "bound"),
                    "todo_bound_at": next_context.get("todo_bound_at", ""),
                }
    return next_context


def restore_active_todo_context_from_history(history: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(history, list) or not history:
        return {}

    tool_results_by_call_id: Dict[str, Dict[str, Any]] = {}
    for msg in history:
        if str(msg.get("role", "")).strip().lower() != "tool":
            continue
        call_id = str(msg.get("tool_call_id", "") or "").strip()
        if not call_id:
            continue
        try:
            parsed = json.loads(str(msg.get("content", "") or "").strip() or "{}")
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            tool_results_by_call_id[call_id] = parsed

    executions: List[Dict[str, Any]] = []
    for msg in history:
        if str(msg.get("role", "")).strip().lower() != "assistant":
            continue
        tool_calls = msg.get("tool_calls", [])
        if not isinstance(tool_calls, list):
            continue
        for call in tool_calls:
            if not isinstance(call, dict):
                continue
            call_id = str(call.get("id", "") or "").strip()
            fn = call.get("function", {}) if isinstance(call.get("function"), dict) else {}
            tool_name = str(fn.get("name", "") or "").strip()
            if not call_id or not tool_name:
                continue
            tool_result = tool_results_by_call_id.get(call_id)
            if not isinstance(tool_result, dict):
                continue
            raw_args = fn.get("arguments", "{}")
            if isinstance(raw_args, str):
                try:
                    tool_args = json.loads(raw_args)
                except json.JSONDecodeError:
                    tool_args = {}
            else:
                tool_args = raw_args or {}
            if not isinstance(tool_args, dict):
                tool_args = {}
            payload = tool_result.get("result", {}) if isinstance(tool_result.get("result"), dict) else {}
            executions.append(
                {
                    "tool": tool_name,
                    "args": tool_args,
                    "success": bool(tool_result.get("success")),
                    "error": str(tool_result.get("error", "") or ""),
                    "payload": payload,
                }
            )

    return update_active_todo_context(current_context={}, executions=executions)


def tool_requires_todo_binding(tool_name: str, exempt_tools: set[str]) -> bool:
    tool_norm = str(tool_name or "").strip()
    if not tool_norm:
        return False
    return tool_norm not in exempt_tools


def maybe_emit_todo_binding_warning(
    tool_name: str,
    task_id: str,
    run_id: str,
    todo_context: Dict[str, Any],
    guard_mode: str,
    exempt_tools: set[str],
    emit_event: Callable[..., Dict[str, Any]],
) -> None:
    if guard_mode != "warn":
        return
    ctx = todo_context if isinstance(todo_context, dict) else {}
    todo_id = str(ctx.get("todo_id", "") or "").strip()
    active_subtask_number = ctx.get("active_subtask_number")
    binding_required = bool(ctx.get("binding_required"))
    if not todo_id or not binding_required:
        return
    if active_subtask_number not in (None, ""):
        return
    if not tool_requires_todo_binding(tool_name=tool_name, exempt_tools=exempt_tools):
        return
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
