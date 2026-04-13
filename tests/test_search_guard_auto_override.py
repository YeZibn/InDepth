import unittest

from app.tool.search_tool.search_guard import SearchGuardManager


class SearchGuardAutoOverrideTests(unittest.TestCase):
    def setUp(self) -> None:
        self.guard = SearchGuardManager()

    def _init(self, task_id: str = "t1"):
        return self.guard.init_session(
            task_id=task_id,
            time_basis="Asia/Shanghai, cutoff=2026-04-13",
            question_ids=["1", "2"],
            questions=["q1", "q2"],
            stop_threshold="done",
            max_rounds=3,
            max_seconds=900,
            auto_override_enabled=True,
            auto_override_rounds_left_threshold=1,
            auto_override_seconds_left_threshold=120,
            auto_override_rounds_step=1,
            auto_override_seconds_step=180,
            auto_override_max_times=2,
            auto_override_max_total_rounds=2,
            auto_override_max_total_seconds=600,
        )

    def test_auto_override_when_near_round_limit(self):
        session = self._init("near")
        self.guard.add_log("near", {"type": "ddg_search", "returned_results": 2})
        self.guard.add_log("near", {"type": "ddg_search", "returned_results": 1})

        gate_error = self.guard.check_gate("near")

        self.assertIsNone(gate_error)
        self.assertEqual(session.max_rounds, 4)
        self.assertEqual(session.auto_overrides_used, 1)
        self.assertEqual(session.auto_override_total_rounds, 1)

    def test_block_after_auto_override_limit_reached(self):
        session = self.guard.init_session(
            task_id="limit",
            time_basis="Asia/Shanghai, cutoff=2026-04-13",
            question_ids=["1"],
            questions=["q1"],
            stop_threshold="done",
            max_rounds=1,
            max_seconds=900,
            auto_override_enabled=True,
            auto_override_rounds_left_threshold=1,
            auto_override_seconds_left_threshold=0,
            auto_override_rounds_step=1,
            auto_override_seconds_step=0,
            auto_override_max_times=1,
            auto_override_max_total_rounds=1,
            auto_override_max_total_seconds=0,
        )

        # First pre-check should auto-override from 1 -> 2 rounds.
        self.assertIsNone(self.guard.check_gate("limit"))
        self.assertEqual(session.max_rounds, 2)

        # Consume both rounds; now no auto budget left.
        self.guard.add_log("limit", {"type": "ddg_search", "returned_results": 1})
        self.guard.add_log("limit", {"type": "ddg_search", "returned_results": 1})
        session.stopped = False

        gate_error = self.guard.check_gate("limit")

        self.assertIsNotNone(gate_error)
        self.assertIn("round budget exhausted", gate_error)

    def test_manual_override_still_works_after_auto_limit(self):
        session = self.guard.init_session(
            task_id="manual",
            time_basis="Asia/Shanghai, cutoff=2026-04-13",
            question_ids=["1"],
            questions=["q1"],
            stop_threshold="done",
            max_rounds=1,
            max_seconds=900,
            auto_override_enabled=True,
            auto_override_rounds_left_threshold=1,
            auto_override_seconds_left_threshold=0,
            auto_override_rounds_step=1,
            auto_override_seconds_step=0,
            auto_override_max_times=1,
            auto_override_max_total_rounds=1,
            auto_override_max_total_seconds=0,
        )
        self.assertIsNone(self.guard.check_gate("manual"))
        self.guard.add_log("manual", {"type": "ddg_search", "returned_results": 1})
        self.guard.add_log("manual", {"type": "ddg_search", "returned_results": 1})
        session.stopped = True
        session.stop_reason = "round budget exhausted"

        result = self.guard.override_budget(
            task_id="manual",
            extra_rounds=1,
            extra_seconds=60,
            reason="Need one more source",
            expected_gain="Close remaining evidence gap",
        )

        self.assertTrue(result["success"])
        self.assertEqual(session.max_rounds, 3)
        self.assertFalse(session.stopped)

    def test_no_gain_streak_blocks_auto_override(self):
        session = self._init("nogain")
        self.guard.update_progress(
            task_id="nogain",
            answered_question_ids=[],
            stable_conclusion=False,
            new_evidence_count=0,
            dedup_count=0,
            note="no gain 1",
        )
        self.guard.update_progress(
            task_id="nogain",
            answered_question_ids=[],
            stable_conclusion=False,
            new_evidence_count=0,
            dedup_count=0,
            note="no gain 2",
        )

        session.rounds_used = session.max_rounds
        session.stopped = False

        gate_error = self.guard.check_gate("nogain")

        self.assertIsNotNone(gate_error)
        self.assertIn("round budget exhausted", gate_error)
        self.assertEqual(session.auto_overrides_used, 0)


if __name__ == "__main__":
    unittest.main()
