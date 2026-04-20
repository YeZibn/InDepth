import os
import re
import sqlite3
from typing import Any, Dict, List, Optional

from app.core.memory.recall_service import build_memory_vector_text


class SystemMemoryStore:
    """SQLite store for lightweight recall-oriented memory cards."""

    def __init__(
        self,
        db_file: str = "db/system_memory.db",
        vector_index: Any = None,
        embedding_provider: Any = None,
        embedding_model_id: str = "",
    ):
        self.db_file = db_file
        self.vector_index = vector_index
        self.embedding_provider = embedding_provider
        self.embedding_model_id = str(embedding_model_id or "").strip()
        os.makedirs(os.path.dirname(db_file) or ".", exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_file)

    def _init_db(self) -> None:
        conn = self._connect()
        try:
            cols = self._table_columns(conn, "memory_card")
            if cols and not self._is_lightweight_schema(cols):
                self._migrate_legacy_memory_card(conn)
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memory_card (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    recall_hint TEXT NOT NULL DEFAULT '',
                    content TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'active',
                    updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
                    expire_at TEXT
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_card_status ON memory_card(status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_card_expire_at ON memory_card(expire_at)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_card_title ON memory_card(title)")
            conn.commit()
        finally:
            conn.close()

    def _table_columns(self, conn: sqlite3.Connection, table: str) -> List[str]:
        try:
            return [row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]
        except Exception:
            return []

    def _is_lightweight_schema(self, cols: List[str]) -> bool:
        expected = {"id", "title", "recall_hint", "content", "status", "updated_at", "expire_at"}
        return set(cols) == expected

    def _migrate_legacy_memory_card(self, conn: sqlite3.Connection) -> None:
        rows = conn.execute(
            """
            SELECT id, title, recall_hint, payload_json, status, expire_at, updated_at
            FROM memory_card
            """
        ).fetchall()
        conn.execute("ALTER TABLE memory_card RENAME TO memory_card_legacy")
        conn.execute(
            """
            CREATE TABLE memory_card (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                recall_hint TEXT NOT NULL DEFAULT '',
                content TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'active',
                updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
                expire_at TEXT
            )
            """
        )
        for row in rows:
            normalized = self._normalize_legacy_row(row)
            conn.execute(
                """
                INSERT INTO memory_card (id, title, recall_hint, content, status, updated_at, expire_at)
                VALUES (:id, :title, :recall_hint, :content, :status, :updated_at, :expire_at)
                """,
                normalized,
            )
        conn.execute("DROP TABLE memory_card_legacy")

    def _normalize_legacy_row(self, row: Any) -> Dict[str, Any]:
        card_id = str(row[0] or "").strip()
        title = self._preview_text(str(row[1] or "").strip(), 120) or "任务经验摘要"
        payload_raw = row[3] if len(row) > 3 else ""
        payload = self._parse_payload(payload_raw)
        recall_hint = self._preview_text(
            str(row[2] or "").strip() or self._safe_text(payload.get("recall_hint"), default=""),
            220,
        )
        status = self._safe_status(row[4] if len(row) > 4 else payload.get("status"))
        expire_at = self._nullable_text(row[5] if len(row) > 5 else payload.get("expire_at"))
        updated_at = self._nullable_text(row[6] if len(row) > 6 else None) or self._now_text()
        content = self._build_content_from_payload(payload=payload, title=title, recall_hint=recall_hint)
        if not recall_hint:
            recall_hint = self._preview_text(content, 220)
        return {
            "id": card_id,
            "title": title,
            "recall_hint": recall_hint,
            "content": content,
            "status": status,
            "updated_at": updated_at,
            "expire_at": expire_at,
        }

    def upsert_card(self, card: Dict[str, Any]) -> Dict[str, Any]:
        normalized = self._normalize_card(card)
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO memory_card (
                    id, title, recall_hint, content, status, updated_at, expire_at
                ) VALUES (
                    :id, :title, :recall_hint, :content, :status, datetime('now','localtime'), :expire_at
                )
                ON CONFLICT(id) DO UPDATE SET
                    title = excluded.title,
                    recall_hint = excluded.recall_hint,
                    content = excluded.content,
                    status = excluded.status,
                    expire_at = excluded.expire_at,
                    updated_at = datetime('now','localtime')
                """,
                normalized,
            )
            conn.commit()
        finally:
            conn.close()
        self._sync_vector_index(normalized)
        return {"success": True, "id": normalized["id"]}

    def get_card(self, card_id: str, only_active: bool = False) -> Optional[Dict[str, Any]]:
        card_id_norm = (card_id or "").strip()
        if not card_id_norm:
            return None
        conn = self._connect()
        try:
            sql = """
                SELECT id, title, recall_hint, content, status, updated_at, expire_at
                FROM memory_card
                WHERE id = ?
            """
            args: List[Any] = [card_id_norm]
            if only_active:
                sql += " AND status = 'active' AND (expire_at IS NULL OR date(expire_at) >= date('now','localtime'))"
            row = conn.execute(sql, tuple(args)).fetchone()
        finally:
            conn.close()
        return self._row_to_card(row) if row else None

    def search_cards(
        self,
        stage: str = "",
        query: str = "",
        limit: int = 5,
        only_active: bool = True,
    ) -> List[Dict[str, Any]]:
        _ = stage
        clauses: List[str] = ["1=1"]
        args: List[Any] = []

        query_norm = (query or "").strip().lower()
        if query_norm:
            query_tokens = [t for t in query_norm.split() if t]
            for token in query_tokens:
                like = f"%{token}%"
                clauses.append("(lower(title) LIKE ? OR lower(recall_hint) LIKE ? OR lower(content) LIKE ?)")
                args.extend([like, like, like])

        if only_active:
            clauses.append("status = 'active'")
            clauses.append("(expire_at IS NULL OR date(expire_at) >= date('now','localtime'))")

        sql = f"""
            SELECT id, title, recall_hint, content, status, updated_at, expire_at
            FROM memory_card
            WHERE {' AND '.join(clauses)}
            ORDER BY updated_at DESC
            LIMIT ?
        """
        args.append(max(1, int(limit)))

        conn = self._connect()
        try:
            rows = conn.execute(sql, tuple(args)).fetchall()
        finally:
            conn.close()

        cards: List[Dict[str, Any]] = []
        for row in rows:
            card = self._row_to_card(row)
            if not card:
                continue
            card["retrieval_score"] = self._score_card(card, query_norm)
            cards.append(card)
        cards.sort(key=lambda x: x.get("retrieval_score", 0.0), reverse=True)
        return cards

    def list_due_review_cards(self, within_days: int = 7, limit: int = 50) -> List[Dict[str, Any]]:
        days = max(0, int(within_days))
        conn = self._connect()
        try:
            rows = conn.execute(
                """
                SELECT id, title, recall_hint, content, status, updated_at, expire_at
                FROM memory_card
                WHERE status = 'active'
                  AND expire_at IS NOT NULL
                  AND date(expire_at) <= date('now','localtime', ?)
                ORDER BY date(expire_at) ASC
                LIMIT ?
                """,
                (f"+{days} day", max(1, int(limit))),
            ).fetchall()
        finally:
            conn.close()
        return [x for x in (self._row_to_card(row) for row in rows) if x]

    def _normalize_card(self, card: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(card, dict):
            raise ValueError("card must be an object")
        card_id = self._require_text(card.get("id"), "id")
        raw_title = self._require_text(card.get("title"), "title")
        title = self._normalize_title(raw_title)
        recall_hint = self._safe_text(card.get("recall_hint"), default="")
        if not recall_hint:
            recall_hint = self._safe_text(card.get("summary"), default="")
        content = self._safe_text(card.get("content"), default="")
        if not content:
            content = self._build_content_from_payload(payload=card, title=title, recall_hint=recall_hint)
        if not recall_hint:
            trigger_hint = ""
            scenario = card.get("scenario", {}) if isinstance(card.get("scenario", {}), dict) else {}
            if isinstance(scenario, dict):
                trigger_hint = self._safe_text(scenario.get("trigger_hint"), default="")
            recall_hint = self._compose_recall_hint(card=card, title=title, trigger_hint=trigger_hint)
        lifecycle = card.get("lifecycle", {}) if isinstance(card.get("lifecycle", {}), dict) else {}
        status = self._safe_status(card.get("status") or lifecycle.get("status"))
        expire_at = self._nullable_text(card.get("expire_at") or lifecycle.get("expire_at"))
        return {
            "id": card_id,
            "title": title,
            "recall_hint": self._preview_text(recall_hint, 220),
            "content": self._preview_text(content, 2000),
            "status": status,
            "expire_at": expire_at,
        }

    def _row_to_card(self, row: Any) -> Optional[Dict[str, Any]]:
        if not row:
            return None
        card = {
            "id": str(row[0] or "").strip(),
            "title": str(row[1] or "").strip(),
            "recall_hint": str(row[2] or "").strip(),
            "content": str(row[3] or "").strip(),
            "status": str(row[4] or "").strip() or "active",
            "updated_at": str(row[5] or "").strip(),
            "expire_at": row[6],
        }
        card["lifecycle"] = {
            "status": card["status"],
            "expire_at": card["expire_at"],
        }
        return card

    def _score_card(self, card: Dict[str, Any], query: str) -> float:
        if not query:
            return 0.0
        title = str(card.get("title", "")).lower()
        recall_hint = str(card.get("recall_hint", "")).lower()
        content = str(card.get("content", "")).lower()
        score = 0.0
        for token in [t for t in query.split() if t]:
            if token in title:
                score += 0.6
            elif token in recall_hint:
                score += 0.3
            elif token in content:
                score += 0.1
        return round(min(score, 1.0), 4)

    def _build_content_from_payload(self, payload: Dict[str, Any], title: str, recall_hint: str) -> str:
        if not isinstance(payload, dict):
            return recall_hint or title
        pieces: List[str] = []
        direct_content = self._safe_text(payload.get("content"), default="")
        if direct_content:
            return self._preview_text(direct_content, 2000)
        payload_hint = self._safe_text(payload.get("recall_hint"), default="")
        if payload_hint and not recall_hint:
            recall_hint = payload_hint
        trigger_hint = ""
        scenario = payload.get("scenario", {}) if isinstance(payload.get("scenario", {}), dict) else {}
        if isinstance(scenario, dict):
            trigger_hint = self._safe_text(scenario.get("trigger_hint"), default="")
        solution = payload.get("solution", {}) if isinstance(payload.get("solution", {}), dict) else {}
        expected_outcome = self._safe_text(solution.get("expected_outcome"), default="")
        steps = solution.get("steps", []) if isinstance(solution.get("steps", []), list) else []
        first_step = ""
        for step in steps:
            text = self._safe_text(step, default="")
            if text:
                first_step = text
                break
        for item in [title, recall_hint, trigger_hint, first_step, expected_outcome]:
            text = self._safe_text(item, default="")
            if text and text not in pieces:
                pieces.append(text)
        joined = "；".join(pieces).strip()
        return self._preview_text(joined or title, 2000)

    def _compose_recall_hint(self, card: Dict[str, Any], title: str, trigger_hint: str) -> str:
        solution = card.get("solution", {}) if isinstance(card.get("solution", {}), dict) else {}
        steps = solution.get("steps", []) if isinstance(solution.get("steps", []), list) else []
        first_step = ""
        for step in steps:
            text = str(step).strip()
            if text:
                first_step = text
                break
        problem_pattern = card.get("problem_pattern", {}) if isinstance(card.get("problem_pattern", {}), dict) else {}
        constraints = card.get("constraints", {}) if isinstance(card.get("constraints", {}), dict) else {}
        anti_pattern = card.get("anti_pattern", {}) if isinstance(card.get("anti_pattern", {}), dict) else {}
        symptoms = problem_pattern.get("symptoms", []) if isinstance(problem_pattern.get("symptoms", []), list) else []
        applicable = constraints.get("applicable_if", []) if isinstance(constraints.get("applicable_if", []), list) else []
        not_applicable = anti_pattern.get("not_applicable_if", []) if isinstance(
            anti_pattern.get("not_applicable_if", []), list
        ) else []

        problem_text = str(symptoms[0]).strip() if symptoms else (trigger_hint or title)
        applicable_text = str(applicable[0]).strip() if applicable else "相似上下文且前置条件满足"
        action_text = first_step or "先做最小验证再执行主动作"
        risk_text = str(not_applicable[0]).strip() if not_applicable else "边界不清时先降级并补充验证"

        structured = (
            f"问题：{problem_text}；"
            f"适用：{applicable_text}；"
            f"动作：{action_text}；"
            f"风险：{risk_text}。"
        )
        return self._preview_text(structured, 220)

    def _parse_payload(self, payload_raw: Any) -> Dict[str, Any]:
        if not isinstance(payload_raw, str) or not payload_raw.strip():
            return {}
        import json

        try:
            parsed = json.loads(payload_raw)
        except Exception:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    def _normalize_title(self, title: str) -> str:
        text = self._safe_text(title, default="")
        if not text:
            return "经验复用策略"
        noise_patterns = [
            r"\btask[_\-]?[a-z0-9_\-]{4,}\b",
            r"\brun[_\-]?[a-z0-9_\-]{4,}\b",
            r"\b\d{8,14}\b",
            r"任务总结",
            r"任务结果",
            r"task outcome memory",
        ]
        for p in noise_patterns:
            text = re.sub(p, " ", text, flags=re.IGNORECASE)
        text = re.sub(r"[|｜]+", " ", text)
        text = re.sub(r"\s+", " ", text).strip(" ,;:，；：-")
        return self._preview_text(text or "经验复用策略", 120)

    def _safe_status(self, value: Any) -> str:
        text = self._safe_text(value, default="active").lower()
        if text not in {"active", "archived", "draft"}:
            return "active"
        return text

    def _require_text(self, value: Any, field: str) -> str:
        text = self._safe_text(value, default="")
        if not text:
            raise ValueError(f"{field} is required")
        return text

    def _safe_text(self, value: Any, default: str = "") -> str:
        if value is None:
            return default
        text = str(value).strip()
        return text if text else default

    def _nullable_text(self, value: Any) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def _preview_text(self, value: str, max_len: int = 200) -> str:
        text = (value or "").strip()
        if len(text) <= max_len:
            return text
        return text[:max_len].rstrip() + "..."

    def _now_text(self) -> str:
        conn = self._connect()
        try:
            row = conn.execute("SELECT datetime('now','localtime')").fetchone()
            return str(row[0] or "").strip() if row else ""
        finally:
            conn.close()

    def _sync_vector_index(self, card: Dict[str, Any]) -> None:
        if self.vector_index is None or self.embedding_provider is None:
            return
        title = str(card.get("title", "") or "").strip()
        recall_hint = str(card.get("recall_hint", "") or "").strip()
        memory_id = str(card.get("id", "") or "").strip()
        if not memory_id or not title or not recall_hint:
            return
        vector_text = build_memory_vector_text(title=title, recall_hint=recall_hint)
        try:
            embedding = self.embedding_provider.embed_text(vector_text)
            self.vector_index.upsert_memory_vector(
                memory_id=memory_id,
                vector_text=vector_text,
                embedding=embedding,
                model=self.embedding_model_id,
            )
        except Exception:
            return
