from typing import Any, Dict, Optional

from .schema import EventRecord
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
    event_store = store or EventStore()
    event = EventRecord.new(
        task_id=task_id,
        run_id=run_id,
        actor=actor,
        role=role,
        event_type=event_type,
        status=status,
        duration_ms=duration_ms,
        payload=payload or {},
    )
    event_store.append(event)

    event_dict = event.to_dict()

    # 强制策略：任务结束事件写入后自动生成复盘报告（best-effort，不阻塞主流程）
    if event_type == "task_finished":
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
