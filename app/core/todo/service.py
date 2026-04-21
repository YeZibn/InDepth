from __future__ import annotations

import json
from typing import Any, Dict, List

from app.core.todo.models import TodoBindingState, TodoContext, TodoExecutionPhase


class TodoService:
    """Owns runtime-facing todo context rules during the transition period."""

    def context_from_dict(self, value: Dict[str, Any] | None) -> TodoContext:
        data = value if isinstance(value, dict) else {}
        number_raw = data.get("active_subtask_number")
        active_subtask_number: int | None
        if number_raw in (None, ""):
            active_subtask_number = None
        else:
            try:
                active_subtask_number = int(number_raw)
            except Exception:
                active_subtask_number = None
        phase_raw = str(data.get("execution_phase", "") or TodoExecutionPhase.PLANNING).strip() or TodoExecutionPhase.PLANNING
        binding_raw = str(data.get("binding_state", "") or TodoBindingState.BOUND).strip() or TodoBindingState.BOUND
        try:
            execution_phase = TodoExecutionPhase(phase_raw)
        except Exception:
            execution_phase = TodoExecutionPhase.PLANNING
        try:
            binding_state = TodoBindingState(binding_raw)
        except Exception:
            binding_state = TodoBindingState.BOUND
        return TodoContext(
            todo_id=str(data.get("todo_id", "") or "").strip(),
            active_subtask_id=str(data.get("active_subtask_id", "") or "").strip() or None,
            active_subtask_number=active_subtask_number,
            execution_phase=execution_phase,
            binding_required=bool(data.get("binding_required")),
            binding_state=binding_state,
            todo_bound_at=str(data.get("todo_bound_at", "") or "").strip(),
        )

    def context_to_dict(self, context: TodoContext) -> Dict[str, Any]:
        return {
            "todo_id": context.todo_id,
            "active_subtask_id": context.active_subtask_id,
            "active_subtask_number": context.active_subtask_number,
            "execution_phase": context.execution_phase.value,
            "binding_required": context.binding_required,
            "binding_state": context.binding_state.value,
            "todo_bound_at": context.todo_bound_at,
        }

    def finalize_context(self, current_context: Dict[str, Any], runtime_state: str) -> Dict[str, Any]:
        context = self.context_from_dict(current_context)
        if not context.todo_id:
            return {}
        if runtime_state == "completed":
            context.binding_state = TodoBindingState.CLOSED
            context.binding_required = False
            context.execution_phase = TodoExecutionPhase.FINALIZING
            context.active_subtask_number = None
            context.active_subtask_id = None
        return self.context_to_dict(context)

    def apply_executions(self, current_context: Dict[str, Any], executions: List[Dict[str, Any]]) -> Dict[str, Any]:
        context = self.context_from_dict(current_context)
        for execution in executions:
            tool = str(execution.get("tool", "")).strip()
            args = execution.get("args", {}) if isinstance(execution.get("args"), dict) else {}
            payload = execution.get("payload", {}) if isinstance(execution.get("payload"), dict) else {}
            if tool == "plan_task" and execution.get("success"):
                mode = str(payload.get("mode", "") or "").strip()
                active_todo_id = str(payload.get("active_todo_id", "") or "").strip()
                execution_result = payload.get("execution_result", {}) if isinstance(payload.get("execution_result"), dict) else {}
                if mode == "create":
                    todo_id = str(execution_result.get("todo_id", "") or "").strip()
                    if todo_id:
                        context = TodoContext(
                            todo_id=todo_id,
                            execution_phase=TodoExecutionPhase.PLANNING,
                            binding_required=True,
                            binding_state=TodoBindingState.BOUND,
                            todo_bound_at=str(execution_result.get("todo_bound_at", "") or "").strip(),
                        )
                elif mode == "update" and active_todo_id:
                    context = TodoContext(
                        todo_id=active_todo_id,
                        execution_phase=TodoExecutionPhase.PLANNING,
                        binding_required=True,
                        binding_state=TodoBindingState.BOUND,
                        todo_bound_at=context.todo_bound_at,
                    )
            elif tool == "update_task_status":
                todo_id = str(args.get("todo_id", payload.get("todo_id", ""))).strip()
                subtask_number = args.get("subtask_number")
                if todo_id and subtask_number is not None:
                    status = str(args.get("status", "") or "").strip()
                    active_number = int(subtask_number)
                    active_subtask_id = str(payload.get("subtask_id", "") or "").strip() or None
                    if status in {"completed", "abandoned", "pending"}:
                        active_number = None
                        active_subtask_id = None
                    phase = TodoExecutionPhase.EXECUTING if status == "in-progress" else TodoExecutionPhase.PLANNING
                    if status in {"blocked", "awaiting_input", "timed_out"}:
                        phase = TodoExecutionPhase.PLANNING
                    binding_state = TodoBindingState.CLOSED if payload.get("all_completed") else TodoBindingState.BOUND
                    context = TodoContext(
                        todo_id=todo_id,
                        active_subtask_id=active_subtask_id,
                        active_subtask_number=active_number,
                        execution_phase=phase,
                        binding_required=True,
                        binding_state=binding_state,
                        todo_bound_at=context.todo_bound_at,
                    )
            elif tool == "update_subtask":
                todo_id = str(args.get("todo_id", payload.get("todo_id", ""))).strip()
                subtask_number = payload.get("subtask_number") or args.get("subtask_number")
                subtask_id = str(payload.get("subtask_id", "") or args.get("subtask_id", "")).strip()
                if todo_id and subtask_number is not None:
                    context = TodoContext(
                        todo_id=todo_id,
                        active_subtask_id=subtask_id or None,
                        active_subtask_number=int(subtask_number),
                        execution_phase=context.execution_phase,
                        binding_required=True,
                        binding_state=context.binding_state,
                        todo_bound_at=context.todo_bound_at,
                    )
            elif tool == "reopen_subtask":
                todo_id = str(args.get("todo_id", payload.get("todo_id", ""))).strip()
                subtask_number = payload.get("subtask_number") or args.get("subtask_number")
                subtask_id = str(payload.get("subtask_id", "") or args.get("subtask_id", "")).strip()
                if todo_id and subtask_number is not None:
                    context = TodoContext(
                        todo_id=todo_id,
                        active_subtask_id=subtask_id or None,
                        active_subtask_number=int(subtask_number),
                        execution_phase=TodoExecutionPhase.EXECUTING,
                        binding_required=True,
                        binding_state=TodoBindingState.BOUND,
                        todo_bound_at=context.todo_bound_at,
                    )
            elif tool == "get_next_task":
                todo_id = str(args.get("todo_id", "")).strip()
                next_task = payload.get("next_task", {}) if isinstance(payload, dict) else {}
                number = next_task.get("number")
                if todo_id and number:
                    context = TodoContext(
                        todo_id=todo_id,
                        active_subtask_id=str(next_task.get("subtask_id", "") or "").strip() or None,
                        active_subtask_number=int(number),
                        execution_phase=TodoExecutionPhase.PLANNING,
                        binding_required=True,
                        binding_state=context.binding_state,
                        todo_bound_at=context.todo_bound_at,
                    )
        return self.context_to_dict(context)

    def restore_context_from_history(self, history: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not isinstance(history, list) or not history:
            return {}

        tool_results_by_call_id: Dict[str, Dict[str, Any]] = {}
        for msg in history:
            if str(msg.get("role", "")).strip().lower() != "tool":
                continue
            call_id = str(msg.get("tool_call_id", "") or "").strip()
            if not call_id:
                continue
            try:
                parsed = json.loads(str(msg.get("content", "") or "").strip() or "{}")
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                tool_results_by_call_id[call_id] = parsed

        executions: List[Dict[str, Any]] = []
        for msg in history:
            if str(msg.get("role", "")).strip().lower() != "assistant":
                continue
            tool_calls = msg.get("tool_calls", [])
            if not isinstance(tool_calls, list):
                continue
            for call in tool_calls:
                if not isinstance(call, dict):
                    continue
                call_id = str(call.get("id", "") or "").strip()
                fn = call.get("function", {}) if isinstance(call.get("function"), dict) else {}
                tool_name = str(fn.get("name", "") or "").strip()
                if not call_id or not tool_name:
                    continue
                tool_result = tool_results_by_call_id.get(call_id)
                if not isinstance(tool_result, dict):
                    continue
                raw_args = fn.get("arguments", "{}")
                if isinstance(raw_args, str):
                    try:
                        tool_args = json.loads(raw_args)
                    except json.JSONDecodeError:
                        tool_args = {}
                else:
                    tool_args = raw_args or {}
                if not isinstance(tool_args, dict):
                    tool_args = {}
                payload = tool_result.get("result", {}) if isinstance(tool_result.get("result"), dict) else {}
                executions.append(
                    {
                        "tool": tool_name,
                        "args": tool_args,
                        "success": bool(tool_result.get("success")),
                        "error": str(tool_result.get("error", "") or ""),
                        "payload": payload,
                    }
                )

        return self.apply_executions(current_context={}, executions=executions)

    def prepare_phase_snapshot(self, current_context: Dict[str, Any]) -> Dict[str, Any]:
        context = self.context_from_dict(current_context)
        active_number = context.active_subtask_number or 0
        active_status = ""
        if active_number:
            active_status = "in-progress" if context.execution_phase == TodoExecutionPhase.EXECUTING else ""
        return {
            "active_todo_id": context.todo_id,
            "active_todo_exists": bool(context.todo_id),
            "active_subtask_number": active_number,
            "active_subtask_status": active_status,
            "execution_phase": context.execution_phase.value,
        }

    def build_prepare_phase_inputs(
        self,
        current_context: Dict[str, Any],
        user_input: str,
        task_name: str,
        active_todo_full_text: str,
        current_state_scan: Dict[str, Any],
        resume_from_waiting: bool,
    ) -> Dict[str, Any]:
        snapshot = self.prepare_phase_snapshot(current_context)
        return {
            "task_name": task_name,
            "context": user_input,
            "active_todo_id": snapshot["active_todo_id"],
            "active_todo_exists": snapshot["active_todo_exists"],
            "active_todo_summary": "",
            "active_todo_full_text": active_todo_full_text,
            "active_subtask_number": int(snapshot["active_subtask_number"] or 0),
            "active_subtask_status": snapshot["active_subtask_status"],
            "execution_phase": snapshot["execution_phase"],
            "current_state_scan": current_state_scan if isinstance(current_state_scan, dict) else {},
            "resume_from_waiting": bool(resume_from_waiting),
            "execution_intent": "runtime_preflight",
        }

    def bind_plan_task_args(self, current_context: Dict[str, Any], tool_args: Dict[str, Any]) -> Dict[str, Any]:
        context = self.context_from_dict(current_context)
        if context.todo_id and context.binding_state == TodoBindingState.BOUND and not str(tool_args.get("active_todo_id", "") or "").strip():
            out = dict(tool_args)
            out["active_todo_id"] = context.todo_id
            return out
        return tool_args

    def tool_requires_todo_binding(self, tool_name: str, exempt_tools: set[str]) -> bool:
        tool_norm = str(tool_name or "").strip()
        if not tool_norm:
            return False
        return tool_norm not in exempt_tools

    def should_emit_binding_warning(
        self,
        tool_name: str,
        current_context: Dict[str, Any],
        guard_mode: str,
        exempt_tools: set[str],
    ) -> bool:
        if guard_mode != "warn":
            return False
        context = self.context_from_dict(current_context)
        if not context.todo_id or not context.binding_required:
            return False
        if context.active_subtask_number is not None:
            return False
        return self.tool_requires_todo_binding(tool_name=tool_name, exempt_tools=exempt_tools)
