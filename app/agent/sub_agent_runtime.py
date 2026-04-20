import json
from typing import Any, Dict, List, Optional

from app.core.memory.base import MemoryStore
from app.core.model import GenerationConfig, ModelProvider
from app.core.runtime.tool_execution import handle_native_tool_calls
from app.core.tools.registry import ToolRegistry
from app.observability.events import emit_event


class SubAgentRuntime:
    """A lightweight runtime for subagents without prepare/todo orchestration."""

    def __init__(
        self,
        model_provider: ModelProvider,
        tool_registry: ToolRegistry,
        system_prompt: str,
        max_steps: int = 25,
        memory_store: Optional[MemoryStore] = None,
        generation_config: Optional[GenerationConfig] = None,
    ) -> None:
        self.model_provider = model_provider
        self.tool_registry = tool_registry
        self.system_prompt = system_prompt
        self.max_steps = max(int(max_steps), 1)
        self.memory_store = memory_store
        self.generation_config = generation_config

    def _trace(self, message: str) -> None:
        print(message)

    def _preview(self, value: Any, limit: int = 200) -> str:
        text = "" if value is None else str(value)
        text = text.replace("\n", "\\n")
        return text if len(text) <= limit else f"{text[:limit]}..."

    def _preview_json(self, value: Any, limit: int = 200) -> str:
        try:
            rendered = json.dumps(value, ensure_ascii=False)
        except Exception:
            rendered = str(value)
        return self._preview(rendered, limit)

    def _extract_finish_reason_and_message(self, raw: Dict[str, Any]) -> tuple[str, Dict[str, Any]]:
        choices = raw.get("choices", []) if isinstance(raw, dict) else []
        if not choices:
            return "", {}
        first = choices[0] if isinstance(choices[0], dict) else {}
        finish_reason = str(first.get("finish_reason", "") or "").strip()
        message = first.get("message", {}) if isinstance(first.get("message", {}), dict) else {}
        return finish_reason, message

    def run(
        self,
        user_input: str,
        task_id: str = "subagent_task",
        run_id: str = "subagent_run",
    ) -> str:
        messages: List[Dict[str, Any]] = [{"role": "system", "content": self.system_prompt}]
        if self.memory_store:
            messages.extend(self.memory_store.get_recent_messages(task_id, limit=20))
        messages.append({"role": "user", "content": user_input})

        emit_event(
            task_id=task_id,
            run_id=run_id,
            actor="main",
            role="general",
            event_type="task_started",
        )
        self._trace(f"[runtime] task_started task_id={task_id} run_id={run_id}")
        if self.memory_store:
            self.memory_store.append_message(task_id, "user", user_input, run_id=run_id, step_id="1")

        final_answer = ""
        runtime_status = "ok"
        stop_reason = "stop"

        for step in range(1, self.max_steps + 1):
            try:
                self._trace(f"[step {step}] model_request")
                model_output = self.model_provider.generate(
                    messages=messages,
                    tools=self.tool_registry.list_tool_schemas(),
                    config=self.generation_config,
                )
            except Exception as exc:
                runtime_status = "error"
                stop_reason = "model_failed"
                final_answer = f"模型调用失败：{exc}"
                self._trace(f"[step {step}] model_failed error={exc}")
                emit_event(
                    task_id=task_id,
                    run_id=run_id,
                    actor="main",
                    role="general",
                    event_type="model_failed",
                    status="error",
                    payload={"error": str(exc)},
                )
                break

            finish_reason, raw_message = self._extract_finish_reason_and_message(model_output.raw)
            content = str(raw_message.get("content", "") or model_output.content or "").strip()
            tool_calls = raw_message.get("tool_calls", []) if isinstance(raw_message, dict) else []
            self._trace(
                f"[step {step}] model_response finish_reason={finish_reason or 'none'} "
                f"content={self._preview(content)} tool_calls={len(tool_calls) if isinstance(tool_calls, list) else 0}"
            )

            if finish_reason == "tool_calls" and isinstance(tool_calls, list) and tool_calls:
                assistant_tool_message = {
                    "role": "assistant",
                    "content": raw_message.get("content", "") or "",
                    "tool_calls": tool_calls,
                }
                messages.append(assistant_tool_message)
                if self.memory_store:
                    self.memory_store.append_message(
                        task_id,
                        "assistant",
                        raw_message.get("content", "") or "",
                        tool_calls=tool_calls,
                        run_id=run_id,
                        step_id=str(step),
                    )
                self._trace(f"[step {step}] execute_tool_calls count={len(tool_calls)}")
                handle_native_tool_calls(
                    tool_calls=tool_calls,
                    messages=messages,
                    task_id=task_id,
                    run_id=run_id,
                    step_id=str(step),
                    tool_registry=self.tool_registry,
                    memory_store=self.memory_store,
                    enrich_runtime_tool_args=lambda tool_name, tool_args, _task_id, _run_id, _step_id: tool_args,
                    emit_event=emit_event,
                    trace=self._trace,
                    preview_json=self._preview_json,
                )
                continue

            assistant_message = {"role": "assistant", "content": content}
            messages.append(assistant_message)
            if self.memory_store:
                self.memory_store.append_message(
                    task_id,
                    "assistant",
                    content,
                    run_id=run_id,
                    step_id=str(step),
                )

            final_answer = content or "已完成。"
            self._trace(f"[step {step}] completed finish_reason={finish_reason or 'none'} final={self._preview(final_answer)}")
            break
        else:
            runtime_status = "error"
            stop_reason = "max_steps_exceeded"
            final_answer = "任务未能在限定步数内完成。"
            self._trace(f"[runtime] stopped reason={stop_reason}")

        emit_event(
            task_id=task_id,
            run_id=run_id,
            actor="main",
            role="general",
            event_type="task_finished",
            status=runtime_status,
            payload={
                "stop_reason": stop_reason,
                "runtime_state": "completed" if runtime_status == "ok" else "failed",
                "has_tool_failures": False,
                "tool_failure_count": 0,
            },
        )
        self._trace(f"[runtime] task_finished final={self._preview(final_answer)}")
        return final_answer
