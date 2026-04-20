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
    estimate_context_usage,
    extract_finish_reason_and_message,
    extract_missing_info_hints,
    parse_json_dict,
    preview,
    preview_json,
    slug,
)
from app.core.runtime.token_counter import (
    build_request_token_metrics,
    count_chat_messages_tokens,
    resolve_request_model_id,
)
from app.core.runtime.task_token_store import TaskTokenStore
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


PREPARE_PLANNER_SYSTEM_PROMPT = """你是 Runtime 的前置 Todo 规划器。

你的职责只有思考，不执行，不调用工具，不读取文件，不探索环境。

请基于输入事实判断：
1. 当前请求是否需要使用 todo 跟踪
2. 如果需要，输出一份可直接交给 plan_task 的完整计划
3. 如果输入已提供 current_state_summary，请把它视为“当前已有内容”的事实基础，不要把已存在的工作重新规划成从零开始

要求：
1. 只输出 JSON
2. 不要输出 markdown
3. 不要请求调用任何工具
4. 若 active_todo_exists=true，优先沿用 active_todo_id，不要重新开始新 todo
5. 当 should_use_todo=true 时，必须一次性给出 task_name/context/split_reason/subtasks
6. subtasks 至少 1 项，每项至少包含 name、description、split_rationale
7. 若已有 active todo，可用一个“承接当前请求并继续推进”的 bootstrap 子任务作为最小更新骨架

输出 JSON 结构：
{
  "should_use_todo": true,
  "task_name": "string",
  "context": "string",
  "split_reason": "string",
  "subtasks": [
    {
      "name": "string",
      "description": "string",
      "split_rationale": "string",
      "dependencies": ["optional task number strings"],
      "acceptance_criteria": ["optional string array"]
    }
  ],
  "notes": ["string"]
}
"""

PHASE_OVERLAY_PROMPTS = {
    "preparing": (
        "[Current Phase]\n"
        "You are currently in preparing phase.\n"
        "Primary goal: understand the task, decide whether todo tracking is needed, and shape the execution skeleton.\n"
        "You may use lightweight observational abilities when genuinely helpful, such as checking time, reviewing history, and reading current runtime facts.\n"
        "Do not expand into full execution, broad exploration, or deliver final artifacts in this phase."
    ),
    "executing": (
        "[Current Phase]\n"
        "You are currently in executing phase.\n"
        "Primary goal: advance the task, use tools when needed, and complete the requested work.\n"
        "Do not restart broad planning unless execution is genuinely blocked."
    ),
    "finalizing": (
        "[Current Phase]\n"
        "You are currently in finalizing phase.\n"
        "Primary goal: evaluate existing results, summarize honestly, and close out this run.\n"
        "Do not expand task scope during closeout."
    ),
}


class AgentRuntime:
    START_RECALL_TOP_K = 5
    START_RECALL_MIN_SCORE = 0.65
    START_RECALL_CANDIDATE_POOL = 50
    TODO_BINDING_GUARD_MODE = "warn"
    TODO_BINDING_EXEMPT_TOOLS = {
        "plan_task",
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
        enable_llm_todo_planner: Optional[bool] = None,
        clarification_judge_confidence_threshold: float = 0.60,
        enable_clarification_heuristic_fallback: bool = True,
        system_memory_store: Optional[SystemMemoryStore] = None,
        compression_config: Optional[RuntimeCompressionConfig] = None,
        user_preference_config: Optional[RuntimeUserPreferenceConfig] = None,
        task_token_store: Optional[TaskTokenStore] = None,
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
        self.task_token_store = task_token_store
        if self.task_token_store is None:
            try:
                self.task_token_store = TaskTokenStore()
            except Exception:
                self.task_token_store = None
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
        if enable_llm_todo_planner is None:
            # Default on for real providers, off for deterministic test mock provider.
            self.enable_llm_todo_planner = self.model_provider.__class__.__name__ != "MockModelProvider"
        else:
            self.enable_llm_todo_planner = bool(enable_llm_todo_planner)
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
        self._runtime_phase = "preparing"

    def _set_runtime_phase(self, phase: str, task_id: str = "", run_id: str = "") -> None:
        phase_norm = str(phase or "").strip().lower() or "executing"
        if phase_norm not in PHASE_OVERLAY_PROMPTS:
            phase_norm = "executing"
        previous = str(getattr(self, "_runtime_phase", "") or "").strip().lower()
        if previous == phase_norm:
            self._runtime_phase = phase_norm
            return
        if previous and task_id and run_id:
            emit_event(
                task_id=task_id,
                run_id=run_id,
                actor="main",
                role="general",
                event_type="phase_completed",
                payload={"phase": previous},
            )
        self._runtime_phase = phase_norm
        if task_id and run_id:
            emit_event(
                task_id=task_id,
                run_id=run_id,
                actor="main",
                role="general",
                event_type="phase_started",
                payload={"phase": phase_norm},
            )

    def _build_prepare_planner_config(self) -> GenerationConfig:
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
            max_tokens=900,
            provider_options=options,
        )

    def _load_active_todo_full_text(self, todo_id: str) -> str:
        todo_id = str(todo_id or "").strip()
        if not todo_id:
            return ""
        try:
            from app.tool.todo_tool.todo_tool import _get_task_by_todo_id

            task_data = _get_task_by_todo_id(todo_id)
        except Exception:
            task_data = None
        if not isinstance(task_data, dict):
            return ""
        filepath = str(task_data.get("filepath", "") or "").strip()
        if not filepath:
            return ""
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return f.read()
        except Exception:
            return ""

    def _run_prepare_phase_rule_fallback(self, args: Dict[str, Any], task_id: str, run_id: str) -> Dict[str, Any]:
        if not self.tool_registry.has("prepare_task"):
            self._prepare_phase_completed = False
            self._prepare_phase_result = {}
            return {}
        fallback_args = {
            "task_name": str(args.get("task_name", "") or "").strip(),
            "context": str(args.get("context", "") or "").strip(),
            "active_todo_id": str(args.get("active_todo_id", "") or "").strip(),
            "active_todo_exists": bool(args.get("active_todo_exists")),
            "active_todo_summary": str(args.get("active_todo_summary", "") or "").strip(),
            "active_subtask_number": int(args.get("active_subtask_number") or 0),
            "active_subtask_status": str(args.get("active_subtask_status", "") or "").strip(),
            "execution_intent": str(args.get("execution_intent", "") or "").strip(),
            "resume_from_waiting": bool(args.get("resume_from_waiting")),
        }
        emit_event(
            task_id=task_id,
            run_id=run_id,
            actor="main",
            role="general",
            event_type="tool_called",
            payload={"tool": "prepare_task", "args": fallback_args, "source": "rule_fallback"},
        )
        result = self.tool_registry.invoke("prepare_task", fallback_args)
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
                payload={"tool": "prepare_task", "error": str(result.get("error", "")), "source": "rule_fallback"},
            )
            return {}
        emit_event(
            task_id=task_id,
            run_id=run_id,
            actor="main",
            role="general",
            event_type="tool_succeeded",
            payload={"tool": "prepare_task", "error": "", "source": "rule_fallback"},
        )
        payload = result.get("result", {})
        prepared = payload if isinstance(payload, dict) else {}
        if not str(prepared.get("current_state_summary", "") or "").strip():
            current_state_scan = args.get("current_state_scan", {}) if isinstance(args.get("current_state_scan"), dict) else {}
            prepared["current_state_scan"] = current_state_scan
            prepared["current_state_summary"] = str(current_state_scan.get("summary", "") or "").strip()
        prepared["planner_source"] = "rule_fallback"
        self._prepare_phase_completed = True
        self._prepare_phase_result = prepared
        return prepared

    def _run_prepare_phase_llm(self, args: Dict[str, Any], task_id: str, run_id: str) -> Dict[str, Any]:
        current_state_scan = args.get("current_state_scan", {}) if isinstance(args.get("current_state_scan"), dict) else {}
        abandon_subtasks: List[int] = []
        if bool(args.get("resume_from_waiting")):
            unfinished = current_state_scan.get("unfinished_subtasks", [])
            if isinstance(unfinished, list):
                for item in unfinished:
                    if not isinstance(item, dict):
                        continue
                    number_text = str(item.get("number", "") or "").strip()
                    if number_text.isdigit():
                        abandon_subtasks.append(int(number_text))
        abandon_subtasks = sorted(set(abandon_subtasks))
        payload = {
            "user_input": str(args.get("context", "") or "").strip(),
            "active_todo_exists": bool(args.get("active_todo_exists")),
            "active_todo_id": str(args.get("active_todo_id", "") or "").strip(),
            "active_todo_full_text": str(args.get("active_todo_full_text", "") or "").strip(),
            "current_state_summary": str(current_state_scan.get("summary", "") or "").strip(),
            "current_state_scan": current_state_scan,
            "active_subtask_number": int(args.get("active_subtask_number") or 0),
            "execution_phase": str(args.get("execution_phase", "") or "planning").strip() or "planning",
            "resume_from_waiting": bool(args.get("resume_from_waiting")),
            "latest_recovery": args.get("latest_recovery", {}) if isinstance(args.get("latest_recovery"), dict) else {},
        }
        emit_event(
            task_id=task_id,
            run_id=run_id,
            actor="main",
            role="general",
            event_type="tool_called",
            payload={"tool": "planning_llm_prepare", "args": payload},
        )
        output = self.model_provider.generate(
            messages=[
                {"role": "system", "content": PREPARE_PLANNER_SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            tools=[],
            config=self._build_prepare_planner_config(),
        )
        parsed = parse_json_dict(str(getattr(output, "content", "") or ""))
        should_use_todo = bool(parsed.get("should_use_todo"))
        notes = parsed.get("notes", [])
        if not isinstance(notes, list):
            notes = []
        prepared = {
            "success": True,
            "should_use_todo": should_use_todo,
            "task_name": str(parsed.get("task_name", "") or "").strip() or str(args.get("task_name", "") or "").strip(),
            "context": str(parsed.get("context", "") or "").strip() or str(args.get("context", "") or "").strip(),
            "split_reason": str(parsed.get("split_reason", "") or "").strip(),
            "subtasks": self._normalize_prepare_subtasks(
                parsed.get("subtasks", []) if isinstance(parsed.get("subtasks"), list) else [],
                split_reason=str(parsed.get("split_reason", "") or "").strip(),
            ),
            "planning_confidence": "high" if should_use_todo else "low",
            "active_todo_id": str(args.get("active_todo_id", "") or "").strip(),
            "active_todo_summary": "",
            "current_state_scan": current_state_scan,
            "current_state_summary": str(current_state_scan.get("summary", "") or "").strip(),
            "abandon_subtasks": abandon_subtasks,
            "abandon_reason": (
                "收到澄清回复后，旧计划中的未完成 subtasks 先标记为 abandoned，再继续追加新计划。"
                if abandon_subtasks
                else ""
            ),
            "notes": [str(item).strip() for item in notes if str(item).strip()],
            "planner_source": "llm",
        }
        if should_use_todo:
            subtasks = prepared.get("subtasks", [])
            if (
                not prepared["task_name"]
                or not prepared["context"]
                or not prepared["split_reason"]
                or not isinstance(subtasks, list)
                or not subtasks
            ):
                raise ValueError("invalid_llm_prepare_output_missing_required_fields")
            prepared["recommended_plan_task_args"] = {
                "task_name": prepared["task_name"],
                "context": prepared["context"],
                "split_reason": prepared["split_reason"],
                "subtasks": subtasks,
                "active_todo_id": prepared["active_todo_id"],
            }
        emit_event(
            task_id=task_id,
            run_id=run_id,
            actor="main",
            role="general",
            event_type="tool_succeeded",
            payload={"tool": "planning_llm_prepare", "error": ""},
        )
        self._prepare_phase_completed = True
        self._prepare_phase_result = prepared
        return prepared

    def _run_prepare_phase(self, user_input: str, task_id: str, run_id: str, resume_from_waiting: bool = False) -> Dict[str, Any]:
        ctx = self._active_todo_context if isinstance(self._active_todo_context, dict) else {}
        todo_id = str(ctx.get("todo_id", "") or "").strip()
        active_number = ctx.get("active_subtask_number")
        if active_number in (None, ""):
            active_number = 0
        active_status = ""
        execution_phase = str(ctx.get("execution_phase", "") or "planning").strip() or "planning"
        if active_number:
            active_status = "in-progress" if execution_phase == "executing" else ""
        current_state_scan: Dict[str, Any] = {}
        if todo_id:
            try:
                from app.tool.todo_tool.todo_tool import _build_current_state_scan

                current_state_scan = _build_current_state_scan(todo_id)
            except Exception:
                current_state_scan = {}
        args = {
            "task_name": self._extract_title_topic(user_input),
            "context": user_input,
            "active_todo_id": todo_id,
            "active_todo_exists": bool(todo_id),
            "active_todo_summary": "",
            "active_todo_full_text": self._load_active_todo_full_text(todo_id),
            "active_subtask_number": int(active_number or 0),
            "active_subtask_status": active_status,
            "execution_phase": execution_phase,
            "current_state_scan": current_state_scan,
            "resume_from_waiting": bool(resume_from_waiting),
            "latest_recovery": self._latest_todo_recovery if isinstance(self._latest_todo_recovery, dict) else {},
            "execution_intent": "runtime_preflight",
        }
        if not self.enable_llm_todo_planner:
            return self._run_prepare_phase_rule_fallback(args=args, task_id=task_id, run_id=run_id)
        try:
            return self._run_prepare_phase_llm(args=args, task_id=task_id, run_id=run_id)
        except Exception as e:
            emit_event(
                task_id=task_id,
                run_id=run_id,
                actor="main",
                role="general",
                event_type="tool_failed",
                status="error",
                payload={"tool": "planning_llm_prepare", "error": str(e), "source": "llm_fallback_to_rule"},
            )
            return self._run_prepare_phase_rule_fallback(args=args, task_id=task_id, run_id=run_id)

    def _render_prepare_phase_message(self, prepared: Dict[str, Any]) -> str:
        if not isinstance(prepared, dict) or not prepared:
            return ""
        lines = [
            "[Prepare Phase]",
            f"should_use_todo={bool(prepared.get('should_use_todo'))}",
        ]
        active_todo_id = str(prepared.get("active_todo_id", "") or "").strip()
        if active_todo_id:
            lines.append(f"active_todo_id={active_todo_id}")
        active_summary = str(prepared.get("active_todo_summary", "") or "").strip()
        if active_summary:
            lines.append(f"active_todo_summary={active_summary}")
        current_state_summary = str(prepared.get("current_state_summary", "") or "").strip()
        if current_state_summary:
            lines.append(f"current_state_summary={current_state_summary}")
        notes = prepared.get("notes", [])
        if isinstance(notes, list):
            normalized_notes = [str(item).strip() for item in notes if str(item).strip()]
            if normalized_notes:
                lines.append("notes:")
                lines.extend([f"- {item}" for item in normalized_notes[:4]])
        abandon_subtasks = prepared.get("abandon_subtasks", [])
        if isinstance(abandon_subtasks, list) and abandon_subtasks:
            lines.append("abandon_subtasks=" + ",".join([str(item) for item in abandon_subtasks if str(item).strip()]))
        suggested = prepared.get("recommended_plan_task_args", {})
        if isinstance(suggested, dict) and suggested:
            lines.append("If you decide to use todo tracking, prefer calling plan_task with these prepared fields instead of designing a new plan from scratch.")
            lines.append(preview_json(suggested, max_len=800))
        return "\n".join(lines).strip()

    def _render_prepare_cli_summary(self, user_input: str, prepared: Dict[str, Any]) -> str:
        if not isinstance(prepared, dict) or not prepared:
            return ""
        task_goal = str(prepared.get("context", "") or "").strip() or str(user_input or "").strip()
        task_goal = self._preview(task_goal, 120)
        should_use_todo = bool(prepared.get("should_use_todo"))
        active_todo_id = str(prepared.get("active_todo_id", "") or "").strip()
        decision = "启用 todo" if should_use_todo else "不启用 todo"
        if active_todo_id:
            decision = f"沿用已有 todo（{active_todo_id}）" if should_use_todo else f"继续参考已有 todo（{active_todo_id}）"
        next_phase = "executing"
        subtasks = prepared.get("subtasks", [])
        if not isinstance(subtasks, list):
            subtasks = []
        plan_summary = ""
        if should_use_todo and subtasks:
            names = [str(item.get("name", "")).strip() for item in subtasks if isinstance(item, dict) and str(item.get("name", "")).strip()]
            if names:
                plan_summary = " -> ".join(names[:3])
        if not plan_summary:
            notes = prepared.get("notes", [])
            if isinstance(notes, list):
                note_items = [str(item).strip() for item in notes if str(item).strip()]
                if note_items:
                    plan_summary = "；".join(note_items[:2])
        if not plan_summary:
            split_reason = str(prepared.get("split_reason", "") or "").strip()
            if split_reason:
                plan_summary = self._preview(split_reason, 80)
        if not plan_summary:
            plan_summary = "进入执行阶段"
        split_reason = str(prepared.get("split_reason", "") or "").strip()
        lines = [
            "[Prepare]",
            f"任务目标：{task_goal}",
            f"决策：{decision}",
            f"下一阶段：{next_phase}",
            f"拆分理由：{self._preview(split_reason, 120) if split_reason else '未显式提供'}",
            f"计划摘要：{plan_summary}",
        ]
        current_state_summary = str(prepared.get("current_state_summary", "") or "").strip()
        if current_state_summary:
            lines.append(f"当前现状：{self._preview(current_state_summary, 140)}")
        abandon_subtasks = prepared.get("abandon_subtasks", [])
        if isinstance(abandon_subtasks, list) and abandon_subtasks:
            preview_list = ", ".join([f"Task {item}" for item in abandon_subtasks if str(item).strip()])
            if preview_list:
                lines.append(f"旧计划处理：将废弃 {self._preview(preview_list, 140)}")
        if subtasks:
            lines.append("计划明细：")
            for idx, item in enumerate(subtasks, 1):
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name", "") or "").strip() or f"子任务 {idx}"
                description = str(item.get("description", "") or "").strip()
                split_rationale = str(item.get("split_rationale", "") or "").strip()
                line = f"{idx}. {name}"
                if description:
                    line += f"：{self._preview(description, 120)}"
                lines.append(line)
                if split_rationale:
                    lines.append(f"   拆分依据：{self._preview(split_rationale, 120)}")
        return "\n".join(lines).strip()

    def _normalize_prepare_subtasks(self, subtasks: Any, split_reason: str = "") -> List[Dict[str, Any]]:
        if not isinstance(subtasks, list):
            return []
        normalized: List[Dict[str, Any]] = []
        total = len(subtasks)
        for idx, item in enumerate(subtasks, 1):
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "") or item.get("title", "") or "").strip()
            description = str(item.get("description", "") or item.get("desc", "") or "").strip()
            if not name or not description:
                continue
            split_rationale = str(
                item.get("split_rationale")
                or item.get("split_reason")
                or item.get("rationale")
                or item.get("reason")
                or ""
            ).strip()
            if not split_rationale:
                if total == 1:
                    split_rationale = split_reason or "将任务先收敛为一个最小可执行步骤，便于进入执行阶段。"
                elif idx == 1:
                    split_rationale = "先完成首个基础步骤，建立后续执行所需的上下文。"
                else:
                    split_rationale = "将任务拆成更小步骤，降低执行复杂度并便于跟踪进度。"
            normalized_item: Dict[str, Any] = {
                "name": name,
                "description": description,
                "split_rationale": split_rationale,
            }
            dependencies = item.get("dependencies", [])
            if isinstance(dependencies, list):
                deps = [str(dep).strip() for dep in dependencies if str(dep).strip()]
                if deps:
                    normalized_item["dependencies"] = deps
            acceptance_criteria = item.get("acceptance_criteria", [])
            if isinstance(acceptance_criteria, list):
                criteria = [str(entry).strip() for entry in acceptance_criteria if str(entry).strip()]
                if criteria:
                    normalized_item["acceptance_criteria"] = criteria
            for key in ["owner", "kind", "origin_subtask_id", "origin_subtask_number", "subtask_id", "status", "priority"]:
                value = str(item.get(key, "") or "").strip()
                if value:
                    normalized_item[key] = value
            normalized.append(normalized_item)
        return normalized

    def _build_prepare_phase_guard_error(self, tool_name: str) -> Dict[str, Any]:
        prepared = self._prepare_phase_result if isinstance(self._prepare_phase_result, dict) else {}
        guidance = (
            "Prepare phase must run before planning tools. "
            "Run prepare_task first, then call plan_task using the prepared result."
        )
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
        todo_id = str(prepared.get("active_todo_id", "") or "").strip()
        abandon_subtasks = prepared.get("abandon_subtasks", [])
        if todo_id and isinstance(abandon_subtasks, list):
            for subtask_number in abandon_subtasks:
                number_text = str(subtask_number).strip()
                if not number_text.isdigit():
                    continue
                abandon_args = {
                    "todo_id": todo_id,
                    "subtask_number": int(number_text),
                    "status": "abandoned",
                }
                tool_name = "update_task_status"
                emit_event(
                    task_id=task_id,
                    run_id=run_id,
                    actor="main",
                    role="general",
                    event_type="tool_called",
                    payload={"tool": tool_name, "args": abandon_args, "source": "prepare_phase_auto_abandon"},
                )
                result = self.tool_registry.invoke(tool_name, abandon_args)
                event_type = "tool_succeeded" if result.get("success") else "tool_failed"
                emit_event(
                    task_id=task_id,
                    run_id=run_id,
                    actor="main",
                    role="general",
                    event_type=event_type,
                    status="ok" if result.get("success") else "error",
                    payload={"tool": tool_name, "error": str(result.get("error", "")), "source": "prepare_phase_auto_abandon"},
                )
                self._append_internal_tool_execution_to_messages(
                    messages=messages,
                    task_id=task_id,
                    run_id=run_id,
                    step_id="prepare",
                    tool_name=tool_name,
                    tool_args=abandon_args,
                    result=result,
                    call_id=f"auto_prepare_{tool_name}_{self._slug(run_id)}_{number_text}",
                )
                execution_payload = result.get("result", {})
                execution = {
                    "tool": tool_name,
                    "args": abandon_args,
                    "success": bool(result.get("success")),
                    "error": str(result.get("error", "")),
                    "payload": execution_payload if isinstance(execution_payload, dict) else {},
                }
                self._active_todo_context = update_active_todo_context(
                    current_context=self._active_todo_context,
                    executions=[execution],
                )
        if not bool(prepared.get("should_use_todo")):
            return {}
        suggested = prepared.get("recommended_plan_task_args", {})
        if not isinstance(suggested, dict) or not suggested:
            return {}
        subtasks = suggested.get("subtasks")
        if not isinstance(subtasks, list) or not subtasks:
            return {}
        tool_name = "plan_task"
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
        self._runtime_phase = ""
        self._set_runtime_phase("preparing", task_id=task_id, run_id=run_id)
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
        prepared = self._run_prepare_phase(
            user_input=user_input,
            task_id=task_id,
            run_id=run_id,
            resume_from_waiting=resume_from_waiting,
        )
        self._maybe_apply_prepared_plan(
            prepared=prepared,
            messages=messages,
            task_id=task_id,
            run_id=run_id,
        )
        prepare_message = self._render_prepare_phase_message(prepared)
        if prepare_message:
            messages.append({"role": "system", "content": prepare_message})
        prepare_cli_summary = self._render_prepare_cli_summary(user_input=user_input, prepared=prepared)
        if prepare_cli_summary:
            self._trace(prepare_cli_summary)
        previous_base_system_prompt = self._build_system_prompt()
        self._set_runtime_phase("executing", task_id=task_id, run_id=run_id)
        if messages and isinstance(messages[0], dict) and messages[0].get("role") == "system":
            messages[0]["content"] = self._refresh_first_system_prompt_preserving_dynamic_context(
                current_content=str(messages[0].get("content", "") or ""),
                previous_base_prompt=previous_base_system_prompt,
            )
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

        # Runtime 主循环只负责“编排”三件事：请求模型、执行工具、收敛本轮状态。
        # 具体的 todo 恢复、memory 生命周期、verification handoff 都尽量下沉到独立模块。
        for step in range(1, self.max_steps + 1):
            step_messages = self._build_step_seed_messages(step=step, user_input=user_input)
            tools = self.tool_registry.list_tool_schemas()
            messages = self._maybe_compact_mid_run(
                step=step,
                task_id=task_id,
                run_id=run_id,
                messages=messages,
                tools=tools,
                consecutive_tool_calls=consecutive_tool_calls,
            )
            request_metrics = self._build_request_token_metrics(messages=messages, tools=tools)
            request_metrics["step"] = step
            request_metrics["context_usage_ratio"] = round(
                self._estimate_context_usage(int(request_metrics.get("input_tokens", 0) or 0)),
                4,
            )
            request_metrics["compression_trigger_window_tokens"] = (
                self.compression_config.compression_trigger_window_tokens
            )
            request_metrics["model_context_window_tokens"] = self.compression_config.model_context_window_tokens
            emit_event(
                task_id=task_id,
                run_id=run_id,
                actor="main",
                role="general",
                event_type="model_request_started",
                payload=request_metrics,
            )
            self._record_task_token_metrics(task_id=task_id, run_id=run_id, step=step, metrics=request_metrics)
            self._trace(f"[step {step}] model_request")
            try:
                model_output = self.model_provider.generate(
                    messages=messages,
                    tools=tools,
                    config=self.generation_config,
                )
            except Exception as e:
                self._record_task_token_metrics(
                    task_id=task_id,
                    run_id=run_id,
                    step=step,
                    metrics=self._with_step_input_tokens(request_metrics, step_messages),
                )
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
                # Event compaction trigger is based on current tool_calls batch size.
                consecutive_tool_calls = len(tool_calls)
                self._trace(f"[step {step}] execute_tool_calls count={len(tool_calls)}")
                assistant_tool_message = {
                    "role": "assistant",
                    "content": raw_message.get("content", "") or "",
                    "tool_calls": tool_calls,
                }
                messages.append(assistant_tool_message)
                step_messages.append(dict(assistant_tool_message))
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
                batch_messages = tool_outcome.get("appended_messages", [])
                if isinstance(batch_messages, list):
                    step_messages.extend([dict(item) for item in batch_messages if isinstance(item, dict)])
                self._record_task_token_metrics(
                    task_id=task_id,
                    run_id=run_id,
                    step=step,
                    metrics=self._with_step_input_tokens(request_metrics, step_messages),
                )
                continue
            consecutive_tool_calls = 0

            if finish_reason == "stop":
                assistant_message = {"role": "assistant", "content": content}
                messages.append(assistant_message)
                step_messages.append(dict(assistant_message))
                if self.memory_store:
                    self.memory_store.append_message(task_id, "assistant", content, run_id=run_id, step_id=str(step))
                    final_answer_written = True
                self._record_task_token_metrics(
                    task_id=task_id,
                    run_id=run_id,
                    step=step,
                    metrics=self._with_step_input_tokens(request_metrics, step_messages),
                )
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
                self._trace(f"[step {step}] completed finish_reason=stop final={self._preview(final_answer)}")
                break

            assistant_message = {"role": "assistant", "content": content}
            messages.append(assistant_message)
            step_messages.append(dict(assistant_message))
            if self.memory_store:
                self.memory_store.append_message(task_id, "assistant", content, run_id=run_id, step_id=str(step))
                final_answer_written = True
            self._record_task_token_metrics(
                task_id=task_id,
                run_id=run_id,
                step=step,
                metrics=self._with_step_input_tokens(request_metrics, step_messages),
            )

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
        finalizing_outcome = self._run_finalizing_pipeline(
            task_id=task_id,
            run_id=run_id,
            user_input=user_input,
            final_answer=final_answer,
            stop_reason=stop_reason,
            runtime_state=runtime_state,
            task_status=task_status,
            last_tool_failures=last_tool_failures,
            context_messages=messages,
            verification_handoff=verification_handoff,
            handoff_source=handoff_source,
        )
        final_answer = finalizing_outcome["final_answer"]
        if finalizing_outcome.get("mode") == "paused":
            self.last_runtime_state = runtime_state
            self.last_stop_reason = stop_reason
            self._trace(str(finalizing_outcome.get("trace_message", "") or ""))
            return final_answer

        task_finished_status = str(finalizing_outcome.get("task_finished_status", task_status) or task_status)
        verification_handoff = (
            finalizing_outcome.get("verification_handoff", {})
            if isinstance(finalizing_outcome.get("verification_handoff", {}), dict)
            else {}
        )

        self._trace(f"[runtime] task_finished final={self._preview(final_answer)}")
        self._run_parallel_completed_finalizers(
            task_id=task_id,
            run_id=run_id,
            user_input=user_input,
            final_answer=final_answer,
            stop_reason=stop_reason,
            runtime_status=task_finished_status,
            tool_failures=last_tool_failures,
            verification_handoff=verification_handoff,
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
        tools: List[Dict[str, Any]],
        consecutive_tool_calls: int,
    ) -> List[Dict[str, Any]]:
        # context compaction 是 runtime 对上下文预算的调度策略，而不是 memory store 本身的职责。
        return maybe_compact_mid_run(
            step=step,
            task_id=task_id,
            run_id=run_id,
            messages=messages,
            tools=tools,
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
        context_messages: List[Dict[str, Any]],
    ) -> tuple[Dict[str, Any], str]:
        # verification handoff 的触发时机属于 runtime，但 handoff 的构造/归一化属于 eval 能力层。
        return build_verification_handoff(
            user_input=user_input,
            final_answer=final_answer,
            stop_reason=stop_reason,
            runtime_status=runtime_status,
            tool_failures=tool_failures,
            context_messages=context_messages,
            recovery_context=self._latest_todo_recovery,
            model_provider=self.model_provider,
            enabled=self.enable_verification_handoff_llm,
            build_config=self._build_verification_handoff_config,
            parse_json_dict=self._parse_json_dict,
            preview=self._preview,
        )

    def _run_finalizing_pipeline(
        self,
        *,
        task_id: str,
        run_id: str,
        user_input: str,
        final_answer: str,
        stop_reason: str,
        runtime_state: str,
        task_status: str,
        last_tool_failures: List[Dict[str, str]],
        context_messages: List[Dict[str, Any]],
        verification_handoff: Optional[Dict[str, Any]],
        handoff_source: str,
    ) -> Dict[str, Any]:
        # finalizing 是单独的第三阶段：只基于已有结果收尾，不继续扩张执行范围。
        self._set_runtime_phase("finalizing", task_id=task_id, run_id=run_id)
        if runtime_state == "awaiting_user_input":
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
            return {
                "mode": "paused",
                "final_answer": paused_outcome["final_answer"],
                "trace_message": paused_outcome["trace_message"],
                "task_finished_status": task_status,
            }

        self._trace("[runtime] finalizing(answer) started")
        self._trace("[runtime] finalizing(answer) completed")
        if verification_handoff is None:
            self._trace("[runtime] finalizing(handoff) started")
            verification_handoff, handoff_source = self._build_verification_handoff(
                user_input=user_input,
                final_answer=final_answer,
                stop_reason=stop_reason,
                runtime_status=task_status,
                tool_failures=last_tool_failures,
                context_messages=context_messages,
            )
            self._trace(f"[runtime] finalizing(handoff) completed source={handoff_source}")

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
            auto_manage_todo_recovery=self._auto_manage_todo_recovery,
            append_recovery_summary_for_user=self._append_recovery_summary_for_user,
            has_latest_todo_recovery=lambda: bool(self._latest_todo_recovery),
            eval_orchestrator=self.eval_orchestrator,
            emit_event=emit_event,
        )
        return {
            "mode": "completed",
            "final_answer": completed_outcome["final_answer"],
            "verification_handoff": completed_outcome.get("verification_handoff", {}),
            "task_finished_status": completed_outcome["task_finished_status"],
        }

    def _finalize_task_memory(
        self,
        task_id: str,
        run_id: str,
        user_input: str,
        final_answer: str,
        stop_reason: str,
        runtime_status: str,
        tool_failures: List[Dict[str, str]],
        verification_handoff: Dict[str, Any],
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
            verification_handoff=verification_handoff,
            system_memory_store=store,
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
        verification_handoff: Dict[str, Any],
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
                    verification_handoff=verification_handoff,
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
        phase_prompt = PHASE_OVERLAY_PROMPTS.get(self._runtime_phase, "")
        if phase_prompt:
            parts.append(phase_prompt)
        retry_guidance = self._build_retry_guidance_prompt()
        if retry_guidance:
            parts.append(retry_guidance)
        return "\n\n".join(parts)

    def _refresh_first_system_prompt_preserving_dynamic_context(
        self,
        current_content: str,
        previous_base_prompt: str,
    ) -> str:
        current_text = str(current_content or "")
        previous_base = str(previous_base_prompt or "")
        new_base = self._build_system_prompt()
        if not current_text:
            return new_base
        if current_text == previous_base:
            return new_base
        if previous_base and current_text.startswith(previous_base):
            suffix = current_text[len(previous_base) :].lstrip("\n")
            if suffix:
                return f"{new_base}\n\n{suffix}".strip()
            return new_base
        return current_text

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
            if tool_name == "plan_task" and not self._prepare_phase_completed:
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

    def _resolve_request_model_id(self) -> str:
        return resolve_request_model_id(
            config=self.generation_config,
            model_provider=self.model_provider,
            default_model="gpt-4-turbo",
        )

    def _build_request_token_metrics(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        max_output_tokens = self.generation_config.max_tokens if self.generation_config else None
        return build_request_token_metrics(
            messages=messages,
            tools=tools,
            model=self._resolve_request_model_id(),
            max_output_tokens=max_output_tokens,
        )

    def _record_task_token_metrics(
        self,
        *,
        task_id: str,
        run_id: str,
        step: int,
        metrics: Dict[str, Any],
    ) -> None:
        if self.task_token_store is None:
            return
        try:
            self.task_token_store.record_step_metrics(
                task_id=task_id,
                run_id=run_id,
                step=step,
                metrics=metrics,
            )
        except Exception as e:
            self._trace(f"[runtime] task_token_store_failed step={step} error={str(e)}")

    def _build_step_seed_messages(self, step: int, user_input: str) -> List[Dict[str, Any]]:
        if int(step or 0) != 1:
            return []
        return [{"role": "user", "content": user_input}]

    def _count_step_input_tokens(self, step_messages: List[Dict[str, Any]]) -> int:
        if not step_messages:
            return 0
        return count_chat_messages_tokens(
            messages=step_messages,
            model=self._resolve_request_model_id(),
            include_reply_primer=False,
        )

    def _with_step_input_tokens(
        self,
        metrics: Dict[str, Any],
        step_messages: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        payload = dict(metrics)
        payload["step_input_tokens"] = self._count_step_input_tokens(step_messages)
        return payload

    def _estimate_context_tokens(self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]]) -> int:
        return count_chat_messages_tokens(messages=messages, model=self._resolve_request_model_id())

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
