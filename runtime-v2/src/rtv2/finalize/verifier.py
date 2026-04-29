"""Lightweight verifier agent for runtime-v2 finalize."""

from __future__ import annotations

import json

from rtv2.finalize.models import Handoff, VerificationResult, VerificationResultStatus
from rtv2.model import GenerationConfig, HttpChatModelProvider, ModelOutput, ModelProvider


class RuntimeVerifier:
    """Run a lightweight multi-round verifier loop over a final handoff."""

    def __init__(
        self,
        *,
        model_provider: ModelProvider | None = None,
        generation_config: GenerationConfig | None = None,
        max_rounds: int = 20,
    ) -> None:
        if max_rounds <= 0:
            raise ValueError("max_rounds must be positive")
        self.model_provider = model_provider or HttpChatModelProvider(
            default_config=GenerationConfig(temperature=0.1, max_tokens=600)
        )
        self.generation_config = generation_config or GenerationConfig(
            temperature=0.1,
            max_tokens=600,
        )
        self.max_rounds = max_rounds

    def verify(self, handoff: Handoff) -> VerificationResult:
        """Verify the final handoff through a bounded multi-round loop."""

        messages = self._build_initial_messages(handoff)
        for round_index in range(self.max_rounds):
            model_output = self.model_provider.generate(
                messages=messages,
                tools=[],
                config=self.generation_config,
            )
            payload = self._load_payload(model_output)
            verdict = self._extract_verification_result(payload)
            if verdict is not None:
                return verdict

            thought = str(payload.get("thought", "") or "").strip() or "Continue verification."
            messages.extend(
                [
                    {"role": "assistant", "content": thought},
                    {
                        "role": "user",
                        "content": (
                            f"Continue final verification. This is round {round_index + 2} "
                            f"of at most {self.max_rounds}. Return JSON only."
                        ),
                    },
                ]
            )

        return VerificationResult(
            result_status=VerificationResultStatus.FAIL,
            summary="Verifier exceeded the maximum number of rounds.",
            issues=["verifier round limit reached"],
        )

    @staticmethod
    def _build_initial_messages(handoff: Handoff) -> list[dict[str, str]]:
        return [
            {
                "role": "system",
                "content": (
                    "You are an independent final verifier agent. "
                    "Your job is to evaluate the provided handoff only. "
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
                        "Final handoff:",
                        f"Goal: {handoff.goal or '(empty)'}",
                        f"User input: {handoff.user_input or '(empty)'}",
                        "Graph summary:",
                        handoff.graph_summary or "(empty)",
                        "Final output:",
                        handoff.final_output or "(empty)",
                    ]
                ),
            },
        ]

    @staticmethod
    def _load_payload(model_output: ModelOutput) -> dict[str, object]:
        text = model_output.content.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines).strip()
        payload = json.loads(text)
        if not isinstance(payload, dict):
            raise ValueError("Verifier output must be a JSON object")
        return payload

    @staticmethod
    def _extract_verification_result(payload: dict[str, object]) -> VerificationResult | None:
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
