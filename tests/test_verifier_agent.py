import unittest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from app.core.model.mock_provider import MockModelProvider
from app.eval.agent import VerifierAgent
from app.eval.schema import ExpectedArtifact, RunOutcome, TaskSpec


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

    def test_verifier_agent_uses_expected_artifact_root_as_default_evidence(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            out_dir = root / "outputs" / "task1"
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "report.md").write_text("hello", encoding="utf-8")

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
                        "content": '{"passed": true, "score": 0.9, "reason": "ok", "checks": []}',
                        "raw": {"mock": True},
                    },
                ]
            )
            with patch("app.eval.agent.verifier_agent._find_project_root", return_value=str(root)):
                agent = VerifierAgent(model_provider=provider)
                result = agent.evaluate(
                    task_spec=TaskSpec(
                        goal="check outputs",
                        expected_artifacts=[ExpectedArtifact(path="outputs/task1/report.md")],
                    ),
                    run_outcome=RunOutcome(
                        task_id="t3",
                        run_id="r3",
                        user_input="write report",
                        final_answer="done",
                        stop_reason="stop",
                    ),
                )

            self.assertTrue(result["passed"])
            # 第二次请求消息中应包含工具返回，且 root 指向 expected_artifacts 推断出的目录
            tool_msg = [m for m in provider.requests[1]["messages"] if m.get("role") == "tool"][-1]
            payload = json.loads(tool_msg["content"])
            self.assertEqual(payload.get("root"), "outputs/task1")


if __name__ == "__main__":
    unittest.main()
