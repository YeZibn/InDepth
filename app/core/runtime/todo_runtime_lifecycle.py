import json
from typing import Any, Callable, Dict, List, Optional

from app.core.model.base import GenerationConfig, ModelProvider
from app.core.runtime.recovery_planner_service import (
    build_default_failure_interpretation,
    build_rule_recovery_guardrails,
    generate_recovery_assessment_llm,
    normalize_llm_recovery_assessment,
)
from app.core.tools.registry import ToolRegistry


def _merge_failure_interpretation_into_fallback_record(
    fallback_record: Dict[str, Any],
    failure_interpretation: Dict[str, Any],
) -> Dict[str, Any]:
    record = dict(fallback_record or {})
    interpretation = failure_interpretation if isinstance(failure_interpretation, dict) else {}
    if not interpretation:
        return record

    reason_code = str(interpretation.get("reason_code", "") or "").strip()
    if reason_code:
        record["reason_code"] = reason_code

    reason_detail = str(interpretation.get("reason_detail", "") or "").strip()
    if reason_detail:
        record["reason_detail"] = reason_detail

    if "retryable" in interpretation:
        record["retryable"] = bool(interpretation.get("retryable"))

    evidence = interpretation.get("evidence")
    if isinstance(evidence, list):
        normalized_evidence = [str(item).strip() for item in evidence if str(item).strip()]
        if normalized_evidence:
            record["evidence"] = normalized_evidence

    risk_markers = {
        "waiting_user_input": "wait_user",
        "budget_exhausted": "split",
        "dependency_unmet": "resolve_dependency",
        "orphan_subtask_unbound": "decision_handoff",
    }
    if reason_code and not str(record.get("suggested_next_action", "") or "").strip():
        mapped = risk_markers.get(reason_code, "")
        if mapped:
            record["suggested_next_action"] = mapped

    record["failure_interpretation"] = interpretation
    return record


def build_duplicate_todo_binding_error(todo_context: Dict[str, Any]) -> Dict[str, Any]:
    ctx = todo_context if isinstance(todo_context, dict) else {}
    todo_id = str(ctx.get("todo_id", "") or "").strip()
    return {
        "success": False,
        "error": (
            f"Active todo already bound for this task: {todo_id or 'unknown'}. "
            "Use update_task to continue the existing todo, or pass force_new_cycle=true only when intentionally starting a new task cycle."
        ),
        "result": {
            "success": False,
            "error": (
                f"Active todo already bound for this task: {todo_id or 'unknown'}. "
                "Use update_task to continue the existing todo, or pass force_new_cycle=true only when intentionally starting a new task cycle."
            ),
            "active_todo_id": todo_id,
        },
    }


def build_create_task_arg_error(tool_args: Dict[str, Any], todo_context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    args = tool_args if isinstance(tool_args, dict) else {}
    missing_fields: List[str] = []
    for field in ["task_name", "context", "split_reason", "subtasks"]:
        value = args.get(field)
        if value is None:
            missing_fields.append(field)
            continue
        if isinstance(value, str) and not value.strip():
            missing_fields.append(field)

    subtasks = args.get("subtasks")
    subtasks_invalid = False
    if "subtasks" not in missing_fields:
        if not isinstance(subtasks, list) or not subtasks:
            subtasks_invalid = True

    if not missing_fields and not subtasks_invalid:
        return None

    ctx = todo_context if isinstance(todo_context, dict) else {}
    todo_id = str(ctx.get("todo_id", "") or "").strip()
    details: List[str] = []
    if missing_fields:
        details.append(f"Missing required field(s): {', '.join(missing_fields)}")
    if subtasks_invalid:
        details.append("Field 'subtasks' must be a non-empty array of structured subtask objects.")

    guidance = (
        "create_task creates a tracked todo and requires a complete task envelope with "
        "task_name, context, split_reason, and a non-empty subtasks array. "
        "Validate or assemble that envelope with plan_task before calling create_task."
    )
    if todo_id:
        guidance += f" Active todo already exists: {todo_id}. Use update_task to continue or extend the existing todo instead of calling create_task again."
    else:
        guidance += " Only call create_task when no active todo is currently bound."

    error = f"Invalid create_task arguments. {' '.join(details)} {guidance}".strip()
    return {
        "success": False,
        "error": error,
        "result": {
            "success": False,
            "error": error,
            "missing_fields": missing_fields,
            "subtasks_invalid": subtasks_invalid,
            "active_todo_id": todo_id,
        },
    }


def derive_subtask_status_from_failure(fallback_record: Dict[str, Any]) -> str:
    record = fallback_record if isinstance(fallback_record, dict) else {}
    failure_state = str(record.get("failure_state") or record.get("state") or "failed").strip() or "failed"
    reason_code = str(record.get("reason_code", "") or "").strip()
    retryable = bool(record.get("retryable", True))
    if failure_state == "awaiting_input" or reason_code == "waiting_user_input":
        return "awaiting_input"
    if failure_state == "timed_out":
        return "timed_out"
    if failure_state == "partial" or reason_code == "partial_progress":
        return "partial"
    if failure_state == "blocked" or reason_code == "dependency_unmet":
        return "blocked"
    if failure_state == "failed" and retryable:
        return "failed"
    return failure_state


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
    def _extract_retry_guidance(payload: Dict[str, Any], args: Dict[str, Any]) -> List[str]:
        candidates = []
        if isinstance(payload, dict):
            fallback = payload.get("fallback_record", {})
            if isinstance(fallback, dict):
                candidates = fallback.get("retry_guidance", [])
        if not candidates and isinstance(args, dict):
            candidates = args.get("retry_guidance", [])
        if isinstance(candidates, str):
            candidates = [candidates]
        if not isinstance(candidates, list):
            return []
        return [str(item).strip() for item in candidates if str(item).strip()]

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
                    "active_retry_guidance": [],
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
                    "active_retry_guidance": [],
                }
        elif tool == "create_task" and execution.get("success"):
            todo_id = str(payload.get("todo_id", "")).strip()
            if todo_id:
                next_context = {
                    "todo_id": todo_id,
                    "active_subtask_id": None,
                    "active_subtask_number": None,
                    "execution_phase": "planning",
                    "binding_required": True,
                    "binding_state": "bound",
                    "todo_bound_at": payload.get("todo_bound_at", ""),
                    "active_retry_guidance": [],
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
                retry_guidance = list(next_context.get("active_retry_guidance", []) or [])
                if status in {"completed", "abandoned", "pending"}:
                    retry_guidance = []
                phase = "executing" if status == "in-progress" else "planning"
                if status in {"blocked", "failed", "partial", "awaiting_input", "timed_out"}:
                    phase = "recovering"
                binding_state = "closed" if payload.get("all_completed") else "bound"
                next_context = {
                    "todo_id": todo_id,
                    "active_subtask_id": active_subtask_id,
                    "active_subtask_number": active_number,
                    "execution_phase": phase,
                    "binding_required": True,
                    "binding_state": binding_state,
                    "todo_bound_at": next_context.get("todo_bound_at", ""),
                    "active_retry_guidance": retry_guidance,
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
                    "active_retry_guidance": list(next_context.get("active_retry_guidance", []) or []),
                }
        elif tool == "record_task_fallback":
            todo_id = str(args.get("todo_id", payload.get("todo_id", ""))).strip()
            subtask_number = args.get("subtask_number")
            if todo_id and subtask_number is not None:
                retry_guidance = _extract_retry_guidance(payload=payload, args=args)
                next_context = {
                    "todo_id": todo_id,
                    "active_subtask_id": str(payload.get("subtask_id", "") or "").strip() or None,
                    "active_subtask_number": int(subtask_number),
                    "execution_phase": "recovering",
                    "binding_required": True,
                    "binding_state": "bound",
                    "todo_bound_at": next_context.get("todo_bound_at", ""),
                    "active_retry_guidance": retry_guidance,
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
                    "active_retry_guidance": list(next_context.get("active_retry_guidance", []) or []),
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
                    "active_retry_guidance": list(next_context.get("active_retry_guidance", []) or []),
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
            payload = tool_result.get("result", {}) if tool_result.get("success") else tool_result.get("result", {})
            executions.append(
                {
                    "tool": tool_name,
                    "args": tool_args,
                    "success": bool(tool_result.get("success")),
                    "error": str(tool_result.get("error", "") or ""),
                    "payload": payload if isinstance(payload, dict) else {},
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
        "failure_state": "failed",
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
        "can_resume_in_place": False,
        "needs_derived_recovery_subtask": False,
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
    def _signal_tags(*parts: str) -> List[str]:
        joined = " ".join(str(part or "") for part in parts).lower()
        tags: List[str] = []
        candidates = [
            ("http_504", ["http 504", "504"]),
            ("timeout", ["timeout", "timed out"]),
            ("bad_response_status_code", ["bad_response_status_code"]),
            ("network", ["network", "connection", "dns", "host", "unreachable"]),
            ("permission_denied", ["permission", "denied"]),
            ("model_failed", ["model request failed after retries", "model_failed"]),
        ]
        for tag, hints in candidates:
            if any(hint in joined for hint in hints) and tag not in tags:
                tags.append(tag)
        return tags

    if runtime_state == "awaiting_user_input":
        detail = preview(final_answer, 300)
        return {
            "state": "awaiting_input",
            "failure_state": "awaiting_input",
            "reason_code": "waiting_user_input",
            "reason_detail": detail,
            "impact_scope": "Requires user input before this subtask can continue",
            "retryable": False,
            "required_input": extract_missing_info_hints(final_answer),
            "suggested_next_action": "wait_user",
            "evidence": [detail],
            "owner": "user",
            "retry_count": 0,
            "retry_budget_remaining": 0,
            "failure_facts": {
                "runtime_state": runtime_state,
                "stop_reason": stop_reason,
                "final_answer_preview": detail,
                "tool_failures": [],
                "signal_tags": _signal_tags(detail),
                "retry_count": 0,
                "retry_budget_remaining": 0,
            },
        }
    if stop_reason == "max_steps_reached":
        detail = preview(final_answer, 300)
        return {
            "state": "timed_out",
            "failure_state": "timed_out",
            "reason_code": "budget_exhausted",
            "reason_detail": "Runtime reached max_steps without converging.",
            "impact_scope": "Recovery is needed before this subtask can be considered complete",
            "retryable": True,
            "required_input": [],
            "suggested_next_action": "split",
            "evidence": [detail],
            "owner": "main",
            "retry_count": 1,
            "retry_budget_remaining": 0,
            "failure_facts": {
                "runtime_state": runtime_state,
                "stop_reason": stop_reason,
                "final_answer_preview": detail,
                "tool_failures": [],
                "signal_tags": _signal_tags(detail, stop_reason),
                "retry_count": 1,
                "retry_budget_remaining": 0,
            },
        }
    if last_tool_failures:
        details = [
            f"{item.get('tool', 'unknown')}: {item.get('error', '')}".strip(": ")
            for item in last_tool_failures[:3]
        ]
        joined = " ; ".join(details).lower()
        reason_code = "tool_invocation_error"
        if any(keyword in joined for keyword in ["permission", "denied", "network", "timeout", "timed out", "connection", "dns", "unreachable", "host"]):
            reason_code = "execution_environment_error"
        return {
            "state": "failed",
            "failure_state": "failed",
            "reason_code": reason_code,
            "reason_detail": "; ".join(details),
            "impact_scope": "Current subtask could not complete because one or more tools failed",
            "retryable": True,
            "required_input": [],
            "evidence": details,
            "owner": "main",
            "retry_count": len(last_tool_failures),
            "retry_budget_remaining": max(0, 2 - len(last_tool_failures)),
            "failure_facts": {
                "runtime_state": runtime_state,
                "stop_reason": stop_reason,
                "final_answer_preview": preview(final_answer, 300),
                "tool_failures": details,
                "signal_tags": _signal_tags(joined, stop_reason),
                "retry_count": len(last_tool_failures),
                "retry_budget_remaining": max(0, 2 - len(last_tool_failures)),
            },
        }
    reason_code = "missing_context"
    if stop_reason == "model_failed":
        reason_code = "execution_environment_error"
    elif stop_reason in {"length", "content_filter"}:
        reason_code = "budget_exhausted" if stop_reason == "length" else "missing_context"
    detail = preview(final_answer, 300)
    retry_budget_remaining = 1
    signal_tags = _signal_tags(detail, stop_reason)
    record = {
        "state": "failed",
        "failure_state": "failed",
        "reason_code": reason_code,
        "reason_detail": detail,
        "impact_scope": "Current subtask did not finish successfully",
        "retryable": True,
        "required_input": [],
        "evidence": [detail],
        "owner": "main",
        "retry_count": 1,
        "retry_budget_remaining": retry_budget_remaining,
        "failure_facts": {
            "runtime_state": runtime_state,
            "stop_reason": stop_reason,
            "final_answer_preview": detail,
            "tool_failures": [],
            "signal_tags": signal_tags,
            "retry_count": 1,
            "retry_budget_remaining": retry_budget_remaining,
        },
    }
    if stop_reason == "length":
        record["suggested_next_action"] = "split"
    return record


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
    model_provider: Optional[ModelProvider] = None,
    enable_llm_recovery_planner: bool = False,
    build_recovery_planner_config: Optional[Callable[[], GenerationConfig]] = None,
    parse_json_dict: Optional[Callable[[str], Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    ctx = todo_context or {}
    todo_id = str(ctx.get("todo_id", "")).strip()
    subtask_number = ctx.get("active_subtask_number")
    subtask_id = str(ctx.get("active_subtask_id", "") or "").strip()
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
    recovery_context = {
        "todo_id": todo_id,
        "subtask_id": subtask_id,
        "subtask_number": int(subtask_number),
        "runtime_state": runtime_state,
        "stop_reason": stop_reason,
        "fallback_record": fallback_record,
        "last_tool_failures": last_tool_failures[:5] if isinstance(last_tool_failures, list) else [],
        "final_answer_preview": preview(final_answer, 300),
        "todo_context": {
            "binding_state": str(ctx.get("binding_state", "") or ""),
            "execution_phase": str(ctx.get("execution_phase", "") or ""),
        },
    }
    failure_interpretation = build_default_failure_interpretation(
        fallback_record=fallback_record,
        preview=preview,
    )
    initial_record_result = tool_registry.invoke(
        "record_task_fallback",
        {"todo_id": todo_id, "subtask_number": int(subtask_number), **fallback_record},
    )
    if not initial_record_result.get("success"):
        return {}
    recovery_context["subtask_id"] = subtask_id or str(initial_record_result.get("result", {}).get("subtask_id", "") or "").strip()

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

    planner_source = "rule"
    if (
        enable_llm_recovery_planner
        and model_provider is not None
        and build_recovery_planner_config is not None
        and parse_json_dict is not None
    ):
        guardrails = build_rule_recovery_guardrails(
            fallback_record=fallback_record,
            fallback_decision=decision_payload,
        )
        llm_candidate = generate_recovery_assessment_llm(
            model_provider=model_provider,
            enabled=True,
            build_config=build_recovery_planner_config,
            parse_json_dict=parse_json_dict,
            recovery_context=recovery_context,
            fallback_interpretation=failure_interpretation,
            fallback_decision=decision_payload,
            guardrails=guardrails,
        )
        normalized_assessment = normalize_llm_recovery_assessment(
            candidate=llm_candidate,
            fallback_interpretation=failure_interpretation,
            fallback_decision=decision_payload,
            guardrails=guardrails,
            current_subtask_id=recovery_context["subtask_id"] or subtask_id,
            current_subtask_number=int(subtask_number),
            preview=preview,
        )
        failure_interpretation = normalized_assessment.get("failure_interpretation", failure_interpretation)
        decision_payload = normalized_assessment.get("recovery_decision", decision_payload)
        planner_source = str(decision_payload.get("planner_source", "") or "rule")

    fallback_record = _merge_failure_interpretation_into_fallback_record(
        fallback_record=fallback_record,
        failure_interpretation=failure_interpretation,
    )
    if decision_payload.get("retry_guidance"):
        fallback_record["retry_guidance"] = decision_payload.get("retry_guidance", [])
    recovery_context["failure_interpretation"] = failure_interpretation
    recovery_context["fallback_record"] = fallback_record

    record_result = tool_registry.invoke(
        "record_task_fallback",
        {"todo_id": todo_id, "subtask_number": int(subtask_number), **fallback_record},
    )
    if not record_result.get("success"):
        return {}

    recovery_context["subtask_id"] = subtask_id or str(record_result.get("result", {}).get("subtask_id", "") or "").strip()

    derived_status = derive_subtask_status_from_failure(fallback_record)
    if tool_registry.has("update_task_status"):
        tool_registry.invoke(
            "update_task_status",
            {"todo_id": todo_id, "subtask_number": int(subtask_number), "status": derived_status},
        )

    recovery = {
        "todo_id": todo_id,
        "subtask_id": recovery_context["subtask_id"],
        "subtask_number": int(subtask_number),
        "fallback_record": fallback_record,
        "failure_interpretation": failure_interpretation,
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
            "planner_source": planner_source,
        },
    )

    if (
        decision_payload.get("needs_derived_recovery_subtask")
        and decision_payload.get("decision_level") == "auto"
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
