from typing import Any, Dict, List


def build_trace(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    ordered = sorted(events, key=lambda x: x.get("timestamp", ""))
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

