import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import json

from app.observability.postmortem import generate_postmortem


class PostmortemOutputLayoutTests(unittest.TestCase):
    def test_generate_postmortem_uses_task_root_when_run_matches_task(self):
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
                    task_id="same-id",
                    run_id="same-id",
                    events=events,
                )

            self.assertTrue(result["success"])
            out = Path(result["output_path"])
            self.assertTrue(out.exists())
            self.assertEqual(out.parent.name, "same-id")
            self.assertEqual(out.parent.parent, Path(td) / "observability-evals")

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
            self.assertEqual(out.parent.name, "run_01")
            self.assertEqual(out.parent.parent.name, "task_A")
            self.assertEqual(out.parent.parent.parent, Path(td) / "observability-evals")

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

    def test_generate_postmortem_writes_task_summary_and_judgement_files(self):
        events = [
            {
                "timestamp": "2026-04-10T10:00:00+00:00",
                "event_type": "task_started",
                "actor": "main",
                "role": "general",
                "status": "ok",
                "run_id": "run_1",
                "payload": {},
            },
            {
                "timestamp": "2026-04-10T10:00:02+00:00",
                "event_type": "task_judged",
                "actor": "main",
                "role": "general",
                "status": "ok",
                "run_id": "run_1",
                "payload": {"final_status": "pass", "verified_success": True},
            },
        ]
        with tempfile.TemporaryDirectory() as td:
            with patch("app.observability.postmortem._find_project_root", return_value=td):
                result = generate_postmortem(task_id="task-alpha", run_id="run_1", events=events)

            self.assertTrue(result["success"])
            task_root = Path(td) / "observability-evals" / "task-alpha"
            self.assertTrue((task_root / "task_summary.json").exists())
            self.assertTrue((task_root / "task_judgement.json").exists())
            history = task_root / "task_judgement_history.jsonl"
            self.assertTrue(history.exists())
            lines = [x for x in history.read_text(encoding="utf-8").splitlines() if x.strip()]
            self.assertEqual(len(lines), 1)
            row = json.loads(lines[0])
            self.assertEqual(row.get("run_id"), "run_1")
            self.assertEqual((row.get("judgement") or {}).get("final_status"), "pass")
            self.assertTrue((task_root / "run_1" / "events.jsonl").exists())
            self.assertTrue((task_root / "run_1" / "judgement.json").exists())

    def test_generate_postmortem_renders_delivery_section_from_verification_handoff(self):
        events = [
            {
                "timestamp": "2026-04-10T10:00:00+00:00",
                "event_type": "task_started",
                "actor": "main",
                "role": "general",
                "status": "ok",
                "run_id": "run_delivery",
                "payload": {},
            },
            {
                "timestamp": "2026-04-10T10:00:02+00:00",
                "event_type": "task_judged",
                "actor": "main",
                "role": "general",
                "status": "ok",
                "run_id": "run_delivery",
                "payload": {
                    "final_status": "pass",
                    "verified_success": True,
                    "verification_handoff_source": "llm",
                    "verification_handoff": {
                        "goal": "交付接口文档与测试",
                        "claimed_done_items": ["补充接口文档", "补充回归测试"],
                        "expected_artifacts": [
                            {"path": "doc/api.md", "must_exist": True, "non_empty": True}
                        ],
                        "known_gaps": ["未执行全量回归"],
                    },
                },
            },
        ]
        with tempfile.TemporaryDirectory() as td:
            with patch("app.observability.postmortem._find_project_root", return_value=td):
                result = generate_postmortem(task_id="task-delivery", run_id="run_delivery", events=events)

            self.assertTrue(result["success"])
            content = Path(result["output_path"]).read_text(encoding="utf-8")
            self.assertIn("## 4. 交付内容", content)
            self.assertIn("handoff 来源: llm", content)
            self.assertIn("补充接口文档", content)
            self.assertIn("path=doc/api.md; must_exist=True; non_empty=True", content)
            self.assertIn("未执行全量回归", content)


if __name__ == "__main__":
    unittest.main()
