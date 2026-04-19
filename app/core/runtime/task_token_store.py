import os
import sqlite3
from contextlib import closing
from typing import Any, Dict, List, Optional


class _ManagedSQLiteConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        try:
            return super().__exit__(exc_type, exc_val, exc_tb)
        finally:
            self.close()


class TaskTokenStore:
    def __init__(self, db_file: str = "db/task_token_ledger.db"):
        self.db_file = db_file
        os.makedirs(os.path.dirname(db_file) or ".", exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_file, factory=_ManagedSQLiteConnection)

    def _init_db(self) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS task_token_step (
                    task_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    step INTEGER NOT NULL,
                    model TEXT NOT NULL,
                    encoding TEXT NOT NULL,
                    token_counter_kind TEXT NOT NULL,
                    messages_tokens INTEGER NOT NULL,
                    tools_tokens INTEGER NOT NULL,
                    step_input_tokens INTEGER NOT NULL DEFAULT 0,
                    input_tokens INTEGER NOT NULL,
                    reserved_output_tokens INTEGER NOT NULL,
                    total_window_claim_tokens INTEGER NOT NULL,
                    context_usage_ratio REAL NOT NULL,
                    compression_trigger_window_tokens INTEGER NOT NULL,
                    model_context_window_tokens INTEGER NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
                    updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
                    PRIMARY KEY (task_id, run_id, step)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS task_token_summary (
                    task_id TEXT PRIMARY KEY,
                    total_step_input_tokens INTEGER NOT NULL DEFAULT 0,
                    total_input_tokens INTEGER NOT NULL DEFAULT 0,
                    total_reserved_output_tokens INTEGER NOT NULL DEFAULT 0,
                    total_window_claim_tokens INTEGER NOT NULL DEFAULT 0,
                    peak_step_input_tokens INTEGER NOT NULL DEFAULT 0,
                    peak_input_tokens INTEGER NOT NULL DEFAULT 0,
                    peak_total_window_claim_tokens INTEGER NOT NULL DEFAULT 0,
                    step_count INTEGER NOT NULL DEFAULT 0,
                    last_run_id TEXT NOT NULL DEFAULT '',
                    last_step INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
                )
                """
            )
            self._ensure_column(conn, "task_token_step", "step_input_tokens", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "task_token_summary", "total_step_input_tokens", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "task_token_summary", "peak_step_input_tokens", "INTEGER NOT NULL DEFAULT 0")
            conn.commit()

    def _ensure_column(self, conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        existing = {str(row[1] or "") for row in rows}
        if column in existing:
            return
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def record_step_metrics(
        self,
        *,
        task_id: str,
        run_id: str,
        step: int,
        metrics: Dict[str, Any],
    ) -> None:
        task_id_norm = str(task_id or "").strip()
        run_id_norm = str(run_id or "").strip()
        step_num = int(step or 0)
        if not task_id_norm or not run_id_norm or step_num <= 0:
            return

        payload = {
            "model": str(metrics.get("model", "") or "").strip(),
            "encoding": str(metrics.get("encoding", "") or "").strip(),
            "token_counter_kind": str(metrics.get("token_counter_kind", "") or "").strip(),
            "messages_tokens": int(metrics.get("messages_tokens", 0) or 0),
            "tools_tokens": int(metrics.get("tools_tokens", 0) or 0),
            "step_input_tokens": int(metrics.get("step_input_tokens", 0) or 0),
            "input_tokens": int(metrics.get("input_tokens", 0) or 0),
            "reserved_output_tokens": int(metrics.get("reserved_output_tokens", 0) or 0),
            "total_window_claim_tokens": int(metrics.get("total_window_claim_tokens", 0) or 0),
            "context_usage_ratio": float(metrics.get("context_usage_ratio", 0.0) or 0.0),
            "compression_trigger_window_tokens": int(metrics.get("compression_trigger_window_tokens", 0) or 0),
            "model_context_window_tokens": int(metrics.get("model_context_window_tokens", 0) or 0),
        }
        with closing(self._connect()) as conn:
            existing = conn.execute(
                """
                SELECT
                    step_input_tokens,
                    input_tokens,
                    reserved_output_tokens,
                    total_window_claim_tokens
                FROM task_token_step
                WHERE task_id = ? AND run_id = ? AND step = ?
                """,
                (task_id_norm, run_id_norm, step_num),
            ).fetchone()

            old_step_input = int(existing[0]) if existing else 0
            old_input = int(existing[1]) if existing else 0
            old_reserved = int(existing[2]) if existing else 0
            old_total = int(existing[3]) if existing else 0
            delta_step_input = payload["step_input_tokens"] - old_step_input
            delta_input = payload["input_tokens"] - old_input
            delta_reserved = payload["reserved_output_tokens"] - old_reserved
            delta_total = payload["total_window_claim_tokens"] - old_total

            conn.execute(
                """
                INSERT INTO task_token_step (
                    task_id,
                    run_id,
                    step,
                    model,
                    encoding,
                    token_counter_kind,
                    messages_tokens,
                    tools_tokens,
                    step_input_tokens,
                    input_tokens,
                    reserved_output_tokens,
                    total_window_claim_tokens,
                    context_usage_ratio,
                    compression_trigger_window_tokens,
                    model_context_window_tokens,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now','localtime'), datetime('now','localtime'))
                ON CONFLICT(task_id, run_id, step) DO UPDATE SET
                    model = excluded.model,
                    encoding = excluded.encoding,
                    token_counter_kind = excluded.token_counter_kind,
                    messages_tokens = excluded.messages_tokens,
                    tools_tokens = excluded.tools_tokens,
                    step_input_tokens = excluded.step_input_tokens,
                    input_tokens = excluded.input_tokens,
                    reserved_output_tokens = excluded.reserved_output_tokens,
                    total_window_claim_tokens = excluded.total_window_claim_tokens,
                    context_usage_ratio = excluded.context_usage_ratio,
                    compression_trigger_window_tokens = excluded.compression_trigger_window_tokens,
                    model_context_window_tokens = excluded.model_context_window_tokens,
                    updated_at = datetime('now','localtime')
                """,
                (
                    task_id_norm,
                    run_id_norm,
                    step_num,
                    payload["model"],
                    payload["encoding"],
                    payload["token_counter_kind"],
                    payload["messages_tokens"],
                    payload["tools_tokens"],
                    payload["step_input_tokens"],
                    payload["input_tokens"],
                    payload["reserved_output_tokens"],
                    payload["total_window_claim_tokens"],
                    payload["context_usage_ratio"],
                    payload["compression_trigger_window_tokens"],
                    payload["model_context_window_tokens"],
                ),
            )

            conn.execute(
                """
                INSERT INTO task_token_summary (
                    task_id,
                    total_step_input_tokens,
                    total_input_tokens,
                    total_reserved_output_tokens,
                    total_window_claim_tokens,
                    peak_step_input_tokens,
                    peak_input_tokens,
                    peak_total_window_claim_tokens,
                    step_count,
                    last_run_id,
                    last_step,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now','localtime'))
                ON CONFLICT(task_id) DO UPDATE SET
                    total_step_input_tokens = task_token_summary.total_step_input_tokens + excluded.total_step_input_tokens,
                    total_input_tokens = task_token_summary.total_input_tokens + excluded.total_input_tokens,
                    total_reserved_output_tokens = task_token_summary.total_reserved_output_tokens + excluded.total_reserved_output_tokens,
                    total_window_claim_tokens = task_token_summary.total_window_claim_tokens + excluded.total_window_claim_tokens,
                    peak_step_input_tokens = MAX(task_token_summary.peak_step_input_tokens, ?),
                    peak_input_tokens = MAX(task_token_summary.peak_input_tokens, ?),
                    peak_total_window_claim_tokens = MAX(task_token_summary.peak_total_window_claim_tokens, ?),
                    step_count = task_token_summary.step_count + ?,
                    last_run_id = excluded.last_run_id,
                    last_step = excluded.last_step,
                    updated_at = datetime('now','localtime')
                """,
                (
                    task_id_norm,
                    delta_step_input,
                    delta_input,
                    delta_reserved,
                    delta_total,
                    payload["step_input_tokens"],
                    payload["input_tokens"],
                    payload["total_window_claim_tokens"],
                    1 if not existing else 0,
                    run_id_norm,
                    step_num,
                    payload["step_input_tokens"],
                    payload["input_tokens"],
                    payload["total_window_claim_tokens"],
                    1 if not existing else 0,
                ),
            )
            conn.commit()

    def get_task_summary(self, task_id: str) -> Dict[str, Any]:
        task_id_norm = str(task_id or "").strip()
        if not task_id_norm:
            return {}
        with closing(self._connect()) as conn:
            row = conn.execute(
                """
                SELECT
                    task_id,
                    total_step_input_tokens,
                    total_input_tokens,
                    total_reserved_output_tokens,
                    total_window_claim_tokens,
                    peak_step_input_tokens,
                    peak_input_tokens,
                    peak_total_window_claim_tokens,
                    step_count,
                    last_run_id,
                    last_step,
                    updated_at
                FROM task_token_summary
                WHERE task_id = ?
                """,
                (task_id_norm,),
            ).fetchone()
        if not row:
            return {}
        return {
            "task_id": str(row[0] or ""),
            "total_step_input_tokens": int(row[1] or 0),
            "total_input_tokens": int(row[2] or 0),
            "total_reserved_output_tokens": int(row[3] or 0),
            "total_window_claim_tokens": int(row[4] or 0),
            "peak_step_input_tokens": int(row[5] or 0),
            "peak_input_tokens": int(row[6] or 0),
            "peak_total_window_claim_tokens": int(row[7] or 0),
            "step_count": int(row[8] or 0),
            "last_run_id": str(row[9] or ""),
            "last_step": int(row[10] or 0),
            "updated_at": str(row[11] or ""),
        }

    def list_task_steps(self, task_id: str) -> List[Dict[str, Any]]:
        task_id_norm = str(task_id or "").strip()
        if not task_id_norm:
            return []
        with closing(self._connect()) as conn:
            rows = conn.execute(
                """
                SELECT
                    task_id,
                    run_id,
                    step,
                    model,
                    encoding,
                    token_counter_kind,
                    messages_tokens,
                    tools_tokens,
                    step_input_tokens,
                    input_tokens,
                    reserved_output_tokens,
                    total_window_claim_tokens,
                    context_usage_ratio,
                    compression_trigger_window_tokens,
                    model_context_window_tokens,
                    created_at,
                    updated_at
                FROM task_token_step
                WHERE task_id = ?
                ORDER BY created_at ASC, run_id ASC, step ASC
                """,
                (task_id_norm,),
            ).fetchall()
        out: List[Dict[str, Any]] = []
        for row in rows:
            out.append(
                {
                    "task_id": str(row[0] or ""),
                    "run_id": str(row[1] or ""),
                    "step": int(row[2] or 0),
                    "model": str(row[3] or ""),
                    "encoding": str(row[4] or ""),
                    "token_counter_kind": str(row[5] or ""),
                    "messages_tokens": int(row[6] or 0),
                    "tools_tokens": int(row[7] or 0),
                    "step_input_tokens": int(row[8] or 0),
                    "input_tokens": int(row[9] or 0),
                    "reserved_output_tokens": int(row[10] or 0),
                    "total_window_claim_tokens": int(row[11] or 0),
                    "context_usage_ratio": float(row[12] or 0.0),
                    "compression_trigger_window_tokens": int(row[13] or 0),
                    "model_context_window_tokens": int(row[14] or 0),
                    "created_at": str(row[15] or ""),
                    "updated_at": str(row[16] or ""),
                }
            )
        return out

    def get_step_input_token_map(self, task_id: str) -> Dict[tuple[str, str], int]:
        mapping: Dict[tuple[str, str], int] = {}
        for row in self.list_task_steps(task_id):
            run_id = str(row.get("run_id", "") or "").strip()
            step = str(row.get("step", "") or "").strip()
            if not run_id or not step:
                continue
            mapping[(run_id, step)] = int(row.get("step_input_tokens", 0) or 0)
        return mapping
