import unittest
from unittest.mock import Mock

from app.core.runtime.todo_session import TodoSession


class TodoSessionTests(unittest.TestCase):
    def test_prepare_phase_snapshot_reports_active_execution_state(self):
        session = TodoSession(
            context={
                "todo_id": "todo_123",
                "active_subtask_id": "st_1",
                "active_subtask_number": 2,
                "execution_phase": "executing",
                "binding_required": True,
                "binding_state": "bound",
            }
        )

        snapshot = session.prepare_phase_snapshot()

        self.assertEqual(snapshot["active_todo_id"], "todo_123")
        self.assertEqual(snapshot["active_subtask_number"], 2)
        self.assertEqual(snapshot["execution_phase"], "executing")
        self.assertEqual(snapshot["active_subtask_status"], "in-progress")

    def test_bind_plan_task_args_injects_active_todo_id_when_bound(self):
        session = TodoSession(
            context={
                "todo_id": "todo_123",
                "binding_state": "bound",
            }
        )

        bound = session.bind_plan_task_args({"task_name": "Continue"})

        self.assertEqual(bound["active_todo_id"], "todo_123")
        self.assertEqual(bound["task_name"], "Continue")

    def test_apply_executions_tracks_latest_active_subtask(self):
        session = TodoSession()

        session.apply_executions(
            [
                {
                    "tool": "plan_task",
                    "args": {},
                    "success": True,
                    "error": "",
                    "payload": {
                        "mode": "create",
                        "execution_result": {
                            "todo_id": "todo_123",
                            "todo_bound_at": "now",
                        },
                    },
                },
                {
                    "tool": "update_task_status",
                    "args": {
                        "todo_id": "todo_123",
                        "subtask_number": 1,
                        "status": "in-progress",
                    },
                    "success": True,
                    "error": "",
                    "payload": {
                        "todo_id": "todo_123",
                        "subtask_id": "st_1",
                        "all_completed": False,
                    },
                },
            ]
        )

        self.assertEqual(session.todo_id, "todo_123")
        self.assertEqual(session.active_subtask_number, 1)
        self.assertEqual(session.active_subtask_id, "st_1")
        self.assertEqual(session.execution_phase, "executing")

    def test_build_prepare_phase_inputs_uses_session_state(self):
        session = TodoSession(
            context={
                "todo_id": "todo_123",
                "active_subtask_number": 3,
                "execution_phase": "planning",
            }
        )

        args = session.build_prepare_phase_inputs(
            user_input="继续处理已有 todo",
            task_name="Continue todo",
            active_todo_full_text="todo markdown",
            current_state_scan={"summary": "当前 todo 进度 1/3"},
            resume_from_waiting=True,
        )

        self.assertEqual(args["active_todo_id"], "todo_123")
        self.assertEqual(args["active_subtask_number"], 3)
        self.assertEqual(args["execution_phase"], "planning")
        self.assertTrue(args["resume_from_waiting"])
        self.assertEqual(args["current_state_scan"]["summary"], "当前 todo 进度 1/3")

    def test_maybe_emit_binding_warning_delegates_with_session_context(self):
        session = TodoSession(
            context={
                "todo_id": "todo_123",
                "binding_required": True,
                "binding_state": "bound",
                "execution_phase": "planning",
                "active_subtask_number": None,
            }
        )
        emit_event = Mock(return_value={})

        session.maybe_emit_binding_warning(
            tool_name="bash",
            task_id="task_1",
            run_id="run_1",
            guard_mode="warn",
            exempt_tools={"plan_task"},
            emit_event=emit_event,
        )

        emit_event.assert_called_once()
        payload = emit_event.call_args.kwargs["payload"]
        self.assertEqual(payload["todo_id"], "todo_123")
        self.assertEqual(payload["tool"], "bash")


if __name__ == "__main__":
    unittest.main()
