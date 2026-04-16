import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.core.model.mock_provider import MockModelProvider
from app.core.runtime.agent_runtime import AgentRuntime
from app.core.tools.adapters import register_tool_functions
from app.core.tools.registry import ToolRegistry, ToolSpec
from app.eval.schema import RunJudgement
from app.tool.todo_tool.todo_tool import _parse_task_file, load_todo_tools


class RuntimeTodoRecoveryIntegrationTests(unittest.TestCase):
    def test_runtime_auto_records_fallback_and_appends_followups_after_tool_failure(self):
        provider = MockModelProvider(
            scripted_outputs=[
                {
                    "content": "",
                    "raw": {
                        "choices": [
                            {
                                "finish_reason": "tool_calls",
                                "message": {
                                    "role": "assistant",
                                    "content": "",
                                    "tool_calls": [
                                        {
                                            "id": "call_create",
                                            "type": "function",
                                            "function": {
                                                "name": "create_task",
                                                "arguments": (
                                                    '{"task_name":"Demo Todo","context":"Runtime recovery demo",'
                                                    '"split_reason":"Need tracked todo recovery",'
                                                    '"subtasks":[{"name":"Implement step","description":"Do the work"}]}'
                                                ),
                                            },
                                        }
                                    ],
                                },
                            }
                        ]
                    },
                },
                {
                    "content": "",
                    "raw": {
                        "choices": [
                            {
                                "finish_reason": "tool_calls",
                                "message": {
                                    "role": "assistant",
                                    "content": "",
                                    "tool_calls": [
                                        {
                                            "id": "call_activate",
                                            "type": "function",
                                            "function": {
                                                "name": "update_task_status",
                                                "arguments": '{"todo_id":"20260416_999999_demo","subtask_number":1,"status":"in-progress"}',
                                            },
                                        }
                                    ],
                                },
                            }
                        ]
                    },
                },
                {
                    "content": "",
                    "raw": {
                        "choices": [
                            {
                                "finish_reason": "tool_calls",
                                "message": {
                                    "role": "assistant",
                                    "content": "",
                                    "tool_calls": [
                                        {
                                            "id": "call_fail",
                                            "type": "function",
                                            "function": {
                                                "name": "always_fail",
                                                "arguments": '{"text":"boom"}',
                                            },
                                        }
                                    ],
                                },
                            }
                        ]
                    },
                },
                {
                    "content": "",
                    "raw": {
                        "choices": [
                            {
                                "finish_reason": "stop",
                                "message": {"role": "assistant", "content": ""},
                            }
                        ]
                    },
                },
            ]
        )

        registry = ToolRegistry()
        register_tool_functions(registry, load_todo_tools().get_tools())
        registry.register(
            ToolSpec(
                name="always_fail",
                description="Always fail for testing",
                handler=lambda text: {"success": False, "error": f"forced failure: {text}"},
                parameters={
                    "type": "object",
                    "properties": {"text": {"type": "string"}},
                    "required": ["text"],
                },
            )
        )

        runtime = AgentRuntime(model_provider=provider, tool_registry=registry, max_steps=4, enable_verification_handoff_llm=False)

        with tempfile.TemporaryDirectory() as tmpdir:
            with (
                patch("app.tool.todo_tool.todo_tool._get_todo_dir", return_value=tmpdir),
                patch("app.tool.todo_tool.todo_tool._generate_todo_id", return_value="20260416_999999_demo"),
            ):
                final = runtime.run(
                    "Please create a todo and execute the implementation step.",
                    task_id="runtime_todo_recovery_task",
                    run_id="runtime_todo_recovery_run",
                )

            self.assertIn("任务未完成", final)
            self.assertIn("恢复摘要:", final)
            self.assertIn("next: retry_with_fix / auto", final)
            parsed = _parse_task_file(Path(tmpdir) / "20260416_999999_demo.md")
            self.assertEqual(parsed["subtasks"][0]["status"], "failed")
            self.assertEqual(parsed["subtasks"][0]["fallback_record"]["reason_code"], "tool_error")
            self.assertGreaterEqual(len(parsed["subtasks"]), 3)
            self.assertEqual(parsed["subtasks"][1]["kind"], "diagnose")

    def test_runtime_includes_recovery_context_in_task_judged_handoff(self):
        provider = MockModelProvider(
            scripted_outputs=[
                {
                    "content": "",
                    "raw": {
                        "choices": [
                            {
                                "finish_reason": "tool_calls",
                                "message": {
                                    "role": "assistant",
                                    "content": "",
                                    "tool_calls": [
                                        {
                                            "id": "call_create",
                                            "type": "function",
                                            "function": {
                                                "name": "create_task",
                                                "arguments": (
                                                    '{"task_name":"Demo Todo","context":"Runtime recovery demo",'
                                                    '"split_reason":"Need tracked todo recovery",'
                                                    '"subtasks":[{"name":"Implement step","description":"Do the work"}]}'
                                                ),
                                            },
                                        }
                                    ],
                                },
                            }
                        ]
                    },
                },
                {
                    "content": "",
                    "raw": {
                        "choices": [
                            {
                                "finish_reason": "tool_calls",
                                "message": {
                                    "role": "assistant",
                                    "content": "",
                                    "tool_calls": [
                                        {
                                            "id": "call_activate",
                                            "type": "function",
                                            "function": {
                                                "name": "update_task_status",
                                                "arguments": '{"todo_id":"20260416_999999_demo","subtask_number":1,"status":"in-progress"}',
                                            },
                                        }
                                    ],
                                },
                            }
                        ]
                    },
                },
                {
                    "content": "",
                    "raw": {
                        "choices": [
                            {
                                "finish_reason": "tool_calls",
                                "message": {
                                    "role": "assistant",
                                    "content": "",
                                    "tool_calls": [
                                        {
                                            "id": "call_fail",
                                            "type": "function",
                                            "function": {
                                                "name": "always_fail",
                                                "arguments": '{"text":"boom"}',
                                            },
                                        }
                                    ],
                                },
                            }
                        ]
                    },
                },
                {
                    "content": "",
                    "raw": {
                        "choices": [
                            {
                                "finish_reason": "stop",
                                "message": {"role": "assistant", "content": ""},
                            }
                        ]
                    },
                },
            ]
        )

        registry = ToolRegistry()
        register_tool_functions(registry, load_todo_tools().get_tools())
        registry.register(
            ToolSpec(
                name="always_fail",
                description="Always fail for testing",
                handler=lambda text: {"success": False, "error": f"forced failure: {text}"},
                parameters={
                    "type": "object",
                    "properties": {"text": {"type": "string"}},
                    "required": ["text"],
                },
            )
        )

        class _CaptureOrchestrator:
            def __init__(self):
                self.last_run_outcome = None

            def evaluate(self, run_outcome):
                self.last_run_outcome = run_outcome
                return RunJudgement(
                    self_reported_success=False,
                    verified_success=False,
                    final_status="fail",
                    failure_type="stop_reason_verifier",
                    overclaim=False,
                    confidence=0.7,
                    verifier_breakdown=[],
                )

        orchestrator = _CaptureOrchestrator()
        runtime = AgentRuntime(
            model_provider=provider,
            tool_registry=registry,
            max_steps=4,
            enable_verification_handoff_llm=False,
            eval_orchestrator=orchestrator,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            with (
                patch("app.tool.todo_tool.todo_tool._get_todo_dir", return_value=tmpdir),
                patch("app.tool.todo_tool.todo_tool._generate_todo_id", return_value="20260416_999999_demo"),
            ):
                runtime.run(
                    "Please create a todo and execute the implementation step.",
                    task_id="runtime_todo_recovery_task_handoff",
                    run_id="runtime_todo_recovery_run_handoff",
                )

        handoff = orchestrator.last_run_outcome.verification_handoff
        recovery = handoff.get("recovery", {})
        self.assertEqual(recovery.get("todo_id"), "20260416_999999_demo")
        self.assertEqual(recovery.get("subtask_number"), 1)
        self.assertEqual(recovery.get("fallback_record", {}).get("reason_code"), "tool_error")
        self.assertEqual(recovery.get("recovery_decision", {}).get("primary_action"), "retry_with_fix")


if __name__ == "__main__":
    unittest.main()
