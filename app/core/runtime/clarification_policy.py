import time
from typing import Any, Callable, Dict

from app.config import load_runtime_model_config
from app.core.model.base import GenerationConfig, ModelProvider
from app.core.runtime.runtime_utils import is_clarification_request
from app.eval.verification_handoff_service import clamp_float


CLARIFICATION_JUDGE_SYSTEM_PROMPT = """你是一个二分类判定器，只负责判断 assistant 文本是否在向用户索取缺失信息。

判定标准：
1) 若 assistant 明确要求用户补充/确认关键信息（例如范围、目标、时间、验收标准）后才能继续执行，则是澄清请求。
2) 礼貌问候、一般性反问、结果交付后的可选追问，不算澄清请求。
3) 只输出 JSON，不要输出 markdown 或额外文本。
"""

CLARIFICATION_JUDGE_USER_PROMPT_TEMPLATE = """请判定下面 assistant 回复是否为澄清请求。

返回 JSON:
{{
  "is_clarification_request": <true|false>,
  "confidence": <0-1 浮点>,
  "reason": "<简短原因>"
}}

用户最新输入：
{user_input}

assistant 回复：
{assistant_output}
"""


def build_clarification_judge_config() -> GenerationConfig:
    options: Dict[str, Any] = {}
    try:
        model_cfg = load_runtime_model_config()
        mini_id = str(getattr(model_cfg, "mini_model_id", "") or "").strip()
        if mini_id:
            options["model"] = mini_id
    except Exception:
        pass
    return GenerationConfig(
        temperature=0.0,
        max_tokens=160,
        provider_options=options,
    )


def judge_clarification_request(
    content: str,
    user_input: str,
    task_id: str,
    run_id: str,
    step: int,
    model_provider: ModelProvider,
    enable_llm_clarification_judge: bool,
    clarification_judge_confidence_threshold: float,
    enable_clarification_heuristic_fallback: bool,
    parse_json_dict: Callable[[str], Dict[str, Any]],
    preview: Callable[[str, int], str],
    emit_event: Callable[..., Dict[str, Any]],
) -> Dict[str, Any]:
    default_confidence = 0.5
    if not enable_llm_clarification_judge:
        return {
            "is_clarification_request": is_clarification_request(content),
            "confidence": default_confidence,
            "source": "heuristic",
            "reason": "llm_judge_disabled",
        }

    emit_event(
        task_id=task_id,
        run_id=run_id,
        actor="main",
        role="general",
        event_type="clarification_judge_started",
        payload={"step": step, "content_preview": preview(content, 300)},
    )
    started_at = time.perf_counter()
    fallback_reason = ""
    try:
        prompt = CLARIFICATION_JUDGE_USER_PROMPT_TEMPLATE.format(
            user_input=user_input.strip() or "(empty)",
            assistant_output=content.strip() or "(empty)",
        )
        output = model_provider.generate(
            messages=[
                {"role": "system", "content": CLARIFICATION_JUDGE_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            tools=[],
            config=build_clarification_judge_config(),
        )
        parsed = parse_json_dict(output.content)
        decision_raw = parsed.get("is_clarification_request")
        if not isinstance(decision_raw, bool):
            fallback_reason = "invalid_output_missing_boolean"
            raise ValueError(fallback_reason)
        confidence_raw = parsed.get("confidence", default_confidence)
        try:
            confidence = clamp_float(float(confidence_raw), default_confidence)
        except Exception:
            confidence = default_confidence
        decision = bool(decision_raw) and confidence >= clarification_judge_confidence_threshold
        reason = str(parsed.get("reason", "") or "")
        emit_event(
            task_id=task_id,
            run_id=run_id,
            actor="main",
            role="general",
            event_type="clarification_judge_completed",
            payload={
                "step": step,
                "decision": decision,
                "decision_raw": bool(decision_raw),
                "confidence": confidence,
                "threshold": clarification_judge_confidence_threshold,
                "source": "llm",
                "reason": reason,
                "latency_ms": int(max((time.perf_counter() - started_at) * 1000, 0)),
            },
        )
        return {
            "is_clarification_request": decision,
            "confidence": confidence,
            "source": "llm",
            "reason": reason,
        }
    except Exception as e:
        fallback_reason = fallback_reason or str(e) or "llm_judge_exception"

    if enable_clarification_heuristic_fallback:
        fallback_decision = is_clarification_request(content)
        emit_event(
            task_id=task_id,
            run_id=run_id,
            actor="main",
            role="general",
            event_type="clarification_judge_fallback",
            payload={
                "step": step,
                "reason": fallback_reason,
                "fallback_decision": fallback_decision,
                "source": "heuristic",
                "latency_ms": int(max((time.perf_counter() - started_at) * 1000, 0)),
            },
        )
        return {
            "is_clarification_request": fallback_decision,
            "confidence": default_confidence,
            "source": "heuristic_fallback",
            "reason": fallback_reason,
        }
    return {
        "is_clarification_request": False,
        "confidence": default_confidence,
        "source": "llm_no_fallback",
        "reason": fallback_reason,
    }
