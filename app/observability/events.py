from typing import Any, Dict, Optional

from .schema import EVENT_TYPES, MEMORY_EVENT_TYPES, EventRecord
from .store import EventStore, SystemMemoryEventStore


def emit_event(
    task_id: str,
    run_id: str,
    actor: str,
    role: str,
    event_type: str,
    status: str = "ok",
    duration_ms: Optional[int] = None,
    payload: Optional[Dict[str, Any]] = None,
    store: Optional[EventStore] = None,
    system_memory_store: Optional[SystemMemoryEventStore] = None,
) -> Dict[str, Any]:
    normalized_payload = dict(payload or {})
    normalized_event_type = (event_type or "").strip()
    if normalized_event_type not in set(EVENT_TYPES):
        normalized_payload["_original_event_type"] = normalized_event_type
        normalized_payload["_observability_warning"] = "unknown_event_type_normalized"
        normalized_event_type = "unknown_event_type"

    event_store = store or EventStore()
    event = EventRecord.new(
        task_id=task_id,
        run_id=run_id,
        actor=actor,
        role=role,
        event_type=normalized_event_type,
        status=status,
        duration_ms=duration_ms,
        payload=normalized_payload,
    )
    event_store.append(event)

    if normalized_event_type in MEMORY_EVENT_TYPES:
        try:
            mem_store = system_memory_store or SystemMemoryEventStore()
            mem_store.append(event)
        except Exception:
            # SQLite 观测链路异常不影响业务主流程
            pass

    event_dict = event.to_dict()

    # 强制策略：任务结束事件写入后自动生成复盘报告（best-effort，不阻塞主流程）
    if normalized_event_type == "task_finished":
        try:
            from .postmortem import generate_postmortem

            result = generate_postmortem(
                task_id=task_id,
                run_id=run_id,
                store=event_store,
            )
            if result.get("success"):
                event_dict["postmortem_path"] = result.get("output_path")
        except Exception:
            # 观测链路异常不影响业务主流程
            pass

    return event_dict


def emit_memory_triggered(
    task_id: str,
    run_id: str,
    actor: str,
    role: str,
    stage: str,
    context_id: str = "",
    risk_level: str = "",
    status: str = "ok",
    store: Optional[EventStore] = None,
    system_memory_store: Optional[SystemMemoryEventStore] = None,
    payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    merged_payload = {
        "stage": stage,
        "context_id": context_id,
        "risk_level": risk_level,
        **(payload or {}),
    }
    return emit_event(
        task_id=task_id,
        run_id=run_id,
        actor=actor,
        role=role,
        event_type="memory_triggered",
        status=status,
        payload=merged_payload,
        store=store,
        system_memory_store=system_memory_store,
    )


def emit_memory_retrieved(
    task_id: str,
    run_id: str,
    actor: str,
    role: str,
    trigger_event_id: str,
    memory_id: str,
    score: Optional[float] = None,
    status: str = "ok",
    store: Optional[EventStore] = None,
    system_memory_store: Optional[SystemMemoryEventStore] = None,
    payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    merged_payload = {
        "trigger_event_id": trigger_event_id,
        "memory_id": memory_id,
        "score": score,
        **(payload or {}),
    }
    return emit_event(
        task_id=task_id,
        run_id=run_id,
        actor=actor,
        role=role,
        event_type="memory_retrieved",
        status=status,
        payload=merged_payload,
        store=store,
        system_memory_store=system_memory_store,
    )


def emit_memory_decision_made(
    task_id: str,
    run_id: str,
    actor: str,
    role: str,
    trigger_event_id: str,
    memory_id: str,
    decision: str,
    reason: str = "",
    status: str = "ok",
    store: Optional[EventStore] = None,
    system_memory_store: Optional[SystemMemoryEventStore] = None,
    payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    merged_payload = {
        "trigger_event_id": trigger_event_id,
        "memory_id": memory_id,
        "decision": decision,
        "reason": reason,
        **(payload or {}),
    }
    return emit_event(
        task_id=task_id,
        run_id=run_id,
        actor=actor,
        role=role,
        event_type="memory_decision_made",
        status=status,
        payload=merged_payload,
        store=store,
        system_memory_store=system_memory_store,
    )
