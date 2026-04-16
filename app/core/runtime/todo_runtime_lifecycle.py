from typing import Any, Callable, Dict, List

from app.core.tools.registry import ToolRegistry


def update_active_todo_context(
    current_context: Dict[str, Any],
    executions: List[Dict[str, Any]],
) -> Dict[str, Any]:
    next_context = dict(current_context or {})
    for execution in executions:
        tool = str(execution.get("tool", "")).strip()
        args = execution.get("args", {}) if isinstance(execution.get("args"), dict) else {}
        payload = execution.get("payload", {}) if isinstance(execution.get("payload"), dict) else {}
        if tool == "create_task" and execution.get("success"):
            todo_id = str(payload.get("todo_id", "")).strip()
            if todo_id:
                next_context = {
                    "todo_id": todo_id,
                    "active_subtask_number": None,
                    "execution_phase": "planning",
                    "binding_required": True,
                }
        elif tool == "update_task_status":
            todo_id = str(args.get("todo_id", payload.get("todo_id", ""))).strip()
            subtask_number = args.get("subtask_number")
            if todo_id and subtask_number is not None:
                status = str(args.get("status", "") or "").strip()
                active_number = int(subtask_number)
                if status in {"completed", "abandoned", "pending"}:
                    active_number = None
                phase = "executing" if status == "in-progress" else "planning"
                if status in {"blocked", "failed", "partial", "awaiting_input", "timed_out"}:
                    phase = "recovering"
                next_context = {
                    "todo_id": todo_id,
                    "active_subtask_number": active_number,
                    "execution_phase": phase,
                    "binding_required": True,
                }
        elif tool == "record_task_fallback":
            todo_id = str(args.get("todo_id", payload.get("todo_id", ""))).strip()
            subtask_number = args.get("subtask_number")
            if todo_id and subtask_number is not None:
                next_context = {
                    "todo_id": todo_id,
                    "active_subtask_number": int(subtask_number),
                    "execution_phase": "recovering",
                    "binding_required": True,
                }
        elif tool == "get_next_task":
            todo_id = str(args.get("todo_id", "")).strip()
            next_task = payload.get("next_task", {}) if isinstance(payload, dict) else {}
            number = next_task.get("number")
            if todo_id and number:
                next_context = {
                    "todo_id": todo_id,
                    "active_subtask_number": int(number),
                    "execution_phase": "planning",
                    "binding_required": True,
                }
    return next_context


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


def build_orphan_todo_recovery(
    todo_context: Dict[str, Any],
    final_answer: str,
    preview: Callable[[str, int], str],
) -> Dict[str, Any]:
    ctx = todo_context if isinstance(todo_context, dict) else {}
    todo_id = str(ctx.get("todo_id", "") or "").strip()
    phase = str(ctx.get("execution_phase", "") or "planning").strip() or "planning"
    fallback_record = {
        "state": "failed",
        "reason_code": "orphan_subtask_unbound",
        "reason_detail": "Todo flow failed before the runtime could bind the current step to an active subtask.",
        "impact_scope": "Automatic subtask-level recovery could not continue because no active subtask was selected.",
        "retryable": True,
        "required_input": ["Bind the next action to a concrete subtask before resuming execution."],
        "suggested_next_action": "decision_handoff",
        "evidence": [preview(final_answer, 300)],
        "owner": "main",
        "retry_count": 0,
        "retry_budget_remaining": 1,
        "failure_stage": phase,
    }
    recovery_decision = {
        "primary_action": "decision_handoff",
        "recommended_actions": ["decision_handoff", "split"],
        "decision_level": "agent_decide",
        "rationale": "The todo is active, but the failing step was not bound to a concrete subtask.",
        "preserve_artifacts": [],
        "next_subtasks": [],
        "resume_condition": "Select or create the correct subtask, then mark it in-progress before resuming work.",
        "escalation_reason": "Runtime could not attribute the failure to a concrete subtask.",
        "stop_auto_recovery": True,
        "suggested_owner": "main",
    }
    return {
        "todo_id": todo_id,
        "fallback_record": fallback_record,
        "recovery_decision": recovery_decision,
    }


def build_runtime_fallback_record(
    runtime_state: str,
    stop_reason: str,
    final_answer: str,
    last_tool_failures: List[Dict[str, str]],
    preview: Callable[[str, int], str],
    extract_missing_info_hints: Callable[[str], List[str]],
) -> Dict[str, Any]:
    if runtime_state == "awaiting_user_input":
        return {
            "state": "awaiting_input",
            "reason_code": "waiting_user_input",
            "reason_detail": preview(final_answer, 300),
            "impact_scope": "Requires user input before this subtask can continue",
            "retryable": False,
            "required_input": extract_missing_info_hints(final_answer),
            "suggested_next_action": "decision_handoff",
            "evidence": [preview(final_answer, 300)],
            "owner": "user",
            "retry_count": 0,
            "retry_budget_remaining": 0,
        }
    if stop_reason == "max_steps_reached":
        return {
            "state": "timed_out",
            "reason_code": "budget_exhausted",
            "reason_detail": "Runtime reached max_steps without converging.",
            "impact_scope": "Recovery is needed before this subtask can be considered complete",
            "retryable": True,
            "required_input": [],
            "suggested_next_action": "split",
            "evidence": [preview(final_answer, 300)],
            "owner": "main",
            "retry_count": 1,
            "retry_budget_remaining": 0,
        }
    if last_tool_failures:
        details = [
            f"{item.get('tool', 'unknown')}: {item.get('error', '')}".strip(": ")
            for item in last_tool_failures[:3]
        ]
        return {
            "state": "failed",
            "reason_code": "tool_error",
            "reason_detail": "; ".join(details),
            "impact_scope": "Current subtask could not complete because one or more tools failed",
            "retryable": True,
            "required_input": [],
            "suggested_next_action": "retry_with_fix",
            "evidence": details,
            "owner": "main",
            "retry_count": len(last_tool_failures),
            "retry_budget_remaining": max(0, 2 - len(last_tool_failures)),
        }
    reason_code = "output_not_verifiable"
    if stop_reason == "model_failed":
        reason_code = "tool_error"
    elif stop_reason in {"length", "content_filter"}:
        reason_code = "output_not_verifiable"
    return {
        "state": "failed",
        "reason_code": reason_code,
        "reason_detail": preview(final_answer, 300),
        "impact_scope": "Current subtask did not finish successfully",
        "retryable": True,
        "required_input": [],
        "suggested_next_action": "split",
        "evidence": [preview(final_answer, 300)],
        "owner": "main",
        "retry_count": 1,
        "retry_budget_remaining": 1,
    }


def auto_manage_todo_recovery(
    task_id: str,
    run_id: str,
    runtime_state: str,
    stop_reason: str,
    final_answer: str,
    last_tool_failures: List[Dict[str, str]],
    todo_context: Dict[str, Any],
    tool_registry: ToolRegistry,
    preview: Callable[[str, int], str],
    extract_missing_info_hints: Callable[[str], List[str]],
    emit_event: Callable[..., Dict[str, Any]],
) -> Dict[str, Any]:
    ctx = todo_context or {}
    todo_id = str(ctx.get("todo_id", "")).strip()
    subtask_number = ctx.get("active_subtask_number")
    if not todo_id or runtime_state == "completed":
        return {}
    # 只有已经绑定到具体 subtask，runtime 才能安全地把失败写回 todo 系统并规划恢复。
    # 否则只能生成 orphan recovery，把后续决策交回主 agent 或用户。
    if subtask_number is None:
        recovery = build_orphan_todo_recovery(
            todo_context=ctx,
            final_answer=final_answer,
            preview=preview,
        )
        emit_event(
            task_id=task_id,
            run_id=run_id,
            actor="main",
            role="general",
            event_type="todo_orphan_failure_detected",
            status="error",
            payload={
                "todo_id": todo_id,
                "stop_reason": stop_reason,
                "runtime_state": runtime_state,
                "execution_phase": str(ctx.get("execution_phase", "") or ""),
            },
        )
        return recovery
    if not tool_registry.has("record_task_fallback") or not tool_registry.has("plan_task_recovery"):
        return {}

    fallback_record = build_runtime_fallback_record(
        runtime_state=runtime_state,
        stop_reason=stop_reason,
        final_answer=final_answer,
        last_tool_failures=last_tool_failures,
        preview=preview,
        extract_missing_info_hints=extract_missing_info_hints,
    )
    record_result = tool_registry.invoke(
        "record_task_fallback",
        {"todo_id": todo_id, "subtask_number": int(subtask_number), **fallback_record},
    )
    if not record_result.get("success"):
        return {}

    plan_result = tool_registry.invoke(
        "plan_task_recovery",
        {
            "todo_id": todo_id,
            "subtask_number": int(subtask_number),
            "retry_budget_remaining": int(fallback_record.get("retry_budget_remaining", 1) or 1),
            "available_roles": ["builder", "verifier", "researcher", "general"],
            "allowed_degraded_delivery": False,
            "is_on_critical_path": False,
        },
    )
    decision_payload = {}
    if isinstance(plan_result.get("result"), dict):
        decision_payload = plan_result["result"].get("recovery_decision", {}) or {}
    if not plan_result.get("success") or not decision_payload:
        return {}

    recovery = {
        "todo_id": todo_id,
        "subtask_number": int(subtask_number),
        "fallback_record": fallback_record,
        "recovery_decision": decision_payload,
    }

    emit_event(
        task_id=task_id,
        run_id=run_id,
        actor="main",
        role="general",
        event_type="todo_recovery_auto_planned",
        payload={
            "todo_id": todo_id,
            "subtask_number": int(subtask_number),
            "primary_action": decision_payload.get("primary_action", ""),
            "decision_level": decision_payload.get("decision_level", ""),
        },
    )

    if (
        decision_payload.get("decision_level") == "auto"
        and not decision_payload.get("stop_auto_recovery")
        and tool_registry.has("append_followup_subtasks")
    ):
        next_subtasks = decision_payload.get("next_subtasks", [])
        if next_subtasks:
            append_result = tool_registry.invoke(
                "append_followup_subtasks",
                {"todo_id": todo_id, "follow_up_subtasks": next_subtasks},
            )
            if append_result.get("success") and isinstance(append_result.get("result"), dict):
                recovery["appended_subtasks"] = append_result["result"]
    return recovery


def append_recovery_summary_for_user(answer: str, recovery: Dict[str, Any]) -> str:
    base = str(answer or "").strip()
    recovery = recovery if isinstance(recovery, dict) else {}
    if not recovery:
        return base

    fallback = recovery.get("fallback_record", {}) if isinstance(recovery.get("fallback_record"), dict) else {}
    decision = recovery.get("recovery_decision", {}) if isinstance(recovery.get("recovery_decision"), dict) else {}
    todo_id = str(recovery.get("todo_id", "") or "").strip()
    subtask_number = recovery.get("subtask_number")
    state = str(fallback.get("state", "") or "").strip()
    reason_code = str(fallback.get("reason_code", "") or "").strip()
    primary_action = str(decision.get("primary_action", "") or "").strip()
    decision_level = str(decision.get("decision_level", "") or "").strip()

    lines = []
    if todo_id:
        lines.append(f"todo: {todo_id}")
    if subtask_number not in (None, ""):
        lines.append(f"subtask: {subtask_number}")
    if state or reason_code:
        lines.append(f"failure: {state or 'unknown'} / {reason_code or 'n/a'}")
    if primary_action or decision_level:
        lines.append(f"next: {primary_action or 'n/a'} / {decision_level or 'n/a'}")

    append_info = recovery.get("appended_subtasks", {})
    if isinstance(append_info, dict):
        numbers = append_info.get("added_subtask_numbers", [])
        if isinstance(numbers, list) and numbers:
            lines.append(f"follow-up subtasks: {', '.join(str(item) for item in numbers)}")

    if not lines:
        return base

    summary = "\n".join(["", "恢复摘要:", *lines]).strip()
    if base:
        if "恢复摘要:" in base:
            return base
        return f"{base}\n\n{summary}"
    return summary
