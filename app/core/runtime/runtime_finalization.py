from typing import Any, Callable, Dict, List, Optional

from app.eval.schema import RunOutcome


def finalize_paused_run(
    task_id: str,
    run_id: str,
    runtime_state: str,
    stop_reason: str,
    final_answer: str,
    last_tool_failures: List[Dict[str, str]],
    auto_manage_todo_recovery: Callable[..., None],
    append_recovery_summary_for_user: Callable[[str], str],
    has_latest_todo_recovery: Callable[[], bool],
    preview: Callable[[str, int], str],
    emit_event: Callable[..., Dict[str, Any]],
) -> Dict[str, Any]:
    # clarification pause 属于“中间暂停”而不是最终失败，这里只做恢复兜底与观测，不进入 verifier。
    auto_manage_todo_recovery(
        task_id=task_id,
        run_id=run_id,
        runtime_state=runtime_state,
        stop_reason=stop_reason,
        final_answer=final_answer,
        last_tool_failures=last_tool_failures,
    )
    if has_latest_todo_recovery():
        final_answer = append_recovery_summary_for_user(final_answer)
    emit_event(
        task_id=task_id,
        run_id=run_id,
        actor="main",
        role="general",
        event_type="verification_skipped",
        payload={
            "reason": "awaiting_user_input",
            "stop_reason": stop_reason,
            "runtime_state": runtime_state,
        },
    )
    return {
        "final_answer": final_answer,
        "trace_message": f"[runtime] paused awaiting_user_input final={preview(final_answer)}",
    }


def finalize_completed_run(
    task_id: str,
    run_id: str,
    user_input: str,
    final_answer: str,
    stop_reason: str,
    runtime_state: str,
    task_status: str,
    last_tool_failures: List[Dict[str, str]],
    verification_handoff: Optional[Dict[str, Any]],
    handoff_source: str,
    build_verification_handoff: Callable[..., tuple[Dict[str, Any], str]],
    auto_manage_todo_recovery: Callable[..., None],
    append_recovery_summary_for_user: Callable[[str], str],
    has_latest_todo_recovery: Callable[[], bool],
    eval_orchestrator: Any,
    emit_event: Callable[..., Dict[str, Any]],
) -> Dict[str, Any]:
    # task_finished 必须在 verifier 前发出，这样 verifier 可以读取同一轮 run 的 postmortem 证据。
    emit_event(
        task_id=task_id,
        run_id=run_id,
        actor="main",
        role="general",
        event_type="task_finished",
        status=task_status,
        payload={
            "stop_reason": stop_reason,
            "runtime_state": runtime_state,
            "has_tool_failures": bool(last_tool_failures),
            "tool_failure_count": len(last_tool_failures),
        },
    )
    auto_manage_todo_recovery(
        task_id=task_id,
        run_id=run_id,
        runtime_state=runtime_state,
        stop_reason=stop_reason,
        final_answer=final_answer,
        last_tool_failures=last_tool_failures,
    )
    if has_latest_todo_recovery():
        verification_handoff = None
        handoff_source = "fallback_rule"
        final_answer = append_recovery_summary_for_user(final_answer)

    judgement_payload: Dict[str, Any] = {}
    task_finished_status = task_status
    try:
        if verification_handoff is None:
            verification_handoff, handoff_source = build_verification_handoff(
                user_input=user_input,
                final_answer=final_answer,
                stop_reason=stop_reason,
                runtime_status=task_status,
                tool_failures=last_tool_failures,
            )
        run_outcome = RunOutcome(
            task_id=task_id,
            run_id=run_id,
            user_input=user_input,
            final_answer=final_answer,
            stop_reason=stop_reason,
            tool_failures=last_tool_failures[:],
            runtime_status=task_status,
            verification_handoff=verification_handoff,
        )
        emit_event(
            task_id=task_id,
            run_id=run_id,
            actor="main",
            role="general",
            event_type="verification_started",
            payload={"stop_reason": stop_reason, "handoff_source": handoff_source},
        )
        judgement = eval_orchestrator.evaluate(run_outcome=run_outcome)
        judgement_payload = judgement.to_dict()
        emit_event(
            task_id=task_id,
            run_id=run_id,
            actor="main",
            role="general",
            event_type="verification_passed" if judgement.verified_success else "verification_failed",
            status="ok" if judgement.verified_success else "error",
            payload={
                "final_status": judgement.final_status,
                "failure_type": judgement.failure_type,
                "confidence": judgement.confidence,
            },
        )
        emit_event(
            task_id=task_id,
            run_id=run_id,
            actor="main",
            role="general",
            event_type="task_judged",
            status="ok" if judgement.verified_success else "error",
            payload={
                **judgement_payload,
                "verification_handoff_source": handoff_source,
                "verification_handoff": verification_handoff,
            },
        )
        task_finished_status = "ok" if judgement.verified_success else "error"
    except Exception as e:
        emit_event(
            task_id=task_id,
            run_id=run_id,
            actor="main",
            role="general",
            event_type="verification_failed",
            status="error",
            payload={"error": str(e)},
        )
    return {
        "final_answer": final_answer,
        "verification_handoff": verification_handoff,
        "handoff_source": handoff_source,
        "judgement_payload": judgement_payload,
        "task_finished_status": task_finished_status,
    }
