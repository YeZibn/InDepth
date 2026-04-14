import os
import json
import re
import sqlite3
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from app.core.memory.context_compressor import ContextCompressor


@dataclass
class _MessageRow:
    id: int
    role: str
    content: str
    tool_call_id: str
    tool_calls_json: Optional[str]


@dataclass
class _ToolChainUnit:
    start_idx: int
    end_idx: int
    tool_names: List[str]
    is_stateful: bool


class SQLiteMemoryStore:
    def __init__(
        self,
        db_file: str = "db/runtime_memory.db",
        keep_recent: int = 8,
        summarize_threshold: int = 15,
        consistency_guard: bool = True,
        context_window_tokens: int = 16000,
        target_keep_ratio_light: float = 0.55,
        target_keep_ratio_strong: float = 0.35,
        target_keep_ratio_finalize: float = 0.50,
        min_keep_messages: int = 6,
        keep_recent_event_tool_pairs: int = 1,
        event_stateful_tools: Optional[List[str]] = None,
    ):
        self.db_file = db_file
        self.keep_recent = keep_recent
        self.summarize_threshold = summarize_threshold
        self.consistency_guard = bool(consistency_guard)
        self.context_window_tokens = max(int(context_window_tokens), 64)
        self.target_keep_ratio_light = max(0.0, min(float(target_keep_ratio_light), 1.0))
        self.target_keep_ratio_strong = max(0.0, min(float(target_keep_ratio_strong), 1.0))
        self.target_keep_ratio_finalize = max(0.0, min(float(target_keep_ratio_finalize), 1.0))
        self.min_keep_messages = max(int(min_keep_messages), 1)
        self.keep_recent_event_tool_pairs = max(int(keep_recent_event_tool_pairs), 0)
        default_stateful_tools = [
            "create_task",
            "get_next_task",
            "update_task_status",
            "init_search_guard",
        ]
        self.event_stateful_tools = {
            str(x).strip().lower()
            for x in (event_stateful_tools or default_stateful_tools)
            if str(x).strip()
        }
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
                    created_at TIMESTAMP DEFAULT (datetime('now','localtime'))
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
                    updated_at TIMESTAMP DEFAULT (datetime('now','localtime'))
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

            rows_raw = conn.execute(
                """
                SELECT role, content, tool_call_id, tool_calls_json FROM messages
                WHERE conversation_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (conversation_id, max(limit, 1)),
            ).fetchall()
        rows_raw.reverse()
        rows = self._filter_orphan_tool_rows(
            [
                _MessageRow(
                    id=0,
                    role=str(r[0] or ""),
                    content=r[1] or "",
                    tool_call_id=str(r[2] or ""),
                    tool_calls_json=(r[3] if len(r) > 3 else None),
                )
                for r in rows_raw
            ]
        )
        out.extend(
            [
                self._normalize_message_row(
                    role=r.role,
                    content=r.content,
                    tool_call_id=r.tool_call_id,
                    tool_calls_json=r.tool_calls_json,
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
        trigger: str = "token",
        mode: str = "light",
        token_budget: Optional[int] = None,
    ) -> Dict[str, Any]:
        if str(trigger or "").strip() == "event":
            event_result = self._compact_event_tool_chain(conversation_id=conversation_id, mode=mode)
            if bool(event_result.get("applied")):
                return event_result
        return self._compact_impl(
            conversation_id=conversation_id,
            mode=mode,
            trigger=trigger,
            force=False,
            min_total=max(self.keep_recent + 2, 10),
            token_budget=token_budget,
        )

    def compact_final(
        self,
        conversation_id: str,
        token_budget: Optional[int] = None,
    ) -> Dict[str, Any]:
        return self._compact_impl(
            conversation_id=conversation_id,
            mode="finalize",
            trigger="finalize",
            force=False,
            min_total=self.summarize_threshold + 1,
            token_budget=token_budget,
        )

    def _compact_impl(
        self,
        conversation_id: str,
        mode: str,
        trigger: str,
        force: bool,
        min_total: int,
        token_budget: Optional[int],
    ) -> Dict[str, Any]:
        with self._connect() as conn:
            all_rows = self._load_conversation_rows(conn, conversation_id=conversation_id)
            total = len(all_rows)
            if not force and total < max(min_total, 1):
                return {"success": True, "applied": False, "reason": "below_threshold", "total": total}

            target_keep_tokens = self._resolve_target_keep_tokens(mode=mode, token_budget=token_budget)
            trim_strategy = "token_budget"
            cut_idx, cut_adjustment_reason = self._compute_token_budget_cut_index(
                rows=all_rows,
                target_keep_tokens=target_keep_tokens,
                min_keep_messages=self.min_keep_messages,
            )
            if target_keep_tokens <= 0:
                # Fallback for invalid token budget config.
                trim_strategy = "turn_fallback"
                cut_idx = self._compute_turn_based_cut_index(all_rows, keep_recent_turns=self.keep_recent)
                cut_adjustment_reason = "budget_unavailable_fallback"
            if cut_idx <= 0:
                return {"success": True, "applied": False, "reason": "nothing_to_cut", "total": total}

            old_rows = all_rows[:cut_idx]
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
                after_messages=total - len(old_rows),
                dropped_messages=len(old_rows),
            )
            if self.consistency_guard and not self.compressor.validate_consistency(existing_json, merged_json):
                return {"success": False, "applied": False, "reason": "consistency_check_failed", "total": total}

            merged_text = self.compressor.summary_to_text(merged_json)
            anchor_id = old_rows[-1].id

            conn.execute(
                """
                INSERT INTO summaries (
                    conversation_id, summary, schema_version, summary_json, last_anchor_msg_id, updated_at
                )
                VALUES (?, ?, ?, ?, ?, datetime('now','localtime'))
                ON CONFLICT(conversation_id) DO UPDATE
                SET
                    summary = excluded.summary,
                    schema_version = excluded.schema_version,
                    summary_json = excluded.summary_json,
                    last_anchor_msg_id = excluded.last_anchor_msg_id,
                    updated_at = datetime('now','localtime')
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
            kept_rows = all_rows[cut_idx:]
            actual_kept_tokens = self._estimate_rows_tokens(kept_rows)
            return {
                "success": True,
                "applied": True,
                "trigger": trigger,
                "mode": mode,
                "before_messages": total,
                "after_messages": total - len(old_rows),
                "dropped_messages": len(old_rows),
                "immutable_constraints_count": len(immutable_constraints),
                "immutable_constraints_preview": [
                    str(c.get("rule", "")).strip()[:120] for c in immutable_constraints[-3:]
                ],
                "immutable_hits_count": int(
                    ((merged_json.get("compression_meta") or {}).get("immutable_hits_count") or 0)
                ),
                "target_keep_tokens": target_keep_tokens,
                "actual_kept_tokens_est": actual_kept_tokens,
                "trim_strategy": trim_strategy,
                "cut_adjustment_reason": cut_adjustment_reason,
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

    def _rows_to_compaction_messages(self, rows: List[_MessageRow]) -> List[Dict[str, Any]]:
        messages: List[Dict[str, Any]] = []
        for idx, row in enumerate(rows, 1):
            msg_id = row.id
            role = row.role
            content = row.content
            tool_call_id = row.tool_call_id
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

    def _load_conversation_rows(
        self,
        conn: sqlite3.Connection,
        conversation_id: str,
    ) -> List[_MessageRow]:
        rows = conn.execute(
            """
            SELECT id, role, content, tool_call_id, tool_calls_json
            FROM messages
            WHERE conversation_id = ?
            ORDER BY id ASC
            """,
            (conversation_id,),
        ).fetchall()
        return [
            _MessageRow(
                id=int(r[0]),
                role=str(r[1] or ""),
                content=r[2] or "",
                tool_call_id=str(r[3] or ""),
                tool_calls_json=(r[4] if len(r) > 4 else None),
            )
            for r in rows
        ]

    def _compute_turn_based_cut_index(self, rows: List[_MessageRow], keep_recent_turns: int) -> int:
        if keep_recent_turns <= 0 or not rows:
            return 0
        assistant_seen = 0
        for idx in range(len(rows) - 1, -1, -1):
            role = str(rows[idx].role or "").strip().lower()
            if role == "assistant":
                assistant_seen += 1
                if assistant_seen >= keep_recent_turns:
                    return idx
        return 0

    def _resolve_target_keep_tokens(self, mode: str, token_budget: Optional[int]) -> int:
        if token_budget is not None:
            try:
                return max(int(token_budget), 0)
            except (TypeError, ValueError):
                return 0
        ratio = self.target_keep_ratio_light
        if mode == "strong":
            ratio = self.target_keep_ratio_strong
        elif mode == "finalize":
            ratio = self.target_keep_ratio_finalize
        return max(int(self.context_window_tokens * ratio), 0)

    def _compute_token_budget_cut_index(
        self,
        rows: List[_MessageRow],
        target_keep_tokens: int,
        min_keep_messages: int,
    ) -> Tuple[int, str]:
        if target_keep_tokens <= 0 or not rows:
            return 0, "budget_unavailable"
        if len(rows) <= max(min_keep_messages, 1):
            return 0, "below_min_keep_messages"

        turn_ranges = self._split_turn_ranges(rows)
        if not turn_ranges:
            return 0, "empty_turns"

        keep_from = len(rows)
        kept_tokens = 0
        for idx in range(len(turn_ranges) - 1, -1, -1):
            start, end = turn_ranges[idx]
            turn_tokens = self._estimate_rows_tokens(rows[start:end])
            if keep_from == len(rows):
                keep_from = start
                kept_tokens = turn_tokens
                continue
            if kept_tokens + turn_tokens > target_keep_tokens:
                break
            keep_from = start
            kept_tokens += turn_tokens

        cut_adjustment_reason = ""
        min_keep = max(min_keep_messages, 1)
        if len(rows) - keep_from < min_keep:
            keep_from = max(0, len(rows) - min_keep)
            cut_adjustment_reason = "min_keep_guard"

        keep_from, pair_adjustment = self._adjust_cut_for_tool_pairing(rows, keep_from)
        if pair_adjustment:
            cut_adjustment_reason = pair_adjustment
        return keep_from, cut_adjustment_reason

    def _split_turn_ranges(self, rows: List[_MessageRow]) -> List[Tuple[int, int]]:
        if not rows:
            return []
        has_user = any(str(row.role or "").strip().lower() == "user" for row in rows)
        ranges: List[Tuple[int, int]] = []
        start = 0
        for idx, row in enumerate(rows):
            role = str(row.role or "").strip().lower()
            if idx == 0:
                continue
            if has_user and role == "user":
                ranges.append((start, idx))
                start = idx
                continue
            if not has_user and role == "assistant":
                ranges.append((start, idx))
                start = idx
        ranges.append((start, len(rows)))
        return ranges

    def _adjust_cut_for_tool_pairing(self, rows: List[_MessageRow], cut_idx: int) -> Tuple[int, str]:
        idx = max(0, min(int(cut_idx), len(rows)))
        if idx <= 0 or idx >= len(rows):
            return idx, ""

        while idx < len(rows):
            row = rows[idx]
            role = str(row.role or "").strip().lower()
            tool_call_id = str(row.tool_call_id or "").strip()
            if role != "tool" or not tool_call_id:
                return idx, ""

            paired_assistant_idx = -1
            for j in range(idx - 1, -1, -1):
                prev = rows[j]
                prev_role = str(prev.role or "").strip().lower()
                if prev_role != "assistant":
                    continue
                for call in self._parse_tool_calls_json(prev.tool_calls_json):
                    if str(call.get("id", "")).strip() == tool_call_id:
                        paired_assistant_idx = j
                        break
                if paired_assistant_idx >= 0:
                    break

            if paired_assistant_idx < 0:
                return idx, ""
            idx = paired_assistant_idx
            if idx <= 0:
                return idx, "tool_pair_guard"
            return idx, "tool_pair_guard"
        return idx, ""

    def _estimate_rows_tokens(self, rows: List[_MessageRow]) -> int:
        total = 0
        for row in rows:
            total += self._estimate_message_tokens(row.content, row.tool_calls_json)
        return max(total, 1) if rows else 0

    def _estimate_message_tokens(self, content: str, tool_calls_json: Optional[str]) -> int:
        text = str(content or "")
        cjk_count = len(re.findall(r"[\u4e00-\u9fff]", text))
        latin_words = len(re.findall(r"[A-Za-z0-9_]+", text))
        punctuation = len(re.findall(r"[^\w\s]", text))
        tokens = cjk_count + latin_words + max(punctuation // 2, 0) + 8
        if tool_calls_json:
            tokens += max(len(tool_calls_json) // 4, 1)
        return max(tokens, 1)

    def _compact_event_tool_chain(self, conversation_id: str, mode: str) -> Dict[str, Any]:
        with self._connect() as conn:
            all_rows = self._load_conversation_rows(conn, conversation_id=conversation_id)
            total = len(all_rows)
            if total <= 0:
                return {"success": True, "applied": False, "reason": "empty_rows", "total": total}

            span = self._find_latest_tool_chain_span(all_rows)
            if span is None:
                return {"success": True, "applied": False, "reason": "no_tool_chain", "total": total}
            start_idx, end_idx = span
            units = self._split_tool_chain_units(all_rows, start_idx, end_idx)
            if not units:
                return {"success": True, "applied": False, "reason": "empty_tool_units", "total": total}

            unit_span = self._select_event_compaction_unit_span(units)
            if unit_span is None:
                return {"success": True, "applied": False, "reason": "no_eligible_tool_chain", "total": total}
            unit_start, unit_end = unit_span
            replaced_start_idx = units[unit_start].start_idx
            replaced_end_idx = units[unit_end].end_idx
            chain_rows = all_rows[replaced_start_idx:replaced_end_idx]
            if len(chain_rows) <= 1:
                return {"success": True, "applied": False, "reason": "tool_chain_too_short", "total": total}

            chain_summary = self._build_tool_chain_summary(chain_rows)
            anchor_id = chain_rows[0].id
            conn.execute(
                """
                UPDATE messages
                SET role = ?, content = ?, tool_call_id = NULL, tool_calls_json = NULL
                WHERE conversation_id = ? AND id = ?
                """,
                ("assistant", chain_summary, conversation_id, anchor_id),
            )
            delete_ids = [row.id for row in chain_rows[1:]]
            if delete_ids:
                placeholders = ",".join("?" for _ in delete_ids)
                conn.execute(
                    f"DELETE FROM messages WHERE conversation_id = ? AND id IN ({placeholders})",
                    (conversation_id, *delete_ids),
                )
            conn.commit()
            return {
                "success": True,
                "applied": True,
                "trigger": "event",
                "mode": mode,
                "trim_strategy": "tool_chain_replace",
                "before_messages": total,
                "after_messages": total - len(chain_rows) + 1,
                "dropped_messages": max(len(chain_rows) - 1, 0),
                "replaced_message_count": len(chain_rows),
                "inserted_summary_message_id": anchor_id,
                "tool_chain_span": {
                    "start_message_id": chain_rows[0].id,
                    "end_message_id": chain_rows[-1].id,
                },
            }

    def _find_latest_tool_chain_span(self, rows: List[_MessageRow]) -> Optional[Tuple[int, int]]:
        if not rows:
            return None
        idx = len(rows) - 1
        has_tool = False
        while idx >= 0:
            role = str(rows[idx].role or "").strip().lower()
            if role == "tool":
                has_tool = True
                idx -= 1
                continue
            if role == "assistant" and self._parse_tool_calls_json(rows[idx].tool_calls_json):
                idx -= 1
                continue
            break
        start = idx + 1
        if not has_tool:
            return None
        if start >= len(rows):
            return None
        return (start, len(rows))

    def _split_tool_chain_units(
        self,
        rows: List[_MessageRow],
        start_idx: int,
        end_idx: int,
    ) -> List[_ToolChainUnit]:
        units: List[_ToolChainUnit] = []
        idx = max(0, start_idx)
        end = min(len(rows), max(end_idx, start_idx))
        while idx < end:
            row = rows[idx]
            role = str(row.role or "").strip().lower()
            if role == "assistant" and self._parse_tool_calls_json(row.tool_calls_json):
                unit_start = idx
                tool_names = self._extract_tool_names_from_assistant_row(row)
                idx += 1
                while idx < end and str(rows[idx].role or "").strip().lower() == "tool":
                    idx += 1
                unit_end = idx
                is_stateful = any(self._is_stateful_tool_name(name) for name in tool_names)
                units.append(
                    _ToolChainUnit(
                        start_idx=unit_start,
                        end_idx=unit_end,
                        tool_names=tool_names,
                        is_stateful=is_stateful,
                    )
                )
                continue

            # Fallback unit for orphan tool groups.
            if role == "tool":
                unit_start = idx
                idx += 1
                while idx < end and str(rows[idx].role or "").strip().lower() == "tool":
                    idx += 1
                units.append(
                    _ToolChainUnit(
                        start_idx=unit_start,
                        end_idx=idx,
                        tool_names=[],
                        is_stateful=False,
                    )
                )
                continue
            idx += 1
        return units

    def _select_event_compaction_unit_span(self, units: List[_ToolChainUnit]) -> Optional[Tuple[int, int]]:
        if not units:
            return None
        eligible_end = len(units) - self.keep_recent_event_tool_pairs
        if eligible_end <= 0:
            return None

        best_span: Optional[Tuple[int, int]] = None
        best_len = 0
        run_start = -1
        for idx in range(eligible_end):
            is_eligible = not units[idx].is_stateful
            if is_eligible:
                if run_start < 0:
                    run_start = idx
                continue
            if run_start >= 0:
                run_len = idx - run_start
                if run_len > best_len:
                    best_len = run_len
                    best_span = (run_start, idx - 1)
                run_start = -1
        if run_start >= 0:
            run_len = eligible_end - run_start
            if run_len > best_len:
                best_span = (run_start, eligible_end - 1)
        return best_span

    def _extract_tool_names_from_assistant_row(self, row: _MessageRow) -> List[str]:
        names: List[str] = []
        for call in self._parse_tool_calls_json(row.tool_calls_json):
            fn = call.get("function", {}) if isinstance(call, dict) else {}
            name = str(fn.get("name", "")).strip()
            if name:
                names.append(name)
        return names

    def _is_stateful_tool_name(self, tool_name: str) -> bool:
        return str(tool_name or "").strip().lower() in self.event_stateful_tools

    def _build_tool_chain_summary(self, rows: List[_MessageRow]) -> str:
        tool_names: List[str] = []
        success_count = 0
        failed_count = 0
        failure_samples: List[str] = []
        result_samples: List[str] = []
        key_ids: Dict[str, str] = {}

        for row in rows:
            role = str(row.role or "").strip().lower()
            if role == "assistant":
                tool_names.extend(self._extract_tool_names_from_assistant_row(row))
                continue
            if role != "tool":
                continue

            parsed = self._parse_json_object(row.content)
            if isinstance(parsed, dict):
                success_val = parsed.get("success")
                if isinstance(success_val, bool):
                    if success_val:
                        success_count += 1
                    else:
                        failed_count += 1
                        err = str(parsed.get("error", "")).strip()
                        if err:
                            failure_samples.append(err[:120])
                preview = self._compact_preview_json(parsed)
                if preview:
                    result_samples.append(preview)
                for key, value in self._extract_key_identifiers(parsed).items():
                    key_ids.setdefault(key, value)
            else:
                result_samples.append(str(row.content or "").strip()[:120])

        tool_counter: Dict[str, int] = {}
        for name in tool_names:
            tool_counter[name] = tool_counter.get(name, 0) + 1
        tool_parts = [f"{name}x{count}" for name, count in tool_counter.items()]
        tools_text = ", ".join(tool_parts[:8]) if tool_parts else "unknown"
        result_text = " | ".join([x for x in result_samples[:3] if x]) or "n/a"
        failure_text = "; ".join([x for x in failure_samples[:3] if x]) or "none"
        key_id_text = "; ".join([f"{k}={v}" for k, v in key_ids.items()]) if key_ids else "none"

        return (
            "[tool-chain-compact] 已压缩连续工具调用段。\n"
            f"- tools: {tools_text}\n"
            f"- stats: success={success_count}, failed={failed_count}\n"
            f"- key_ids: {key_id_text}\n"
            f"- key_results: {result_text}\n"
            f"- failures: {failure_text}"
        )[:2200]

    def _parse_json_object(self, text: str) -> Optional[Dict[str, Any]]:
        raw = str(text or "").strip()
        if not raw:
            return None
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None

    def _compact_preview_json(self, value: Dict[str, Any]) -> str:
        try:
            text = json.dumps(value, ensure_ascii=False)
        except Exception:
            text = str(value)
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) <= 120:
            return text
        return text[:120] + "..."

    def _extract_key_identifiers(self, payload: Dict[str, Any]) -> Dict[str, str]:
        out: Dict[str, str] = {}

        def _walk(obj: Any) -> None:
            if isinstance(obj, dict):
                for key, val in obj.items():
                    key_norm = str(key).strip().lower()
                    if key_norm in {"todo_id", "task_id", "run_id", "subtask_number", "filepath"}:
                        text = str(val).strip()
                        if text and key_norm not in out:
                            out[key_norm] = text
                    _walk(val)
                return
            if isinstance(obj, list):
                for item in obj:
                    _walk(item)

        _walk(payload)
        return out

    def _filter_orphan_tool_rows(self, rows: List[_MessageRow]) -> List[_MessageRow]:
        valid_call_ids: set[str] = set()
        for row in rows:
            if str(row.role or "").strip().lower() != "assistant":
                continue
            parsed = self._parse_tool_calls_json(row.tool_calls_json)
            for call in parsed:
                call_id = str(call.get("id", "")).strip()
                if call_id:
                    valid_call_ids.add(call_id)

        filtered: List[_MessageRow] = []
        for row in rows:
            role = str(row.role or "").strip().lower()
            if role != "tool":
                filtered.append(row)
                continue
            call_id = str(row.tool_call_id or "").strip()
            if not call_id:
                filtered.append(row)
                continue
            if call_id in valid_call_ids:
                filtered.append(row)
        return filtered

    def _parse_tool_calls_json(self, raw: Optional[str]) -> List[Dict[str, Any]]:
        if not raw:
            return []
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return []
        if not isinstance(parsed, list):
            return []
        out: List[Dict[str, Any]] = []
        for item in parsed:
            if isinstance(item, dict):
                out.append(item)
        return out

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
