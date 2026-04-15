import time
from typing import Any, Callable, Dict, List, Optional

from app.config import (
    RuntimeCompressionConfig,
    RuntimeUserPreferenceConfig,
    load_runtime_compression_config,
    load_runtime_model_config,
    load_runtime_user_preference_config,
)
from app.core.runtime.runtime_utils import (
    estimate_context_tokens,
    estimate_context_usage,
    extract_finish_reason_and_message,
    extract_missing_info_hints,
    is_clarification_request,
    parse_json_dict,
    preview,
    preview_json,
    slug,
)
from app.core.runtime.system_memory_lifecycle import (
    build_memory_metadata_config,
    build_memory_reranker_config,
    build_recall_query,
    build_semantic_memory_title,
    extract_title_topic,
    finalize_task_memory,
    generate_memory_card_metadata_llm,
    inject_system_memory_recall,
    render_memory_recall_block,
    rerank_memory_candidates_llm,
)
from app.core.runtime.tool_execution import (
    enrich_capture_memory_tool_args,
    handle_native_tool_calls,
)
from app.core.runtime.verification_handoff import (
    build_rule_verification_handoff,
    clamp_float,
    generate_verification_handoff_llm,
    normalize_expected_artifacts,
    normalize_handoff_str_list,
    normalize_key_tool_results,
    normalize_verification_handoff,
)
from app.eval.orchestrator import EvalOrchestrator
from app.eval.schema import RunOutcome
from app.core.model.base import GenerationConfig, ModelProvider
from app.core.memory.base import MemoryStore
from app.core.memory.system_memory_store import SystemMemoryStore
from app.core.memory.user_preference_store import UserPreferenceStore
from app.core.tools.registry import ToolRegistry
from app.observability.events import emit_event


RUNTIME_SYSTEM_PROMPT = """你是 InDepth 智能体运行时中的助手。
你可以回答问题，或调用工具。

优先使用模型原生 tool-calling 能力来调用工具。
当无需调用工具时，直接输出最终回答文本。

调用 `update_task_status` 时，`status` 只能使用：`pending`、`in-progress`、`completed`。
注意：必须使用 `in-progress`（连字符），不要使用 `in_progress`（下划线）。
"""

CLARIFICATION_JUDGE_SYSTEM_PROMPT = """你是一个二分类判定器，只负责判断 assistant 文本是否在向用户索取缺失信息。

判定标准：
1) 若 assistant 明确要求用户补充/确认关键信息（例如范围、目标、时间、验收标准）后才能继续执行，则是澄清请求。
2) 礼貌问候、一般性反问、结果交付后的可选追问，不算澄清请求。
3) 只输出 JSON，不要输出 markdown 或额外文本。
"""

CLARIFICATION_JUDGE_USER_PROMPT_TEMPLATE = """请判定下面 assistant 回复是否为澄清请求。

返回 JSON:
{{
  "is_clarification_request": <true|false>,
  "confidence": <0-1 浮点>,
  "reason": "<简短原因>"
}}

用户最新输入：
{user_input}

assistant 回复：
{assistant_output}
"""

USER_PREFERENCE_EXTRACT_SYSTEM_PROMPT = """你是用户偏好抽取器，只能输出 JSON。
目标：从用户输入中提取“明确表达”的偏好，不要猜测。

输出格式：
{
  "updates": [
    {
      "key": "job_role|domain_expertise|interest_topics|language_preference|response_style|tooling_stack|goal_long_term",
      "value": "string 或 string数组",
      "confidence": 0.0,
      "explicit": true,
      "action": "upsert|delete|ignore",
      "evidence_span": "原文证据片段"
    }
  ]
}

规则：
1) 仅输出白名单 key，未知 key 不输出。
2) 只有用户明确表达时 explicit=true。
3) 不输出解释文本，只输出 JSON。
"""

USER_PREFERENCE_EXTRACT_USER_PROMPT_TEMPLATE = """请基于以下用户输入提取偏好更新：

用户输入：
{user_input}
"""


class AgentRuntime:
    START_RECALL_TOP_K = 5
    START_RECALL_MIN_SCORE = 0.65
    START_RECALL_CANDIDATE_POOL = 50

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
        enable_memory_recall_reranker: Optional[bool] = None,
        enable_memory_card_metadata_llm: Optional[bool] = None,
        enable_verification_handoff_llm: Optional[bool] = None,
        enable_llm_clarification_judge: Optional[bool] = None,
        clarification_judge_confidence_threshold: float = 0.60,
        enable_clarification_heuristic_fallback: bool = True,
        system_memory_store: Optional[SystemMemoryStore] = None,
        compression_config: Optional[RuntimeCompressionConfig] = None,
        user_preference_config: Optional[RuntimeUserPreferenceConfig] = None,
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
        self.user_preference_config = user_preference_config or load_runtime_user_preference_config()
        self.user_preference_store: Optional[UserPreferenceStore] = None
        if self.user_preference_config.enabled:
            try:
                self.user_preference_store = UserPreferenceStore(file_path=self.user_preference_config.file_path)
            except Exception:
                self.user_preference_store = None
        if enable_memory_recall_reranker is None:
            # Default on for real providers, off for deterministic test mock provider.
            self.enable_memory_recall_reranker = self.model_provider.__class__.__name__ != "MockModelProvider"
        else:
            self.enable_memory_recall_reranker = bool(enable_memory_recall_reranker)
        if enable_memory_card_metadata_llm is None:
            # Default on for real providers, off for deterministic test mock provider.
            self.enable_memory_card_metadata_llm = self.model_provider.__class__.__name__ != "MockModelProvider"
        else:
            self.enable_memory_card_metadata_llm = bool(enable_memory_card_metadata_llm)
        if enable_verification_handoff_llm is None:
            # Default on for real providers, off for deterministic test mock provider.
            self.enable_verification_handoff_llm = self.model_provider.__class__.__name__ != "MockModelProvider"
        else:
            self.enable_verification_handoff_llm = bool(enable_verification_handoff_llm)
        if enable_llm_clarification_judge is None:
            # Default on for real providers, off for deterministic test mock provider.
            self.enable_llm_clarification_judge = self.model_provider.__class__.__name__ != "MockModelProvider"
        else:
            self.enable_llm_clarification_judge = bool(enable_llm_clarification_judge)
        self.clarification_judge_confidence_threshold = clamp_float(clarification_judge_confidence_threshold, 0.6)
        self.enable_clarification_heuristic_fallback = bool(enable_clarification_heuristic_fallback)
        self.last_runtime_state = "idle"
        self.last_stop_reason = ""
        self.last_run_id = ""
        self.last_task_id = ""

    def run(
        self,
        user_input: str,
        task_id: str = "runtime_task",
        run_id: str = "runtime_run",
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
        messages = self._inject_user_preference_recall(
            task_id=task_id,
            run_id=run_id,
            user_input=user_input,
            messages=messages,
        )
        messages = self._inject_system_memory_recall(
            task_id=task_id,
            run_id=run_id,
            user_input=user_input,
            messages=messages,
        )
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
        verification_handoff: Optional[Dict[str, Any]] = None
        handoff_source = "fallback_rule"

        def _build_handoff_if_needed() -> None:
            nonlocal verification_handoff, handoff_source
            if verification_handoff is not None:
                return
            verification_handoff, handoff_source = self._build_verification_handoff(
                user_input=user_input,
                final_answer=final_answer or "",
                stop_reason=stop_reason,
                runtime_status=task_status,
                tool_failures=last_tool_failures,
            )

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
                _build_handoff_if_needed()
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
                # Event compaction trigger is based on current tool_calls batch size.
                consecutive_tool_calls = len(tool_calls)
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
                    clarification_result = self._judge_clarification_request(
                        content=content,
                        user_input=user_input,
                        task_id=task_id,
                        run_id=run_id,
                        step=step,
                    )
                    if clarification_result.get("is_clarification_request", False):
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
                                "judge_source": clarification_result.get("source", "heuristic"),
                                "judge_confidence": clarification_result.get("confidence", 0.5),
                                "judge_reason": clarification_result.get("reason", ""),
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
                if runtime_state != "awaiting_user_input":
                    _build_handoff_if_needed()
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
                _build_handoff_if_needed()
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
                _build_handoff_if_needed()
                break

            messages.append({"role": "assistant", "content": content})
            if self.memory_store:
                self.memory_store.append_message(task_id, "assistant", content)
                final_answer_written = True

            if content:
                final_answer = content
                stop_reason = "fallback_content"
                runtime_state = "completed"
                _build_handoff_if_needed()
                self._trace(f"[step {step}] completed finish_reason=fallback final={self._preview(final_answer)}")
                break

        if final_answer is None:
            final_answer = "未在预算步数内收敛，建议缩小问题范围后重试。"
            task_status = "error"
            stop_reason = "max_steps_reached"
            runtime_state = "failed"
            self._trace("[runtime] max_steps_reached")
            _build_handoff_if_needed()

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
            if verification_handoff is None:
                verification_handoff, handoff_source = self._build_verification_handoff(
                    user_input=user_input,
                    final_answer=final_answer,
                    stop_reason=stop_reason,
                    runtime_status=task_status,
                    tool_failures=last_tool_failures,
                )
            run_outcome = RunOutcome(
                task_id=task_id,
                run_id=run_id,
                user_input=user_input,
                final_answer=final_answer,
                stop_reason=stop_reason,
                tool_failures=last_tool_failures[:],
                runtime_status=task_status,
                verification_handoff=verification_handoff,
            )
            emit_event(
                task_id=task_id,
                run_id=run_id,
                actor="main",
                role="general",
                event_type="verification_started",
                payload={"stop_reason": stop_reason, "handoff_source": handoff_source},
            )
            judgement = self.eval_orchestrator.evaluate(run_outcome=run_outcome)
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
                payload={
                    **judgement_payload,
                    "verification_handoff_source": handoff_source,
                    "verification_handoff": verification_handoff,
                },
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
        self._capture_user_preferences(task_id=task_id, run_id=run_id, user_input=user_input)
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

    def _build_verification_handoff(
        self,
        user_input: str,
        final_answer: str,
        stop_reason: str,
        runtime_status: str,
        tool_failures: List[Dict[str, str]],
    ) -> tuple[Dict[str, Any], str]:
        fallback = self._build_rule_verification_handoff(
            user_input=user_input,
            final_answer=final_answer,
            stop_reason=stop_reason,
            runtime_status=runtime_status,
            tool_failures=tool_failures,
        )
        llm_generated = self._generate_verification_handoff_llm(
            user_input=user_input,
            final_answer=final_answer,
            stop_reason=stop_reason,
            runtime_status=runtime_status,
            tool_failures=tool_failures,
            fallback_handoff=fallback,
        )
        if not llm_generated:
            return fallback, "fallback_rule"
        return self._normalize_verification_handoff(candidate=llm_generated, fallback=fallback), "llm"

    def _build_rule_verification_handoff(
        self,
        user_input: str,
        final_answer: str,
        stop_reason: str,
        runtime_status: str,
        tool_failures: List[Dict[str, str]],
    ) -> Dict[str, Any]:
        return build_rule_verification_handoff(
            user_input=user_input,
            final_answer=final_answer,
            stop_reason=stop_reason,
            runtime_status=runtime_status,
            tool_failures=tool_failures,
            preview=self._preview,
        )

    def _generate_verification_handoff_llm(
        self,
        user_input: str,
        final_answer: str,
        stop_reason: str,
        runtime_status: str,
        tool_failures: List[Dict[str, str]],
        fallback_handoff: Dict[str, Any],
    ) -> Dict[str, Any]:
        return generate_verification_handoff_llm(
            model_provider=self.model_provider,
            enabled=self.enable_verification_handoff_llm,
            build_config=self._build_verification_handoff_config,
            parse_json_dict=self._parse_json_dict,
            user_input=user_input,
            final_answer=final_answer,
            stop_reason=stop_reason,
            runtime_status=runtime_status,
            tool_failures=tool_failures,
            fallback_handoff=fallback_handoff,
        )

    def _normalize_verification_handoff(self, candidate: Dict[str, Any], fallback: Dict[str, Any]) -> Dict[str, Any]:
        return normalize_verification_handoff(
            candidate=candidate,
            fallback=fallback,
            preview=self._preview,
        )

    def _normalize_handoff_str_list(self, value: Any, max_items: int, max_len: int) -> List[str]:
        return normalize_handoff_str_list(
            value=value,
            max_items=max_items,
            max_len=max_len,
            preview=self._preview,
        )

    def _normalize_expected_artifacts(self, value: Any) -> List[Dict[str, Any]]:
        return normalize_expected_artifacts(
            value=value,
            preview=self._preview,
        )

    def _normalize_key_tool_results(self, value: Any) -> List[Dict[str, Any]]:
        return normalize_key_tool_results(
            value=value,
            preview=self._preview,
        )

    def _clamp_float(self, value: Any, default: float) -> float:
        return clamp_float(value, default)

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
        store = self.system_memory_store
        if store is None:
            try:
                store = SystemMemoryStore()
            except Exception:
                store = None
        finalize_task_memory(
            task_id=task_id,
            run_id=run_id,
            user_input=user_input,
            final_answer=final_answer,
            stop_reason=stop_reason,
            runtime_status=runtime_status,
            tool_failures=tool_failures,
            system_memory_store=store,
            preview=self._preview,
            slug=self._slug,
            build_semantic_memory_title=self._build_semantic_memory_title,
            generate_memory_card_metadata_llm=self._generate_memory_card_metadata_llm,
            emit_event=emit_event,
        )

    def _inject_system_memory_recall(
        self,
        task_id: str,
        run_id: str,
        user_input: str,
        messages: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        store = self.system_memory_store
        if store is None:
            try:
                store = SystemMemoryStore()
            except Exception:
                store = None
        return inject_system_memory_recall(
            task_id=task_id,
            run_id=run_id,
            user_input=user_input,
            messages=messages,
            system_memory_store=store,
            emit_event=emit_event,
            enable_memory_recall_reranker=self.enable_memory_recall_reranker,
            rerank_memory_candidates_llm=self._rerank_memory_candidates_llm,
            render_memory_recall_block=self._render_memory_recall_block,
            build_recall_query=self._build_recall_query,
            start_recall_candidate_pool=self.START_RECALL_CANDIDATE_POOL,
            start_recall_top_k=self.START_RECALL_TOP_K,
            start_recall_min_score=self.START_RECALL_MIN_SCORE,
        )

    def _build_recall_query(self, user_input: str) -> str:
        return build_recall_query(user_input)

    def _inject_user_preference_recall(
        self,
        task_id: str,
        run_id: str,
        user_input: str,
        messages: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        store = self.user_preference_store
        cfg = self.user_preference_config
        if not cfg.enabled or store is None:
            return messages
        try:
            block = store.render_recall_block(
                user_input=user_input,
                top_k=cfg.recall_top_k,
                always_include_keys=list(cfg.always_include_keys),
                max_chars=cfg.max_inject_chars,
            )
        except Exception as e:
            emit_event(
                task_id=task_id,
                run_id=run_id,
                actor="main",
                role="general",
                event_type="user_preference_recall_failed",
                status="error",
                payload={"error": str(e)},
            )
            return messages
        if not block:
            emit_event(
                task_id=task_id,
                run_id=run_id,
                actor="main",
                role="general",
                event_type="user_preference_recall_succeeded",
                payload={"injected": False, "items": 0},
            )
            return messages
        out: List[Dict[str, Any]] = []
        inserted = False
        for msg in messages:
            if not inserted and str(msg.get("role", "")) == "user":
                out.append({"role": "system", "content": block})
                inserted = True
            out.append(msg)
        if not inserted:
            out.append({"role": "system", "content": block})
        emit_event(
            task_id=task_id,
            run_id=run_id,
            actor="main",
            role="general",
            event_type="user_preference_recall_succeeded",
            payload={"injected": True, "chars": len(block)},
        )
        return out

    def _render_memory_recall_block(self, cards: List[Dict[str, Any]]) -> str:
        return render_memory_recall_block(cards=cards, preview=self._preview)

    def _capture_user_preferences(self, task_id: str, run_id: str, user_input: str) -> None:
        store = self.user_preference_store
        cfg = self.user_preference_config
        if not cfg.enabled or store is None:
            return
        try:
            raw_updates = self._extract_user_preferences_llm(
                task_id=task_id,
                run_id=run_id,
                user_input=user_input,
            )
            changed_keys, skipped = self._apply_user_preference_updates(
                updates=raw_updates,
                task_id=task_id,
                run_id=run_id,
            )
            emit_event(
                task_id=task_id,
                run_id=run_id,
                actor="main",
                role="general",
                event_type="user_preference_capture_succeeded",
                payload={
                    "updated_keys": changed_keys,
                    "updated_count": len(changed_keys),
                    "skipped_count": len(skipped),
                    "skipped_reasons": skipped[:8],
                },
            )
        except Exception as e:
            emit_event(
                task_id=task_id,
                run_id=run_id,
                actor="main",
                role="general",
                event_type="user_preference_capture_failed",
                status="error",
                payload={"error": str(e)},
            )

    def _extract_user_preferences_llm(self, task_id: str, run_id: str, user_input: str) -> List[Dict[str, Any]]:
        cfg = self.user_preference_config
        if not cfg.enable_llm_extract:
            return []
        emit_event(
            task_id=task_id,
            run_id=run_id,
            actor="main",
            role="general",
            event_type="user_preference_extract_started",
        )
        try:
            result = self.model_provider.generate(
                messages=[
                    {"role": "system", "content": USER_PREFERENCE_EXTRACT_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": USER_PREFERENCE_EXTRACT_USER_PROMPT_TEMPLATE.format(user_input=user_input),
                    },
                ],
                tools=[],
                config=self._build_user_preference_extract_config(),
            )
            parsed = self._parse_json_dict(result.content)
            updates = parsed.get("updates", []) if isinstance(parsed, dict) else []
            if not isinstance(updates, list):
                updates = []
            emit_event(
                task_id=task_id,
                run_id=run_id,
                actor="main",
                role="general",
                event_type="user_preference_extract_succeeded",
                payload={"candidate_count": len(updates)},
            )
            return [x for x in updates if isinstance(x, dict)]
        except Exception as e:
            emit_event(
                task_id=task_id,
                run_id=run_id,
                actor="main",
                role="general",
                event_type="user_preference_extract_failed",
                status="error",
                payload={"error": str(e)},
            )
            raise

    def _normalize_preference_value(self, value: Any) -> Any:
        if isinstance(value, list):
            items: List[str] = []
            for part in value:
                text = str(part or "").strip()
                if text and text not in items:
                    items.append(text)
            return items[:10]
        return str(value or "").strip()

    def _is_sensitive_preference_value(self, value: Any) -> bool:
        text = str(value or "")
        if not text:
            return False
        digits = "".join([c for c in text if c.isdigit()])
        if len(digits) >= 11:
            return True
        lowered = text.lower()
        sensitive_tokens = ["身份证", "银行卡", "信用卡", "住址", "手机号", "password", "passwd"]
        return any(token in lowered for token in sensitive_tokens)

    def _value_changed(self, old_value: Any, new_value: Any) -> bool:
        if isinstance(old_value, list) or isinstance(new_value, list):
            old_list = old_value if isinstance(old_value, list) else [str(old_value or "").strip()]
            new_list = new_value if isinstance(new_value, list) else [str(new_value or "").strip()]
            old_norm = [str(x).strip() for x in old_list if str(x).strip()]
            new_norm = [str(x).strip() for x in new_list if str(x).strip()]
            return old_norm != new_norm
        return str(old_value or "").strip() != str(new_value or "").strip()

    def _apply_user_preference_updates(
        self,
        updates: List[Dict[str, Any]],
        task_id: str,
        run_id: str,
    ) -> tuple[List[str], List[str]]:
        store = self.user_preference_store
        cfg = self.user_preference_config
        if store is None:
            return [], ["store_unavailable"]
        allowed_keys = {
            "job_role",
            "domain_expertise",
            "interest_topics",
            "language_preference",
            "response_style",
            "tooling_stack",
            "goal_long_term",
        }
        existing = store.list_preferences()
        changed: List[str] = []
        skipped: List[str] = []

        for row in updates:
            key = str(row.get("key", "") or "").strip()
            action = str(row.get("action", "ignore") or "ignore").strip().lower()
            explicit = bool(row.get("explicit", False))
            evidence = str(row.get("evidence_span", "") or "").strip()
            try:
                confidence = float(row.get("confidence", 0.0) or 0.0)
            except Exception:
                confidence = 0.0

            if key not in allowed_keys:
                skipped.append(f"{key or 'unknown'}:key_not_allowed")
                continue
            if action not in {"upsert", "delete", "ignore"}:
                skipped.append(f"{key}:action_invalid")
                continue
            if action == "ignore":
                skipped.append(f"{key}:ignored")
                continue
            if not explicit:
                skipped.append(f"{key}:not_explicit")
                continue
            if confidence < cfg.auto_write_min_confidence:
                skipped.append(f"{key}:low_confidence")
                continue

            if action == "delete":
                store.delete_preference(key)
                changed.append(key)
                continue

            new_value = self._normalize_preference_value(row.get("value", ""))
            if (isinstance(new_value, list) and not new_value) or (not isinstance(new_value, list) and not new_value):
                skipped.append(f"{key}:empty_value")
                continue
            if self._is_sensitive_preference_value(new_value):
                skipped.append(f"{key}:sensitive_blocked")
                continue
            old_rec = existing.get(key, {}) if isinstance(existing.get(key), dict) else {}
            old_value = old_rec.get("value", "")
            has_existing = bool(str(old_value).strip()) or (isinstance(old_value, list) and bool(old_value))
            if has_existing and self._value_changed(old_value, new_value) and confidence < cfg.conflict_min_confidence:
                skipped.append(f"{key}:conflict_low_confidence")
                continue
            store.upsert_preference(
                key=key,
                value=new_value,
                source="llm_extract_v1",
                confidence=confidence,
                note=f"evidence={self._preview(evidence, max_len=120)}" if evidence else "",
            )
            changed.append(key)

        return changed, skipped

    def _rerank_memory_candidates_llm(self, user_input: str, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return rerank_memory_candidates_llm(
            model_provider=self.model_provider,
            user_input=user_input,
            candidates=candidates,
            start_recall_candidate_pool=self.START_RECALL_CANDIDATE_POOL,
            start_recall_top_k=self.START_RECALL_TOP_K,
            build_memory_reranker_config=self._build_memory_reranker_config,
            parse_json_dict=self._parse_json_dict,
        )

    def _build_memory_reranker_config(self) -> GenerationConfig:
        return build_memory_reranker_config()

    def _parse_json_dict(self, text: str) -> Dict[str, Any]:
        return parse_json_dict(text)

    def _slug(self, value: str) -> str:
        return slug(value)

    def _build_semantic_memory_title(self, user_input: str, runtime_status: str, stop_reason: str) -> str:
        return build_semantic_memory_title(
            user_input=user_input,
            runtime_status=runtime_status,
            stop_reason=stop_reason,
            extract_title_topic=self._extract_title_topic,
            preview=self._preview,
        )

    def _extract_title_topic(self, user_input: str) -> str:
        return extract_title_topic(user_input=user_input, preview=self._preview)

    def _extract_finish_reason_and_message(self, raw: Dict[str, Any]) -> tuple[str, Dict[str, Any]]:
        return extract_finish_reason_and_message(raw)

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
        return handle_native_tool_calls(
            tool_calls=tool_calls,
            messages=messages,
            task_id=task_id,
            run_id=run_id,
            tool_registry=self.tool_registry,
            memory_store=self.memory_store,
            enrich_capture_memory_tool_args=self._enrich_capture_memory_tool_args,
            emit_event=emit_event,
            trace=self._trace,
            preview_json=self._preview_json,
        )

    def _enrich_capture_memory_tool_args(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        task_id: str,
        run_id: str,
    ) -> Dict[str, Any]:
        return enrich_capture_memory_tool_args(
            tool_name=tool_name,
            tool_args=tool_args,
            task_id=task_id,
            run_id=run_id,
            enable_memory_card_metadata_llm=self.enable_memory_card_metadata_llm,
            extract_title_topic=self._extract_title_topic,
            preview=self._preview,
            generate_memory_card_metadata_llm=self._generate_memory_card_metadata_llm,
        )

    def _generate_memory_card_metadata_llm(
        self,
        mode: str,
        user_input: str,
        runtime_status: str,
        stop_reason: str,
        failure_brief: str,
        answer_brief: str,
        fallback_title: str,
        fallback_recall_hint: str,
        task_id: str = "",
        run_id: str = "",
    ) -> Dict[str, str]:
        return generate_memory_card_metadata_llm(
            model_provider=self.model_provider,
            enabled=self.enable_memory_card_metadata_llm,
            build_memory_metadata_config=self._build_memory_metadata_config,
            parse_json_dict=self._parse_json_dict,
            preview=self._preview,
            mode=mode,
            user_input=user_input,
            runtime_status=runtime_status,
            stop_reason=stop_reason,
            failure_brief=failure_brief,
            answer_brief=answer_brief,
            fallback_title=fallback_title,
            fallback_recall_hint=fallback_recall_hint,
            task_id=task_id,
            run_id=run_id,
        )

    def _build_memory_metadata_config(self) -> GenerationConfig:
        return build_memory_metadata_config()

    def _build_verification_handoff_config(self) -> GenerationConfig:
        options: Dict[str, Any] = {}
        try:
            model_cfg = load_runtime_model_config()
            mini_id = str(getattr(model_cfg, "mini_model_id", "") or "").strip()
            if mini_id:
                options["model"] = mini_id
        except Exception:
            pass
        return GenerationConfig(
            temperature=0.1,
            max_tokens=900,
            provider_options=options,
        )

    def _build_user_preference_extract_config(self) -> GenerationConfig:
        options: Dict[str, Any] = {}
        try:
            model_cfg = load_runtime_model_config()
            mini_id = str(getattr(model_cfg, "mini_model_id", "") or "").strip()
            if mini_id:
                options["model"] = mini_id
        except Exception:
            pass
        return GenerationConfig(
            temperature=0.0,
            max_tokens=700,
            provider_options=options,
        )

    def _trace(self, msg: str) -> None:
        if self.trace_steps:
            try:
                self.trace_printer(msg)
            except Exception:
                pass

    def _preview(self, text: str, max_len: int = 120) -> str:
        return preview(text, max_len=max_len)

    def _preview_json(self, obj: Any, max_len: int = 200) -> str:
        return preview_json(obj, max_len=max_len)

    def _estimate_context_tokens(self, messages: List[Dict[str, Any]]) -> int:
        return estimate_context_tokens(messages)

    def _estimate_context_usage(self, estimated_tokens: int) -> float:
        return estimate_context_usage(
            estimated_tokens=estimated_tokens,
            context_window_tokens=self.compression_config.context_window_tokens,
        )

    def _is_clarification_request(self, content: str) -> bool:
        return is_clarification_request(content)

    def _build_clarification_judge_config(self) -> GenerationConfig:
        options: Dict[str, Any] = {}
        try:
            model_cfg = load_runtime_model_config()
            mini_id = str(getattr(model_cfg, "mini_model_id", "") or "").strip()
            if mini_id:
                options["model"] = mini_id
        except Exception:
            pass
        return GenerationConfig(
            temperature=0.0,
            max_tokens=160,
            provider_options=options,
        )

    def _judge_clarification_request(
        self,
        content: str,
        user_input: str,
        task_id: str,
        run_id: str,
        step: int,
    ) -> Dict[str, Any]:
        default_confidence = 0.5
        if not self.enable_llm_clarification_judge:
            return {
                "is_clarification_request": self._is_clarification_request(content),
                "confidence": default_confidence,
                "source": "heuristic",
                "reason": "llm_judge_disabled",
            }

        emit_event(
            task_id=task_id,
            run_id=run_id,
            actor="main",
            role="general",
            event_type="clarification_judge_started",
            payload={"step": step, "content_preview": self._preview(content, max_len=300)},
        )
        started_at = time.perf_counter()
        fallback_reason = ""
        try:
            prompt = CLARIFICATION_JUDGE_USER_PROMPT_TEMPLATE.format(
                user_input=user_input.strip() or "(empty)",
                assistant_output=content.strip() or "(empty)",
            )
            output = self.model_provider.generate(
                messages=[
                    {"role": "system", "content": CLARIFICATION_JUDGE_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                tools=[],
                config=self._build_clarification_judge_config(),
            )
            parsed = self._parse_json_dict(output.content)
            decision_raw = parsed.get("is_clarification_request")
            if not isinstance(decision_raw, bool):
                fallback_reason = "invalid_output_missing_boolean"
                raise ValueError(fallback_reason)
            confidence_raw = parsed.get("confidence", default_confidence)
            try:
                confidence = clamp_float(float(confidence_raw), default_confidence)
            except Exception:
                confidence = default_confidence
            decision = bool(decision_raw) and confidence >= self.clarification_judge_confidence_threshold
            reason = str(parsed.get("reason", "") or "")
            emit_event(
                task_id=task_id,
                run_id=run_id,
                actor="main",
                role="general",
                event_type="clarification_judge_completed",
                payload={
                    "step": step,
                    "decision": decision,
                    "decision_raw": bool(decision_raw),
                    "confidence": confidence,
                    "threshold": self.clarification_judge_confidence_threshold,
                    "source": "llm",
                    "reason": reason,
                    "latency_ms": int(max((time.perf_counter() - started_at) * 1000, 0)),
                },
            )
            return {
                "is_clarification_request": decision,
                "confidence": confidence,
                "source": "llm",
                "reason": reason,
            }
        except Exception as e:
            fallback_reason = fallback_reason or str(e) or "llm_judge_exception"

        if self.enable_clarification_heuristic_fallback:
            fallback_decision = self._is_clarification_request(content)
            emit_event(
                task_id=task_id,
                run_id=run_id,
                actor="main",
                role="general",
                event_type="clarification_judge_fallback",
                payload={
                    "step": step,
                    "reason": fallback_reason,
                    "fallback_decision": fallback_decision,
                    "source": "heuristic",
                    "latency_ms": int(max((time.perf_counter() - started_at) * 1000, 0)),
                },
            )
            return {
                "is_clarification_request": fallback_decision,
                "confidence": default_confidence,
                "source": "heuristic_fallback",
                "reason": fallback_reason,
            }
        return {
            "is_clarification_request": False,
            "confidence": default_confidence,
            "source": "llm_no_fallback",
            "reason": fallback_reason,
        }

    def _extract_missing_info_hints(self, content: str) -> List[str]:
        return extract_missing_info_hints(content)
