import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.observability.postmortem import generate_postmortem


class PostmortemOutputLayoutTests(unittest.TestCase):
    def test_generate_postmortem_uses_task_and_run_scoped_folder(self):
        events = [
            {
                "timestamp": "2026-04-10T10:00:00+00:00",
                "event_type": "task_started",
                "actor": "main",
                "role": "general",
                "status": "ok",
                "payload": {},
            },
            {
                "timestamp": "2026-04-10T10:00:02+00:00",
                "event_type": "task_finished",
                "actor": "main",
                "role": "general",
                "status": "ok",
                "payload": {},
            },
        ]
        with tempfile.TemporaryDirectory() as td:
            with patch("app.observability.postmortem._find_project_root", return_value=td):
                result = generate_postmortem(
                    task_id="task/A 中文",
                    run_id="run:01",
                    events=events,
                )

            self.assertTrue(result["success"])
            out = Path(result["output_path"])
            self.assertTrue(out.exists())
            self.assertEqual(out.parent.name, "task_A__run_01")
            self.assertEqual(out.parent.parent, Path(td) / "observability-evals")

    def test_generate_postmortem_uses_task_scoped_folder_without_run_id(self):
        events = [
            {
                "timestamp": "2026-04-10T10:00:00+00:00",
                "event_type": "task_started",
                "actor": "main",
                "role": "general",
                "status": "ok",
                "payload": {},
            },
            {
                "timestamp": "2026-04-10T10:00:02+00:00",
                "event_type": "task_finished",
                "actor": "main",
                "role": "general",
                "status": "ok",
                "payload": {},
            },
        ]
        with tempfile.TemporaryDirectory() as td:
            with patch("app.observability.postmortem._find_project_root", return_value=td):
                result = generate_postmortem(
                    task_id="my-task",
                    events=events,
                )

            self.assertTrue(result["success"])
            out = Path(result["output_path"])
            self.assertTrue(out.exists())
            self.assertEqual(out.parent.name, "my-task")
            self.assertEqual(out.parent.parent, Path(td) / "observability-evals")


if __name__ == "__main__":
    unittest.main()
