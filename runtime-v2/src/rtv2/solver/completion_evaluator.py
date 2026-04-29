"""Node-level completion evaluator for runtime-v2."""

from __future__ import annotations

from rtv2.judge import BaseJudge, JudgeResultStatus
from rtv2.model import GenerationConfig, ModelProvider
from rtv2.solver.models import CompletionCheckInput, CompletionCheckResult


class CompletionEvaluator(BaseJudge):
    """Evaluate whether a node is ready to be marked completed."""

    def __init__(
        self,
        *,
        model_provider: ModelProvider | None = None,
        generation_config: GenerationConfig | None = None,
        max_rounds: int = 10,
    ) -> None:
        super().__init__(
            model_provider=model_provider,
            generation_config=generation_config or GenerationConfig(temperature=0.1, max_tokens=600),
            max_rounds=max_rounds,
            default_max_tokens=600,
        )

    def evaluate(self, input: CompletionCheckInput) -> CompletionCheckResult:
        return self._run_loop(input)

    @staticmethod
    def _build_initial_messages(input: CompletionCheckInput) -> list[dict[str, str]]:
        return [
            {
                "role": "system",
                "content": (
                    "You are an independent node-level completion evaluator. "
                    "Judge only whether the current node is sufficiently complete. "
                    "Do not call tools. Return JSON only. "
                    "If you need another internal review round, return {\"thought\": \"...\"}. "
                    "If you are ready to decide, return "
                    "{\"result_status\": \"pass|fail\", \"summary\": \"...\", \"issues\": [\"...\"]}."
                ),
            },
            {
                "role": "user",
                "content": "\n".join(
                    [
                        f"Node id: {input.node_id or '(empty)'}",
                        f"Node name: {input.node_name or '(empty)'}",
                        f"Node kind: {input.node_kind or '(empty)'}",
                        "Node description:",
                        input.node_description or "(empty)",
                        "Completion summary:",
                        input.completion_summary or "(empty)",
                        "Completion evidence:",
                        "\n".join(f"- {item}" for item in input.completion_evidence) or "(empty)",
                        "Completion notes:",
                        "\n".join(f"- {item}" for item in input.completion_notes) or "(empty)",
                        "Completion reason:",
                        input.completion_reason or "(empty)",
                    ]
                ),
            },
        ]

    def _default_thought(self) -> str:
        return "Continue completion evaluation."

    def _build_continue_instruction(self, round_number: int) -> str:
        return (
            f"Continue node completion evaluation. This is round {round_number} "
            f"of at most {self.max_rounds}. Return JSON only."
        )

    @staticmethod
    def _extract_result(payload: dict[str, object]) -> CompletionCheckResult | None:
        raw_status = str(payload.get("result_status", "") or "").strip().lower()
        if not raw_status:
            return None
        if raw_status not in {JudgeResultStatus.PASS.value, JudgeResultStatus.FAIL.value}:
            raise ValueError("Completion evaluator result_status must be pass or fail")

        summary = str(payload.get("summary", "") or "").strip()
        if not summary:
            raise ValueError("Completion evaluator summary is required when returning a verdict")

        raw_issues = payload.get("issues", [])
        if not isinstance(raw_issues, list):
            raise ValueError("Completion evaluator issues must be a list")
        issues = [str(issue or "").strip() for issue in raw_issues]
        if any(not issue for issue in issues):
            raise ValueError("Completion evaluator issues entries must be non-empty strings")

        return CompletionCheckResult(
            result_status=JudgeResultStatus(raw_status),
            summary=summary,
            issues=issues,
        )

    @staticmethod
    def _build_round_limit_result() -> CompletionCheckResult:
        return CompletionCheckResult(
            result_status=JudgeResultStatus.FAIL,
            summary="Completion evaluator exceeded the maximum number of rounds.",
            issues=["completion evaluator round limit reached"],
        )
