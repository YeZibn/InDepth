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
    parse_json_dict,
    preview,
    preview_json,
    slug,
)
from app.core.runtime.system_memory_lifecycle import (
    extract_title_topic,
    finalize_task_memory,
    inject_system_memory_recall,
)
from app.core.memory.memory_metadata_service import (
    build_memory_metadata_config,
    generate_memory_card_metadata_llm,
)
from app.core.runtime.runtime_stop_policy import (
    resolve_max_steps_outcome,
    resolve_non_stop_finish_reason,
    resolve_stop_finish_reason,
)
from app.core.runtime.clarification_policy import judge_clarification_request
from app.core.runtime.runtime_compaction_policy import (
    finalize_memory_compaction,
    maybe_compact_mid_run,
)
from app.core.runtime.runtime_finalization import (
    finalize_completed_run,
    finalize_paused_run,
)
from app.core.runtime.todo_runtime_lifecycle import (
    append_recovery_summary_for_user,
    auto_manage_todo_recovery,
    maybe_emit_todo_binding_warning,
    update_active_todo_context,
)
from app.core.runtime.user_preference_lifecycle import (
    capture_user_preferences,
    inject_user_preference_recall,
)
from app.core.runtime.tool_execution import (
    enrich_capture_memory_tool_args,
    handle_native_tool_calls,
)
from app.eval.verification_handoff_service import (
    build_verification_handoff,
    clamp_float,
)
from app.eval.orchestrator import EvalOrchestrator
from app.core.model.base import GenerationConfig, ModelProvider
from app.core.memory.base import MemoryStore
from app.core.memory.system_memory_store import SystemMemoryStore
from app.core.memory.user_preference_store import UserPreferenceStore
from app.core.tools.registry import ToolRegistry
from app.observability.events import emit_event

class AgentRuntime:
    START_RECALL_TOP_K = 5
    START_RECALL_MIN_SCORE = 0.65
    START_RECALL_CANDIDATE_POOL = 50
    TODO_BINDING_GUARD_MODE = "warn"
    TODO_BINDING_EXEMPT_TOOLS = {
        "create_task",
        "list_tasks",
        "get_next_task",
        "get_task_progress",
        "generate_task_report",
        "update_task_status",
        "record_task_fallback",
        "plan_task_recovery",
        "append_followup_subtasks",
    }

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
        self._active_todo_context: Dict[str, Any] = {}
        self._latest_todo_recovery: Dict[str, Any] = {}

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
        self._active_todo_context = {}
        self._latest_todo_recovery = {}
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
        last_tool_executions: List[Dict[str, Any]] = []
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

        # Runtime 主循环只负责“编排”三件事：请求模型、执行工具、收敛本轮状态。
        # 具体的 todo 恢复、memory 生命周期、verification handoff 都尽量下沉到独立模块。
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
                tool_outcome = self._handle_native_tool_calls(tool_calls, messages, task_id, run_id)
                last_tool_failures = tool_outcome.get("failures", [])
                last_tool_executions = tool_outcome.get("executions", [])
                continue
            consecutive_tool_calls = 0

            if finish_reason == "stop":
                messages.append({"role": "assistant", "content": content})
                if self.memory_store:
                    self.memory_store.append_message(task_id, "assistant", content)
                    final_answer_written = True
                # stop 分支既可能是正常完成，也可能是“等待用户补充信息”或失败兜底。
                # 这些收敛规则统一放在 stop policy，避免主循环继续堆分支细节。
                stop_outcome = resolve_stop_finish_reason(
                    content=content,
                    user_input=user_input,
                    task_id=task_id,
                    run_id=run_id,
                    step=step,
                    last_tool_failures=last_tool_failures,
                    judge_clarification_request=self._judge_clarification_request,
                    extract_missing_info_hints=self._extract_missing_info_hints,
                    preview=self._preview,
                    emit_event=emit_event,
                )
                final_answer = stop_outcome["final_answer"]
                task_status = stop_outcome["task_status"]
                stop_reason = stop_outcome["stop_reason"]
                runtime_state = stop_outcome["runtime_state"]
                if stop_outcome.get("should_build_handoff"):
                    _build_handoff_if_needed()
                self._trace(f"[step {step}] completed finish_reason=stop final={self._preview(final_answer)}")
                break

            messages.append({"role": "assistant", "content": content})
            if self.memory_store:
                self.memory_store.append_message(task_id, "assistant", content)
                final_answer_written = True

            # 对于非 stop 的 finish_reason，这里统一做“失败收敛”或“fallback 内容收敛”。
            # 主循环只负责接收 policy 的结果，而不再直接维护每一种停止条件的细节。
            non_stop_outcome = resolve_non_stop_finish_reason(
                finish_reason=finish_reason,
                content=content,
                task_id=task_id,
                run_id=run_id,
                emit_event=emit_event,
            )
            if non_stop_outcome:
                final_answer = non_stop_outcome["final_answer"]
                task_status = non_stop_outcome["task_status"]
                stop_reason = non_stop_outcome["stop_reason"]
                runtime_state = non_stop_outcome["runtime_state"]
                _build_handoff_if_needed()
                trace_label = str(non_stop_outcome.get("trace_label", "stop")).strip() or "stop"
                if trace_label in {"length", "content_filter"}:
                    self._trace(f"[step {step}] stopped finish_reason={trace_label}")
                else:
                    self._trace(f"[step {step}] completed finish_reason={trace_label} final={self._preview(final_answer)}")
                break

        if final_answer is None:
            max_steps_outcome = resolve_max_steps_outcome()
            final_answer = max_steps_outcome["final_answer"]
            task_status = max_steps_outcome["task_status"]
            stop_reason = max_steps_outcome["stop_reason"]
            runtime_state = max_steps_outcome["runtime_state"]
            self._trace("[runtime] max_steps_reached")
            if max_steps_outcome.get("should_build_handoff"):
                _build_handoff_if_needed()

        if runtime_state == "awaiting_user_input":
            # clarification pause 属于编排层的“中间暂停收尾”，这里统一交给 finalization 模块处理。
            paused_outcome = finalize_paused_run(
                task_id=task_id,
                run_id=run_id,
                runtime_state=runtime_state,
                stop_reason=stop_reason,
                final_answer=final_answer,
                last_tool_failures=last_tool_failures,
                auto_manage_todo_recovery=self._auto_manage_todo_recovery,
                append_recovery_summary_for_user=self._append_recovery_summary_for_user,
                has_latest_todo_recovery=lambda: bool(self._latest_todo_recovery),
                preview=self._preview,
                emit_event=emit_event,
            )
            final_answer = paused_outcome["final_answer"]
            self.last_runtime_state = runtime_state
            self.last_stop_reason = stop_reason
            self._trace(paused_outcome["trace_message"])
            return final_answer

        completed_outcome = finalize_completed_run(
            task_id=task_id,
            run_id=run_id,
            user_input=user_input,
            final_answer=final_answer,
            stop_reason=stop_reason,
            runtime_state=runtime_state,
            task_status=task_status,
            last_tool_failures=last_tool_failures,
            verification_handoff=verification_handoff,
            handoff_source=handoff_source,
            build_verification_handoff=self._build_verification_handoff,
            auto_manage_todo_recovery=self._auto_manage_todo_recovery,
            append_recovery_summary_for_user=self._append_recovery_summary_for_user,
            has_latest_todo_recovery=lambda: bool(self._latest_todo_recovery),
            eval_orchestrator=self.eval_orchestrator,
            emit_event=emit_event,
        )
        final_answer = completed_outcome["final_answer"]
        task_finished_status = completed_outcome["task_finished_status"]

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
        finalize_memory_compaction(
            task_id=task_id,
            final_answer=final_answer,
            final_answer_written=final_answer_written,
            memory_store=self.memory_store,
        )
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
        # context compaction 是 runtime 对上下文预算的调度策略，而不是 memory store 本身的职责。
        return maybe_compact_mid_run(
            step=step,
            task_id=task_id,
            run_id=run_id,
            messages=messages,
            consecutive_tool_calls=consecutive_tool_calls,
            memory_store=self.memory_store,
            compression_config=self.compression_config,
            estimate_context_tokens=self._estimate_context_tokens,
            estimate_context_usage=self._estimate_context_usage,
            build_system_prompt=self._build_system_prompt,
            emit_event=emit_event,
        )

    def _build_verification_handoff(
        self,
        user_input: str,
        final_answer: str,
        stop_reason: str,
        runtime_status: str,
        tool_failures: List[Dict[str, str]],
    ) -> tuple[Dict[str, Any], str]:
        # verification handoff 的触发时机属于 runtime，但 handoff 的构造/归一化属于 eval 能力层。
        return build_verification_handoff(
            user_input=user_input,
            final_answer=final_answer,
            stop_reason=stop_reason,
            runtime_status=runtime_status,
            tool_failures=tool_failures,
            recovery_context=self._latest_todo_recovery,
            model_provider=self.model_provider,
            enabled=self.enable_verification_handoff_llm,
            build_config=self._build_verification_handoff_config,
            parse_json_dict=self._parse_json_dict,
            preview=self._preview,
        )

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
            model_provider=self.model_provider,
            enable_memory_card_metadata_llm=self.enable_memory_card_metadata_llm,
            parse_json_dict=self._parse_json_dict,
            preview=self._preview,
            slug=self._slug,
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
            model_provider=self.model_provider,
            enable_memory_recall_reranker=self.enable_memory_recall_reranker,
            parse_json_dict=self._parse_json_dict,
            preview=self._preview,
            start_recall_candidate_pool=self.START_RECALL_CANDIDATE_POOL,
            start_recall_top_k=self.START_RECALL_TOP_K,
            start_recall_min_score=self.START_RECALL_MIN_SCORE,
        )

    def _inject_user_preference_recall(
        self,
        task_id: str,
        run_id: str,
        user_input: str,
        messages: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        return inject_user_preference_recall(
            task_id=task_id,
            run_id=run_id,
            user_input=user_input,
            messages=messages,
            store=self.user_preference_store,
            cfg=self.user_preference_config,
            emit_event=emit_event,
        )

    def _capture_user_preferences(self, task_id: str, run_id: str, user_input: str) -> None:
        # 用户偏好属于 run 前 recall、run 后 capture 的独立生命周期。
        # 这里保留一个薄入口，避免把抽取/过滤/写入规则继续堆回 AgentRuntime。
        capture_user_preferences(
            task_id=task_id,
            run_id=run_id,
            user_input=user_input,
            store=self.user_preference_store,
            cfg=self.user_preference_config,
            model_provider=self.model_provider,
            parse_json_dict=self._parse_json_dict,
            preview=self._preview,
            emit_event=emit_event,
        )

    def _parse_json_dict(self, text: str) -> Dict[str, Any]:
        return parse_json_dict(text)

    def _slug(self, value: str) -> str:
        return slug(value)

    def _extract_title_topic(self, user_input: str) -> str:
        return extract_title_topic(user_input=user_input, preview=self._preview)

    def _extract_finish_reason_and_message(self, raw: Dict[str, Any]) -> tuple[str, Dict[str, Any]]:
        return extract_finish_reason_and_message(raw)

    def _build_system_prompt(self) -> str:
        parts = [p for p in [self.system_prompt, self.skill_prompt] if p]
        return "\n\n".join(parts)

    def _handle_native_tool_calls(
        self,
        tool_calls: List[Dict[str, Any]],
        messages: List[Dict[str, Any]],
        task_id: str,
        run_id: str,
    ) -> Dict[str, Any]:
        failures: List[Dict[str, str]] = []
        executions: List[Dict[str, Any]] = []
        for call in tool_calls:
            fn = call.get("function", {}) if isinstance(call, dict) else {}
            tool_name = str(fn.get("name", "")).strip()
            # todo guard 只做提醒，不阻断执行；这样既能保留观测信号，也不改变现有工具调用语义。
            maybe_emit_todo_binding_warning(
                tool_name=tool_name,
                task_id=task_id,
                run_id=run_id,
                todo_context=self._active_todo_context,
                guard_mode=self.TODO_BINDING_GUARD_MODE,
                exempt_tools=self.TODO_BINDING_EXEMPT_TOOLS,
                emit_event=emit_event,
            )
            outcome = handle_native_tool_calls(
                tool_calls=[call],
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
            batch_failures = outcome.get("failures", [])
            batch_executions = outcome.get("executions", [])
            if isinstance(batch_failures, list):
                failures.extend(batch_failures)
            if isinstance(batch_executions, list):
                executions.extend(batch_executions)
                self._active_todo_context = update_active_todo_context(
                    current_context=self._active_todo_context,
                    executions=batch_executions,
                )
        return {"failures": failures, "executions": executions}

    def _auto_manage_todo_recovery(
        self,
        task_id: str,
        run_id: str,
        runtime_state: str,
        stop_reason: str,
        final_answer: str,
        last_tool_failures: List[Dict[str, str]],
    ) -> None:
        self._latest_todo_recovery = auto_manage_todo_recovery(
            task_id=task_id,
            run_id=run_id,
            runtime_state=runtime_state,
            stop_reason=stop_reason,
            final_answer=final_answer,
            last_tool_failures=last_tool_failures,
            todo_context=self._active_todo_context,
            tool_registry=self.tool_registry,
            preview=self._preview,
            extract_missing_info_hints=self._extract_missing_info_hints,
            emit_event=emit_event,
        )

    def _append_recovery_summary_for_user(self, answer: str) -> str:
        return append_recovery_summary_for_user(answer=answer, recovery=self._latest_todo_recovery)

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
            build_memory_metadata_config=build_memory_metadata_config,
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

    def _judge_clarification_request(
        self,
        content: str,
        user_input: str,
        task_id: str,
        run_id: str,
        step: int,
    ) -> Dict[str, Any]:
        # clarification 判断是 runtime 的一个策略子域：它决定当前回复是“完成”还是“暂停等待输入”。
        return judge_clarification_request(
            content=content,
            user_input=user_input,
            task_id=task_id,
            run_id=run_id,
            step=step,
            model_provider=self.model_provider,
            enable_llm_clarification_judge=self.enable_llm_clarification_judge,
            clarification_judge_confidence_threshold=self.clarification_judge_confidence_threshold,
            enable_clarification_heuristic_fallback=self.enable_clarification_heuristic_fallback,
            parse_json_dict=self._parse_json_dict,
            preview=self._preview,
            emit_event=emit_event,
        )

    def _extract_missing_info_hints(self, content: str) -> List[str]:
        return extract_missing_info_hints(content)
