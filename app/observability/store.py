import json
import os
from typing import Dict, List, Optional

from .schema import EventRecord


def _find_project_root() -> str:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    while current_dir != os.path.dirname(current_dir):
        if os.path.isdir(os.path.join(current_dir, ".git")):
            return current_dir
        current_dir = os.path.dirname(current_dir)
    return os.getcwd()


def _default_events_path() -> str:
    root = _find_project_root()
    data_dir = os.path.join(root, "app", "observability", "data")
    os.makedirs(data_dir, exist_ok=True)
    return os.path.join(data_dir, "events.jsonl")


class EventStore:
    def __init__(self, events_path: Optional[str] = None) -> None:
        self.events_path = events_path or _default_events_path()
        os.makedirs(os.path.dirname(self.events_path), exist_ok=True)

    def append(self, event: EventRecord) -> None:
        with open(self.events_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")

    def query(
        self,
        task_id: Optional[str] = None,
        run_id: Optional[str] = None,
        event_type: Optional[str] = None,
    ) -> List[Dict]:
        if not os.path.exists(self.events_path):
            return []

        results: List[Dict] = []
        with open(self.events_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if task_id and row.get("task_id") != task_id:
                    continue
                if run_id and row.get("run_id") != run_id:
                    continue
                if event_type and row.get("event_type") != event_type:
                    continue
                results.append(row)
        return results

