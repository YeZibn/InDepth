import json
import re
from datetime import datetime
from typing import Any, Dict, List, Optional


IMMUTABLE_KEYWORDS = [
    "必须",
    "禁止",
    "不可",
    "务必",
    "审批",
    "权限",
    "安全",
    "密钥",
    "deadline",
    "must",
    "never",
]


class ContextCompressor:
    """Structured context compressor for runtime memory compaction."""

    VERSION = "v1"

    def merge_summary(
        self,
        previous: Optional[Dict[str, Any]],
        messages: List[Dict[str, Any]],
        mode: str,
        trigger: str,
        before_messages: int,
        after_messages: int,
        dropped_messages: int,
    ) -> Dict[str, Any]:
        prev = previous if isinstance(previous, dict) else {}
        now = datetime.now().astimezone().isoformat()
        immutable_hits = self._extract_immutable_hits(messages)

        merged = {
            "version": self.VERSION,
            "task_state": self._merge_task_state(prev.get("task_state"), messages),
            "decisions": self._merge_list(prev.get("decisions"), self._extract_decisions(messages), key="id"),
            "constraints": self._merge_list(prev.get("constraints"), self._extract_constraints(messages), key="id"),
            "artifacts": self._merge_list(prev.get("artifacts"), self._extract_artifacts(messages), key="id"),
            "open_questions": self._merge_list(
                prev.get("open_questions"),
                self._extract_open_questions(messages),
                key="id",
            ),
            "compression_meta": {
                "mode": mode,
                "trigger": trigger,
                "before_messages": before_messages,
                "after_messages": after_messages,
                "dropped_messages": dropped_messages,
                "immutable_hits_count": len(immutable_hits),
                "immutable_hits": immutable_hits[-10:],
                "timestamp": now,
            },
        }
        # Keep summaries bounded.
        merged["decisions"] = merged["decisions"][-30:]
        merged["constraints"] = merged["constraints"][-30:]
        merged["artifacts"] = merged["artifacts"][-50:]
        merged["open_questions"] = merged["open_questions"][-20:]
        return merged

    def validate_consistency(self, previous: Optional[Dict[str, Any]], current: Dict[str, Any]) -> bool:
        prev = previous if isinstance(previous, dict) else {}
        if not prev:
            return True

        prev_goal = str((prev.get("task_state") or {}).get("goal") or "").strip()
        cur_goal = str((current.get("task_state") or {}).get("goal") or "").strip()
        if prev_goal and not cur_goal:
            return False

        prev_constraints = [
            c for c in (prev.get("constraints") or [])
            if isinstance(c, dict) and bool(c.get("immutable"))
        ]
        if prev_constraints:
            cur_ids = {
                str(c.get("id"))
                for c in (current.get("constraints") or [])
                if isinstance(c, dict)
            }
            for c in prev_constraints:
                if str(c.get("id")) not in cur_ids:
                    return False
        return True

    def render_summary_prompt(self, summary: Dict[str, Any]) -> str:
        task_state = summary.get("task_state") or {}
        lines = ["结构化历史摘要(v1)："]
        lines.append(f"- 目标: {task_state.get('goal', '')}")
        lines.append(f"- 进展: {task_state.get('progress', '')}")
        lines.append(f"- 下一步: {task_state.get('next_step', '')}")

        constraints = summary.get("constraints") or []
        if constraints:
            lines.append("- 不可违反约束:")
            for item in constraints[-5:]:
                if not isinstance(item, dict):
                    continue
                text = str(item.get("rule", "")).strip()
                if text:
                    lines.append(f"  - {text}")

        decisions = summary.get("decisions") or []
        if decisions:
            lines.append("- 已做决策:")
            for item in decisions[-5:]:
                if not isinstance(item, dict):
                    continue
                what = str(item.get("what", "")).strip()
                why = str(item.get("why", "")).strip()
                if what:
                    lines.append(f"  - {what} | 原因: {why}")

        open_questions = [
            x for x in (summary.get("open_questions") or [])
            if isinstance(x, dict) and str(x.get("status", "open")).strip() != "resolved"
        ]
        if open_questions:
            lines.append("- 待确认:")
            for item in open_questions[-5:]:
                q = str(item.get("question", "")).strip()
                if q:
                    lines.append(f"  - {q}")

        artifacts = summary.get("artifacts") or []
        if artifacts:
            lines.append("- 关键产物索引:")
            for item in artifacts[-5:]:
                if not isinstance(item, dict):
                    continue
                ref = str(item.get("ref", "")).strip()
                desc = str(item.get("summary", "")).strip()
                if ref or desc:
                    lines.append(f"  - {ref} | {desc}")

        return "\n".join(lines)

    def summary_to_text(self, summary: Dict[str, Any]) -> str:
        return self.render_summary_prompt(summary)

    def load_summary_json(self, raw: Optional[str]) -> Optional[Dict[str, Any]]:
        if not raw:
            return None
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None

    def _merge_task_state(self, previous: Any, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        prev_state = previous if isinstance(previous, dict) else {}
        goal = str(prev_state.get("goal") or "").strip()
        progress = str(prev_state.get("progress") or "").strip()
        next_step = str(prev_state.get("next_step") or "").strip()
        completion = float(prev_state.get("completion") or 0.0)

        latest_user = self._latest_content(messages, "user")
        latest_assistant = self._latest_content(messages, "assistant")
        if latest_user:
            goal = goal or latest_user[:200]
            next_step = latest_user[:200]
        if latest_assistant:
            progress = latest_assistant[:240]
        if goal and progress:
            completion = min(max(completion, 0.6), 1.0)

        return {
            "goal": goal,
            "progress": progress,
            "next_step": next_step,
            "completion": round(completion, 4),
        }

    def _extract_constraints(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for msg in messages:
            role = str(msg.get("role", "")).strip().lower()
            content = str(msg.get("content", "")).strip()
            if not content:
                continue
            if role == "system" or self._contains_immutable_keyword(content):
                msg_id = int(msg.get("id") or 0)
                out.append(
                    {
                        "id": f"c_{msg_id}",
                        "rule": content[:300],
                        "source": "system" if role == "system" else "user",
                        "immutable": True,
                        **self._anchor_fields(msg),
                    }
                )
        return out

    def _extract_immutable_hits(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        hits: List[Dict[str, Any]] = []
        for msg in messages:
            role = str(msg.get("role", "")).strip().lower()
            content = str(msg.get("content", "")).strip()
            if not content:
                continue
            if role == "system" or self._contains_immutable_keyword(content):
                hits.append(
                    {
                        "msg_id": int(msg.get("id") or 0),
                        "role": role,
                        "snippet": content[:120],
                    }
                )
        return hits

    def _extract_decisions(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for msg in messages:
            role = str(msg.get("role", "")).strip().lower()
            if role not in {"assistant", "tool"}:
                continue
            content = str(msg.get("content", "")).strip()
            if not content:
                continue
            msg_id = int(msg.get("id") or 0)
            out.append(
                {
                    "id": f"d_{msg_id}",
                    "what": content[:180],
                    "why": "runtime progress",
                    "turn": int(msg.get("turn") or 0),
                    "confidence": "medium",
                    **self._anchor_fields(msg),
                }
            )
        return out[-12:]

    def _extract_artifacts(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for msg in messages:
            role = str(msg.get("role", "")).strip().lower()
            content = str(msg.get("content", "")).strip()
            if not content:
                continue
            msg_id = int(msg.get("id") or 0)
            if role == "tool":
                out.append(
                    {
                        "id": f"a_{msg_id}",
                        "type": "tool_result",
                        "ref": str(msg.get("tool_call_id") or f"msg:{msg_id}"),
                        "summary": content[:180],
                        "turn": int(msg.get("turn") or 0),
                        **self._anchor_fields(msg),
                    }
                )
                continue
            if role == "assistant" and ("/" in content or "db/" in content or "Return code:" in content):
                out.append(
                    {
                        "id": f"a_{msg_id}",
                        "type": "file",
                        "ref": f"msg:{msg_id}",
                        "summary": content[:180],
                        "turn": int(msg.get("turn") or 0),
                        **self._anchor_fields(msg),
                    }
                )
        return out[-15:]

    def _extract_open_questions(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for msg in messages:
            role = str(msg.get("role", "")).strip().lower()
            if role != "user":
                continue
            content = str(msg.get("content", "")).strip()
            if not content:
                continue
            if "?" in content or "？" in content:
                msg_id = int(msg.get("id") or 0)
                out.append(
                    {
                        "id": f"q_{msg_id}",
                        "question": content[:200],
                        "owner": "main",
                        "status": "open",
                    }
                )
        return out[-12:]

    def _contains_immutable_keyword(self, text: str) -> bool:
        lower = text.lower()
        return any(keyword in text or keyword in lower for keyword in IMMUTABLE_KEYWORDS)

    def _latest_content(self, messages: List[Dict[str, Any]], role: str) -> str:
        role_norm = role.strip().lower()
        for msg in reversed(messages):
            if str(msg.get("role", "")).strip().lower() != role_norm:
                continue
            content = str(msg.get("content", "")).strip()
            if content:
                # Flatten too-long lines for summary stability.
                return re.sub(r"\s+", " ", content)
        return ""

    def _merge_list(self, previous: Any, current: Any, key: str) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        seen: set[str] = set()

        for raw in (previous or []):
            if not isinstance(raw, dict):
                continue
            k = str(raw.get(key) or "").strip()
            if not k or k in seen:
                continue
            out.append(raw)
            seen.add(k)

        for raw in (current or []):
            if not isinstance(raw, dict):
                continue
            k = str(raw.get(key) or "").strip()
            if not k or k in seen:
                continue
            out.append(raw)
            seen.add(k)

        return out

    def _anchor_fields(self, msg: Dict[str, Any]) -> Dict[str, Any]:
        run_id = str(msg.get("run_id") or "").strip()
        step_id = str(msg.get("step_id") or "").strip()
        if not run_id or not step_id:
            return {}
        return {
            "source_anchor": {
                "run_id": run_id,
                "step_id": step_id,
            }
        }
