from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional
import uuid


def local_now_iso() -> str:
    return datetime.now().astimezone().isoformat()


@dataclass
class EventRecord:
    event_id: str
    task_id: str
    run_id: str
    timestamp: str
    actor: str
    role: str
    event_type: str
    status: str
    duration_ms: Optional[int] = None
    payload: Dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def new(
        task_id: str,
        run_id: str,
        actor: str,
        role: str,
        event_type: str,
        status: str = "ok",
        duration_ms: Optional[int] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> "EventRecord":
        return EventRecord(
            event_id=str(uuid.uuid4()),
            task_id=task_id,
            run_id=run_id,
            timestamp=local_now_iso(),
            actor=actor,
            role=role,
            event_type=event_type,
            status=status,
            duration_ms=duration_ms,
            payload=payload or {},
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


EVENT_TYPES = [
    "phase_started",
    "phase_completed",
    "task_started",
    "task_finished",
    "task_judged",
    "task_updated",
    "run_resumed",
    "user_clarification_received",
    "unknown_event_type",
    "verification_started",
    "verification_passed",
    "verification_failed",
    "verification_skipped",
    "tool_called",
    "tool_succeeded",
    "tool_failed",
    "subagent_created",
    "subagent_started",
    "subagent_finished",
    "subagent_failed",
    "status_updated",
    "subtask_updated",
    "subtask_reopened",
    "followup_subtasks_appended",
    "todo_binding_missing_warning",
    "search_guard_initialized",
    "search_round_started",
    "search_round_finished",
    "search_stopped",
    "search_budget_auto_overridden",
    "model_request_started",
    "model_failed",
    "model_reasoning",
    "model_stopped_length",
    "model_stopped_content_filter",
    "clarification_requested",
    "clarification_judge_started",
    "clarification_judge_completed",
    "clarification_judge_fallback",
    "memory_triggered",
    "memory_retrieved",
    "memory_decision_made",
    "user_preference_recall_succeeded",
    "user_preference_recall_failed",
    "user_preference_extract_started",
    "user_preference_extract_succeeded",
    "user_preference_extract_failed",
    "user_preference_capture_succeeded",
    "user_preference_capture_failed",
    "context_compression_started",
    "context_compression_succeeded",
    "context_compression_failed",
    "context_consistency_check_failed",
]

MEMORY_EVENT_TYPES = {
    "memory_triggered",
    "memory_retrieved",
    "memory_decision_made",
}
