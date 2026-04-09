from typing import Optional

from app.core.model.base import GenerationConfig, ModelProvider
from app.eval.agent import VerifierAgent
from app.eval.schema import RunOutcome, TaskSpec, VerifierResult
from app.eval.verifiers.base import Verifier


class LLMJudgeVerifier(Verifier):
    name = "verifier_agent_judge"

    def __init__(
        self,
        model_provider: ModelProvider,
        generation_config: Optional[GenerationConfig] = None,
    ):
        self.agent = VerifierAgent(
            model_provider=model_provider,
            generation_config=generation_config,
        )

    def verify(self, task_spec: TaskSpec, run_outcome: RunOutcome) -> VerifierResult:
        try:
            parsed = self.agent.evaluate(task_spec=task_spec, run_outcome=run_outcome)
            return VerifierResult(
                verifier_name=self.name,
                passed=bool(parsed["passed"]),
                hard=False,
                score=float(parsed["score"]),
                confidence=0.75,
                reason=str(parsed["reason"]),
                evidence={
                    "agent_checks": parsed.get("checks", []),
                    "judge_output_preview": str(parsed.get("raw", ""))[:500],
                },
            )
        except Exception as e:
            return VerifierResult(
                verifier_name=self.name,
                passed=True,
                hard=False,
                score=None,
                confidence=0.2,
                reason=f"llm_judge_unavailable: {e}",
                evidence={},
            )
