import json
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.core.memory.context_compressor import ContextCompressor
from app.core.model.base import GenerationConfig, ModelProvider


class LLMContextCompressor(ContextCompressor):
    """LLM-backed structured compressor with rule-based fallback."""

    VERSION = "v1_llm"

    def __init__(
        self,
        model_provider: ModelProvider,
        fallback: Optional[ContextCompressor] = None,
        max_tokens: int = 1200,
    ):
        super().__init__()
        self.model_provider = model_provider
        self.fallback = fallback or ContextCompressor()
        self.max_tokens = max(int(max_tokens), 200)

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
        fallback_reason = ""
        candidate: Optional[Dict[str, Any]] = None
        try:
            candidate = self._generate_summary(previous=previous, messages=messages, mode=mode, trigger=trigger)
        except Exception as e:
            fallback_reason = f"llm_error:{str(e).strip()[:200]}"

        if not isinstance(candidate, dict):
            merged = self.fallback.merge_summary(
                previous=previous,
                messages=messages,
                mode=mode,
                trigger=trigger,
                before_messages=before_messages,
                after_messages=after_messages,
                dropped_messages=dropped_messages,
            )
            meta = merged.setdefault("compression_meta", {})
            meta["compressor_kind_requested"] = "llm"
            meta["compressor_kind_applied"] = "rule"
            meta["compressor_fallback_used"] = True
            meta["compressor_failure_reason"] = fallback_reason or "llm_invalid_output"
            return merged

        normalized = self._normalize_summary(candidate, previous=previous)
        if not self.fallback.validate_consistency(previous, normalized):
            merged = self.fallback.merge_summary(
                previous=previous,
                messages=messages,
                mode=mode,
                trigger=trigger,
                before_messages=before_messages,
                after_messages=after_messages,
                dropped_messages=dropped_messages,
            )
            meta = merged.setdefault("compression_meta", {})
            meta["compressor_kind_requested"] = "llm"
            meta["compressor_kind_applied"] = "rule"
            meta["compressor_fallback_used"] = True
            meta["compressor_failure_reason"] = "llm_consistency_failed"
            return merged

        immutable_hits = self._extract_immutable_hits(messages)
        normalized["compression_meta"] = {
            "mode": mode,
            "trigger": trigger,
            "before_messages": before_messages,
            "after_messages": after_messages,
            "dropped_messages": dropped_messages,
            "immutable_hits_count": len(immutable_hits),
            "immutable_hits": immutable_hits[-10:],
            "timestamp": datetime.now().astimezone().isoformat(),
            "compressor_kind_requested": "llm",
            "compressor_kind_applied": "llm",
            "compressor_fallback_used": False,
        }
        return normalized

    def _generate_summary(
        self,
        previous: Optional[Dict[str, Any]],
        messages: List[Dict[str, Any]],
        mode: str,
        trigger: str,
    ) -> Dict[str, Any]:
        prev = previous if isinstance(previous, dict) else {}
        serializable_messages = []
        for item in messages:
            serializable_messages.append(
                {
                    "id": int(item.get("id") or 0),
                    "turn": int(item.get("turn") or 0),
                    "role": str(item.get("role", "")).strip().lower(),
                    "tool_call_id": str(item.get("tool_call_id", "")).strip(),
                    "content": self._truncate_content(str(item.get("content", "") or "").strip()),
                }
            )
        user_payload = {
            "task": "Compress runtime history into a compact structured JSON summary for future context injection.",
            "mode": mode,
            "trigger": trigger,
            "previous_summary": prev,
            "messages_to_compress": serializable_messages,
            "output_schema": {
                "version": "v1_llm",
                "task_state": {"goal": "", "progress": "", "next_step": "", "completion": 0.0},
                "decisions": [{"id": "", "what": "", "why": "", "turn": 0, "confidence": "medium"}],
                "constraints": [{"id": "", "rule": "", "source": "", "immutable": True}],
                "artifacts": [{"id": "", "type": "", "ref": "", "summary": "", "turn": 0}],
                "open_questions": [{"id": "", "question": "", "owner": "main", "status": "open"}],
                "anchors": [{"msg_id": 0, "turn": 0, "role": "", "reason": ""}],
            },
            "rules": [
                "Return a single JSON object only.",
                "Preserve hard constraints, approvals, security boundaries, deadlines, and user non-negotiables.",
                "Deduplicate repeated tool outputs and repeated progress chatter.",
                "Task state must reflect original user goal, current progress, and the best next step.",
                "Keep lists compact and high-signal.",
            ],
        }
        messages_in = [
            {
                "role": "system",
                "content": (
                    "You are a runtime context compressor. "
                    "Produce only valid JSON matching the requested schema. "
                    "Do not use markdown fences or explanations."
                ),
            },
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
        ]
        output = self.model_provider.generate(
            messages=messages_in,
            tools=[],
            config=GenerationConfig(temperature=0.0, max_tokens=self.max_tokens),
        )
        parsed = self.load_summary_json(self._extract_json_object(str(output.content or "")))
        if not parsed:
            raise ValueError("llm summary is not valid json object")
        return parsed

    def _normalize_summary(self, raw: Dict[str, Any], previous: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        prev = previous if isinstance(previous, dict) else {}
        out = {
            "version": str(raw.get("version") or self.VERSION),
            "task_state": self._normalize_task_state(raw.get("task_state"), prev.get("task_state")),
            "decisions": self._normalize_list(raw.get("decisions"), key="id", limit=30),
            "constraints": self._normalize_list(raw.get("constraints"), key="id", limit=30),
            "artifacts": self._normalize_list(raw.get("artifacts"), key="id", limit=50),
            "open_questions": self._normalize_list(raw.get("open_questions"), key="id", limit=20),
            "anchors": self._normalize_list(raw.get("anchors"), key="msg_id", limit=60),
        }
        return out

    def _normalize_task_state(self, current: Any, previous: Any) -> Dict[str, Any]:
        cur = current if isinstance(current, dict) else {}
        prev = previous if isinstance(previous, dict) else {}
        completion_raw = cur.get("completion", prev.get("completion", 0.0))
        try:
            completion = float(completion_raw)
        except Exception:
            completion = 0.0
        return {
            "goal": str(cur.get("goal") or prev.get("goal") or "").strip()[:300],
            "progress": str(cur.get("progress") or prev.get("progress") or "").strip()[:500],
            "next_step": str(cur.get("next_step") or prev.get("next_step") or "").strip()[:300],
            "completion": max(0.0, min(completion, 1.0)),
        }

    def _normalize_list(self, value: Any, key: str, limit: int) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        seen: set[str] = set()
        for raw in value or []:
            if not isinstance(raw, dict):
                continue
            k = str(raw.get(key) or "").strip()
            if not k or k in seen:
                continue
            normalized = {str(k2): v for k2, v in raw.items()}
            out.append(normalized)
            seen.add(k)
        return out[-limit:]

    def _truncate_content(self, text: str) -> str:
        flat = re.sub(r"\s+", " ", text).strip()
        if len(flat) <= 1200:
            return flat
        return flat[:1200] + "..."

    def _extract_json_object(self, text: str) -> str:
        raw = str(text or "").strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end >= start:
            return raw[start : end + 1]
        return raw
