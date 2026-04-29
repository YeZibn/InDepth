"""Shared judge-agent base for runtime-v2."""

from __future__ import annotations

import json
from enum import StrEnum
from typing import Any

from rtv2.model import GenerationConfig, HttpChatModelProvider, ModelOutput, ModelProvider


class JudgeResultStatus(StrEnum):
    """Minimal verdict status shared by judge-style agents."""

    PASS = "pass"
    FAIL = "fail"


class BaseJudge:
    """Run a bounded multi-round JSON judge loop."""

    def __init__(
        self,
        *,
        model_provider: ModelProvider | None = None,
        generation_config: GenerationConfig | None = None,
        max_rounds: int,
        default_max_tokens: int = 600,
    ) -> None:
        if max_rounds <= 0:
            raise ValueError("max_rounds must be positive")
        self.model_provider = model_provider or HttpChatModelProvider(
            default_config=GenerationConfig(temperature=0.1, max_tokens=default_max_tokens)
        )
        self.generation_config = generation_config or GenerationConfig(
            temperature=0.1,
            max_tokens=default_max_tokens,
        )
        self.max_rounds = max_rounds

    def _run_loop(self, input: object) -> object:
        messages = self._build_initial_messages(input)
        for round_index in range(self.max_rounds):
            model_output = self.model_provider.generate(
                messages=messages,
                tools=[],
                config=self.generation_config,
            )
            payload = self._load_payload(model_output)
            verdict = self._extract_result(payload)
            if verdict is not None:
                return verdict

            thought = str(payload.get("thought", "") or "").strip() or self._default_thought()
            messages.extend(
                [
                    {"role": "assistant", "content": thought},
                    {
                        "role": "user",
                        "content": self._build_continue_instruction(round_index + 2),
                    },
                ]
            )
        return self._build_round_limit_result()

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
            raise ValueError("Judge output must be a JSON object")
        return payload

    def _default_thought(self) -> str:
        return "Continue evaluation."

    def _build_continue_instruction(self, round_number: int) -> str:
        return f"Continue evaluation. This is round {round_number} of at most {self.max_rounds}. Return JSON only."

    def _build_initial_messages(self, input: object) -> list[dict[str, str]]:
        raise NotImplementedError

    def _extract_result(self, payload: dict[str, Any]) -> object | None:
        raise NotImplementedError

    def _build_round_limit_result(self) -> object:
        raise NotImplementedError
