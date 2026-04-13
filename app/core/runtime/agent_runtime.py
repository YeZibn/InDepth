import json
import re
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

from app.config import RuntimeCompressionConfig, load_runtime_compression_config
from app.eval.orchestrator import EvalOrchestrator
from app.eval.schema import RunOutcome, TaskSpec
from app.core.model.base import GenerationConfig, ModelProvider
from app.core.memory.base import MemoryStore
from app.core.memory.system_memory_store import SystemMemoryStore
from app.core.tools.registry import ToolRegistry
from app.observability.events import emit_event


RUNTIME_SYSTEM_PROMPT = """你是 InDepth 智能体运行时中的助手。
你可以回答问题，或调用工具。

优先使用模型原生 tool-calling 能力来调用工具。
当无需调用工具时，直接输出最终回答文本。

调用 `update_task_status` 时，`status` 只能使用：`pending`、`in-progress`、`completed`。
注意：必须使用 `in-progress`（连字符），不要使用 `in_progress`（下划线）。
"""


class AgentRuntime:
    def __init__(
        self,
        model_provider: ModelProvider,
        tool_registry: ToolRegistry,
        system_prompt: str = "",
        max_steps: int = 50,
        memory_store: Optional[MemoryStore] = None,
        skill_prompt: str = "",
        trace_steps: bool = True,
        trace_printer: Optional[Callable[[str], None]] = None,
        generation_config: Optional[GenerationConfig] = None,
        eval_orchestrator: Optional[EvalOrchestrator] = None,
        enable_llm_judge: bool = False,
        system_memory_store: Optional[SystemMemoryStore] = None,
        compression_config: Optional[RuntimeCompressionConfig] = None,
    ):
        self.model_provider = model_provider
        self.tool_registry = tool_registry
        self.system_prompt = (system_prompt or "").strip()
        self.max_steps = max_steps
        self.memory_store = memory_store
        self.skill_prompt = (skill_prompt or "").strip()
        self.trace_steps = trace_steps
        self.trace_printer = trace_printer or print
        self.generation_config = generation_config
        self.eval_orchestrator = eval_orchestrator or EvalOrchestrator(
            enable_llm_judge=enable_llm_judge,
            llm_judge_provider=model_provider,
            llm_judge_config=generation_config,
        )
        self.system_memory_store = system_memory_store
        self.compression_config = compression_config or load_runtime_compression_config()
        self.last_runtime_state = "idle"
        self.last_stop_reason = ""
        self.last_run_id = ""
        self.last_task_id = ""

    def run(
        self,
        user_input: str,
        task_id: str = "runtime_task",
        run_id: str = "runtime_run",
        task_spec: Optional[Dict[str, Any]] = None,
        resume_from_waiting: bool = False,
    ) -> str:
        self.last_run_id = run_id
        self.last_task_id = task_id
        self.last_runtime_state = "running"
        self.last_stop_reason = ""
        history = self.memory_store.get_recent_messages(task_id, limit=20) if self.memory_store else []
        messages: List[Dict[str, Any]] = [{"role": "system", "content": self._build_system_prompt()}] + history + [
            {"role": "user", "content": user_input}
        ]
        tools = self.tool_registry.list_tool_schemas()
        if resume_from_waiting:
            emit_event(
                task_id=task_id,
                run_id=run_id,
                actor="main",
                role="general",
                event_type="user_clarification_received",
            )
            emit_event(
                task_id=task_id,
                run_id=run_id,
                actor="main",
                role="general",
                event_type="run_resumed",
            )
        else:
            emit_event(
                task_id=task_id,
                run_id=run_id,
                actor="main",
                role="general",
                event_type="task_started",
            )
        self._trace(f"[runtime] task_started task_id={task_id} run_id={run_id}")
        if self.memory_store:
            self.memory_store.append_message(task_id, "user", user_input)

        final_answer: Optional[str] = None
        final_answer_written = False
        last_tool_failures: List[Dict[str, str]] = []
        consecutive_tool_calls = 0
        task_status = "ok"
        stop_reason = "completed"
        runtime_state = "running"
        for step in range(1, self.max_steps + 1):
            messages = self._maybe_compact_mid_run(
                step=step,
                task_id=task_id,
                run_id=run_id,
                messages=messages,
                consecutive_tool_calls=consecutive_tool_calls,
            )
            self._trace(f"[step {step}] model_request")
            try:
                model_output = self.model_provider.generate(
                    messages=messages,
                    tools=tools,
                    config=self.generation_config,
                )
            except Exception as e:
                final_answer = f"模型调用失败：{str(e)}"
                task_status = "error"
                stop_reason = "model_failed"
                runtime_state = "failed"
                self._trace(f"[step {step}] model_failed error={str(e)}")
                emit_event(
                    task_id=task_id,
                    run_id=run_id,
                    actor="main",
                    role="general",
                    event_type="model_failed",
                    status="error",
                    payload={"error": str(e)},
                )
                break
            content = model_output.content.strip()
            finish_reason, raw_message = self._extract_finish_reason_and_message(model_output.raw)
            tool_calls = raw_message.get("tool_calls", []) if isinstance(raw_message, dict) else []
            reasoning_content = raw_message.get("reasoning_content", "") if isinstance(raw_message, dict) else ""
            self._trace(
                f"[step {step}] model_response finish_reason={finish_reason or 'none'} "
                f"content={self._preview(content)} tool_calls={len(tool_calls)}"
            )

            if reasoning_content:
                emit_event(
                    task_id=task_id,
                    run_id=run_id,
                    actor="main",
                    role="general",
                    event_type="model_reasoning",
                    payload={"chars": len(reasoning_content)},
                )

            if finish_reason == "tool_calls":
                consecutive_tool_calls += len(tool_calls)
                self._trace(f"[step {step}] execute_tool_calls count={len(tool_calls)}")
                messages.append(
                    {
                        "role": "assistant",
                        "content": raw_message.get("content", "") or "",
                        "tool_calls": tool_calls,
                    }
                )
                if self.memory_store:
                    self.memory_store.append_message(
                        task_id,
                        "assistant",
                        raw_message.get("content", "") or "",
                        tool_calls=tool_calls,
                    )
                last_tool_failures = self._handle_native_tool_calls(tool_calls, messages, task_id, run_id)
                continue
            consecutive_tool_calls = 0

            if finish_reason == "stop":
                messages.append({"role": "assistant", "content": content})
                if self.memory_store:
                    self.memory_store.append_message(task_id, "assistant", content)
                    final_answer_written = True
                if content:
                    final_answer = content
                    if self._is_clarification_request(content):
                        stop_reason = "awaiting_user_input"
                        runtime_state = "awaiting_user_input"
                        emit_event(
                            task_id=task_id,
                            run_id=run_id,
                            actor="main",
                            role="general",
                            event_type="clarification_requested",
                            payload={
                                "question_preview": self._preview(content, max_len=300),
                                "missing_info_hints": self._extract_missing_info_hints(content),
                                "step": step,
                            },
                        )
                    else:
                        stop_reason = "stop"
                        runtime_state = "completed"
                elif last_tool_failures:
                    details = "; ".join(
                        [
                            f"{item.get('tool', 'unknown')}: {item.get('error', '')}"
                            for item in last_tool_failures[:3]
                        ]
                    )
                    final_answer = f"任务未完成：工具调用失败（{details}）。"
                    task_status = "error"
                    stop_reason = "tool_failed_before_stop"
                    runtime_state = "failed"
                else:
                    final_answer = "模型未返回有效内容，任务可能未完成。"
                    task_status = "error"
                    stop_reason = "empty_stop_content"
                    runtime_state = "failed"
                self._trace(f"[step {step}] completed finish_reason=stop final={self._preview(final_answer)}")
                break

            if finish_reason == "length":
                final_answer = content or "模型达到输出长度上限，已停止。"
                task_status = "error"
                stop_reason = "length"
                runtime_state = "failed"
                self._trace(f"[step {step}] stopped finish_reason=length")
                emit_event(
                    task_id=task_id,
                    run_id=run_id,
                    actor="main",
                    role="general",
                    event_type="model_stopped_length",
                    status="error",
                )
                break

            if finish_reason == "content_filter":
                final_answer = "输出被内容策略拦截，已停止。"
                task_status = "error"
                stop_reason = "content_filter"
                runtime_state = "failed"
                self._trace(f"[step {step}] stopped finish_reason=content_filter")
                emit_event(
                    task_id=task_id,
                    run_id=run_id,
                    actor="main",
                    role="general",
                    event_type="model_stopped_content_filter",
                    status="error",
                )
                break

            messages.append({"role": "assistant", "content": content})
            if self.memory_store:
                self.memory_store.append_message(task_id, "assistant", content)
                final_answer_written = True

            if content:
                final_answer = content
                stop_reason = "fallback_content"
                runtime_state = "completed"
                self._trace(f"[step {step}] completed finish_reason=fallback final={self._preview(final_answer)}")
                break

        if final_answer is None:
            final_answer = "未在预算步数内收敛，建议缩小问题范围后重试。"
            task_status = "error"
            stop_reason = "max_steps_reached"
            runtime_state = "failed"
            self._trace("[runtime] max_steps_reached")

        if runtime_state == "awaiting_user_input":
            self.last_runtime_state = runtime_state
            self.last_stop_reason = stop_reason
            emit_event(
                task_id=task_id,
                run_id=run_id,
                actor="main",
                role="general",
                event_type="verification_skipped",
                payload={
                    "reason": "awaiting_user_input",
                    "stop_reason": stop_reason,
                    "runtime_state": runtime_state,
                },
            )
            self._trace(f"[runtime] paused awaiting_user_input final={self._preview(final_answer)}")
            return final_answer

        # Emit task_finished before verifier evaluation so postmortem evidence is
        # generated and available to verifier agent in the same run.
        emit_event(
            task_id=task_id,
            run_id=run_id,
            actor="main",
            role="general",
            event_type="task_finished",
            status=task_status,
            payload={
                "stop_reason": stop_reason,
                "runtime_state": runtime_state,
                "has_tool_failures": bool(last_tool_failures),
                "tool_failure_count": len(last_tool_failures),
            },
        )

        judgement_payload: Dict[str, Any] = {}
        task_finished_status = task_status
        try:
            spec = TaskSpec.from_dict(task_spec)
            run_outcome = RunOutcome(
                task_id=task_id,
                run_id=run_id,
                user_input=user_input,
                final_answer=final_answer,
                stop_reason=stop_reason,
                tool_failures=last_tool_failures[:],
                runtime_status=task_status,
            )
            emit_event(
                task_id=task_id,
                run_id=run_id,
                actor="main",
                role="general",
                event_type="verification_started",
                payload={"stop_reason": stop_reason},
            )
            judgement = self.eval_orchestrator.evaluate(task_spec=spec, run_outcome=run_outcome)
            judgement_payload = judgement.to_dict()
            emit_event(
                task_id=task_id,
                run_id=run_id,
                actor="main",
                role="general",
                event_type="verification_passed" if judgement.verified_success else "verification_failed",
                status="ok" if judgement.verified_success else "error",
                payload={
                    "final_status": judgement.final_status,
                    "failure_type": judgement.failure_type,
                    "confidence": judgement.confidence,
                },
            )
            emit_event(
                task_id=task_id,
                run_id=run_id,
                actor="main",
                role="general",
                event_type="task_judged",
                status="ok" if judgement.verified_success else "error",
                payload=judgement_payload,
            )
            task_finished_status = "ok" if judgement.verified_success else "error"
        except Exception as e:
            emit_event(
                task_id=task_id,
                run_id=run_id,
                actor="main",
                role="general",
                event_type="verification_failed",
                status="error",
                payload={"error": str(e)},
            )

        self._finalize_task_memory(
            task_id=task_id,
            run_id=run_id,
            user_input=user_input,
            final_answer=final_answer,
            stop_reason=stop_reason,
            runtime_status=task_finished_status,
            tool_failures=last_tool_failures,
        )
        self._trace(f"[runtime] task_finished final={self._preview(final_answer)}")
        if self.memory_store:
            if not final_answer_written:
                self.memory_store.append_message(task_id, "assistant", final_answer)
            compact_final = getattr(self.memory_store, "compact_final", None)
            if callable(compact_final):
                compact_final(task_id)
            else:
                self.memory_store.compact(task_id)
        self.last_runtime_state = runtime_state
        self.last_stop_reason = stop_reason
        return final_answer

    def _maybe_compact_mid_run(
        self,
        step: int,
        task_id: str,
        run_id: str,
        messages: List[Dict[str, Any]],
        consecutive_tool_calls: int,
    ) -> List[Dict[str, Any]]:
        if not self.memory_store or not self.compression_config.enabled_mid_run:
            return messages
        if step <= 1:
            return messages
        compact_mid_run = getattr(self.memory_store, "compact_mid_run", None)
        if not callable(compact_mid_run):
            return messages

        trigger = ""
        mode = "light"
        estimated_tokens = self._estimate_context_tokens(messages)
        usage = self._estimate_context_usage(estimated_tokens)
        if usage >= self.compression_config.strong_token_ratio:
            trigger = "token"
            mode = "strong"
        elif consecutive_tool_calls >= self.compression_config.tool_burst_threshold:
            trigger = "event"
            mode = "light"
        elif (step - 1) % self.compression_config.round_interval == 0:
            trigger = "round"
            mode = "light"
        elif usage >= self.compression_config.light_token_ratio:
            trigger = "token"
            mode = "light"

        if not trigger:
            return messages

        emit_event(
            task_id=task_id,
            run_id=run_id,
            actor="main",
            role="general",
            event_type="context_compression_started",
            payload={
                "trigger": trigger,
                "mode": mode,
                "step": step - 1,
                "estimated_tokens": estimated_tokens,
                "context_usage_ratio": round(usage, 4),
            },
        )
        try:
            result = compact_mid_run(task_id, trigger=trigger, mode=mode)
        except Exception as e:
            emit_event(
                task_id=task_id,
                run_id=run_id,
                actor="main",
                role="general",
                event_type="context_compression_failed",
                status="error",
                payload={"error": str(e), "trigger": trigger, "mode": mode},
            )
            return messages

        if not isinstance(result, dict):
            result = {"success": True, "applied": False}
        if not bool(result.get("success", True)):
            event_type = "context_consistency_check_failed"
            if str(result.get("reason", "")).strip() != "consistency_check_failed":
                event_type = "context_compression_failed"
            emit_event(
                task_id=task_id,
                run_id=run_id,
                actor="main",
                role="general",
                event_type=event_type,
                status="error",
                payload={"result": result, "trigger": trigger, "mode": mode},
            )
            return messages
        emit_event(
            task_id=task_id,
            run_id=run_id,
            actor="main",
            role="general",
            event_type="context_compression_succeeded",
            payload={"trigger": trigger, "mode": mode, "result": result},
        )

        if not result.get("applied"):
            return messages
        history = self.memory_store.get_recent_messages(task_id, limit=20)
        return [{"role": "system", "content": self._build_system_prompt()}] + history

    def _finalize_task_memory(
        self,
        task_id: str,
        run_id: str,
        user_input: str,
        final_answer: str,
        stop_reason: str,
        runtime_status: str,
        tool_failures: List[Dict[str, str]],
    ) -> None:
        try:
            store = self.system_memory_store or SystemMemoryStore()
        except Exception:
            return

        now = datetime.now().astimezone()
        today = now.date().isoformat()
        expire_at = (now.date() + timedelta(days=180)).isoformat()
        mem_id = f"mem_task_{self._slug(task_id)}_{self._slug(run_id)}"
        stage = "postmortem"
        risk_level = "P1" if runtime_status == "error" else "P3"
        short_answer = self._preview(final_answer, max_len=500)
        failure_brief = "; ".join(
            [f"{x.get('tool', 'unknown')}: {x.get('error', '')}" for x in (tool_failures or [])[:3]]
        ).strip()

        card = {
            "id": mem_id,
            "title": f"Task outcome memory: {task_id}",
            "memory_type": "experience",
            "domain": "runtime",
            "tags": ["task-finish", runtime_status, stop_reason],
            "scenario": {
                "stage": stage,
                "trigger_hint": f"Task {task_id} finished with status={runtime_status}",
                "roles": ["dev", "reviewer", "verifier"],
            },
            "problem_pattern": {
                "symptoms": [self._preview(user_input, max_len=200) or "task request"],
                "root_cause_hypothesis": failure_brief or "See task output summary",
                "risk_level": risk_level,
            },
            "solution": {
                "steps": [
                    "Review final answer and runtime stop reason",
                    "Reuse successful pattern or avoid failed tool path in similar tasks",
                ],
                "expected_outcome": short_answer or "Task finished with no explicit answer.",
                "rollback": "Fallback to manual troubleshooting when similar failures repeat",
            },
            "constraints": {
                "applicable_if": ["Same or similar runtime task context appears"],
                "dependencies": [],
            },
            "anti_pattern": {
                "not_applicable_if": ["Task scope differs significantly from this run context"],
                "danger_signals": [failure_brief] if failure_brief else [],
            },
            "evidence": {
                "source_links": [f"urn:runtime:{task_id}:{run_id}"],
                "verified_at": now.isoformat(),
                "verifier": "runtime-framework",
            },
            "impact": {},
            "owner": {"team": "runtime", "primary": "main-agent", "reviewers": []},
            "lifecycle": {
                "status": "active",
                "version": "v1.0",
                "effective_from": today,
                "expire_at": expire_at,
                "last_reviewed_at": today,
                "change_log": [
                    {
                        "version": "v1.0",
                        "changed_at": now.isoformat(),
                        "summary": "Auto-finalized by runtime framework at task completion",
                    }
                ],
            },
            "confidence": "B" if runtime_status == "ok" else "C",
        }
        try:
            store.upsert_card(card)
        except Exception:
            return

        try:
            triggered = emit_event(
                task_id=task_id,
                run_id=run_id,
                actor="main",
                role="general",
                event_type="memory_triggered",
                payload={
                    "stage": stage,
                    "context_id": run_id,
                    "risk_level": risk_level,
                    "source_event": "runtime_forced_finalize",
                },
            )
            trigger_event_id = str(triggered.get("event_id", "")).strip()
            if trigger_event_id:
                emit_event(
                    task_id=task_id,
                    run_id=run_id,
                    actor="main",
                    role="general",
                    event_type="memory_retrieved",
                    payload={
                        "trigger_event_id": trigger_event_id,
                        "memory_id": mem_id,
                        "score": 1.0,
                        "stage": stage,
                        "source": "runtime_finalize_upsert",
                    },
                )
                emit_event(
                    task_id=task_id,
                    run_id=run_id,
                    actor="main",
                    role="general",
                    event_type="memory_decision_made",
                    payload={
                        "trigger_event_id": trigger_event_id,
                        "memory_id": mem_id,
                        "decision": "accepted",
                        "reason": "framework forced finalization",
                        "stage": stage,
                    },
                )
        except Exception:
            pass

    def _slug(self, value: str) -> str:
        text = (value or "").strip().lower()
        text = re.sub(r"[^a-z0-9]+", "-", text)
        text = re.sub(r"-+", "-", text).strip("-")
        return text or "na"

    def _extract_finish_reason_and_message(self, raw: Dict[str, Any]) -> tuple[str, Dict[str, Any]]:
        if not isinstance(raw, dict):
            return "", {}
        choices = raw.get("choices", [])
        if not isinstance(choices, list) or not choices:
            return "", {}
        choice0 = choices[0] if isinstance(choices[0], dict) else {}
        finish_reason = str(choice0.get("finish_reason", "") or "").strip()
        message = choice0.get("message", {})
        if not isinstance(message, dict):
            message = {}
        return finish_reason, message

    def _build_system_prompt(self) -> str:
        extra = f"\n\n{self.system_prompt}" if self.system_prompt else ""
        skill_extra = f"\n\n{self.skill_prompt}" if self.skill_prompt else ""
        return (
            RUNTIME_SYSTEM_PROMPT
            + extra
            + skill_extra
        )

    def _handle_native_tool_calls(
        self,
        tool_calls: List[Dict[str, Any]],
        messages: List[Dict[str, Any]],
        task_id: str,
        run_id: str,
    ) -> List[Dict[str, str]]:
        failures: List[Dict[str, str]] = []
        for call in tool_calls:
            call_id = str(call.get("id", ""))
            fn = call.get("function", {}) if isinstance(call, dict) else {}
            tool_name = str(fn.get("name", "")).strip()
            raw_args = fn.get("arguments", "{}")
            try:
                tool_args = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
                if not isinstance(tool_args, dict):
                    tool_args = {}
            except Exception:
                tool_args = {}
            emit_event(
                task_id=task_id,
                run_id=run_id,
                actor="main",
                role="general",
                event_type="tool_called",
                payload={"tool": tool_name, "args": tool_args},
            )
            result = self.tool_registry.invoke(tool_name, tool_args)
            self._trace(
                f"[tool] name={tool_name} args={self._preview_json(tool_args)} "
                f"success={result.get('success')} result={self._preview_json(result)}"
            )
            event_type = "tool_succeeded" if result.get("success") else "tool_failed"
            if not result.get("success"):
                failures.append(
                    {
                        "tool": tool_name,
                        "error": str(result.get("error", "")).strip(),
                    }
                )
            emit_event(
                task_id=task_id,
                run_id=run_id,
                actor="main",
                role="general",
                event_type=event_type,
                status="ok" if result.get("success") else "error",
                payload={"tool": tool_name},
            )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call_id,
                    "content": json.dumps(result, ensure_ascii=False),
                }
            )
            if self.memory_store:
                self.memory_store.append_message(
                    task_id,
                    "tool",
                    json.dumps(result, ensure_ascii=False),
                    tool_call_id=call_id,
                )
        return failures

    def _trace(self, msg: str) -> None:
        if self.trace_steps:
            try:
                self.trace_printer(msg)
            except Exception:
                pass

    def _preview(self, text: str, max_len: int = 120) -> str:
        value = (text or "").replace("\n", " ").strip()
        if len(value) <= max_len:
            return value
        return value[:max_len] + "..."

    def _preview_json(self, obj: Any, max_len: int = 200) -> str:
        try:
            text = json.dumps(obj, ensure_ascii=False)
        except Exception:
            text = str(obj)
        return self._preview(text, max_len=max_len)

    def _estimate_context_tokens(self, messages: List[Dict[str, Any]]) -> int:
        # Hybrid estimator: CJK chars ~= 1 token, latin words ~= 1 token, plus JSON overhead.
        tokens = 0
        for msg in messages:
            content = str(msg.get("content", "") or "")
            cjk_count = len(re.findall(r"[\u4e00-\u9fff]", content))
            latin_words = len(re.findall(r"[A-Za-z0-9_]+", content))
            punctuation = len(re.findall(r"[^\w\s]", content))
            tokens += cjk_count + latin_words + max(punctuation // 2, 0) + 8  # per-message envelope
            if msg.get("tool_calls"):
                try:
                    tokens += len(json.dumps(msg.get("tool_calls"), ensure_ascii=False)) // 4
                except Exception:
                    tokens += 20
        return max(tokens, 1)

    def _estimate_context_usage(self, estimated_tokens: int) -> float:
        window = max(int(self.compression_config.context_window_tokens), 1024)
        return min(estimated_tokens / window, 1.0)

    def _is_clarification_request(self, content: str) -> bool:
        text = (content or "").strip()
        if not text:
            return False
        lowered = text.lower()
        clarification_hints = [
            "请确认",
            "请补充",
            "请提供",
            "请明确",
            "你是指",
            "是否",
            "能否",
            "which",
            "what exactly",
            "can you clarify",
            "please clarify",
            "need more details",
        ]
        if any(hint in lowered for hint in clarification_hints):
            return True
        if "？" in text or "?" in text:
            complete_hints = ["已完成", "完成了", "done", "completed", "success", "成功"]
            if not any(hint in lowered for hint in complete_hints):
                return True
        return False

    def _extract_missing_info_hints(self, content: str) -> List[str]:
        text = (content or "").strip()
        if not text:
            return []
        fields = [
            ("时间", ["时间", "日期", "截止", "deadline", "when"]),
            ("范围", ["范围", "边界", "scope"]),
            ("目标", ["目标", "预期", "goal", "outcome"]),
            ("环境", ["环境", "分支", "workspace", "repo"]),
            ("验收标准", ["验收", "标准", "acceptance", "criteria"]),
        ]
        lowered = text.lower()
        hits: List[str] = []
        for label, hints in fields:
            if any(h in lowered for h in hints):
                hits.append(label)
        return hits
