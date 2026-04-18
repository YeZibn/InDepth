import ast
import tempfile
import unittest
from pathlib import Path

from app.observability.events import emit_event
from app.observability.schema import EVENT_TYPES
from app.observability.store import EventStore


class ObservabilityEventWhitelistTests(unittest.TestCase):
    def _project_root(self) -> Path:
        return Path(__file__).resolve().parents[1]

    def _make_store(self, tmpdir: str) -> EventStore:
        return EventStore(events_path=str(Path(tmpdir) / "events.jsonl"))

    def _collect_literal_event_types_from_app(self) -> set[str]:
        root = self._project_root()
        found: set[str] = set()
        for path in root.glob("app/**/*.py"):
            source = path.read_text(encoding="utf-8")
            module = ast.parse(source, filename=str(path))
            for node in ast.walk(module):
                if not isinstance(node, ast.Call):
                    continue
                for keyword in node.keywords:
                    if keyword.arg != "event_type":
                        continue
                    value = keyword.value
                    if isinstance(value, ast.Constant) and isinstance(value.value, str):
                        found.add(value.value)
        return found

    def test_newly_whitelisted_events_preserve_event_type(self):
        whitelisted = [
            "task_fallback_recorded",
            "task_recovery_planned",
            "todo_recovery_auto_planned",
            "followup_subtasks_appended",
            "subtask_updated",
            "subtask_reopened",
            "task_updated",
            "todo_binding_missing_warning",
            "todo_orphan_failure_detected",
            "search_budget_auto_overridden",
            "user_preference_recall_succeeded",
            "user_preference_recall_failed",
            "user_preference_extract_started",
            "user_preference_extract_succeeded",
            "user_preference_extract_failed",
            "user_preference_capture_succeeded",
            "user_preference_capture_failed",
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            store = self._make_store(tmpdir)
            for name in whitelisted:
                event = emit_event(
                    task_id="task_alpha",
                    run_id="run_alpha",
                    actor="main",
                    role="general",
                    event_type=name,
                    payload={"source": "test"},
                    store=store,
                    generate_postmortem_artifacts=False,
                )
                self.assertEqual(event["event_type"], name)
                self.assertNotIn("_original_event_type", event["payload"])

    def test_unknown_event_type_still_normalizes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = self._make_store(tmpdir)
            event = emit_event(
                task_id="task_beta",
                run_id="run_beta",
                actor="main",
                role="general",
                event_type="totally_new_event_type",
                payload={"source": "test"},
                store=store,
                generate_postmortem_artifacts=False,
            )

            self.assertEqual(event["event_type"], "unknown_event_type")
            self.assertEqual(event["payload"]["_original_event_type"], "totally_new_event_type")

    def test_all_literal_app_event_types_are_whitelisted(self):
        found = self._collect_literal_event_types_from_app()
        missing = sorted(found - set(EVENT_TYPES))
        self.assertEqual(
            missing,
            [],
            msg=(
                "These literal app event types are emitted in code but missing from "
                f"app.observability.schema.EVENT_TYPES: {missing}"
            ),
        )


if __name__ == "__main__":
    unittest.main()
