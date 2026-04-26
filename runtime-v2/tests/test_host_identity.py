import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from rtv2.host.interfaces import HostTaskRef, RuntimeHostState, StartRunIdentity


class HostIdentityTests(unittest.TestCase):
    def test_runtime_host_state_keeps_session_and_optional_bindings(self):
        host_state = RuntimeHostState(
            session_id="sess-1",
            current_task_id="task-1",
            active_run_id="run-1",
        )

        self.assertEqual(host_state.session_id, "sess-1")
        self.assertEqual(host_state.current_task_id, "task-1")
        self.assertEqual(host_state.active_run_id, "run-1")

    def test_runtime_host_state_defaults_to_unbound_task_and_run(self):
        host_state = RuntimeHostState(session_id="sess-2")

        self.assertEqual(host_state.session_id, "sess-2")
        self.assertEqual(host_state.current_task_id, "")
        self.assertEqual(host_state.active_run_id, "")

    def test_host_task_ref_keeps_task_id(self):
        task_ref = HostTaskRef(task_id="task-2")

        self.assertEqual(task_ref.task_id, "task-2")

    def test_start_run_identity_keeps_host_managed_identifier_mapping(self):
        start_run_identity = StartRunIdentity(
            session_id="sess-3",
            task_id="task-3",
            run_id="run-3",
            user_input="Continue runtime-v2 implementation.",
        )

        self.assertEqual(start_run_identity.session_id, "sess-3")
        self.assertEqual(start_run_identity.task_id, "task-3")
        self.assertEqual(start_run_identity.run_id, "run-3")
        self.assertEqual(
            start_run_identity.user_input,
            "Continue runtime-v2 implementation.",
        )


if __name__ == "__main__":
    unittest.main()
