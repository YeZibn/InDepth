from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List


def _parse_ts(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def aggregate_task_metrics(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not events:
        return {
            "event_count": 0,
            "duration_seconds": 0,
            "success_count": 0,
            "failure_count": 0,
            "tool_called_count": 0,
            "tool_failed_count": 0,
            "subagent_started_count": 0,
            "subagent_failed_count": 0,
            "event_type_breakdown": {},
            "role_breakdown": {},
        }

    ordered = sorted(events, key=lambda x: x.get("timestamp", ""))
    start_dt = _parse_ts(ordered[0]["timestamp"])
    end_dt = _parse_ts(ordered[-1]["timestamp"])
    duration_seconds = int((end_dt - start_dt).total_seconds())

    success_count = 0
    failure_count = 0
    tool_called_count = 0
    tool_failed_count = 0
    subagent_started_count = 0
    subagent_failed_count = 0
    event_type_breakdown = defaultdict(int)
    role_breakdown = defaultdict(int)

    for e in ordered:
        et = e.get("event_type", "unknown")
        role = e.get("role", "unknown")
        status = e.get("status", "ok")

        event_type_breakdown[et] += 1
        role_breakdown[role] += 1

        if status == "ok":
            success_count += 1
        elif status == "error":
            failure_count += 1

        if et == "tool_called":
            tool_called_count += 1
        if et == "tool_failed":
            tool_failed_count += 1
        if et == "subagent_started":
            subagent_started_count += 1
        if et == "subagent_failed":
            subagent_failed_count += 1

    return {
        "event_count": len(ordered),
        "duration_seconds": duration_seconds,
        "success_count": success_count,
        "failure_count": failure_count,
        "tool_called_count": tool_called_count,
        "tool_failed_count": tool_failed_count,
        "subagent_started_count": subagent_started_count,
        "subagent_failed_count": subagent_failed_count,
        "event_type_breakdown": dict(event_type_breakdown),
        "role_breakdown": dict(role_breakdown),
    }

