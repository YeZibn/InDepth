from typing import Any, Callable, Dict, List


def resolve_stop_finish_reason(
    content: str,
    user_input: str,
    task_id: str,
    run_id: str,
    step: int,
    last_tool_failures: List[Dict[str, str]],
    judge_clarification_request: Callable[..., Dict[str, Any]],
    extract_missing_info_hints: Callable[[str], List[str]],
    preview: Callable[[str, int], str],
    emit_event: Callable[..., Dict[str, Any]],
) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "final_answer": "",
        "task_status": "ok",
        "stop_reason": "stop",
        "runtime_state": "completed",
        "should_build_handoff": True,
    }
    if content:
        result["final_answer"] = content
        clarification_result = judge_clarification_request(
            content=content,
            user_input=user_input,
            task_id=task_id,
            run_id=run_id,
            step=step,
        )
        if clarification_result.get("is_clarification_request", False):
            result["stop_reason"] = "awaiting_user_input"
            result["runtime_state"] = "awaiting_user_input"
            result["should_build_handoff"] = False
            emit_event(
                task_id=task_id,
                run_id=run_id,
                actor="main",
                role="general",
                event_type="clarification_requested",
                payload={
                    "question_preview": preview(content, 300),
                    "missing_info_hints": extract_missing_info_hints(content),
                    "judge_source": clarification_result.get("source", "heuristic"),
                    "judge_confidence": clarification_result.get("confidence", 0.5),
                    "judge_reason": clarification_result.get("reason", ""),
                    "step": step,
                },
            )
        return result

    if last_tool_failures:
        details = "; ".join(
            [
                f"{item.get('tool', 'unknown')}: {item.get('error', '')}"
                for item in last_tool_failures[:3]
            ]
        )
        result["final_answer"] = f"任务未完成：工具调用失败（{details}）。"
        result["task_status"] = "error"
        result["stop_reason"] = "tool_failed_before_stop"
        result["runtime_state"] = "failed"
        return result

    result["final_answer"] = "模型未返回有效内容，任务可能未完成。"
    result["task_status"] = "error"
    result["stop_reason"] = "empty_stop_content"
    result["runtime_state"] = "failed"
    return result


def resolve_non_stop_finish_reason(
    finish_reason: str,
    content: str,
    task_id: str,
    run_id: str,
    emit_event: Callable[..., Dict[str, Any]],
) -> Dict[str, Any]:
    if finish_reason == "length":
        emit_event(
            task_id=task_id,
            run_id=run_id,
            actor="main",
            role="general",
            event_type="model_stopped_length",
            status="error",
        )
        return {
            "final_answer": content or "模型达到输出长度上限，已停止。",
            "task_status": "error",
            "stop_reason": "length",
            "runtime_state": "failed",
            "should_build_handoff": True,
            "trace_label": "length",
        }

    if finish_reason == "content_filter":
        emit_event(
            task_id=task_id,
            run_id=run_id,
            actor="main",
            role="general",
            event_type="model_stopped_content_filter",
            status="error",
        )
        return {
            "final_answer": "输出被内容策略拦截，已停止。",
            "task_status": "error",
            "stop_reason": "content_filter",
            "runtime_state": "failed",
            "should_build_handoff": True,
            "trace_label": "content_filter",
        }

    if content:
        return {
            "final_answer": content,
            "task_status": "ok",
            "stop_reason": "fallback_content",
            "runtime_state": "completed",
            "should_build_handoff": True,
            "trace_label": "fallback",
        }

    return {}


def resolve_max_steps_outcome() -> Dict[str, Any]:
    return {
        "final_answer": "未在预算步数内收敛，建议缩小问题范围后重试。",
        "task_status": "error",
        "stop_reason": "max_steps_reached",
        "runtime_state": "failed",
        "should_build_handoff": True,
    }
