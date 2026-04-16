import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.tool.todo_tool.todo_tool import (
    _parse_task_file,
    append_followup_subtasks,
    create_task,
    plan_task_recovery,
    record_task_fallback,
    update_task_status,
)


class TodoRecoveryFlowTests(unittest.TestCase):
    def test_update_task_status_accepts_richer_unfinished_states(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with (
                patch("app.tool.todo_tool.todo_tool._get_todo_dir", return_value=tmpdir),
                patch("app.tool.todo_tool.todo_tool._emit_obs"),
                patch("app.tool.todo_tool.todo_tool._generate_todo_id", return_value="20260416_000001_demo"),
            ):
                created = create_task.entrypoint(
                    task_name="Demo Task",
                    context="Exercise richer todo states",
                    split_reason="Need multiple states for unfinished work.",
                    subtasks=[{"name": "Main step", "description": "Do the main thing"}],
                )
                result = update_task_status.entrypoint(
                    todo_id=created["todo_id"],
                    subtask_number=1,
                    status="failed",
                )

            self.assertTrue(result["success"])
            parsed = _parse_task_file(Path(created["filepath"]))
            self.assertEqual(parsed["subtasks"][0]["status"], "failed")

    def test_record_task_fallback_persists_structured_metadata(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with (
                patch("app.tool.todo_tool.todo_tool._get_todo_dir", return_value=tmpdir),
                patch("app.tool.todo_tool.todo_tool._emit_obs"),
                patch("app.tool.todo_tool.todo_tool._generate_todo_id", return_value="20260416_000002_demo"),
            ):
                created = create_task.entrypoint(
                    task_name="Demo Task",
                    context="Record fallback metadata",
                    split_reason="Need explicit recovery metadata.",
                    subtasks=[{"name": "Main step", "description": "Do the main thing"}],
                )
                result = record_task_fallback.entrypoint(
                    todo_id=created["todo_id"],
                    subtask_number=1,
                    state="failed",
                    reason_code="tool_error",
                    reason_detail="Command exited with status 1",
                    impact_scope="Blocks only this implementation step",
                    retryable=True,
                    required_input=["stderr log"],
                    suggested_next_action="retry_with_fix",
                    evidence=["work/error.log"],
                    owner="main",
                    retry_count=1,
                    retry_budget_remaining=1,
                )

            self.assertTrue(result["success"])
            parsed = _parse_task_file(Path(created["filepath"]))
            self.assertEqual(parsed["subtasks"][0]["status"], "failed")
            fallback = parsed["subtasks"][0]["fallback_record"]
            self.assertEqual(fallback["reason_code"], "tool_error")
            self.assertEqual(fallback["retry_count"], 1)
            self.assertEqual(fallback["required_input"], ["stderr log"])

    def test_plan_task_recovery_returns_structured_followups(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with (
                patch("app.tool.todo_tool.todo_tool._get_todo_dir", return_value=tmpdir),
                patch("app.tool.todo_tool.todo_tool._emit_obs"),
                patch("app.tool.todo_tool.todo_tool._generate_todo_id", return_value="20260416_000003_demo"),
            ):
                created = create_task.entrypoint(
                    task_name="Demo Task",
                    context="Plan recovery for a failed task",
                    split_reason="Need a recovery plan.",
                    subtasks=[{"name": "Main step", "description": "Do the main thing", "owner": "subagent:builder"}],
                )
                record_task_fallback.entrypoint(
                    todo_id=created["todo_id"],
                    subtask_number=1,
                    state="failed",
                    reason_code="validation_failed",
                    reason_detail="Tests failed after implementation",
                    impact_scope="Blocks delivery of the feature",
                    retryable=True,
                    suggested_next_action="split",
                    evidence=["tests/output.txt"],
                    owner="subagent:builder",
                )
                decision = plan_task_recovery.entrypoint(
                    todo_id=created["todo_id"],
                    subtask_number=1,
                    retry_budget_remaining=2,
                    time_budget_remaining="15m",
                    available_roles=["builder", "verifier"],
                    allowed_degraded_delivery=False,
                    is_on_critical_path=True,
                )

            self.assertTrue(decision["success"])
            payload = decision["recovery_decision"]
            self.assertEqual(payload["primary_action"], "split")
            self.assertEqual(payload["decision_level"], "auto")
            self.assertGreaterEqual(len(payload["next_subtasks"]), 2)
            self.assertEqual(payload["next_subtasks"][0]["kind"], "diagnose")

    def test_append_followup_subtasks_adds_new_recovery_steps(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with (
                patch("app.tool.todo_tool.todo_tool._get_todo_dir", return_value=tmpdir),
                patch("app.tool.todo_tool.todo_tool._emit_obs"),
                patch("app.tool.todo_tool.todo_tool._generate_todo_id", return_value="20260416_000004_demo"),
            ):
                created = create_task.entrypoint(
                    task_name="Demo Task",
                    context="Append recovery steps",
                    split_reason="Need follow-up tasks after failure.",
                    subtasks=[{"name": "Main step", "description": "Do the main thing"}],
                )
                appended = append_followup_subtasks.entrypoint(
                    todo_id=created["todo_id"],
                    follow_up_subtasks=[
                        {
                            "name": "Diagnose the failure",
                            "goal": "Identify the root cause",
                            "description": "Inspect logs and isolate the problem",
                            "kind": "diagnose",
                            "owner": "main",
                            "depends_on": [1],
                            "acceptance_criteria": ["Root cause documented"],
                        },
                        {
                            "name": "Repair after diagnosis",
                            "goal": "Apply the targeted fix",
                            "description": "Use the diagnosis result to repair the task",
                            "kind": "repair",
                            "owner": "subagent:builder",
                            "depends_on": [2],
                            "acceptance_criteria": ["Repair implemented"],
                        },
                    ],
                )

            self.assertTrue(appended["success"])
            parsed = _parse_task_file(Path(created["filepath"]))
            self.assertEqual(len(parsed["subtasks"]), 3)
            self.assertEqual(parsed["subtasks"][1]["kind"], "diagnose")
            self.assertEqual(parsed["subtasks"][2]["dependencies"], ["2"])


if __name__ == "__main__":
    unittest.main()
