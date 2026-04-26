import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from rtv2.state.models import RunIdentity, RunLifecycle, RunPhase


class RunIdentityTests(unittest.TestCase):
    def test_run_identity_keeps_required_fields(self):
        identity = RunIdentity(
            session_id="sess-1",
            task_id="task-1",
            run_id="run-1",
            user_input="Inspect runtime-v2 state model.",
        )

        self.assertEqual(identity.session_id, "sess-1")
        self.assertEqual(identity.task_id, "task-1")
        self.assertEqual(identity.run_id, "run-1")
        self.assertEqual(identity.user_input, "Inspect runtime-v2 state model.")
        self.assertEqual(identity.goal, "")

    def test_run_identity_accepts_optional_goal(self):
        identity = RunIdentity(
            session_id="sess-2",
            task_id="task-2",
            run_id="run-2",
            user_input="Continue implementation.",
            goal="Land runtime-v2 skeleton.",
        )

        self.assertEqual(identity.goal, "Land runtime-v2 skeleton.")

    def test_run_lifecycle_keeps_required_fields(self):
        lifecycle = RunLifecycle(
            lifecycle_state="running",
            current_phase=RunPhase.PREPARE,
        )

        self.assertEqual(lifecycle.lifecycle_state, "running")
        self.assertEqual(lifecycle.current_phase, RunPhase.PREPARE)
        self.assertEqual(lifecycle.result_status, "")
        self.assertEqual(lifecycle.stop_reason, "")

    def test_run_lifecycle_accepts_result_and_stop_reason(self):
        lifecycle = RunLifecycle(
            lifecycle_state="completed",
            current_phase=RunPhase.FINALIZE,
            result_status="pass",
            stop_reason="finished",
        )

        self.assertEqual(lifecycle.current_phase, RunPhase.FINALIZE)
        self.assertEqual(lifecycle.result_status, "pass")
        self.assertEqual(lifecycle.stop_reason, "finished")


if __name__ == "__main__":
    unittest.main()
