import json
from typing import Any, Callable, Dict, List

from app.core.model.base import GenerationConfig, ModelProvider


DECISION_LEVEL_ORDER = {
    "auto": 0,
    "agent_decide": 1,
    "user_confirm": 2,
}

FAILURE_INTERPRETATION_REASON_CODES = {
    "waiting_user_input",
    "budget_exhausted",
    "tool_invocation_error",
    "execution_environment_error",
    "missing_context",
    "validation_failed",
    "partial_progress",
    "dependency_unmet",
    "subagent_empty_result",
    "subagent_execution_error",
    "orphan_subtask_unbound",
    "oversized_generation_request",
    "transient_model_backend_failure",
}


def build_rule_recovery_guardrails(
    fallback_record: Dict[str, Any],
    fallback_decision: Dict[str, Any],
) -> Dict[str, Any]:
    fallback_record = fallback_record if isinstance(fallback_record, dict) else {}
    fallback_decision = fallback_decision if isinstance(fallback_decision, dict) else {}
    allowed_actions: List[str] = []
    for item in [fallback_decision.get("primary_action"), *(fallback_decision.get("recommended_actions", []) or [])]:
        value = str(item or "").strip()
        if value and value not in allowed_actions:
            allowed_actions.append(value)
    return {
        "allowed_primary_actions": allowed_actions,
        "fallback_primary_action": str(fallback_decision.get("primary_action", "") or "").strip(),
        "must_stop_auto_recovery": bool(fallback_decision.get("stop_auto_recovery")),
        "can_only_escalate_decision_level": str(fallback_decision.get("decision_level", "agent_decide") or "agent_decide"),
        "must_preserve_main_subtask": bool(fallback_decision.get("can_resume_in_place", False)),
        "must_derive_recovery_subtask": bool(fallback_decision.get("needs_derived_recovery_subtask", False)),
        "must_anchor_followups_to_origin": True,
        "retry_budget_remaining": int(fallback_record.get("retry_budget_remaining", 0) or 0),
        "retryable": bool(fallback_record.get("retryable", True)),
    }


def build_default_failure_interpretation(
    fallback_record: Dict[str, Any],
    preview: Callable[[str, int], str],
) -> Dict[str, Any]:
    fallback_record = fallback_record if isinstance(fallback_record, dict) else {}
    reason_code = str(fallback_record.get("reason_code", "") or "").strip() or "execution_environment_error"
    detail = preview(str(fallback_record.get("reason_detail", "") or "").strip(), 320)
    evidence = fallback_record.get("evidence", [])
    if not isinstance(evidence, list):
        evidence = [str(evidence)]
    label_map = {
        "waiting_user_input": "awaiting_user_input",
        "budget_exhausted": "budget_exhausted",
        "tool_invocation_error": "tool_invocation_error",
        "execution_environment_error": "execution_environment_error",
        "missing_context": "missing_context",
        "validation_failed": "validation_failed",
        "partial_progress": "partial_progress",
        "dependency_unmet": "dependency_unmet",
        "subagent_empty_result": "subagent_empty_result",
        "subagent_execution_error": "subagent_execution_error",
        "orphan_subtask_unbound": "orphan_subtask_unbound",
        "oversized_generation_request": "generation_overload",
        "transient_model_backend_failure": "transient_backend_failure",
    }
    interpretation = {
        "failure_label": label_map.get(reason_code, reason_code),
        "reason_code": reason_code,
        "reason_detail": detail,
        "confidence": 0.35,
        "retryable": bool(fallback_record.get("retryable", True)),
        "evidence": [preview(str(item or "").strip(), 160) for item in evidence[:5] if str(item or "").strip()],
        "suspected_root_causes": [],
        "recovery_risks": [],
        "classification_source": "rule",
    }
    if detail:
        interpretation["suspected_root_causes"] = [detail]
    return interpretation


def normalize_failure_interpretation(
    candidate: Dict[str, Any],
    fallback: Dict[str, Any],
    preview: Callable[[str, int], str],
) -> Dict[str, Any]:
    out = dict(fallback if isinstance(fallback, dict) else {})
    if not isinstance(candidate, dict) or not candidate:
        out["classification_source"] = str(out.get("classification_source", "") or "rule")
        return out

    failure_label = preview(str(candidate.get("failure_label", "") or "").strip(), 80)
    if failure_label:
        out["failure_label"] = failure_label

    reason_code = preview(str(candidate.get("reason_code", "") or "").strip(), 80)
    if reason_code and reason_code in FAILURE_INTERPRETATION_REASON_CODES:
        out["reason_code"] = reason_code

    reason_detail = preview(str(candidate.get("reason_detail", "") or "").strip(), 320)
    if reason_detail:
        out["reason_detail"] = reason_detail

    try:
        confidence = float(candidate.get("confidence", out.get("confidence", 0.35)) or 0.35)
    except Exception:
        confidence = float(out.get("confidence", 0.35) or 0.35)
    out["confidence"] = max(0.0, min(confidence, 1.0))
    out["retryable"] = bool(candidate.get("retryable", out.get("retryable", True)))

    for key in ["evidence", "suspected_root_causes", "recovery_risks"]:
        value = candidate.get(key)
        if value is None:
            continue
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            continue
        out[key] = [preview(str(item or "").strip(), 180) for item in value[:6] if str(item or "").strip()]

    out["classification_source"] = "llm"
    return out


def generate_recovery_assessment_llm(
    model_provider: ModelProvider,
    enabled: bool,
    build_config: Callable[[], GenerationConfig],
    parse_json_dict: Callable[[str], Dict[str, Any]],
    recovery_context: Dict[str, Any],
    fallback_interpretation: Dict[str, Any],
    fallback_decision: Dict[str, Any],
    guardrails: Dict[str, Any],
) -> Dict[str, Any]:
    if not enabled:
        return {}
    payload = {
        "task": "recovery_assessment",
        "instruction": (
            "You are an independent failure-and-recovery assessor called after runtime failure facts are recorded. "
            "Return strict JSON only. Stay inside the rule guardrails. "
            "Do not change todo binding, do not create a new todo cycle, and do not invent success."
        ),
        "recovery_context": recovery_context,
        "fallback_interpretation": fallback_interpretation,
        "fallback_rule_decision": fallback_decision,
        "guardrails": guardrails,
        "output_schema": {
            "failure_label": "string",
            "reason_code": "string",
            "reason_detail": "string",
            "confidence": "number",
            "retryable": "boolean",
            "evidence": ["string"],
            "suspected_root_causes": ["string"],
            "recovery_risks": ["string"],
            "can_resume_in_place": "boolean",
            "needs_derived_recovery_subtask": "boolean",
            "primary_action": "string",
            "recommended_actions": ["string"],
            "decision_level": "auto|agent_decide|user_confirm",
            "rationale": "string",
            "resume_condition": "string",
            "retry_guidance": ["string"],
            "stop_auto_recovery": "boolean",
            "suggested_owner": "string",
            "next_subtasks": [
                {
                    "name": "string",
                    "goal": "string",
                    "description": "string",
                    "kind": "string",
                    "owner": "string",
                    "depends_on": ["string|integer"],
                    "acceptance_criteria": ["string"],
                }
            ],
        },
    }
    try:
        output = model_provider.generate(
            messages=[
                {
                    "role": "system",
                    "content": "You generate failure and recovery assessment JSON. Output JSON only.",
                },
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            tools=[],
            config=build_config(),
        )
    except Exception:
        return {}
    return parse_json_dict(str(getattr(output, "content", "") or ""))


def normalize_llm_recovery_assessment(
    candidate: Dict[str, Any],
    fallback_interpretation: Dict[str, Any],
    fallback_decision: Dict[str, Any],
    guardrails: Dict[str, Any],
    current_subtask_id: str,
    current_subtask_number: int,
    preview: Callable[[str, int], str],
) -> Dict[str, Any]:
    interpretation = normalize_failure_interpretation(
        candidate=candidate,
        fallback=fallback_interpretation,
        preview=preview,
    )
    if not isinstance(candidate, dict) or not candidate:
        out = dict(fallback_decision)
        out["planner_source"] = "rule"
        return {"failure_interpretation": interpretation, "recovery_decision": out}

    out = dict(fallback_decision)
    allowed_actions = [
        str(item or "").strip()
        for item in (guardrails.get("allowed_primary_actions", []) or [])
        if str(item or "").strip()
    ]
    candidate_action = str(candidate.get("primary_action", "") or "").strip()
    if candidate_action in allowed_actions:
        out["primary_action"] = candidate_action

    candidate_actions = candidate.get("recommended_actions", [])
    if isinstance(candidate_actions, list):
        filtered_actions: List[str] = []
        for item in candidate_actions:
            value = str(item or "").strip()
            if value and value in allowed_actions and value not in filtered_actions:
                filtered_actions.append(value)
        if filtered_actions:
            if out.get("primary_action") not in filtered_actions:
                filtered_actions.insert(0, str(out.get("primary_action", "") or "").strip())
            out["recommended_actions"] = filtered_actions

    if not bool(guardrails.get("must_preserve_main_subtask")):
        out["can_resume_in_place"] = False
    else:
        out["can_resume_in_place"] = bool(candidate.get("can_resume_in_place", out.get("can_resume_in_place")))

    out["needs_derived_recovery_subtask"] = bool(
        candidate.get("needs_derived_recovery_subtask", out.get("needs_derived_recovery_subtask"))
    ) or bool(guardrails.get("must_derive_recovery_subtask"))

    minimum_level = str(guardrails.get("can_only_escalate_decision_level", "agent_decide") or "agent_decide")
    candidate_level = str(candidate.get("decision_level", "") or "").strip() or str(out.get("decision_level", minimum_level))
    if DECISION_LEVEL_ORDER.get(candidate_level, 1) >= DECISION_LEVEL_ORDER.get(minimum_level, 1):
        out["decision_level"] = candidate_level

    out["stop_auto_recovery"] = bool(candidate.get("stop_auto_recovery", out.get("stop_auto_recovery"))) or bool(
        guardrails.get("must_stop_auto_recovery")
    )

    rationale = preview(str(candidate.get("rationale", "") or "").strip(), 400)
    if rationale:
        out["rationale"] = rationale
    resume_condition = preview(str(candidate.get("resume_condition", "") or "").strip(), 240)
    if resume_condition:
        out["resume_condition"] = resume_condition
    suggested_owner = preview(str(candidate.get("suggested_owner", "") or "").strip(), 80)
    if suggested_owner:
        out["suggested_owner"] = suggested_owner
    retry_guidance = candidate.get("retry_guidance")
    if retry_guidance is not None:
        if isinstance(retry_guidance, str):
            retry_guidance = [retry_guidance]
        if isinstance(retry_guidance, list):
            normalized_guidance = [preview(str(item or "").strip(), 180) for item in retry_guidance[:6] if str(item or "").strip()]
            if normalized_guidance:
                out["retry_guidance"] = normalized_guidance

    if out.get("needs_derived_recovery_subtask"):
        out["next_subtasks"] = normalize_recovery_subtasks(
            candidate.get("next_subtasks", []),
            fallback=out.get("next_subtasks", []),
            current_subtask_id=current_subtask_id,
            current_subtask_number=current_subtask_number,
            preview=preview,
        )
    else:
        out["next_subtasks"] = []

    out["planner_source"] = "llm"
    return {"failure_interpretation": interpretation, "recovery_decision": out}


def normalize_recovery_subtasks(
    candidate: Any,
    fallback: Any,
    current_subtask_id: str,
    current_subtask_number: int,
    preview: Callable[[str, int], str],
) -> List[Dict[str, Any]]:
    items = candidate if isinstance(candidate, list) and candidate else fallback
    if not isinstance(items, list):
        return []
    normalized: List[Dict[str, Any]] = []
    for raw in items[:3]:
        if not isinstance(raw, dict):
            continue
        name = preview(str(raw.get("name", "") or "").strip(), 120)
        description = preview(str(raw.get("description", "") or "").strip(), 240)
        if not name or not description:
            continue
        acceptance = raw.get("acceptance_criteria", [])
        acceptance_items: List[str] = []
        if isinstance(acceptance, list):
            for item in acceptance[:5]:
                value = preview(str(item or "").strip(), 160)
                if value:
                    acceptance_items.append(value)
        normalized.append(
            {
                "origin_subtask_id": current_subtask_id,
                "origin_subtask_number": str(current_subtask_number),
                "name": name,
                "goal": preview(str(raw.get("goal", "") or "").strip(), 180) or name,
                "description": description,
                "kind": preview(str(raw.get("kind", "") or "").strip(), 60) or "diagnose",
                "owner": preview(str(raw.get("owner", "") or "").strip(), 80) or "main",
                "depends_on": normalize_depends_on(raw.get("depends_on", [current_subtask_number])),
                "acceptance_criteria": acceptance_items or ["Recovery step is clearly defined"],
            }
        )
    return normalized


def normalize_depends_on(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    normalized: List[str] = []
    for item in value[:5]:
        text = str(item or "").strip()
        if text:
            normalized.append(text)
    return normalized
