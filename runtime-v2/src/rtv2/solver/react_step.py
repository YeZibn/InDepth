"""Minimal single-step ReAct runner for runtime-v2."""

from __future__ import annotations

import json
from dataclasses import dataclass

from rtv2.model import GenerationConfig, HttpChatModelProvider, ModelOutput, ModelProvider
from rtv2.solver.models import StepResult, StepStatusSignal
from rtv2.tools import LocalToolExecutor, ToolCall, ToolRegistry


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
    tool_call: ToolCall | None = None
    step_result: StepResult | None = None


class ReActStepRunner:
    """Run a single ReAct step using a real LLM provider."""

    def __init__(
        self,
        *,
        model_provider: ModelProvider | None = None,
        generation_config: GenerationConfig | None = None,
        tool_registry: ToolRegistry | None = None,
        tool_executor: LocalToolExecutor | None = None,
    ) -> None:
        self.model_provider = model_provider or HttpChatModelProvider(
            default_config=GenerationConfig(temperature=0.2, max_tokens=800)
        )
        self.generation_config = generation_config or GenerationConfig(
            temperature=0.2,
            max_tokens=800,
        )
        self.tool_registry = tool_registry
        self.tool_executor = tool_executor or (
            LocalToolExecutor(tool_registry=tool_registry)
            if tool_registry is not None
            else None
        )

    def run_step(self, step_input: ReActStepInput) -> ReActStepOutput:
        """Execute one minimal ReAct step and return structured output."""

        initial_messages = self._build_initial_messages(step_input)
        initial_tools = self.tool_registry.list_tool_schemas() if self.tool_registry is not None else []
        initial_model_output = self.model_provider.generate(
            messages=initial_messages,
            tools=initial_tools,
            config=self.generation_config,
        )
        initial_output = self._parse_model_output(initial_model_output, allow_tool_call=True)
        if initial_output.tool_call is None:
            if initial_output.step_result is None:
                return self._build_failed_output(
                    observation=initial_output.observation or initial_model_output.content.strip(),
                    reason="react step did not return a final step_result",
                )
            return initial_output

        if self.tool_executor is None:
            return self._build_failed_output(
                thought=initial_output.thought,
                action=initial_output.action,
                reason="react step requested a tool call but no tool executor is configured",
            )

        tool_result = self.tool_executor.execute(initial_output.tool_call)
        followup_messages = self._build_followup_messages(
            step_input=step_input,
            tool_call=initial_output.tool_call,
            tool_result_text=self._format_tool_result_text(tool_result),
        )
        final_model_output = self.model_provider.generate(
            messages=followup_messages,
            tools=[],
            config=self.generation_config,
        )
        final_output = self._parse_model_output(final_model_output, allow_tool_call=False)
        if final_output.tool_call is not None:
            return self._build_failed_output(
                thought=final_output.thought or initial_output.thought,
                action=final_output.action or initial_output.action,
                observation=tool_result.output_text,
                reason="react step returned an unexpected second tool call",
                tool_call=initial_output.tool_call,
            )
        if final_output.step_result is None:
            return self._build_failed_output(
                thought=final_output.thought or initial_output.thought,
                action=final_output.action or initial_output.action,
                observation=final_output.observation or tool_result.output_text,
                reason="react step did not return a final step_result after tool execution",
                tool_call=initial_output.tool_call,
            )
        return ReActStepOutput(
            thought=final_output.thought or initial_output.thought,
            action=final_output.action or initial_output.action,
            observation=final_output.observation or tool_result.output_text,
            tool_call=initial_output.tool_call,
            step_result=final_output.step_result,
        )

    @staticmethod
    def _build_initial_messages(step_input: ReActStepInput) -> list[dict[str, str]]:
        return [
            {
                "role": "system",
                "content": (
                    "You are a single-step ReAct executor. "
                    "If a tool is needed, call exactly one tool. "
                    "If no tool is needed, respond with JSON only. "
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

    @staticmethod
    def _build_followup_messages(
        *,
        step_input: ReActStepInput,
        tool_call: ToolCall,
        tool_result_text: str,
    ) -> list[dict[str, str]]:
        return [
            {
                "role": "system",
                "content": (
                    "You are a single-step ReAct executor. "
                    "The tool result is now available. "
                    "Do not call any more tools. "
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
            {
                "role": "user",
                "content": (
                    f"Tool call executed: {tool_call.tool_name}\n"
                    f"Tool arguments: {json.dumps(tool_call.arguments, ensure_ascii=False)}\n"
                    f"Tool result:\n{tool_result_text}"
                ),
            },
        ]

    def _parse_model_output(self, model_output: ModelOutput, *, allow_tool_call: bool) -> ReActStepOutput:
        raw_tool_call = self._extract_raw_tool_call(model_output)
        payload = self._load_json_payload(model_output.content)
        json_tool_call = self._extract_json_tool_call(payload)
        tool_call = raw_tool_call or json_tool_call
        if tool_call is not None:
            return ReActStepOutput(
                thought=self._extract_text_field(payload, "thought"),
                action=self._extract_text_field(payload, "action"),
                observation=self._extract_text_field(payload, "observation"),
                tool_call=tool_call if allow_tool_call else tool_call,
            )

        if payload is None:
            return self._build_failed_output(
                observation=model_output.content.strip(),
                reason="react step output was not valid json",
            )

        thought = self._extract_text_field(payload, "thought")
        action = self._extract_text_field(payload, "action")
        observation = self._extract_text_field(payload, "observation")
        step_result = self._build_step_result(payload)
        return ReActStepOutput(
            thought=thought,
            action=action,
            observation=observation,
            step_result=step_result,
        )

    @staticmethod
    def _extract_raw_tool_call(model_output: ModelOutput) -> ToolCall | None:
        raw = model_output.raw or {}
        choices = raw.get("choices", [])
        if not isinstance(choices, list) or not choices:
            return None
        first_choice = choices[0] if isinstance(choices[0], dict) else {}
        message = first_choice.get("message", {}) if isinstance(first_choice, dict) else {}
        tool_calls = message.get("tool_calls", []) if isinstance(message, dict) else []
        if not isinstance(tool_calls, list) or not tool_calls:
            return None
        first_call = tool_calls[0] if isinstance(tool_calls[0], dict) else {}
        function_payload = first_call.get("function", {}) if isinstance(first_call, dict) else {}
        tool_name = str(function_payload.get("name", "") or "").strip()
        if not tool_name:
            return None
        arguments = ReActStepRunner._coerce_arguments_dict(function_payload.get("arguments", {}))
        return ToolCall(tool_name=tool_name, arguments=arguments)

    @staticmethod
    def _extract_json_tool_call(payload: dict[str, object] | None) -> ToolCall | None:
        if not isinstance(payload, dict):
            return None
        raw_tool_call = payload.get("tool_call")
        if not isinstance(raw_tool_call, dict):
            return None
        tool_name = str(raw_tool_call.get("tool_name", "") or "").strip()
        if not tool_name:
            return None
        arguments = ReActStepRunner._coerce_arguments_dict(raw_tool_call.get("arguments", {}))
        return ToolCall(tool_name=tool_name, arguments=arguments)

    @staticmethod
    def _coerce_arguments_dict(raw_arguments: object) -> dict[str, object]:
        if isinstance(raw_arguments, dict):
            return dict(raw_arguments)
        if isinstance(raw_arguments, str):
            try:
                parsed = json.loads(raw_arguments)
            except json.JSONDecodeError:
                return {}
            if isinstance(parsed, dict):
                return parsed
        return {}

    @staticmethod
    def _extract_text_field(payload: dict[str, object] | None, field: str) -> str:
        if not isinstance(payload, dict):
            return ""
        return str(payload.get(field, "") or "").strip()

    @staticmethod
    def _build_step_result(payload: dict[str, object]) -> StepResult | None:
        status_signal_raw = str(payload.get("status_signal", "") or "").strip()
        if not status_signal_raw:
            return None
        reason = str(payload.get("reason", "") or "").strip()
        try:
            status_signal = StepStatusSignal(status_signal_raw)
        except ValueError:
            status_signal = StepStatusSignal.FAILED
            reason = reason or f"invalid status_signal: {status_signal_raw}"
        return StepResult(
            status_signal=status_signal,
            reason=reason,
        )

    @staticmethod
    def _format_tool_result_text(tool_result) -> str:
        if tool_result.success:
            return tool_result.output_text
        return f"Tool execution failed: {tool_result.error}"

    @staticmethod
    def _build_failed_output(
        *,
        thought: str = "",
        action: str = "",
        observation: str = "",
        reason: str,
        tool_call: ToolCall | None = None,
    ) -> ReActStepOutput:
        return ReActStepOutput(
            thought=thought,
            action=action,
            observation=observation,
            tool_call=tool_call,
            step_result=StepResult(
                status_signal=StepStatusSignal.FAILED,
                reason=reason,
            ),
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
