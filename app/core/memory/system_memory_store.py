import json
import os
import re
import sqlite3
from typing import Any, Dict, List, Optional


class SystemMemoryStore:
    """SQLite store for structured memory cards."""

    def __init__(self, db_file: str = "db/system_memory.db"):
        self.db_file = db_file
        os.makedirs(os.path.dirname(db_file) or ".", exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_file)

    def _init_db(self) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memory_card (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    recall_hint TEXT NOT NULL DEFAULT '',
                    memory_type TEXT NOT NULL,
                    domain TEXT NOT NULL,
                    tags_json TEXT NOT NULL,
                    scenario_stage TEXT NOT NULL,
                    trigger_hint TEXT NOT NULL,
                    problem_pattern_json TEXT NOT NULL,
                    solution_json TEXT NOT NULL,
                    constraints_json TEXT NOT NULL,
                    anti_pattern_json TEXT NOT NULL,
                    evidence_json TEXT NOT NULL,
                    impact_json TEXT NOT NULL,
                    owner_team TEXT NOT NULL,
                    owner_primary TEXT NOT NULL,
                    owner_reviewers_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    version TEXT NOT NULL,
                    effective_from TEXT,
                    expire_at TEXT,
                    last_reviewed_at TEXT,
                    confidence TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
                    updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_memory_card_stage_status ON memory_card(scenario_stage, status)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_memory_card_expire_at ON memory_card(expire_at)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_memory_card_title_domain ON memory_card(title, domain)"
            )
            self._ensure_memory_card_columns(conn)
            conn.commit()
        finally:
            conn.close()

    def _ensure_memory_card_columns(self, conn: sqlite3.Connection) -> None:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(memory_card)").fetchall()}
        if "recall_hint" not in cols:
            conn.execute("ALTER TABLE memory_card ADD COLUMN recall_hint TEXT NOT NULL DEFAULT ''")

    def upsert_card(self, card: Dict[str, Any]) -> Dict[str, Any]:
        normalized = self._normalize_card(card)
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO memory_card (
                    id, title, recall_hint, memory_type, domain, tags_json, scenario_stage, trigger_hint,
                    problem_pattern_json, solution_json, constraints_json, anti_pattern_json,
                    evidence_json, impact_json, owner_team, owner_primary, owner_reviewers_json,
                    status, version, effective_from, expire_at, last_reviewed_at, confidence,
                    payload_json, created_at, updated_at
                ) VALUES (
                    :id, :title, :recall_hint, :memory_type, :domain, :tags_json, :scenario_stage, :trigger_hint,
                    :problem_pattern_json, :solution_json, :constraints_json, :anti_pattern_json,
                    :evidence_json, :impact_json, :owner_team, :owner_primary, :owner_reviewers_json,
                    :status, :version, :effective_from, :expire_at, :last_reviewed_at, :confidence,
                    :payload_json, datetime('now','localtime'), datetime('now','localtime')
                )
                ON CONFLICT(id) DO UPDATE SET
                    title = excluded.title,
                    recall_hint = excluded.recall_hint,
                    memory_type = excluded.memory_type,
                    domain = excluded.domain,
                    tags_json = excluded.tags_json,
                    scenario_stage = excluded.scenario_stage,
                    trigger_hint = excluded.trigger_hint,
                    problem_pattern_json = excluded.problem_pattern_json,
                    solution_json = excluded.solution_json,
                    constraints_json = excluded.constraints_json,
                    anti_pattern_json = excluded.anti_pattern_json,
                    evidence_json = excluded.evidence_json,
                    impact_json = excluded.impact_json,
                    owner_team = excluded.owner_team,
                    owner_primary = excluded.owner_primary,
                    owner_reviewers_json = excluded.owner_reviewers_json,
                    status = excluded.status,
                    version = excluded.version,
                    effective_from = excluded.effective_from,
                    expire_at = excluded.expire_at,
                    last_reviewed_at = excluded.last_reviewed_at,
                    confidence = excluded.confidence,
                    payload_json = excluded.payload_json,
                    updated_at = datetime('now','localtime')
                """,
                normalized,
            )
            conn.commit()
        finally:
            conn.close()
        return {"success": True, "id": normalized["id"]}

    def get_card(
        self,
        card_id: str,
        only_active: bool = False,
    ) -> Optional[Dict[str, Any]]:
        card_id_norm = (card_id or "").strip()
        if not card_id_norm:
            return None
        conn = self._connect()
        try:
            sql = """
                SELECT id, payload_json, scenario_stage, title, status, expire_at, recall_hint
                FROM memory_card
                WHERE id = ?
            """
            args: List[Any] = [card_id_norm]
            if only_active:
                sql += " AND status = 'active' AND (expire_at IS NULL OR date(expire_at) >= date('now','localtime'))"
            row = conn.execute(sql, tuple(args)).fetchone()
        finally:
            conn.close()
        if not row:
            return None
        return self._row_to_card(row)

    def search_cards(
        self,
        stage: str = "",
        query: str = "",
        limit: int = 5,
        only_active: bool = True,
    ) -> List[Dict[str, Any]]:
        # stage is accepted for backward compatibility, but retrieval is title-only.
        _ = stage
        clauses: List[str] = ["1=1"]
        args: List[Any] = []

        query_norm = (query or "").strip().lower()
        if query_norm:
            query_tokens = [t for t in query_norm.split() if t]
            for token in query_tokens:
                like = f"%{token}%"
                clauses.append("(lower(title) LIKE ?)")
                args.append(like)

        if only_active:
            clauses.append("status = 'active'")
            clauses.append("(expire_at IS NULL OR date(expire_at) >= date('now','localtime'))")

        sql = f"""
            SELECT id, payload_json, scenario_stage, title, status, expire_at, recall_hint
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
                SELECT id, payload_json, scenario_stage, title, status, expire_at, recall_hint
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
        title = self._normalize_title(raw_title, card=card)
        memory_type = self._safe_text(card.get("memory_type"), default="experience")
        domain = self._safe_text(card.get("domain"), default="general")

        scenario = card.get("scenario", {}) if isinstance(card.get("scenario", {}), dict) else {}
        scenario_stage = self._safe_text(scenario.get("stage"), default="development")
        trigger_hint = self._safe_text(scenario.get("trigger_hint"), default="")

        owner = card.get("owner", {}) if isinstance(card.get("owner", {}), dict) else {}
        owner_team = self._safe_text(owner.get("team"), default="unknown")
        owner_primary = self._safe_text(owner.get("primary"), default="unknown")
        owner_reviewers = owner.get("reviewers", []) if isinstance(owner.get("reviewers", []), list) else []

        lifecycle = card.get("lifecycle", {}) if isinstance(card.get("lifecycle", {}), dict) else {}
        status = self._safe_text(lifecycle.get("status"), default="active")
        version = self._safe_text(lifecycle.get("version"), default="v1.0")
        effective_from = self._nullable_text(lifecycle.get("effective_from"))
        expire_at = self._nullable_text(lifecycle.get("expire_at"))
        last_reviewed_at = self._nullable_text(lifecycle.get("last_reviewed_at"))

        tags = card.get("tags", []) if isinstance(card.get("tags", []), list) else []
        confidence = self._safe_text(card.get("confidence"), default="C")
        recall_hint = self._safe_text(card.get("recall_hint"), default="")
        if not recall_hint:
            # Backward compatibility: allow legacy summary field as source.
            recall_hint = self._safe_text(card.get("summary"), default="")
        if not recall_hint:
            recall_hint = self._compose_recall_hint(card=card, title=title, trigger_hint=trigger_hint)
        card_payload = dict(card)
        card_payload["title"] = title
        card_payload["recall_hint"] = recall_hint
        if "summary" in card_payload and not card_payload.get("summary"):
            card_payload.pop("summary", None)

        return {
            "id": card_id,
            "title": title,
            "recall_hint": recall_hint,
            "memory_type": memory_type,
            "domain": domain,
            "tags_json": json.dumps(tags, ensure_ascii=False),
            "scenario_stage": scenario_stage,
            "trigger_hint": trigger_hint,
            "problem_pattern_json": json.dumps(card.get("problem_pattern", {}), ensure_ascii=False),
            "solution_json": json.dumps(card.get("solution", {}), ensure_ascii=False),
            "constraints_json": json.dumps(card.get("constraints", {}), ensure_ascii=False),
            "anti_pattern_json": json.dumps(card.get("anti_pattern", {}), ensure_ascii=False),
            "evidence_json": json.dumps(card.get("evidence", {}), ensure_ascii=False),
            "impact_json": json.dumps(card.get("impact", {}), ensure_ascii=False),
            "owner_team": owner_team,
            "owner_primary": owner_primary,
            "owner_reviewers_json": json.dumps(owner_reviewers, ensure_ascii=False),
            "status": status,
            "version": version,
            "effective_from": effective_from,
            "expire_at": expire_at,
            "last_reviewed_at": last_reviewed_at,
            "confidence": confidence,
            "payload_json": json.dumps(card_payload, ensure_ascii=False),
        }

    def _row_to_card(self, row: Any) -> Optional[Dict[str, Any]]:
        if not row:
            return None
        payload_raw = row[1]
        try:
            card = json.loads(payload_raw) if isinstance(payload_raw, str) else {}
        except json.JSONDecodeError:
            card = {}
        if not isinstance(card, dict):
            card = {}
        card.setdefault("id", row[0])
        card.setdefault("title", row[3])
        card.setdefault("recall_hint", row[6] if len(row) > 6 else "")
        card.setdefault("scenario", {})
        if isinstance(card["scenario"], dict):
            card["scenario"].setdefault("stage", row[2])
        card.setdefault("lifecycle", {})
        if isinstance(card["lifecycle"], dict):
            card["lifecycle"].setdefault("status", row[4])
            card["lifecycle"].setdefault("expire_at", row[5])
        return card

    def _score_card(self, card: Dict[str, Any], query: str) -> float:
        score = 0.0

        if query:
            text = str(card.get("title", "")).lower()
            for token in [t for t in query.split() if t]:
                if token in text:
                    score += 0.1
        return round(min(score, 1.0), 4)

    def _compose_recall_hint(self, card: Dict[str, Any], title: str, trigger_hint: str) -> str:
        solution = card.get("solution", {}) if isinstance(card.get("solution", {}), dict) else {}
        steps = solution.get("steps", []) if isinstance(solution.get("steps", []), list) else []
        first_step = ""
        for step in steps:
            text = str(step).strip()
            if text:
                first_step = text
                break
        pieces = [title, trigger_hint, first_step]
        summary = "；".join([p.strip() for p in pieces if p and str(p).strip()])
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
        return self._preview_text(structured, max_len=220)

    def _normalize_title(self, title: str, card: Dict[str, Any]) -> str:
        text = self._safe_text(title, default="")
        if not text:
            return "经验复用策略"

        # Remove pipeline noise tokens while preserving semantic nouns/verbs.
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

        if not text:
            problem_pattern = card.get("problem_pattern", {}) if isinstance(card.get("problem_pattern", {}), dict) else {}
            symptoms = problem_pattern.get("symptoms", []) if isinstance(problem_pattern.get("symptoms", []), list) else []
            if symptoms:
                text = str(symptoms[0]).strip()
        if not text:
            text = "经验复用策略"
        return self._preview_text(text, max_len=120)

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
