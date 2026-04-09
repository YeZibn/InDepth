import os
import sqlite3
from typing import Dict, List


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
        self._migrate_legacy_roles()

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
            conn.commit()

    def append_message(self, conversation_id: str, role: str, content: str) -> None:
        if not conversation_id.strip() or not role.strip():
            return
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO messages (conversation_id, role, content) VALUES (?, ?, ?)",
                (conversation_id, role, content or ""),
            )
            conn.commit()

    def get_recent_messages(self, conversation_id: str, limit: int = 20) -> List[Dict[str, str]]:
        out: List[Dict[str, str]] = []
        with self._connect() as conn:
            row = conn.execute(
                "SELECT summary FROM summaries WHERE conversation_id = ?",
                (conversation_id,),
            ).fetchone()
            if row and row[0].strip():
                out.append({"role": "system", "content": f"历史摘要:\n{row[0]}"})

            rows = conn.execute(
                """
                SELECT role, content FROM messages
                WHERE conversation_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (conversation_id, max(limit, 1)),
            ).fetchall()
        rows.reverse()
        out.extend([self._normalize_message_row(role=r[0], content=r[1]) for r in rows])
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

    def _normalize_message_row(self, role: str, content: str) -> Dict[str, str]:
        role_norm = (role or "").strip().lower()
        if role_norm in ("user", "assistant", "system"):
            return {"role": role_norm, "content": content or ""}
        # Legacy compatibility: convert tool/other roles to assistant text blocks.
        return {"role": "assistant", "content": f"[history:{role_norm}] {content or ''}"}

    def _migrate_legacy_roles(self) -> None:
        """Best-effort migration to avoid invalid chat payloads with role=tool."""
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE messages
                SET role = 'assistant',
                    content = '[history:tool] ' || content
                WHERE role = 'tool'
                """
            )
            conn.commit()
