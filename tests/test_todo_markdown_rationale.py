import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.tool.todo_tool.todo_tool import plan_task


class TodoMarkdownRationaleTests(unittest.TestCase):
    def test_plan_task_writes_explicit_split_rationale(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with (
                patch("app.tool.todo_tool.todo_tool._get_todo_dir", return_value=tmpdir),
                patch("app.tool.todo_tool.todo_tool._emit_obs"),
                patch("app.tool.todo_tool.todo_tool._generate_todo_id", return_value="20260413_000000_demo"),
            ):
                result = plan_task.entrypoint(
                    task_name="Demo Task",
                    context="Validate todo markdown format",
                    split_reason="Need an explicit decomposition strategy for this implementation.",
                    subtasks=[
                        {
                            "name": "Collect requirements",
                            "description": "Document the core constraints",
                            "split_reason": "Gathering constraints first prevents rework in later implementation steps.",
                        }
                    ],
                )

                content = Path(result["execution_result"]["filepath"]).read_text(encoding="utf-8")

        self.assertTrue(result["success"])
        self.assertIn("**Split Reason**: Need an explicit decomposition strategy for this implementation.", content)
        self.assertIn("**Split Rationale**: Gathering constraints first prevents rework in later implementation steps.", content)

    def test_plan_task_writes_default_split_rationale_when_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with (
                patch("app.tool.todo_tool.todo_tool._get_todo_dir", return_value=tmpdir),
                patch("app.tool.todo_tool.todo_tool._emit_obs"),
                patch("app.tool.todo_tool.todo_tool._generate_todo_id", return_value="20260413_000001_demo"),
            ):
                result = plan_task.entrypoint(
                    task_name="Demo Task",
                    context="Validate default rationale",
                    split_reason="Need ordered subtasks for dependency-safe execution and progress tracking.",
                    subtasks=[
                        {"name": "Step one", "description": "Do first action"},
                        {"name": "Step two", "description": "Do second action", "dependencies": [1]},
                    ],
                )

                content = Path(result["execution_result"]["filepath"]).read_text(encoding="utf-8")

        self.assertTrue(result["success"])
        self.assertIn("**Split Reason**: Need ordered subtasks for dependency-safe execution and progress tracking.", content)
        self.assertEqual(content.count("**Split Rationale**:"), 2)
        self.assertIn("first step to establish context", content)
        self.assertIn("respect execution order", content)

    def test_plan_task_rejects_empty_split_reason(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with (
                patch("app.tool.todo_tool.todo_tool._get_todo_dir", return_value=tmpdir),
                patch("app.tool.todo_tool.todo_tool._emit_obs"),
                patch("app.tool.todo_tool.todo_tool._generate_todo_id", return_value="20260413_000002_demo"),
            ):
                result = plan_task.entrypoint(
                    task_name="Demo Task",
                    context="Validate split reason validation",
                    split_reason="   ",
                    subtasks=[{"name": "Step one", "description": "Do first action"}],
                )

        self.assertFalse(result["success"])
        self.assertIn("split_reason must be a non-empty string", result["error"])


if __name__ == "__main__":
    unittest.main()
