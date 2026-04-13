import json
import os
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
            conn.commit()
        finally:
            conn.close()

    def upsert_card(self, card: Dict[str, Any]) -> Dict[str, Any]:
        normalized = self._normalize_card(card)
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO memory_card (
                    id, title, memory_type, domain, tags_json, scenario_stage, trigger_hint,
                    problem_pattern_json, solution_json, constraints_json, anti_pattern_json,
                    evidence_json, impact_json, owner_team, owner_primary, owner_reviewers_json,
                    status, version, effective_from, expire_at, last_reviewed_at, confidence,
                    payload_json, created_at, updated_at
                ) VALUES (
                    :id, :title, :memory_type, :domain, :tags_json, :scenario_stage, :trigger_hint,
                    :problem_pattern_json, :solution_json, :constraints_json, :anti_pattern_json,
                    :evidence_json, :impact_json, :owner_team, :owner_primary, :owner_reviewers_json,
                    :status, :version, :effective_from, :expire_at, :last_reviewed_at, :confidence,
                    :payload_json, datetime('now','localtime'), datetime('now','localtime')
                )
                ON CONFLICT(id) DO UPDATE SET
                    title = excluded.title,
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

    def get_card(self, card_id: str) -> Optional[Dict[str, Any]]:
        card_id_norm = (card_id or "").strip()
        if not card_id_norm:
            return None
        conn = self._connect()
        try:
            row = conn.execute(
                """
                SELECT id, payload_json, scenario_stage, title, status, expire_at
                FROM memory_card
                WHERE id = ?
                """,
                (card_id_norm,),
            ).fetchone()
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
        clauses: List[str] = ["1=1"]
        args: List[Any] = []

        stage_norm = (stage or "").strip()
        if stage_norm:
            clauses.append("scenario_stage = ?")
            args.append(stage_norm)

        query_norm = (query or "").strip().lower()
        if query_norm:
            query_tokens = [t for t in query_norm.split() if t]
            for token in query_tokens:
                like = f"%{token}%"
                clauses.append(
                    "(lower(title) LIKE ? OR lower(domain) LIKE ? OR lower(trigger_hint) LIKE ? OR lower(tags_json) LIKE ?)"
                )
                args.extend([like, like, like, like])

        if only_active:
            clauses.append("status = 'active'")
            clauses.append("(expire_at IS NULL OR date(expire_at) >= date('now','localtime'))")

        sql = f"""
            SELECT id, payload_json, scenario_stage, title, status, expire_at
            FROM memory_card
            WHERE {' AND '.join(clauses)}
            ORDER BY
                CASE WHEN scenario_stage = ? THEN 0 ELSE 1 END,
                updated_at DESC
            LIMIT ?
        """
        args.extend([stage_norm, max(1, int(limit))])

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
            card["retrieval_score"] = self._score_card(card, stage_norm, query_norm)
            cards.append(card)
        cards.sort(key=lambda x: x.get("retrieval_score", 0.0), reverse=True)
        return cards

    def list_due_review_cards(self, within_days: int = 7, limit: int = 50) -> List[Dict[str, Any]]:
        days = max(0, int(within_days))
        conn = self._connect()
        try:
            rows = conn.execute(
                """
                SELECT id, payload_json, scenario_stage, title, status, expire_at
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
        title = self._require_text(card.get("title"), "title")
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

        return {
            "id": card_id,
            "title": title,
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
            "payload_json": json.dumps(card, ensure_ascii=False),
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
        card.setdefault("scenario", {})
        if isinstance(card["scenario"], dict):
            card["scenario"].setdefault("stage", row[2])
        card.setdefault("lifecycle", {})
        if isinstance(card["lifecycle"], dict):
            card["lifecycle"].setdefault("status", row[4])
            card["lifecycle"].setdefault("expire_at", row[5])
        return card

    def _score_card(self, card: Dict[str, Any], stage: str, query: str) -> float:
        score = 0.0
        scenario = card.get("scenario", {}) if isinstance(card.get("scenario", {}), dict) else {}
        if stage and scenario.get("stage") == stage:
            score += 0.6

        if query:
            text = " ".join(
                [
                    str(card.get("title", "")),
                    str(card.get("domain", "")),
                    str(scenario.get("trigger_hint", "")),
                    " ".join([str(t) for t in card.get("tags", [])])
                    if isinstance(card.get("tags", []), list)
                    else "",
                ]
            ).lower()
            for token in [t for t in query.split() if t]:
                if token in text:
                    score += 0.1
        return round(min(score, 1.0), 4)

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
