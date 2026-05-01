"""Lightweight verifier agent for runtime-v2 finalize."""

from __future__ import annotations

from rtv2.finalize.models import Handoff, VerificationResult
from rtv2.judge import BaseJudge, JudgeResultStatus
from rtv2.model import GenerationConfig, ModelProvider
from rtv2.prompting import ExecutionPromptAssembler, VerifierPromptInput


VerificationResultStatus = JudgeResultStatus


class RuntimeVerifier(BaseJudge):
    """Run a lightweight multi-round verifier loop over a final handoff."""

    def __init__(
        self,
        *,
        model_provider: ModelProvider | None = None,
        generation_config: GenerationConfig | None = None,
        max_rounds: int = 20,
        prompt_assembler: ExecutionPromptAssembler | None = None,
    ) -> None:
        super().__init__(
            model_provider=model_provider,
            generation_config=generation_config or GenerationConfig(temperature=0.1, max_tokens=600),
            max_rounds=max_rounds,
            default_max_tokens=600,
        )
        self.prompt_assembler = prompt_assembler or ExecutionPromptAssembler()

    def verify(self, handoff: Handoff) -> VerificationResult:
        """Verify the final handoff through a bounded multi-round loop."""

        return self._run_loop(handoff)

    def _build_initial_messages(self, handoff: Handoff) -> list[dict[str, str]]:
        prompt = self.prompt_assembler.build_verifier_prompt(
            VerifierPromptInput(
                user_input=handoff.user_input,
                goal=handoff.goal,
                graph_summary=handoff.graph_summary,
                final_output=handoff.final_output,
            )
        )
        rendered_prompt = "\n\n".join(
            [
                prompt.base_prompt,
                prompt.phase_prompt,
                prompt.dynamic_injection,
            ]
        )
        return [
            {
                "role": "system",
                "content": rendered_prompt,
            },
        ]

    def _default_thought(self) -> str:
        return "Continue verification."

    def _build_continue_instruction(self, round_number: int) -> str:
        return (
            f"Continue final verification. This is round {round_number} "
            f"of at most {self.max_rounds}. Return JSON only."
        )

    @staticmethod
    def _extract_result(payload: dict[str, object]) -> VerificationResult | None:
        raw_status = str(payload.get("result_status", "") or "").strip().lower()
        if not raw_status:
            return None
        if raw_status not in {VerificationResultStatus.PASS.value, VerificationResultStatus.FAIL.value}:
            raise ValueError("Verifier result_status must be pass or fail")

        summary = str(payload.get("summary", "") or "").strip()
        if not summary:
            raise ValueError("Verifier summary is required when returning a verdict")

        raw_issues = payload.get("issues", [])
        if not isinstance(raw_issues, list):
            raise ValueError("Verifier issues must be a list")
        issues = [str(issue or "").strip() for issue in raw_issues]
        if any(not issue for issue in issues):
            raise ValueError("Verifier issues entries must be non-empty strings")

        return VerificationResult(
            result_status=VerificationResultStatus(raw_status),
            summary=summary,
            issues=issues,
        )

    @staticmethod
    def _build_round_limit_result() -> VerificationResult:
        return VerificationResult(
            result_status=VerificationResultStatus.FAIL,
            summary="Verifier exceeded the maximum number of rounds.",
            issues=["verifier round limit reached"],
        )
