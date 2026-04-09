from datetime import datetime, timezone
from typing import Any, Dict, List


def _parse_ts(ts: Any) -> datetime:
    if not isinstance(ts, str) or not ts.strip():
        return datetime.fromtimestamp(0, tz=timezone.utc)
    try:
        parsed = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed
    except Exception:
        return datetime.fromtimestamp(0, tz=timezone.utc)


def build_trace(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    ordered = sorted(events, key=lambda x: _parse_ts(x.get("timestamp")))
    trace = []
    for idx, e in enumerate(ordered, 1):
        trace.append(
            {
                "step": idx,
                "timestamp": e.get("timestamp"),
                "event_type": e.get("event_type"),
                "actor": e.get("actor"),
                "role": e.get("role"),
                "status": e.get("status"),
                "payload": e.get("payload", {}),
            }
        )
    return trace
