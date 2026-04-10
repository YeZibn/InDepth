import json
import os
import sqlite3
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


def _default_system_memory_db_path() -> str:
    root = _find_project_root()
    db_dir = os.path.join(root, "db")
    os.makedirs(db_dir, exist_ok=True)
    return os.path.join(db_dir, "system_memory.db")


class SystemMemoryEventStore:
    """SQLite store for memory trigger/retrieval/decision events."""

    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path = db_path or _default_system_memory_db_path()
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _init_db(self) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memory_trigger_event (
                    event_id TEXT PRIMARY KEY,
                    event_time TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    role TEXT NOT NULL,
                    status TEXT NOT NULL,
                    stage TEXT,
                    context_id TEXT,
                    risk_level TEXT,
                    payload_json TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memory_retrieval_event (
                    event_id TEXT PRIMARY KEY,
                    event_time TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    role TEXT NOT NULL,
                    status TEXT NOT NULL,
                    trigger_event_id TEXT,
                    memory_id TEXT,
                    score REAL,
                    payload_json TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memory_decision_event (
                    event_id TEXT PRIMARY KEY,
                    event_time TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    role TEXT NOT NULL,
                    status TEXT NOT NULL,
                    trigger_event_id TEXT,
                    memory_id TEXT,
                    decision TEXT,
                    reason TEXT,
                    payload_json TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_mem_trigger_time ON memory_trigger_event(event_time)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_mem_retrieval_trigger_id ON memory_retrieval_event(trigger_event_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_mem_decision_trigger_id ON memory_decision_event(trigger_event_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_mem_decision_memory_id ON memory_decision_event(memory_id)"
            )
            conn.commit()
        finally:
            conn.close()

    def append(self, event: EventRecord) -> None:
        event_type = (event.event_type or "").strip()
        if event_type == "memory_triggered":
            self._insert_memory_triggered(event)
            return
        if event_type == "memory_retrieved":
            self._insert_memory_retrieved(event)
            return
        if event_type == "memory_decision_made":
            self._insert_memory_decision(event)
            return

    def _insert_memory_triggered(self, event: EventRecord) -> None:
        payload = event.payload or {}
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO memory_trigger_event (
                    event_id, event_time, task_id, run_id, actor, role, status,
                    stage, context_id, risk_level, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_id,
                    event.timestamp,
                    event.task_id,
                    event.run_id,
                    event.actor,
                    event.role,
                    event.status,
                    self._safe_text(payload.get("stage")),
                    self._safe_text(payload.get("context_id")),
                    self._safe_text(payload.get("risk_level")),
                    json.dumps(payload, ensure_ascii=False),
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def _insert_memory_retrieved(self, event: EventRecord) -> None:
        payload = event.payload or {}
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO memory_retrieval_event (
                    event_id, event_time, task_id, run_id, actor, role, status,
                    trigger_event_id, memory_id, score, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_id,
                    event.timestamp,
                    event.task_id,
                    event.run_id,
                    event.actor,
                    event.role,
                    event.status,
                    self._safe_text(payload.get("trigger_event_id")),
                    self._safe_text(payload.get("memory_id")),
                    self._safe_float(payload.get("score")),
                    json.dumps(payload, ensure_ascii=False),
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def _insert_memory_decision(self, event: EventRecord) -> None:
        payload = event.payload or {}
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO memory_decision_event (
                    event_id, event_time, task_id, run_id, actor, role, status,
                    trigger_event_id, memory_id, decision, reason, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_id,
                    event.timestamp,
                    event.task_id,
                    event.run_id,
                    event.actor,
                    event.role,
                    event.status,
                    self._safe_text(payload.get("trigger_event_id")),
                    self._safe_text(payload.get("memory_id")),
                    self._safe_text(payload.get("decision")),
                    self._safe_text(payload.get("reason")),
                    json.dumps(payload, ensure_ascii=False),
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def _safe_text(self, value: object) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def _safe_float(self, value: object) -> Optional[float]:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
