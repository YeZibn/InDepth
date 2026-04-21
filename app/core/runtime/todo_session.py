from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List

from app.core.runtime.todo_runtime_lifecycle import (
    finalize_active_todo_context,
    maybe_emit_todo_binding_warning,
    restore_active_todo_context_from_history,
    update_active_todo_context,
)


@dataclass
class TodoSession:
    """Owns the runtime-facing todo execution context for a single run."""

    context: Dict[str, Any] = field(default_factory=dict)

    def clear(self) -> None:
        self.context = {}

    def set_context(self, context: Dict[str, Any]) -> Dict[str, Any]:
        self.context = dict(context or {})
        return self.as_dict()

    def as_dict(self) -> Dict[str, Any]:
        return dict(self.context or {})

    def restore_from_history(self, history: List[Dict[str, Any]]) -> Dict[str, Any]:
        self.context = restore_active_todo_context_from_history(history)
        return self.as_dict()

    def apply_executions(self, executions: List[Dict[str, Any]]) -> Dict[str, Any]:
        self.context = update_active_todo_context(
            current_context=self.context,
            executions=executions,
        )
        return self.as_dict()

    def finalize(self, runtime_state: str) -> Dict[str, Any]:
        self.context = finalize_active_todo_context(
            current_context=self.context,
            runtime_state=runtime_state,
        )
        return self.as_dict()

    @property
    def todo_id(self) -> str:
        return str(self.context.get("todo_id", "") or "").strip()

    @property
    def binding_state(self) -> str:
        return str(self.context.get("binding_state", "") or "").strip()

    @property
    def execution_phase(self) -> str:
        return str(self.context.get("execution_phase", "") or "planning").strip() or "planning"

    @property
    def binding_required(self) -> bool:
        return bool(self.context.get("binding_required"))

    @property
    def active_subtask_number(self) -> int | None:
        value = self.context.get("active_subtask_number")
        if value in (None, ""):
            return None
        try:
            return int(value)
        except Exception:
            return None

    @property
    def active_subtask_id(self) -> str:
        return str(self.context.get("active_subtask_id", "") or "").strip()

    def prepare_phase_snapshot(self) -> Dict[str, Any]:
        active_number = self.active_subtask_number or 0
        execution_phase = self.execution_phase
        active_status = ""
        if active_number:
            active_status = "in-progress" if execution_phase == "executing" else ""
        return {
            "active_todo_id": self.todo_id,
            "active_todo_exists": bool(self.todo_id),
            "active_subtask_number": active_number,
            "active_subtask_status": active_status,
            "execution_phase": execution_phase,
        }

    def build_prepare_phase_inputs(
        self,
        user_input: str,
        task_name: str,
        active_todo_full_text: str,
        current_state_scan: Dict[str, Any],
        resume_from_waiting: bool,
    ) -> Dict[str, Any]:
        snapshot = self.prepare_phase_snapshot()
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

    def bind_plan_task_args(self, tool_args: Dict[str, Any]) -> Dict[str, Any]:
        if (
            self.todo_id
            and self.binding_state == "bound"
            and not str(tool_args.get("active_todo_id", "") or "").strip()
        ):
            out = dict(tool_args)
            out["active_todo_id"] = self.todo_id
            return out
        return tool_args

    def maybe_emit_binding_warning(
        self,
        tool_name: str,
        task_id: str,
        run_id: str,
        guard_mode: str,
        exempt_tools: set[str],
        emit_event: Callable[..., Dict[str, Any]],
    ) -> None:
        maybe_emit_todo_binding_warning(
            tool_name=tool_name,
            task_id=task_id,
            run_id=run_id,
            todo_context=self.as_dict(),
            guard_mode=guard_mode,
            exempt_tools=exempt_tools,
            emit_event=emit_event,
        )
