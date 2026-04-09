import os
import tempfile
import unittest

from app.core.model.mock_provider import MockModelProvider
from app.eval.orchestrator import EvalOrchestrator, infer_self_reported_success
from app.eval.schema import RunOutcome, TaskSpec


class EvalOrchestratorTests(unittest.TestCase):
    def test_infer_self_reported_success(self):
        self.assertTrue(infer_self_reported_success("任务已完成。", "stop"))
        self.assertFalse(infer_self_reported_success("任务未完成。", "stop"))
        self.assertFalse(infer_self_reported_success("done", "length"))

    def test_evaluate_fails_when_tool_failures_exist(self):
        orchestrator = EvalOrchestrator()
        spec = TaskSpec()
        outcome = RunOutcome(
            task_id="t1",
            run_id="r1",
            user_input="u",
            final_answer="已完成",
            stop_reason="stop",
            tool_failures=[{"tool": "bash", "error": "x"}],
            runtime_status="ok",
        )
        judgement = orchestrator.evaluate(task_spec=spec, run_outcome=outcome)
        self.assertFalse(judgement.verified_success)
        self.assertEqual(judgement.final_status, "fail")
        self.assertTrue(judgement.overclaim)

    def test_evaluate_passes_with_expected_artifact(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "result.txt")
            with open(path, "w", encoding="utf-8") as f:
                f.write("hello eval")
            orchestrator = EvalOrchestrator()
            spec = TaskSpec.from_dict(
                {
                    "expected_artifacts": [
                        {"path": path, "must_exist": True, "non_empty": True, "contains": "hello"}
                    ]
                }
            )
            outcome = RunOutcome(
                task_id="t1",
                run_id="r1",
                user_input="u",
                final_answer="任务已完成",
                stop_reason="stop",
                tool_failures=[],
                runtime_status="ok",
            )
            judgement = orchestrator.evaluate(task_spec=spec, run_outcome=outcome)
            self.assertTrue(judgement.verified_success)
            self.assertEqual(judgement.final_status, "pass")
            self.assertFalse(judgement.overclaim)

    def test_evaluate_with_llm_judge_soft_score(self):
        judge_provider = MockModelProvider(
            scripted_outputs=[
                {
                    "content": '{"passed": true, "score": 0.85, "reason": "目标和约束满足"}',
                    "raw": {"mock": True},
                }
            ]
        )
        orchestrator = EvalOrchestrator(enable_llm_judge=True, llm_judge_provider=judge_provider)
        spec = TaskSpec.from_dict({"goal": "写总结", "llm_judge_enabled": True, "soft_score_threshold": 0.8})
        outcome = RunOutcome(
            task_id="t2",
            run_id="r2",
            user_input="总结一下",
            final_answer="已完成总结",
            stop_reason="stop",
            tool_failures=[],
            runtime_status="ok",
        )
        judgement = orchestrator.evaluate(task_spec=spec, run_outcome=outcome)
        self.assertTrue(judgement.verified_success)
        llm_results = [x for x in judgement.verifier_breakdown if x.verifier_name == "verifier_agent_judge"]
        self.assertEqual(len(llm_results), 1)
        self.assertEqual(llm_results[0].score, 0.85)


if __name__ == "__main__":
    unittest.main()
