"""Minimal single-step ReAct runner for runtime-v2."""

from __future__ import annotations

import json
from dataclasses import dataclass

from rtv2.model import GenerationConfig, HttpChatModelProvider, ModelOutput, ModelProvider
from rtv2.solver.models import StepResult, StepStatusSignal


@dataclass(slots=True)
class ReActStepInput:
    """Minimal agent-facing input for a single ReAct step."""

    step_prompt: str


@dataclass(slots=True)
class ReActStepOutput:
    """Minimal agent-facing output for a single ReAct step."""

    thought: str
    action: str
    observation: str
    step_result: StepResult


class ReActStepRunner:
    """Run a single ReAct step using a real LLM provider."""

    def __init__(
        self,
        *,
        model_provider: ModelProvider | None = None,
        generation_config: GenerationConfig | None = None,
    ) -> None:
        self.model_provider = model_provider or HttpChatModelProvider(
            default_config=GenerationConfig(temperature=0.2, max_tokens=800)
        )
        self.generation_config = generation_config or GenerationConfig(
            temperature=0.2,
            max_tokens=800,
        )

    def run_step(self, step_input: ReActStepInput) -> ReActStepOutput:
        """Execute one minimal ReAct step and return structured output."""

        messages = self._build_messages(step_input)
        model_output = self.model_provider.generate(
            messages=messages,
            tools=[],
            config=self.generation_config,
        )
        return self._parse_model_output(model_output)

    @staticmethod
    def _build_messages(step_input: ReActStepInput) -> list[dict[str, str]]:
        return [
            {
                "role": "system",
                "content": (
                    "You are a single-step ReAct executor. "
                    "Respond with JSON only. "
                    'Return keys: thought, action, observation, status_signal, reason. '
                    "status_signal must be one of: progressed, ready_for_completion, blocked, failed. "
                    "If status_signal is not progressed, reason must be non-empty."
                ),
            },
            {
                "role": "user",
                "content": step_input.step_prompt,
            },
        ]

    def _parse_model_output(self, model_output: ModelOutput) -> ReActStepOutput:
        payload = self._load_json_payload(model_output.content)
        if payload is None:
            return ReActStepOutput(
                thought="",
                action="",
                observation=model_output.content.strip(),
                step_result=StepResult(
                    status_signal=StepStatusSignal.FAILED,
                    reason="react step output was not valid json",
                ),
            )

        thought = str(payload.get("thought", "") or "").strip()
        action = str(payload.get("action", "") or "").strip()
        observation = str(payload.get("observation", "") or "").strip()
        status_signal_raw = str(payload.get("status_signal", "") or "").strip() or StepStatusSignal.PROGRESSED.value
        reason = str(payload.get("reason", "") or "").strip()

        try:
            status_signal = StepStatusSignal(status_signal_raw)
        except ValueError:
            status_signal = StepStatusSignal.FAILED
            reason = reason or f"invalid status_signal: {status_signal_raw}"

        step_result = StepResult(
            status_signal=status_signal,
            reason=reason,
        )
        return ReActStepOutput(
            thought=thought,
            action=action,
            observation=observation,
            step_result=step_result,
        )

    @staticmethod
    def _load_json_payload(content: str) -> dict[str, object] | None:
        raw = (content or "").strip()
        if not raw:
            return None

        candidates = [raw]
        if "```" in raw:
            for block in raw.split("```"):
                block = block.strip()
                if not block:
                    continue
                if block.startswith("json"):
                    block = block[4:].strip()
                candidates.append(block)

        for candidate in candidates:
            try:
                parsed = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return parsed
        return None
