"""SQLite-backed runtime memory store for runtime-v2."""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import closing

from rtv2.memory.models import (
    ReflexionAction,
    ReflexionTrigger,
    RuntimeMemoryEntry,
    RuntimeMemoryEntryType,
    RuntimeMemoryQuery,
    RuntimeMemoryRole,
)
from rtv2.memory.store import RuntimeMemoryStore
from rtv2.task_graph.models import ResultRef


class _ManagedSQLiteConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        try:
            return super().__exit__(exc_type, exc_val, exc_tb)
        finally:
            self.close()


class SQLiteRuntimeMemoryStore(RuntimeMemoryStore):
    """Persist runtime memory entries in a local SQLite database."""

    def __init__(self, db_file: str = "runtime-v2/db/runtime_memory.db") -> None:
        self.db_file = db_file
        os.makedirs(os.path.dirname(self.db_file) or ".", exist_ok=True)
        self._init_db()

    def append_entry(self, entry: RuntimeMemoryEntry) -> RuntimeMemoryEntry:
        with closing(self._connect()) as conn:
            cursor = conn.execute(
                """
                INSERT INTO runtime_memory_entries (
                    entry_id,
                    task_id,
                    run_id,
                    step_id,
                    node_id,
                    entry_type,
                    role,
                    content,
                    tool_name,
                    tool_call_id,
                    related_result_refs_json,
                    reflexion_trigger,
                    reflexion_reason,
                    next_attempt_hint,
                    reflexion_action,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry.entry_id,
                    entry.task_id,
                    entry.run_id,
                    entry.step_id,
                    entry.node_id,
                    entry.entry_type.value,
                    entry.role.value,
                    entry.content,
                    entry.tool_name,
                    entry.tool_call_id,
                    self._serialize_result_refs(entry.related_result_refs),
                    entry.reflexion_trigger.value if entry.reflexion_trigger is not None else "",
                    entry.reflexion_reason,
                    entry.next_attempt_hint,
                    entry.reflexion_action.value if entry.reflexion_action is not None else "",
                    entry.created_at,
                ),
            )
            conn.commit()
            stored_seq = int(cursor.lastrowid or 0)
        return RuntimeMemoryEntry(
            entry_id=entry.entry_id,
            task_id=entry.task_id,
            run_id=entry.run_id,
            step_id=entry.step_id,
            node_id=entry.node_id,
            entry_type=entry.entry_type,
            role=entry.role,
            content=entry.content,
            tool_name=entry.tool_name,
            tool_call_id=entry.tool_call_id,
            related_result_refs=list(entry.related_result_refs),
            reflexion_trigger=entry.reflexion_trigger,
            reflexion_reason=entry.reflexion_reason,
            next_attempt_hint=entry.next_attempt_hint,
            reflexion_action=entry.reflexion_action,
            created_at=entry.created_at,
            seq=stored_seq,
        )

    def list_entries_for_run(self, *, task_id: str, run_id: str) -> list[RuntimeMemoryEntry]:
        return self.list_entries(RuntimeMemoryQuery(task_id=task_id, run_id=run_id))

    def list_entries_for_task(self, *, task_id: str) -> list[RuntimeMemoryEntry]:
        return self.list_entries(RuntimeMemoryQuery(task_id=task_id))

    def list_entries(self, query: RuntimeMemoryQuery) -> list[RuntimeMemoryEntry]:
        sql = """
            SELECT
                seq,
                entry_id,
                task_id,
                run_id,
                step_id,
                node_id,
                entry_type,
                role,
                content,
                tool_name,
                tool_call_id,
                related_result_refs_json,
                reflexion_trigger,
                reflexion_reason,
                next_attempt_hint,
                reflexion_action,
                created_at
            FROM runtime_memory_entries
        """
        where_parts: list[str] = []
        params: list[object] = []
        self._append_filters(where_parts, params, query)
        if where_parts:
            sql += " WHERE " + " AND ".join(where_parts)
        sql += " ORDER BY seq ASC"
        if query.limit is not None:
            sql += " LIMIT ?"
            params.append(query.limit)

        with closing(self._connect()) as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._row_to_entry(row) for row in rows]

    def get_latest_entries(self, query: RuntimeMemoryQuery) -> list[RuntimeMemoryEntry]:
        sql = """
            SELECT
                seq,
                entry_id,
                task_id,
                run_id,
                step_id,
                node_id,
                entry_type,
                role,
                content,
                tool_name,
                tool_call_id,
                related_result_refs_json,
                reflexion_trigger,
                reflexion_reason,
                next_attempt_hint,
                reflexion_action,
                created_at
            FROM runtime_memory_entries
        """
        where_parts: list[str] = []
        params: list[object] = []
        self._append_filters(where_parts, params, query)
        if where_parts:
            sql += " WHERE " + " AND ".join(where_parts)
        sql += " ORDER BY seq DESC"
        if query.limit is not None:
            sql += " LIMIT ?"
            params.append(query.limit)

        with closing(self._connect()) as conn:
            rows = conn.execute(sql, params).fetchall()
        rows.reverse()
        return [self._row_to_entry(row) for row in rows]

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_file, factory=_ManagedSQLiteConnection)

    def _init_db(self) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS runtime_memory_entries (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    entry_id TEXT NOT NULL UNIQUE,
                    task_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    step_id TEXT NOT NULL,
                    node_id TEXT NOT NULL,
                    entry_type TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    tool_name TEXT NOT NULL DEFAULT '',
                    tool_call_id TEXT NOT NULL DEFAULT '',
                    related_result_refs_json TEXT NOT NULL DEFAULT '[]',
                    reflexion_trigger TEXT NOT NULL DEFAULT '',
                    reflexion_reason TEXT NOT NULL DEFAULT '',
                    next_attempt_hint TEXT NOT NULL DEFAULT '',
                    reflexion_action TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_runtime_memory_entries_task_run ON runtime_memory_entries(task_id, run_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_runtime_memory_entries_run_step ON runtime_memory_entries(run_id, step_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_runtime_memory_entries_run_node ON runtime_memory_entries(run_id, node_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_runtime_memory_entries_entry_type ON runtime_memory_entries(entry_type)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_runtime_memory_entries_tool_name ON runtime_memory_entries(tool_name)"
            )
            conn.commit()

    @staticmethod
    def _append_filters(where_parts: list[str], params: list[object], query: RuntimeMemoryQuery) -> None:
        if query.task_id:
            where_parts.append("task_id = ?")
            params.append(query.task_id)
        if query.run_id:
            where_parts.append("run_id = ?")
            params.append(query.run_id)
        if query.step_id:
            where_parts.append("step_id = ?")
            params.append(query.step_id)
        if query.node_id:
            where_parts.append("node_id = ?")
            params.append(query.node_id)
        if query.entry_type is not None:
            where_parts.append("entry_type = ?")
            params.append(query.entry_type.value)
        if query.tool_name:
            where_parts.append("tool_name = ?")
            params.append(query.tool_name)

    @staticmethod
    def _serialize_result_refs(result_refs: list[ResultRef]) -> str:
        payload = [
            {
                "ref_id": ref.ref_id,
                "ref_type": ref.ref_type,
                "title": ref.title,
                "content": ref.content,
            }
            for ref in result_refs
        ]
        return json.dumps(payload, ensure_ascii=False)

    @staticmethod
    def _deserialize_result_refs(raw_json: str) -> list[ResultRef]:
        try:
            payload = json.loads(raw_json or "[]")
        except json.JSONDecodeError:
            return []
        if not isinstance(payload, list):
            return []
        result_refs: list[ResultRef] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            ref_id = str(item.get("ref_id", "") or "").strip()
            ref_type = str(item.get("ref_type", "") or "").strip()
            if not ref_id or not ref_type:
                continue
            result_refs.append(
                ResultRef(
                    ref_id=ref_id,
                    ref_type=ref_type,
                    title=str(item.get("title", "") or ""),
                    content=str(item.get("content", "") or ""),
                )
            )
        return result_refs

    @classmethod
    def _row_to_entry(cls, row: tuple[object, ...]) -> RuntimeMemoryEntry:
        reflexion_trigger_raw = str(row[12] or "").strip()
        return RuntimeMemoryEntry(
            seq=int(row[0]),
            entry_id=str(row[1]),
            task_id=str(row[2]),
            run_id=str(row[3]),
            step_id=str(row[4]),
            node_id=str(row[5]),
            entry_type=RuntimeMemoryEntryType(str(row[6])),
            role=RuntimeMemoryRole(str(row[7])),
            content=str(row[8]),
            tool_name=str(row[9] or ""),
            tool_call_id=str(row[10] or ""),
            related_result_refs=cls._deserialize_result_refs(str(row[11] or "[]")),
            reflexion_trigger=ReflexionTrigger(reflexion_trigger_raw) if reflexion_trigger_raw else None,
            reflexion_reason=str(row[13] or ""),
            next_attempt_hint=str(row[14] or ""),
            reflexion_action=ReflexionAction(str(row[15])) if str(row[15] or "").strip() else None,
            created_at=str(row[16]),
        )
