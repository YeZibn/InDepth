import unittest

from app.core.todo import TodoBindingState, TodoExecutionPhase, TodoService


class TodoServiceTests(unittest.TestCase):
    def test_apply_executions_tracks_created_todo_and_active_subtask(self):
        service = TodoService()

        context = service.apply_executions(
            current_context={},
            executions=[
                {
                    "tool": "plan_task",
                    "args": {},
                    "success": True,
                    "error": "",
                    "payload": {
                        "mode": "create",
                        "execution_result": {"todo_id": "todo_123", "todo_bound_at": "now"},
                    },
                },
                {
                    "tool": "update_task_status",
                    "args": {"todo_id": "todo_123", "subtask_number": 2, "status": "in-progress"},
                    "success": True,
                    "error": "",
                    "payload": {"todo_id": "todo_123", "subtask_id": "st_2", "all_completed": False},
                },
            ],
        )

        self.assertEqual(context["todo_id"], "todo_123")
        self.assertEqual(context["active_subtask_id"], "st_2")
        self.assertEqual(context["active_subtask_number"], 2)
        self.assertEqual(context["execution_phase"], TodoExecutionPhase.EXECUTING.value)
        self.assertEqual(context["binding_state"], TodoBindingState.BOUND.value)

    def test_finalize_context_closes_completed_todo(self):
        service = TodoService()

        context = service.finalize_context(
            current_context={
                "todo_id": "todo_123",
                "active_subtask_id": "st_1",
                "active_subtask_number": 1,
                "execution_phase": "executing",
                "binding_required": True,
                "binding_state": "bound",
            },
            runtime_state="completed",
        )

        self.assertEqual(context["binding_state"], TodoBindingState.CLOSED.value)
        self.assertEqual(context["execution_phase"], TodoExecutionPhase.FINALIZING.value)
        self.assertFalse(context["binding_required"])
        self.assertIsNone(context["active_subtask_id"])
        self.assertIsNone(context["active_subtask_number"])

    def test_should_emit_binding_warning_only_when_bound_without_active_subtask(self):
        service = TodoService()

        should_warn = service.should_emit_binding_warning(
            tool_name="bash",
            current_context={
                "todo_id": "todo_123",
                "binding_required": True,
                "binding_state": "bound",
                "execution_phase": "planning",
                "active_subtask_number": None,
            },
            guard_mode="warn",
            exempt_tools={"plan_task"},
        )
        should_not_warn = service.should_emit_binding_warning(
            tool_name="plan_task",
            current_context={
                "todo_id": "todo_123",
                "binding_required": True,
                "binding_state": "bound",
                "execution_phase": "planning",
                "active_subtask_number": None,
            },
            guard_mode="warn",
            exempt_tools={"plan_task"},
        )

        self.assertTrue(should_warn)
        self.assertFalse(should_not_warn)


if __name__ == "__main__":
    unittest.main()
