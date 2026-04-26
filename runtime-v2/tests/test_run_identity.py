import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from rtv2.state.models import (
    BudgetStatus,
    CompressionState,
    ExternalSignalState,
    FinalizeReturnInput,
    RunIdentity,
    RunLifecycle,
    RunPhase,
    RuntimeState,
    SignalRef,
    SignalSourceType,
)


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

    def test_runtime_state_keeps_optional_runtime_fields(self):
        runtime_state = RuntimeState(
            active_node_id="node-1",
            compression_state=CompressionState(
                compressed=True,
                compressed_context_ref="ctx-1",
                budget_status=BudgetStatus.TIGHT,
                context_usage_ratio=0.82,
            ),
            external_signal_state=ExternalSignalState(
                pending_user_reply=SignalRef(
                    signal_id="sig-1",
                    source_type=SignalSourceType.USER,
                    ref="message-1",
                    arrived_at="2026-04-26T10:00:00Z",
                )
            ),
            finalize_return_input=FinalizeReturnInput(
                verification_summary="Verifier found a missing test.",
                verification_issues=["Add integration coverage for resume replacement flow."],
            ),
        )

        self.assertEqual(runtime_state.active_node_id, "node-1")
        self.assertTrue(runtime_state.compression_state.compressed)
        self.assertEqual(runtime_state.compression_state.budget_status, BudgetStatus.TIGHT)
        self.assertEqual(
            runtime_state.external_signal_state.pending_user_reply.source_type,
            SignalSourceType.USER,
        )
        self.assertEqual(
            runtime_state.finalize_return_input.verification_issues,
            ["Add integration coverage for resume replacement flow."],
        )

    def test_runtime_state_defaults_to_empty_optional_state(self):
        runtime_state = RuntimeState()

        self.assertEqual(runtime_state.active_node_id, "")
        self.assertIsNone(runtime_state.compression_state)
        self.assertIsNone(runtime_state.external_signal_state)
        self.assertIsNone(runtime_state.finalize_return_input)


if __name__ == "__main__":
    unittest.main()
