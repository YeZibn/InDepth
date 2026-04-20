import json
from typing import Any, Callable, Dict, List

from app.core.model.base import GenerationConfig, ModelProvider


# 这里放的是 verification handoff 的评估能力：
# - fallback handoff 结构化
# - handoff LLM 生成
# - handoff normalize
# runtime 只决定何时构建 handoff，不持有这些细节规则。


def build_verification_handoff(
    user_input: str,
    final_answer: str,
    stop_reason: str,
    runtime_status: str,
    tool_failures: List[Dict[str, str]],
    context_messages: List[Dict[str, Any]],
    recovery_context: Dict[str, Any],
    model_provider: ModelProvider,
    enabled: bool,
    build_config: Callable[[], GenerationConfig],
    parse_json_dict: Callable[[str], Dict[str, Any]],
    preview: Callable[[str, int], str],
) -> tuple[Dict[str, Any], str]:
    fallback_handoff = build_rule_verification_handoff(
        user_input=user_input,
        final_answer=final_answer,
        stop_reason=stop_reason,
        runtime_status=runtime_status,
        tool_failures=tool_failures,
        recovery_context=recovery_context,
        preview=preview,
    )
    llm_candidate = generate_verification_handoff_llm(
        model_provider=model_provider,
        enabled=enabled,
        build_config=build_config,
        parse_json_dict=parse_json_dict,
        user_input=user_input,
        final_answer=final_answer,
        stop_reason=stop_reason,
        runtime_status=runtime_status,
        tool_failures=tool_failures,
        context_messages=context_messages,
        fallback_handoff=fallback_handoff,
        preview=preview,
    )
    if not llm_candidate:
        return fallback_handoff, "fallback_rule"
    return normalize_verification_handoff(
        candidate=llm_candidate,
        fallback=fallback_handoff,
        preview=preview,
    ), "llm"


def clamp_float(value: Any, default: float) -> float:
    try:
        num = float(value)
    except Exception:
        return max(0.0, min(default, 1.0))
    return max(0.0, min(num, 1.0))


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
    subtask_id = preview(str(recovery_context.get("subtask_id", "") or "").strip(), 120)
    subtask_number = recovery_context.get("subtask_number")
    fallback_record = recovery_context.get("fallback_record", {})
    recovery_decision = recovery_context.get("recovery_decision", {})
    if todo_id:
        recovery_handoff["todo_id"] = todo_id
    if subtask_id:
        recovery_handoff["subtask_id"] = subtask_id
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
    final_status = "pass" if runtime_status == "ok" else "fail"
    task_summary = preview(final_answer or user_input, 280)
    memory_title = preview(user_input, 120) or "任务经验摘要"
    memory_recall_hint = preview(
        (
            f"当遇到与“{user_input or '当前任务'}”相似的任务时，"
            f"优先参考本次最终交付与收尾结果。状态={runtime_status}。"
        ),
        200,
    )
    memory_content = preview(
        final_answer or f"任务目标：{user_input}；结束状态：{runtime_status}；stop_reason={stop_reason}",
        500,
    )
    return {
        "goal": preview(user_input, 280),
        "task_summary": task_summary,
        "final_status": final_status,
        "constraints": [],
        "expected_artifacts": [],
        "key_evidence": [],
        "claimed_done_items": [preview(final_answer, 280)] if (final_answer or "").strip() else [],
        "key_tool_results": key_tool_results,
        "known_gaps": known_gaps,
        "risks": [],
        "recovery": recovery_handoff,
        "memory_seed": {
            "title": memory_title,
            "recall_hint": memory_recall_hint,
            "content": memory_content,
        },
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
    context_messages: List[Dict[str, Any]],
    fallback_handoff: Dict[str, Any],
    preview: Callable[[str, int], str],
) -> Dict[str, Any]:
    if not enabled:
        return {}
    output_schema = {
        "goal": "string",
        "task_summary": "string",
        "final_status": "pass|partial|fail",
        "constraints": ["string"],
        "expected_artifacts": [
            {
                "path": "string",
                "must_exist": "boolean",
                "non_empty": "boolean",
                "contains": "string(optional)",
            }
        ],
        "key_evidence": [{"type": "string", "name": "string", "summary": "string"}],
        "claimed_done_items": ["string"],
        "key_tool_results": [
            {
                "tool": "string",
                "status": "ok|error",
                "summary": "string",
            }
        ],
        "known_gaps": ["string"],
        "risks": ["string"],
        "recovery": {
            "todo_id": "string",
            "subtask_number": "integer",
            "fallback_record": "object",
            "recovery_decision": "object",
        },
        "memory_seed": {
            "title": "string",
            "recall_hint": "string",
            "content": "string",
        },
        "self_confidence": "0~1 float",
        "soft_score_threshold": "0~1 float",
        "rubric": "string",
    }
    context_tail = _select_handoff_context_messages(context_messages, preview=preview)
    prompt = {
        "task": "verification_handoff_generation",
        "instruction": (
            "You are in the runtime finalizing handoff step. Read the conversation context above and the runtime facts below, "
            "then produce a concise, faithful verification_handoff as strict JSON only. "
            "Do not invent files, tests, or success claims. If evidence is missing, put it in known_gaps. "
            "Always include memory_seed with title, recall_hint, and content."
        ),
        "runtime_input": {
            "user_input": user_input,
            "final_answer": final_answer,
            "stop_reason": stop_reason,
            "runtime_status": runtime_status,
            "tool_failures": tool_failures[:10] if isinstance(tool_failures, list) else [],
        },
        "fallback_handoff": fallback_handoff,
        "output_schema": output_schema,
    }
    try:
        messages: List[Dict[str, Any]] = list(context_tail)
        messages.append(
            {
                "role": "user",
                "content": json.dumps(prompt, ensure_ascii=False),
            }
        )
        output = model_provider.generate(
            messages=messages,
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
    task_summary = preview(str(candidate.get("task_summary", "") or "").strip(), 280)
    if task_summary:
        out["task_summary"] = task_summary
    final_status = str(candidate.get("final_status", "") or "").strip().lower()
    if final_status in {"pass", "partial", "fail"}:
        out["final_status"] = final_status
    constraints = normalize_handoff_str_list(candidate.get("constraints", []), max_items=12, max_len=120, preview=preview)
    if constraints:
        out["constraints"] = constraints
    expected_artifacts = normalize_expected_artifacts(candidate.get("expected_artifacts", []), preview=preview)
    if expected_artifacts:
        out["expected_artifacts"] = expected_artifacts
    key_evidence = normalize_key_evidence(candidate.get("key_evidence", []), preview=preview)
    if key_evidence:
        out["key_evidence"] = key_evidence
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
    risks = normalize_handoff_str_list(candidate.get("risks", []), max_items=12, max_len=120, preview=preview)
    if risks:
        out["risks"] = risks
    recovery = candidate.get("recovery")
    if isinstance(recovery, dict) and recovery:
        out["recovery"] = recovery
    memory_seed = normalize_memory_seed(candidate.get("memory_seed", {}), fallback=fallback.get("memory_seed", {}), preview=preview)
    if memory_seed:
        out["memory_seed"] = memory_seed
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


def normalize_key_evidence(value: Any, preview: Callable[[str, int], str]) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        return []
    out: List[Dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        etype = preview(str(item.get("type", "") or "").strip(), 40)
        name = preview(str(item.get("name", "") or "").strip(), 80)
        summary = preview(str(item.get("summary", "") or "").strip(), 180)
        if not summary:
            continue
        out.append({"type": etype or "fact", "name": name or "evidence", "summary": summary})
        if len(out) >= 20:
            break
    return out


def normalize_memory_seed(value: Any, fallback: Any, preview: Callable[[str, int], str]) -> Dict[str, str]:
    candidate = value if isinstance(value, dict) else {}
    base = fallback if isinstance(fallback, dict) else {}
    title = preview(str(candidate.get("title", "") or base.get("title", "") or "").strip(), 120)
    recall_hint = preview(str(candidate.get("recall_hint", "") or base.get("recall_hint", "") or "").strip(), 220)
    content = preview(str(candidate.get("content", "") or base.get("content", "") or "").strip(), 500)
    if not any([title, recall_hint, content]):
        return {}
    return {
        "title": title or preview(str(base.get("title", "") or "").strip(), 120) or "任务经验摘要",
        "recall_hint": recall_hint or preview(str(base.get("recall_hint", "") or "").strip(), 220),
        "content": content or preview(str(base.get("content", "") or "").strip(), 500),
    }


def _select_handoff_context_messages(
    context_messages: List[Dict[str, Any]],
    preview: Callable[[str, int], str],
    limit: int = 24,
) -> List[Dict[str, Any]]:
    if not isinstance(context_messages, list):
        return []
    selected = context_messages[-max(limit, 1) :]
    out: List[Dict[str, Any]] = []
    for item in selected:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role", "") or "").strip()
        if role not in {"system", "user", "assistant", "tool"}:
            continue
        normalized: Dict[str, Any] = {"role": role}
        content = item.get("content", "")
        if isinstance(content, str):
            normalized["content"] = preview(content, 1200)
        else:
            normalized["content"] = preview(str(content or ""), 1200)
        if role == "tool":
            tool_call_id = str(item.get("tool_call_id", "") or "").strip()
            if tool_call_id:
                normalized["tool_call_id"] = tool_call_id
        out.append(normalized)
    return out
