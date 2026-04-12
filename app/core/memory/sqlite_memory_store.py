import os
import json
import sqlite3
from typing import Any, Dict, List, Optional

from app.core.memory.context_compressor import ContextCompressor


class SQLiteMemoryStore:
    def __init__(
        self,
        db_file: str = "db/runtime_memory.db",
        keep_recent: int = 8,
        summarize_threshold: int = 15,
        consistency_guard: bool = True,
    ):
        self.db_file = db_file
        self.keep_recent = keep_recent
        self.summarize_threshold = summarize_threshold
        self.consistency_guard = bool(consistency_guard)
        self.compressor = ContextCompressor()
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
                    schema_version TEXT,
                    summary_json TEXT,
                    last_anchor_msg_id INTEGER,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            self._ensure_columns(conn)
            self._ensure_summary_columns(conn)
            conn.commit()

    def _ensure_columns(self, conn: sqlite3.Connection) -> None:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(messages)").fetchall()}
        if "tool_call_id" not in cols:
            conn.execute("ALTER TABLE messages ADD COLUMN tool_call_id TEXT")
        if "tool_calls_json" not in cols:
            conn.execute("ALTER TABLE messages ADD COLUMN tool_calls_json TEXT")

    def _ensure_summary_columns(self, conn: sqlite3.Connection) -> None:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(summaries)").fetchall()}
        if "schema_version" not in cols:
            conn.execute("ALTER TABLE summaries ADD COLUMN schema_version TEXT")
        if "summary_json" not in cols:
            conn.execute("ALTER TABLE summaries ADD COLUMN summary_json TEXT")
        if "last_anchor_msg_id" not in cols:
            conn.execute("ALTER TABLE summaries ADD COLUMN last_anchor_msg_id INTEGER")

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
                "SELECT summary, summary_json FROM summaries WHERE conversation_id = ?",
                (conversation_id,),
            ).fetchone()
            if row:
                summary_text = str(row[0] or "").strip()
                summary_json = self.compressor.load_summary_json(row[1] if len(row) > 1 else None)
                if summary_json:
                    out.append({"role": "system", "content": self.compressor.render_summary_prompt(summary_json)})
                elif summary_text:
                    out.append({"role": "system", "content": f"历史摘要:\n{summary_text}"})

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
        self.compact_final(conversation_id)

    def compact_mid_run(
        self,
        conversation_id: str,
        trigger: str = "round",
        mode: str = "light",
    ) -> Dict[str, Any]:
        return self._compact_impl(
            conversation_id=conversation_id,
            mode=mode,
            trigger=trigger,
            force=False,
            min_total=max(self.keep_recent + 2, 10),
        )

    def compact_final(self, conversation_id: str) -> Dict[str, Any]:
        return self._compact_impl(
            conversation_id=conversation_id,
            mode="finalize",
            trigger="finalize",
            force=False,
            min_total=self.summarize_threshold + 1,
        )

    def _compact_impl(
        self,
        conversation_id: str,
        mode: str,
        trigger: str,
        force: bool,
        min_total: int,
    ) -> Dict[str, Any]:
        with self._connect() as conn:
            total = conn.execute(
                "SELECT COUNT(*) FROM messages WHERE conversation_id = ?",
                (conversation_id,),
            ).fetchone()[0]
            if not force and total < max(min_total, 1):
                return {"success": True, "applied": False, "reason": "below_threshold", "total": total}

            cut = total - self.keep_recent
            if cut <= 0:
                return {"success": True, "applied": False, "reason": "nothing_to_cut", "total": total}

            old_rows = conn.execute(
                """
                SELECT id, role, content, tool_call_id FROM messages
                WHERE conversation_id = ?
                ORDER BY id ASC
                LIMIT ?
                """,
                (conversation_id, cut),
            ).fetchall()
            if not old_rows:
                return {"success": True, "applied": False, "reason": "empty_rows", "total": total}

            existing = conn.execute(
                "SELECT summary, summary_json FROM summaries WHERE conversation_id = ?",
                (conversation_id,),
            ).fetchone()
            existing_text = str(existing[0] or "").strip() if existing else ""
            existing_json = self.compressor.load_summary_json(existing[1] if existing and len(existing) > 1 else None)
            if not existing_json and existing_text:
                # Legacy summary fallback.
                existing_json = {
                    "version": "v0_legacy",
                    "task_state": {"goal": "", "progress": existing_text[:300], "next_step": "", "completion": 0.0},
                    "decisions": [],
                    "constraints": [],
                    "artifacts": [],
                    "open_questions": [],
                    "anchors": [],
                }

            old_messages = self._rows_to_compaction_messages(old_rows)
            merged_json = self.compressor.merge_summary(
                previous=existing_json,
                messages=old_messages,
                mode=mode,
                trigger=trigger,
                before_messages=total,
                after_messages=self.keep_recent,
                dropped_messages=len(old_rows),
            )
            if self.consistency_guard and not self.compressor.validate_consistency(existing_json, merged_json):
                return {"success": False, "applied": False, "reason": "consistency_check_failed", "total": total}

            merged_text = self.compressor.summary_to_text(merged_json)
            anchor_id = old_rows[-1][0]

            conn.execute(
                """
                INSERT INTO summaries (
                    conversation_id, summary, schema_version, summary_json, last_anchor_msg_id, updated_at
                )
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(conversation_id) DO UPDATE
                SET
                    summary = excluded.summary,
                    schema_version = excluded.schema_version,
                    summary_json = excluded.summary_json,
                    last_anchor_msg_id = excluded.last_anchor_msg_id,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    conversation_id,
                    merged_text,
                    str(merged_json.get("version", "v1")),
                    json.dumps(merged_json, ensure_ascii=False),
                    anchor_id,
                ),
            )

            max_old_id = anchor_id
            conn.execute(
                "DELETE FROM messages WHERE conversation_id = ? AND id <= ?",
                (conversation_id, max_old_id),
            )
            conn.commit()
            immutable_constraints = [
                c for c in (merged_json.get("constraints") or [])
                if isinstance(c, dict) and bool(c.get("immutable"))
            ]
            return {
                "success": True,
                "applied": True,
                "trigger": trigger,
                "mode": mode,
                "before_messages": total,
                "after_messages": self.keep_recent,
                "dropped_messages": len(old_rows),
                "immutable_constraints_count": len(immutable_constraints),
                "immutable_constraints_preview": [
                    str(c.get("rule", "")).strip()[:120] for c in immutable_constraints[-3:]
                ],
                "immutable_hits_count": int(
                    ((merged_json.get("compression_meta") or {}).get("immutable_hits_count") or 0)
                ),
            }

    def _build_summary(self, rows: List[tuple]) -> str:
        lines = ["本轮历史关键点："]
        for row in rows[-12:]:
            _, role, content = row[0], row[1], row[2]
            snippet = (content or "").replace("\n", " ").strip()
            if len(snippet) > 80:
                snippet = snippet[:80] + "..."
            lines.append(f"- [{role}] {snippet}")
        return "\n".join(lines)

    def _rows_to_compaction_messages(self, rows: List[tuple]) -> List[Dict[str, Any]]:
        messages: List[Dict[str, Any]] = []
        for idx, row in enumerate(rows, 1):
            msg_id = row[0]
            role = row[1]
            content = row[2]
            tool_call_id = row[3] if len(row) > 3 else ""
            messages.append(
                {
                    "id": msg_id,
                    "turn": idx,
                    "role": str(role or "").strip().lower(),
                    "content": content or "",
                    "tool_call_id": tool_call_id or "",
                }
            )
        return messages

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
