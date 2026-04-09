from typing import List, Optional

from app.core.model.base import GenerationConfig, ModelProvider
from app.eval.schema import RunJudgement, RunOutcome, TaskSpec, VerifierResult
from app.eval.verifiers.base import Verifier
from app.eval.verifiers.deterministic import build_default_deterministic_verifiers
from app.eval.verifiers.llm_judge import LLMJudgeVerifier


POSITIVE_HINTS = [
    "已完成",
    "完成了",
    "done",
    "completed",
    "success",
    "成功",
]
NEGATIVE_HINTS = [
    "未完成",
    "失败",
    "error",
    "无法",
]


def infer_self_reported_success(final_answer: str, stop_reason: str) -> bool:
    if stop_reason in {"length", "content_filter", "model_failed", "max_steps_reached", "tool_failed_before_stop"}:
        return False
    text = (final_answer or "").strip().lower()
    if not text:
        return False
    if any(hint in text for hint in NEGATIVE_HINTS):
        return False
    if any(hint in text for hint in POSITIVE_HINTS):
        return True
    return stop_reason in {"stop", "fallback_content", "completed"}


class EvalOrchestrator:
    def __init__(
        self,
        verifiers: Optional[List[Verifier]] = None,
        enable_llm_judge: bool = False,
        llm_judge_provider: Optional[ModelProvider] = None,
        llm_judge_config: Optional[GenerationConfig] = None,
    ):
        self.verifiers = verifiers or build_default_deterministic_verifiers()
        self.enable_llm_judge = enable_llm_judge
        self.llm_judge_provider = llm_judge_provider
        self.llm_judge_config = llm_judge_config

    def _build_verifier_chain(self, task_spec: TaskSpec) -> List[Verifier]:
        chain: List[Verifier] = list(self.verifiers)
        should_enable_llm_judge = self.enable_llm_judge or task_spec.llm_judge_enabled
        if should_enable_llm_judge and self.llm_judge_provider is not None:
            chain.append(
                LLMJudgeVerifier(
                    model_provider=self.llm_judge_provider,
                    generation_config=self.llm_judge_config,
                )
            )
        return chain

    def evaluate(self, task_spec: TaskSpec, run_outcome: RunOutcome) -> RunJudgement:
        verifier_results: List[VerifierResult] = []
        for verifier in self._build_verifier_chain(task_spec):
            verifier_results.append(verifier.verify(task_spec=task_spec, run_outcome=run_outcome))

        hard_failures = [r for r in verifier_results if r.hard and not r.passed]
        soft_scores = [r.score for r in verifier_results if not r.hard and r.score is not None]
        avg_soft_score = sum(soft_scores) / len(soft_scores) if soft_scores else 1.0

        if hard_failures:
            verified_success = False
            final_status = "fail"
            failure_type = hard_failures[0].verifier_name
        elif avg_soft_score < task_spec.soft_score_threshold:
            verified_success = False
            final_status = "partial"
            failure_type = "soft_score_below_threshold"
        else:
            verified_success = True
            final_status = "pass"
            failure_type = None

        confidences = [max(0.0, min(1.0, r.confidence)) for r in verifier_results] or [0.5]
        confidence = sum(confidences) / len(confidences)
        self_reported_success = infer_self_reported_success(run_outcome.final_answer, run_outcome.stop_reason)
        overclaim = self_reported_success and not verified_success

        return RunJudgement(
            self_reported_success=self_reported_success,
            verified_success=verified_success,
            final_status=final_status,
            failure_type=failure_type,
            overclaim=overclaim,
            confidence=confidence,
            verifier_breakdown=verifier_results,
        )
