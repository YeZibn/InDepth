from typing import Any, Dict, Optional

from .schema import EVENT_TYPES, EventRecord
from .store import EventStore


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
