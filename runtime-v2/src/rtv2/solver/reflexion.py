"""Reflexion helper for runtime-v2 solver."""

from __future__ import annotations

from rtv2.judge import BaseJudge
from rtv2.model import GenerationConfig, ModelProvider
from rtv2.solver.models import ReflexionAction, ReflexionInput, ReflexionResult


class RuntimeReflexion(BaseJudge):
    """Produce a concise reflexion result for solver-side recovery."""

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

    def reflect(self, input: ReflexionInput) -> ReflexionResult:
        return self._run_loop(input)

    @staticmethod
    def _build_initial_messages(input: ReflexionInput) -> list[dict[str, str]]:
        return [
            {
                "role": "system",
                "content": (
                    "You are a solver-side reflexion helper. "
                    "Diagnose the latest local failure and suggest the next action. "
                    "Do not call tools. Return JSON only. "
                    "If you need another internal review round, return {\"thought\": \"...\"}. "
                    "If you are ready to decide, return "
                    "{\"summary\": \"...\", \"next_attempt_hint\": \"...\", "
                    "\"action\": \"retry_current_node|mark_blocked|mark_failed|request_replan\"}."
                ),
            },
            {
                "role": "user",
                "content": "\n".join(
                    [
                        f"Node id: {input.node_id or '(empty)'}",
                        f"Node name: {input.node_name or '(empty)'}",
                        f"Trigger type: {input.trigger_type or '(empty)'}",
                        "Latest summary:",
                        input.latest_summary or "(empty)",
                        "Issues:",
                        "\n".join(f"- {item}" for item in input.issues) or "(empty)",
                    ]
                ),
            },
        ]

    def _default_thought(self) -> str:
        return "Continue reflexion."

    def _build_continue_instruction(self, round_number: int) -> str:
        return (
            f"Continue solver reflexion. This is round {round_number} "
            f"of at most {self.max_rounds}. Return JSON only."
        )

    @staticmethod
    def _extract_result(payload: dict[str, object]) -> ReflexionResult | None:
        summary = str(payload.get("summary", "") or "").strip()
        next_attempt_hint = str(payload.get("next_attempt_hint", "") or "").strip()
        raw_action = str(payload.get("action", "") or "").strip().lower()
        if not summary and not next_attempt_hint and not raw_action:
            return None
        if not summary:
            raise ValueError("Reflexion summary is required when returning a result")
        if not next_attempt_hint:
            raise ValueError("Reflexion next_attempt_hint is required when returning a result")
        if raw_action not in {action.value for action in ReflexionAction}:
            raise ValueError("Reflexion action is invalid")
        return ReflexionResult(
            summary=summary,
            next_attempt_hint=next_attempt_hint,
            action=ReflexionAction(raw_action),
        )

    @staticmethod
    def _build_round_limit_result() -> ReflexionResult:
        return ReflexionResult(
            summary="Reflexion exceeded the maximum number of rounds.",
            next_attempt_hint="Escalate the current failure to a higher-level controller.",
            action=ReflexionAction.REQUEST_REPLAN,
        )
