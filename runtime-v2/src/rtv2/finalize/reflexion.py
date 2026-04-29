"""Run-level reflexion helper for finalize verification failures."""

from __future__ import annotations

from dataclasses import dataclass

from rtv2.finalize.models import RunReflexionAction, RunReflexionInput, RunReflexionResult
from rtv2.judge import BaseJudge
from rtv2.model import GenerationConfig, ModelProvider


@dataclass(slots=True)
class PromptedRunReflexionInput:
    input: RunReflexionInput
    prompt_text: str


class FinalizeReflexion(BaseJudge):
    """Produce a concise run-level reflexion result after verification failure."""

    def __init__(
        self,
        *,
        model_provider: ModelProvider | None = None,
        generation_config: GenerationConfig | None = None,
        max_rounds: int = 10,
    ) -> None:
        super().__init__(
            model_provider=model_provider,
            generation_config=generation_config or GenerationConfig(temperature=0.1, max_tokens=500),
            max_rounds=max_rounds,
            default_max_tokens=500,
        )

    def reflect(self, input: RunReflexionInput, prompt_text: str) -> RunReflexionResult:
        return self._run_loop(PromptedRunReflexionInput(input=input, prompt_text=prompt_text))

    @staticmethod
    def _build_initial_messages(input: PromptedRunReflexionInput) -> list[dict[str, str]]:
        return [
            {
                "role": "system",
                "content": (
                    "You are a run-level reflexion helper after final verification failure. "
                    "Use the provided three-block prompt as the formal context. "
                    "Do not call tools. Return JSON only. "
                    "If you need another internal review round, return {\"thought\": \"...\"}. "
                    "If you are ready to decide, return "
                    "{\"summary\": \"...\", \"action\": \"request_replan|finish_failed\"}."
                ),
            },
            {
                "role": "user",
                "content": input.prompt_text,
            },
        ]

    def _default_thought(self) -> str:
        return "Continue run-level reflexion."

    def _build_continue_instruction(self, round_number: int) -> str:
        return (
            f"Continue run-level reflexion. This is round {round_number} "
            f"of at most {self.max_rounds}. Return JSON only."
        )

    @staticmethod
    def _extract_result(payload: dict[str, object]) -> RunReflexionResult | None:
        summary = str(payload.get("summary", "") or "").strip()
        raw_action = str(payload.get("action", "") or "").strip().lower()
        if not summary and not raw_action:
            return None
        if not summary:
            raise ValueError("Run reflexion summary is required when returning a result")
        if raw_action not in {action.value for action in RunReflexionAction}:
            raise ValueError("Run reflexion action is invalid")
        return RunReflexionResult(
            summary=summary,
            action=RunReflexionAction(raw_action),
        )

    @staticmethod
    def _build_round_limit_result() -> RunReflexionResult:
        return RunReflexionResult(
            summary="Run reflexion exceeded the maximum number of rounds.",
            action=RunReflexionAction.REQUEST_REPLAN,
        )
