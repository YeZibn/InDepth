import json
from typing import Any, Callable, Dict, List

from app.core.model.base import GenerationConfig, ModelProvider


def build_rule_verification_handoff(
    user_input: str,
    final_answer: str,
    stop_reason: str,
    runtime_status: str,
    tool_failures: List[Dict[str, str]],
    recovery_context: Dict[str, Any],
    preview: Callable[[str, int], str],
) -> Dict[str, Any]:
    failures = tool_failures[:5] if isinstance(tool_failures, list) else []
    key_tool_results: List[Dict[str, Any]] = []
    for item in failures:
        if not isinstance(item, dict):
            continue
        key_tool_results.append(
            {
                "tool": str(item.get("tool", "unknown") or "unknown"),
                "status": "error",
                "summary": str(item.get("error", "") or "unknown error"),
            }
        )
    known_gaps: List[str] = []
    if runtime_status != "ok":
        known_gaps.append(f"runtime_status={runtime_status}")
    if stop_reason not in {"stop", "fallback_content", "completed"}:
        known_gaps.append(f"stop_reason={stop_reason}")
    if failures:
        known_gaps.append(f"tool_failures={len(failures)}")
    recovery_context = recovery_context if isinstance(recovery_context, dict) else {}
    recovery_handoff: Dict[str, Any] = {}
    todo_id = preview(str(recovery_context.get("todo_id", "") or "").strip(), 120)
    subtask_number = recovery_context.get("subtask_number")
    fallback_record = recovery_context.get("fallback_record", {})
    recovery_decision = recovery_context.get("recovery_decision", {})
    if todo_id:
        recovery_handoff["todo_id"] = todo_id
    if subtask_number not in (None, ""):
        recovery_handoff["subtask_number"] = subtask_number
    if isinstance(fallback_record, dict) and fallback_record:
        recovery_handoff["fallback_record"] = fallback_record
        reason_code = str(fallback_record.get("reason_code", "") or "").strip()
        state = str(fallback_record.get("state", "") or "").strip()
        if reason_code:
            known_gaps.append(f"recovery_reason={reason_code}")
        if state:
            known_gaps.append(f"recovery_state={state}")
    if isinstance(recovery_decision, dict) and recovery_decision:
        recovery_handoff["recovery_decision"] = recovery_decision
        primary_action = str(recovery_decision.get("primary_action", "") or "").strip()
        if primary_action:
            known_gaps.append(f"recovery_action={primary_action}")
    return {
        "goal": preview(user_input, 280),
        "constraints": [],
        "expected_artifacts": [],
        "claimed_done_items": [preview(final_answer, 280)] if (final_answer or "").strip() else [],
        "key_tool_results": key_tool_results,
        "known_gaps": known_gaps,
        "recovery": recovery_handoff,
        "self_confidence": 0.8 if runtime_status == "ok" else 0.3,
        "soft_score_threshold": 0.7,
        "rubric": "评估任务完成度、约束满足度、证据充分性。",
    }


def generate_verification_handoff_llm(
    model_provider: ModelProvider,
    enabled: bool,
    build_config: Callable[[], GenerationConfig],
    parse_json_dict: Callable[[str], Dict[str, Any]],
    user_input: str,
    final_answer: str,
    stop_reason: str,
    runtime_status: str,
    tool_failures: List[Dict[str, str]],
    fallback_handoff: Dict[str, Any],
) -> Dict[str, Any]:
    if not enabled:
        return {}
    payload = {
        "task": "verification_handoff_generation",
        "instruction": (
            "Generate a concise and faithful verification_handoff from runtime facts. "
            "Return strict JSON only. Do not invent files or success claims."
        ),
        "runtime_input": {
            "user_input": user_input,
            "final_answer": final_answer,
            "stop_reason": stop_reason,
            "runtime_status": runtime_status,
            "tool_failures": tool_failures[:10] if isinstance(tool_failures, list) else [],
        },
        "fallback_handoff": fallback_handoff,
        "output_schema": {
            "goal": "string",
            "constraints": ["string"],
            "expected_artifacts": [
                {
                    "path": "string",
                    "must_exist": "boolean",
                    "non_empty": "boolean",
                    "contains": "string(optional)",
                }
            ],
            "claimed_done_items": ["string"],
            "key_tool_results": [
                {
                    "tool": "string",
                    "status": "ok|error",
                    "summary": "string",
                }
            ],
            "known_gaps": ["string"],
            "recovery": {
                "todo_id": "string",
                "subtask_number": "integer",
                "fallback_record": "object",
                "recovery_decision": "object",
            },
            "self_confidence": "0~1 float",
            "soft_score_threshold": "0~1 float",
            "rubric": "string",
        },
    }
    try:
        output = model_provider.generate(
            messages=[
                {
                    "role": "system",
                    "content": "You generate verification handoff JSON. Output JSON only.",
                },
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            tools=[],
            config=build_config(),
        )
    except Exception:
        return {}
    return parse_json_dict(str(getattr(output, "content", "") or ""))


def normalize_verification_handoff(
    candidate: Dict[str, Any],
    fallback: Dict[str, Any],
    preview: Callable[[str, int], str],
) -> Dict[str, Any]:
    if not isinstance(candidate, dict):
        return dict(fallback)
    out: Dict[str, Any] = dict(fallback)
    goal = preview(str(candidate.get("goal", "") or "").strip(), 280)
    if goal:
        out["goal"] = goal
    constraints = normalize_handoff_str_list(candidate.get("constraints", []), max_items=12, max_len=120, preview=preview)
    if constraints:
        out["constraints"] = constraints
    expected_artifacts = normalize_expected_artifacts(candidate.get("expected_artifacts", []), preview=preview)
    if expected_artifacts:
        out["expected_artifacts"] = expected_artifacts
    claimed_done = normalize_handoff_str_list(
        candidate.get("claimed_done_items", []), max_items=12, max_len=280, preview=preview
    )
    if claimed_done:
        out["claimed_done_items"] = claimed_done
    key_tool_results = normalize_key_tool_results(candidate.get("key_tool_results", []), preview=preview)
    if key_tool_results:
        out["key_tool_results"] = key_tool_results
    known_gaps = normalize_handoff_str_list(candidate.get("known_gaps", []), max_items=12, max_len=120, preview=preview)
    if known_gaps:
        out["known_gaps"] = known_gaps
    recovery = candidate.get("recovery")
    if isinstance(recovery, dict) and recovery:
        out["recovery"] = recovery
    out["self_confidence"] = clamp_float(
        candidate.get("self_confidence", fallback.get("self_confidence", 0.8)),
        default=float(fallback.get("self_confidence", 0.8) or 0.8),
    )
    out["soft_score_threshold"] = clamp_float(
        candidate.get("soft_score_threshold", fallback.get("soft_score_threshold", 0.7)),
        default=float(fallback.get("soft_score_threshold", 0.7) or 0.7),
    )
    rubric = preview(str(candidate.get("rubric", "") or "").strip(), 120)
    if rubric:
        out["rubric"] = rubric
    return out


def normalize_handoff_str_list(
    value: Any,
    max_items: int,
    max_len: int,
    preview: Callable[[str, int], str],
) -> List[str]:
    if not isinstance(value, list):
        return []
    out: List[str] = []
    for item in value:
        text = preview(str(item or "").strip(), max_len)
        if not text:
            continue
        out.append(text)
        if len(out) >= max_items:
            break
    return out


def normalize_expected_artifacts(value: Any, preview: Callable[[str, int], str]) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        return []
    out: List[Dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        path = preview(str(item.get("path", "") or "").strip(), 240)
        if not path:
            continue
        artifact: Dict[str, Any] = {
            "path": path,
            "must_exist": bool(item.get("must_exist", True)),
            "non_empty": bool(item.get("non_empty", False)),
        }
        contains = preview(str(item.get("contains", "") or "").strip(), 120)
        if contains:
            artifact["contains"] = contains
        out.append(artifact)
        if len(out) >= 20:
            break
    return out


def normalize_key_tool_results(value: Any, preview: Callable[[str, int], str]) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        return []
    out: List[Dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        tool = preview(str(item.get("tool", "") or "").strip(), 80) or "unknown"
        status_raw = str(item.get("status", "") or "").strip().lower()
        status = "ok" if status_raw == "ok" else "error"
        summary = preview(str(item.get("summary", "") or "").strip(), 160)
        if not summary:
            continue
        out.append({"tool": tool, "status": status, "summary": summary})
        if len(out) >= 20:
            break
    return out


def clamp_float(value: Any, default: float) -> float:
    try:
        num = float(value)
    except Exception:
        return max(0.0, min(default, 1.0))
    return max(0.0, min(num, 1.0))
