from typing import Any, Callable, Dict, List

from app.config import RuntimeCompressionConfig
from app.core.memory.base import MemoryStore


def maybe_compact_mid_run(
    step: int,
    task_id: str,
    run_id: str,
    messages: List[Dict[str, Any]],
    consecutive_tool_calls: int,
    memory_store: MemoryStore | None,
    compression_config: RuntimeCompressionConfig,
    estimate_context_tokens: Callable[[List[Dict[str, Any]]], int],
    estimate_context_usage: Callable[[int], float],
    build_system_prompt: Callable[[], str],
    emit_event: Callable[..., Dict[str, Any]],
) -> List[Dict[str, Any]]:
    if not memory_store or not compression_config.enabled_mid_run:
        return messages
    if step <= 1:
        return messages
    compact_mid_run = getattr(memory_store, "compact_mid_run", None)
    if not callable(compact_mid_run):
        return messages

    trigger = ""
    mode = ""
    estimated_tokens = estimate_context_tokens(messages)
    usage = estimate_context_usage(estimated_tokens)
    if usage >= compression_config.strong_token_ratio:
        trigger = "token"
        mode = "strong"
    elif consecutive_tool_calls >= compression_config.tool_burst_threshold:
        trigger = "event"
        mode = "event"

    if not trigger:
        return messages

    emit_event(
        task_id=task_id,
        run_id=run_id,
        actor="main",
        role="general",
        event_type="context_compression_started",
        payload={
            "trigger": trigger,
            "mode": mode,
            "step": step - 1,
            "estimated_tokens": estimated_tokens,
            "context_usage_ratio": round(usage, 4),
        },
    )
    try:
        result = compact_mid_run(task_id, trigger=trigger, mode=mode)
    except Exception as e:
        emit_event(
            task_id=task_id,
            run_id=run_id,
            actor="main",
            role="general",
            event_type="context_compression_failed",
            status="error",
            payload={"error": str(e), "trigger": trigger, "mode": mode},
        )
        return messages

    if not isinstance(result, dict):
        result = {"success": True, "applied": False}
    if not bool(result.get("success", True)):
        event_type = "context_consistency_check_failed"
        if str(result.get("reason", "")).strip() != "consistency_check_failed":
            event_type = "context_compression_failed"
        emit_event(
            task_id=task_id,
            run_id=run_id,
            actor="main",
            role="general",
            event_type=event_type,
            status="error",
            payload={"result": result, "trigger": trigger, "mode": mode},
        )
        return messages
    emit_event(
        task_id=task_id,
        run_id=run_id,
        actor="main",
        role="general",
        event_type="context_compression_succeeded",
        payload={"trigger": trigger, "mode": mode, "result": result},
    )

    if not result.get("applied"):
        return messages
    history = memory_store.get_recent_messages(task_id, limit=20)
    return [{"role": "system", "content": build_system_prompt()}] + history


def finalize_memory_compaction(
    task_id: str,
    final_answer: str,
    final_answer_written: bool,
    memory_store: MemoryStore | None,
) -> None:
    if not memory_store:
        return
    if not final_answer_written:
        memory_store.append_message(task_id, "assistant", final_answer)
    compact_final = getattr(memory_store, "compact_final", None)
    if callable(compact_final):
        compact_final(task_id)
    else:
        memory_store.compact(task_id)
