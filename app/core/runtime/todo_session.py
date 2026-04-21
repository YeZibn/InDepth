from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List

from app.core.todo import TodoService
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
    todo_service: TodoService = field(default_factory=TodoService)

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
        return self.todo_service.prepare_phase_snapshot(self.context)

    def build_prepare_phase_inputs(
        self,
        user_input: str,
        task_name: str,
        active_todo_full_text: str,
        current_state_scan: Dict[str, Any],
        resume_from_waiting: bool,
    ) -> Dict[str, Any]:
        return self.todo_service.build_prepare_phase_inputs(
            current_context=self.context,
            user_input=user_input,
            task_name=task_name,
            active_todo_full_text=active_todo_full_text,
            current_state_scan=current_state_scan,
            resume_from_waiting=resume_from_waiting,
        )

    def bind_plan_task_args(self, tool_args: Dict[str, Any]) -> Dict[str, Any]:
        return self.todo_service.bind_plan_task_args(self.context, tool_args)

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
