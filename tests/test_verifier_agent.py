import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.core.model.mock_provider import MockModelProvider
from app.eval.agent import VerifierAgent
from app.eval.schema import RunOutcome


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
            run_outcome=RunOutcome(
                task_id="t1",
                run_id="r1",
                user_input="write report to work",
                final_answer="done",
                stop_reason="stop",
                verification_handoff={"goal": "check work artifacts"},
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
            run_outcome=RunOutcome(
                task_id="t2",
                run_id="r2",
                user_input="check file",
                final_answer="done",
                stop_reason="stop",
                verification_handoff={"goal": "security check"},
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
                    run_outcome=RunOutcome(
                        task_id="t3",
                        run_id="r3",
                        user_input="write report",
                        final_answer="done",
                        stop_reason="stop",
                        verification_handoff={
                            "goal": "check outputs",
                            "expected_artifacts": [{"path": "outputs/task1/report.md"}],
                        },
                    ),
                )

            self.assertTrue(result["passed"])
            tool_msg = [m for m in provider.requests[1]["messages"] if m.get("role") == "tool"][-1]
            payload = json.loads(tool_msg["content"])
            self.assertEqual(payload.get("root"), "outputs/task1")

    def test_verifier_agent_prompt_contains_expected_artifacts_and_key_evidence(self):
        provider = MockModelProvider(
            scripted_outputs=[
                {
                    "content": '{"passed": true, "score": 0.9, "reason": "ok", "checks": []}',
                    "raw": {"mock": True},
                }
            ]
        )
        agent = VerifierAgent(model_provider=provider)
        agent.evaluate(
            run_outcome=RunOutcome(
                task_id="t4",
                run_id="r4",
                user_input="检查交付",
                final_answer="已完成交付",
                stop_reason="stop",
                verification_handoff={
                    "goal": "检查交付",
                    "expected_artifacts": [
                        {"path": "work/report.md", "must_exist": True, "non_empty": True, "contains": "摘要"}
                    ],
                    "key_evidence": [
                        {"type": "command", "name": "pytest", "summary": "目标测试通过"}
                    ],
                },
            ),
        )
        user_prompt = provider.requests[0]["messages"][1]["content"]
        self.assertIn("[主链路交接-预期产物]", user_prompt)
        self.assertIn("path=work/report.md", user_prompt)
        self.assertIn("contains=摘要", user_prompt)
        self.assertIn("[主链路交接-关键证据]", user_prompt)
        self.assertIn("[command] pytest: 目标测试通过", user_prompt)


if __name__ == "__main__":
    unittest.main()
