import os
import json
import sqlite3
from typing import Any, Dict, List, Optional


class SQLiteMemoryStore:
    def __init__(
        self,
        db_file: str = "db/runtime_memory.db",
        keep_recent: int = 8,
        summarize_threshold: int = 15,
    ):
        self.db_file = db_file
        self.keep_recent = keep_recent
        self.summarize_threshold = summarize_threshold
        os.makedirs(os.path.dirname(db_file) or ".", exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_file)

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    tool_call_id TEXT,
                    tool_calls_json TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS summaries (
                    conversation_id TEXT PRIMARY KEY,
                    summary TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            self._ensure_columns(conn)
            conn.commit()

    def _ensure_columns(self, conn: sqlite3.Connection) -> None:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(messages)").fetchall()}
        if "tool_call_id" not in cols:
            conn.execute("ALTER TABLE messages ADD COLUMN tool_call_id TEXT")
        if "tool_calls_json" not in cols:
            conn.execute("ALTER TABLE messages ADD COLUMN tool_calls_json TEXT")

    def append_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        tool_call_id: str = "",
        tool_calls: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        if not conversation_id.strip() or not role.strip():
            return
        tool_call_id_norm = (tool_call_id or "").strip() or None
        tool_calls_json = (
            json.dumps(tool_calls, ensure_ascii=False)
            if isinstance(tool_calls, list) and tool_calls
            else None
        )
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO messages (conversation_id, role, content, tool_call_id, tool_calls_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (conversation_id, role, content or "", tool_call_id_norm, tool_calls_json),
            )
            conn.commit()

    def get_recent_messages(self, conversation_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        with self._connect() as conn:
            row = conn.execute(
                "SELECT summary FROM summaries WHERE conversation_id = ?",
                (conversation_id,),
            ).fetchone()
            if row and row[0].strip():
                out.append({"role": "system", "content": f"历史摘要:\n{row[0]}"})

            rows = conn.execute(
                """
                SELECT role, content, tool_call_id, tool_calls_json FROM messages
                WHERE conversation_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (conversation_id, max(limit, 1)),
            ).fetchall()
        rows.reverse()
        out.extend(
            [
                self._normalize_message_row(
                    role=r[0],
                    content=r[1],
                    tool_call_id=r[2],
                    tool_calls_json=r[3],
                )
                for r in rows
            ]
        )
        return out

    def compact(self, conversation_id: str) -> None:
        with self._connect() as conn:
            total = conn.execute(
                "SELECT COUNT(*) FROM messages WHERE conversation_id = ?",
                (conversation_id,),
            ).fetchone()[0]
            if total <= self.summarize_threshold:
                return

            cut = total - self.keep_recent
            if cut <= 0:
                return

            old_rows = conn.execute(
                """
                SELECT id, role, content FROM messages
                WHERE conversation_id = ?
                ORDER BY id ASC
                LIMIT ?
                """,
                (conversation_id, cut),
            ).fetchall()
            if not old_rows:
                return

            summary = self._build_summary(old_rows)
            existing = conn.execute(
                "SELECT summary FROM summaries WHERE conversation_id = ?",
                (conversation_id,),
            ).fetchone()
            merged = summary if not existing else (existing[0] + "\n" + summary).strip()

            conn.execute(
                """
                INSERT INTO summaries (conversation_id, summary, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(conversation_id) DO UPDATE
                SET summary = excluded.summary, updated_at = CURRENT_TIMESTAMP
                """,
                (conversation_id, merged),
            )

            max_old_id = old_rows[-1][0]
            conn.execute(
                "DELETE FROM messages WHERE conversation_id = ? AND id <= ?",
                (conversation_id, max_old_id),
            )
            conn.commit()

    def _build_summary(self, rows: List[tuple]) -> str:
        lines = ["本轮历史关键点："]
        for _, role, content in rows[-12:]:
            snippet = (content or "").replace("\n", " ").strip()
            if len(snippet) > 80:
                snippet = snippet[:80] + "..."
            lines.append(f"- [{role}] {snippet}")
        return "\n".join(lines)

    def _normalize_message_row(
        self,
        role: str,
        content: str,
        tool_call_id: Optional[str] = None,
        tool_calls_json: Optional[str] = None,
    ) -> Dict[str, Any]:
        role_norm = (role or "").strip().lower()
        msg: Dict[str, Any] = {"role": role_norm, "content": content or ""}
        if role_norm == "assistant":
            if tool_calls_json:
                try:
                    parsed = json.loads(tool_calls_json)
                    if isinstance(parsed, list) and parsed:
                        msg["tool_calls"] = parsed
                except json.JSONDecodeError:
                    pass
            return msg
        if role_norm == "tool":
            call_id = (tool_call_id or "").strip()
            if call_id:
                msg["tool_call_id"] = call_id
                return msg
            return {"role": "assistant", "content": f"[history:tool] {content or ''}"}
        if role_norm in ("user", "system"):
            return msg
        return {"role": "assistant", "content": f"[history:{role_norm}] {content or ''}"}
