import unittest

from app.core.model.mock_provider import MockModelProvider
from app.eval.agent import VerifierAgent
from app.eval.schema import RunOutcome, TaskSpec


class VerifierAgentTests(unittest.TestCase):
    def test_verifier_agent_supports_tool_calling(self):
        provider = MockModelProvider(
            scripted_outputs=[
                {
                    "content": "",
                    "raw": {
                        "choices": [
                            {
                                "finish_reason": "tool_calls",
                                "message": {
                                    "content": "",
                                    "tool_calls": [
                                        {
                                            "id": "call_1",
                                            "type": "function",
                                            "function": {"name": "list_work_files", "arguments": "{}"},
                                        }
                                    ],
                                },
                            }
                        ]
                    },
                },
                {
                    "content": '{"passed": false, "score": 0.2, "reason": "evidence missing", "checks": ["listed work files"]}',
                    "raw": {"mock": True},
                },
            ]
        )
        agent = VerifierAgent(model_provider=provider)
        result = agent.evaluate(
            task_spec=TaskSpec(goal="check work artifacts"),
            run_outcome=RunOutcome(
                task_id="t1",
                run_id="r1",
                user_input="write report to work",
                final_answer="done",
                stop_reason="stop",
            ),
        )
        self.assertEqual(result["passed"], False)
        self.assertEqual(result["score"], 0.2)
        self.assertIn("listed work files", result["checks"])

    def test_verifier_agent_blocks_outside_project_path(self):
        provider = MockModelProvider(
            scripted_outputs=[
                {
                    "content": "",
                    "raw": {
                        "choices": [
                            {
                                "finish_reason": "tool_calls",
                                "message": {
                                    "content": "",
                                    "tool_calls": [
                                        {
                                            "id": "call_1",
                                            "type": "function",
                                            "function": {
                                                "name": "read_project_file",
                                                "arguments": '{"path":"/etc/passwd"}',
                                            },
                                        }
                                    ],
                                },
                            }
                        ]
                    },
                },
                {
                    "content": '{"passed": false, "score": 0.1, "reason": "unsafe path", "checks": []}',
                    "raw": {"mock": True},
                },
            ]
        )
        agent = VerifierAgent(model_provider=provider)
        result = agent.evaluate(
            task_spec=TaskSpec(goal="security check"),
            run_outcome=RunOutcome(
                task_id="t2",
                run_id="r2",
                user_input="check file",
                final_answer="done",
                stop_reason="stop",
            ),
        )
        self.assertEqual(result["passed"], False)
        self.assertEqual(result["reason"], "unsafe path")


if __name__ == "__main__":
    unittest.main()
