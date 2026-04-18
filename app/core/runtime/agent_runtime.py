import json
from concurrent.futures import ThreadPoolExecutor
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
    build_create_task_arg_error,
    build_duplicate_todo_binding_error,
    finalize_active_todo_context,
    maybe_emit_todo_binding_warning,
    restore_active_todo_context_from_history,
    update_active_todo_context,
)
from app.core.runtime.user_preference_lifecycle import (
    capture_user_preferences,
    inject_user_preference_recall,
)
from app.core.runtime.tool_execution import (
    enrich_runtime_tool_args,
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
from app.observability.postmortem import generate_postmortem

class AgentRuntime:
    START_RECALL_TOP_K = 5
    START_RECALL_MIN_SCORE = 0.65
    START_RECALL_CANDIDATE_POOL = 50
    TODO_BINDING_GUARD_MODE = "warn"
    TODO_BINDING_EXEMPT_TOOLS = {
        "plan_task",
        "create_task",
        "update_task",
        "list_tasks",
        "get_next_task",
        "get_task_progress",
        "generate_task_report",
        "update_task_status",
        "update_subtask",
        "record_task_fallback",
        "reopen_subtask",
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
        enable_llm_recovery_planner: Optional[bool] = None,
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
        if enable_llm_recovery_planner is None:
            # Default on for real providers, off for deterministic test mock provider.
            self.enable_llm_recovery_planner = self.model_provider.__class__.__name__ != "MockModelProvider"
        else:
            self.enable_llm_recovery_planner = bool(enable_llm_recovery_planner)
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
        self._prepare_phase_completed = False
        self._prepare_phase_result: Dict[str, Any] = {}

    def _run_prepare_phase(self, user_input: str, task_id: str, run_id: str) -> Dict[str, Any]:
        if not self.tool_registry.has("prepare_task"):
            self._prepare_phase_completed = False
            self._prepare_phase_result = {}
            return {}
        ctx = self._active_todo_context if isinstance(self._active_todo_context, dict) else {}
        todo_id = str(ctx.get("todo_id", "") or "").strip()
        active_number = ctx.get("active_subtask_number")
        if active_number in (None, ""):
            active_number = 0
        active_status = ""
        if active_number:
            active_status = "in-progress" if str(ctx.get("execution_phase", "") or "").strip() == "executing" else ""
        args = {
            "task_name": self._extract_title_topic(user_input),
            "context": user_input,
            "active_todo_id": todo_id,
            "active_todo_exists": bool(todo_id),
            "active_todo_summary": "",
            "active_subtask_number": int(active_number or 0),
            "active_subtask_status": active_status,
            "execution_intent": "runtime_preflight",
        }
        emit_event(
            task_id=task_id,
            run_id=run_id,
            actor="main",
            role="general",
            event_type="tool_called",
            payload={"tool": "prepare_task", "args": args},
        )
        result = self.tool_registry.invoke("prepare_task", args)
        if not result.get("success"):
            self._prepare_phase_completed = False
            self._prepare_phase_result = {}
            emit_event(
                task_id=task_id,
                run_id=run_id,
                actor="main",
                role="general",
                event_type="tool_failed",
                status="error",
                payload={"tool": "prepare_task", "error": str(result.get("error", ""))},
            )
            return {}
        emit_event(
            task_id=task_id,
            run_id=run_id,
            actor="main",
            role="general",
            event_type="tool_succeeded",
            payload={"tool": "prepare_task", "error": ""},
        )
        payload = result.get("result", {})
        prepared = payload if isinstance(payload, dict) else {}
        self._prepare_phase_completed = True
        self._prepare_phase_result = prepared
        return prepared

    def _render_prepare_phase_message(self, prepared: Dict[str, Any]) -> str:
        if not isinstance(prepared, dict) or not prepared:
            return ""
        lines = [
            "[Prepare Phase]",
            f"should_use_todo={bool(prepared.get('should_use_todo'))}",
            f"plan_ready={bool(prepared.get('plan_ready'))}",
            f"recommended_mode={str(prepared.get('recommended_mode', '') or '').strip() or 'unknown'}",
        ]
        active_todo_id = str(prepared.get("active_todo_id", "") or "").strip()
        if active_todo_id:
            lines.append(f"active_todo_id={active_todo_id}")
        active_summary = str(prepared.get("active_todo_summary", "") or "").strip()
        if active_summary:
            lines.append(f"active_todo_summary={active_summary}")
        notes = prepared.get("notes", [])
        if isinstance(notes, list):
            normalized_notes = [str(item).strip() for item in notes if str(item).strip()]
            if normalized_notes:
                lines.append("notes:")
                lines.extend([f"- {item}" for item in normalized_notes[:4]])
        suggested = prepared.get("recommended_plan_task_args", {})
        if isinstance(suggested, dict) and suggested:
            lines.append("If you decide to use todo tracking, prefer calling plan_task with these prepared fields instead of designing a new plan from scratch.")
            lines.append(preview_json(suggested, max_len=800))
        return "\n".join(lines).strip()

    def _build_prepare_phase_guard_error(self, tool_name: str) -> Dict[str, Any]:
        prepared = self._prepare_phase_result if isinstance(self._prepare_phase_result, dict) else {}
        guidance = (
            "Prepare phase must run before planning tools. "
            "Run prepare_task first, then call plan_task using the prepared result."
        )
        if prepared:
            recommended_mode = str(prepared.get("recommended_mode", "") or "").strip()
            if recommended_mode:
                guidance += f" Current prepare recommendation: {recommended_mode}."
        return {
            "success": False,
            "error": f"Prepare phase not completed before calling {tool_name}. {guidance}",
            "result": {
                "success": False,
                "error": f"Prepare phase not completed before calling {tool_name}.",
                "prepare_completed": False,
                "tool": tool_name,
                "prepare_result": prepared,
            },
        }

    def _append_internal_tool_execution_to_messages(
        self,
        messages: List[Dict[str, Any]],
        task_id: str,
        run_id: str,
        step_id: str,
        tool_name: str,
        tool_args: Dict[str, Any],
        result: Dict[str, Any],
        call_id: str,
    ) -> None:
        tool_call = [
            {
                "id": call_id,
                "type": "function",
                "function": {
                    "name": tool_name,
                    "arguments": json.dumps(tool_args, ensure_ascii=False),
                },
            }
        ]
        messages.append({"role": "assistant", "content": "", "tool_calls": tool_call})
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
                "assistant",
                "",
                tool_calls=tool_call,
                run_id=run_id,
                step_id=step_id,
            )
            self.memory_store.append_message(
                task_id,
                "tool",
                json.dumps(result, ensure_ascii=False),
                tool_call_id=call_id,
                run_id=run_id,
                step_id=step_id,
            )

    def _maybe_apply_prepared_plan(
        self,
        prepared: Dict[str, Any],
        messages: List[Dict[str, Any]],
        task_id: str,
        run_id: str,
    ) -> Dict[str, Any]:
        if not isinstance(prepared, dict) or not prepared:
            return {}
        if not bool(prepared.get("should_use_todo")) or not bool(prepared.get("plan_ready")):
            return {}
        recommended_mode = str(prepared.get("recommended_mode", "") or "").strip()
        suggested: Dict[str, Any] = {}
        tool_name = ""
        execution: Dict[str, Any] = {}
        if recommended_mode == "create":
            suggested = prepared.get("recommended_plan_task_args", {})
            if not isinstance(suggested, dict) or not suggested:
                return {}
            subtasks = suggested.get("subtasks")
            if not isinstance(subtasks, list) or not subtasks:
                return {}
            tool_name = "plan_task"
        elif recommended_mode == "update":
            suggested = prepared.get("recommended_update_task_args", {})
            if not isinstance(suggested, dict) or not suggested:
                return {}
            operations = suggested.get("operations")
            if not isinstance(operations, list) or not operations:
                return {}
            tool_name = "update_task"
        else:
            return {}
        emit_event(
            task_id=task_id,
            run_id=run_id,
            actor="main",
            role="general",
            event_type="tool_called",
            payload={"tool": tool_name, "args": suggested, "source": "prepare_phase_auto_apply"},
        )
        result = self.tool_registry.invoke(tool_name, suggested)
        event_type = "tool_succeeded" if result.get("success") else "tool_failed"
        emit_event(
            task_id=task_id,
            run_id=run_id,
            actor="main",
            role="general",
            event_type=event_type,
            status="ok" if result.get("success") else "error",
            payload={"tool": tool_name, "error": str(result.get("error", "")), "source": "prepare_phase_auto_apply"},
        )
        self._append_internal_tool_execution_to_messages(
            messages=messages,
            task_id=task_id,
            run_id=run_id,
            step_id="prepare",
            tool_name=tool_name,
            tool_args=suggested,
            result=result,
            call_id=f"auto_prepare_{tool_name}_{self._slug(run_id)}",
        )
        execution_payload = result.get("result", {})
        execution = {
            "tool": tool_name,
            "args": suggested,
            "success": bool(result.get("success")),
            "error": str(result.get("error", "")),
            "payload": execution_payload if isinstance(execution_payload, dict) else {},
        }
        self._active_todo_context = update_active_todo_context(
            current_context=self._active_todo_context,
            executions=[execution],
        )
        if result.get("success"):
            prepared = dict(prepared)
            prepared["auto_plan_applied"] = True
            prepared["auto_plan_tool"] = tool_name
            self._prepare_phase_result = prepared
        return result

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
        self._prepare_phase_completed = False
        self._prepare_phase_result = {}
        history = self.memory_store.get_recent_messages(task_id, limit=20) if self.memory_store else []
        self._active_todo_context = restore_active_todo_context_from_history(history)
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
        prepared = self._run_prepare_phase(user_input=user_input, task_id=task_id, run_id=run_id)
        self._maybe_apply_prepared_plan(
            prepared=prepared,
            messages=messages,
            task_id=task_id,
            run_id=run_id,
        )
        prepare_message = self._render_prepare_phase_message(prepared)
        if prepare_message:
            messages.append({"role": "system", "content": prepare_message})
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
            self.memory_store.append_message(task_id, "user", user_input, run_id=run_id, step_id="1")

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
                        run_id=run_id,
                        step_id=str(step),
                    )
                tool_outcome = self._handle_native_tool_calls(tool_calls, messages, task_id, run_id, str(step))
                last_tool_failures = tool_outcome.get("failures", [])
                last_tool_executions = tool_outcome.get("executions", [])
                continue
            consecutive_tool_calls = 0

            if finish_reason == "stop":
                messages.append({"role": "assistant", "content": content})
                if self.memory_store:
                    self.memory_store.append_message(task_id, "assistant", content, run_id=run_id, step_id=str(step))
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
                self.memory_store.append_message(task_id, "assistant", content, run_id=run_id, step_id=str(step))
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

        self._trace(f"[runtime] task_finished final={self._preview(final_answer)}")
        self._run_parallel_completed_finalizers(
            task_id=task_id,
            run_id=run_id,
            user_input=user_input,
            final_answer=final_answer,
            stop_reason=stop_reason,
            runtime_status=task_finished_status,
            tool_failures=last_tool_failures,
            final_answer_written=final_answer_written,
        )
        self._active_todo_context = finalize_active_todo_context(
            current_context=self._active_todo_context,
            runtime_state=runtime_state,
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

    def _generate_run_postmortem(self, task_id: str, run_id: str) -> None:
        generate_postmortem(task_id=task_id, run_id=run_id)

    def _run_parallel_completed_finalizers(
        self,
        task_id: str,
        run_id: str,
        user_input: str,
        final_answer: str,
        stop_reason: str,
        runtime_status: str,
        tool_failures: List[Dict[str, str]],
        final_answer_written: bool,
    ) -> None:
        tasks: List[tuple[str, Callable[[], None]]] = [
            ("postmortem", lambda: self._generate_run_postmortem(task_id=task_id, run_id=run_id)),
            (
                "task_memory",
                lambda: self._finalize_task_memory(
                    task_id=task_id,
                    run_id=run_id,
                    user_input=user_input,
                    final_answer=final_answer,
                    stop_reason=stop_reason,
                    runtime_status=runtime_status,
                    tool_failures=tool_failures,
                ),
            ),
            (
                "user_preferences",
                lambda: self._capture_user_preferences(task_id=task_id, run_id=run_id, user_input=user_input),
            ),
            (
                "final_compaction",
                lambda: finalize_memory_compaction(
                    task_id=task_id,
                    final_answer=final_answer,
                    final_answer_written=final_answer_written,
                    memory_store=self.memory_store,
                    enable_finalize_compaction=self.compression_config.enable_finalize_compaction,
                ),
            ),
        ]
        max_workers = max(len(tasks), 1)
        with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="runtime-finalize") as executor:
            futures = {executor.submit(fn): name for name, fn in tasks}
            for future, name in futures.items():
                try:
                    future.result()
                except Exception as e:
                    self._trace(f"[runtime] finalize_task_failed name={name} error={str(e)}")

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
        retry_guidance = self._build_retry_guidance_prompt()
        if retry_guidance:
            parts.append(retry_guidance)
        return "\n\n".join(parts)

    def _build_retry_guidance_prompt(self) -> str:
        ctx = self._active_todo_context if isinstance(self._active_todo_context, dict) else {}
        todo_id = str(ctx.get("todo_id", "") or "").strip()
        subtask_number = ctx.get("active_subtask_number")
        guidance = ctx.get("active_retry_guidance", [])
        if isinstance(guidance, str):
            guidance = [guidance]
        if not todo_id or subtask_number in (None, "") or not isinstance(guidance, list):
            return ""
        guidance_items = [str(item).strip() for item in guidance if str(item).strip()]
        if not guidance_items:
            return ""
        lines = [
            "Retry Guidance:",
            f"- Active todo: {todo_id}",
            f"- Active subtask: {subtask_number}",
            "- The current attempt is a retry/resume path. Follow these constraints when executing:",
        ]
        lines.extend([f"- {item}" for item in guidance_items])
        lines.append("- Do not repeat the previous failed execution pattern if these constraints conflict with it.")
        return "\n".join(lines)

    def _handle_native_tool_calls(
        self,
        tool_calls: List[Dict[str, Any]],
        messages: List[Dict[str, Any]],
        task_id: str,
        run_id: str,
        step_id: str,
    ) -> Dict[str, Any]:
        failures: List[Dict[str, str]] = []
        executions: List[Dict[str, Any]] = []
        for call in tool_calls:
            fn = call.get("function", {}) if isinstance(call, dict) else {}
            tool_name = str(fn.get("name", "")).strip()
            raw_args = fn.get("arguments", "{}") if isinstance(fn, dict) else "{}"
            tool_args = parse_json_dict(raw_args) if isinstance(raw_args, str) else (raw_args or {})
            if not isinstance(tool_args, dict):
                tool_args = {}
            if tool_name in {"plan_task", "create_task", "update_task"} and not self._prepare_phase_completed:
                prepare_guard_error = self._build_prepare_phase_guard_error(tool_name)
                emit_event(
                    task_id=task_id,
                    run_id=run_id,
                    actor="main",
                    role="general",
                    event_type="tool_failed",
                    status="error",
                    payload={"tool": tool_name, "error": str(prepare_guard_error.get("error", ""))},
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": str(call.get("id", "")),
                        "content": '{"success": false, "error": "Prepare phase not completed"}',
                    }
                )
                failures.append({"tool": tool_name, "error": str(prepare_guard_error.get("error", ""))})
                executions.append(
                    {
                        "tool": tool_name,
                        "args": tool_args,
                        "success": False,
                        "error": str(prepare_guard_error.get("error", "")),
                        "payload": (
                            prepare_guard_error.get("result", {})
                            if isinstance(prepare_guard_error.get("result"), dict)
                            else {}
                        ),
                    }
                )
                continue
            if tool_name == "plan_task":
                active_todo_id = str(self._active_todo_context.get("todo_id", "") or "").strip()
                binding_state = str(self._active_todo_context.get("binding_state", "") or "").strip()
                if active_todo_id and binding_state == "bound" and not str(tool_args.get("active_todo_id", "") or "").strip():
                    tool_args = dict(tool_args)
                    tool_args["active_todo_id"] = active_todo_id
            current_todo_id = str(self._active_todo_context.get("todo_id", "") or "").strip()
            binding_state = str(self._active_todo_context.get("binding_state", "") or "unbound").strip()
            if tool_name == "create_task":
                create_task_arg_error = build_create_task_arg_error(tool_args, self._active_todo_context)
                if create_task_arg_error:
                    emit_event(
                        task_id=task_id,
                        run_id=run_id,
                        actor="main",
                        role="general",
                        event_type="tool_failed",
                        status="error",
                        payload={"tool": tool_name, "error": str(create_task_arg_error.get("error", ""))},
                    )
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": str(call.get("id", "")),
                            "content": '{"success": false, "error": "Invalid create_task arguments"}',
                        }
                    )
                    failures.append({"tool": tool_name, "error": str(create_task_arg_error.get("error", ""))})
                    executions.append(
                        {
                            "tool": tool_name,
                            "args": tool_args,
                            "success": False,
                            "error": str(create_task_arg_error.get("error", "")),
                            "payload": (
                                create_task_arg_error.get("result", {})
                                if isinstance(create_task_arg_error.get("result"), dict)
                                else {}
                            ),
                        }
                    )
                    continue
            if tool_name == "create_task" and current_todo_id and binding_state == "bound" and not bool(tool_args.get("force_new_cycle")):
                outcome = build_duplicate_todo_binding_error(self._active_todo_context)
                emit_event(
                    task_id=task_id,
                    run_id=run_id,
                    actor="main",
                    role="general",
                    event_type="tool_failed",
                    status="error",
                    payload={"tool": tool_name, "error": str(outcome.get("error", ""))},
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": str(call.get("id", "")),
                        "content": '{"success": false, "error": "Active todo already bound for this task"}',
                    }
                )
                failures.append({"tool": tool_name, "error": str(outcome.get("error", ""))})
                executions.append(
                    {
                        "tool": tool_name,
                        "args": tool_args,
                        "success": False,
                        "error": str(outcome.get("error", "")),
                        "payload": outcome.get("result", {}) if isinstance(outcome.get("result"), dict) else {},
                    }
                )
                continue
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
                step_id=step_id,
                tool_registry=self.tool_registry,
                memory_store=self.memory_store,
                enrich_runtime_tool_args=self._enrich_runtime_tool_args,
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
            model_provider=self.model_provider,
            enable_llm_recovery_planner=self.enable_llm_recovery_planner,
            build_recovery_planner_config=self._build_recovery_planner_config,
            parse_json_dict=self._parse_json_dict,
        )

    def _append_recovery_summary_for_user(self, answer: str) -> str:
        return append_recovery_summary_for_user(answer=answer, recovery=self._latest_todo_recovery)

    def _enrich_runtime_tool_args(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        task_id: str,
        run_id: str,
        step_id: str,
    ) -> Dict[str, Any]:
        db_file = ""
        if self.memory_store is not None:
            db_file = str(getattr(self.memory_store, "db_file", "") or "").strip()
        return enrich_runtime_tool_args(
            tool_name=tool_name,
            tool_args=tool_args,
            task_id=task_id,
            run_id=run_id,
            step_id=step_id,
            enable_memory_card_metadata_llm=self.enable_memory_card_metadata_llm,
            memory_store_db_file=db_file,
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

    def _build_recovery_planner_config(self) -> GenerationConfig:
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
            max_tokens=1200,
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
            context_window_tokens=self.compression_config.compression_trigger_window_tokens,
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
