import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.core.memory.sqlite_memory_store import SQLiteMemoryStore
from app.core.model.mock_provider import MockModelProvider
from app.core.runtime.agent_runtime import AgentRuntime
from app.core.runtime.todo_runtime_lifecycle import update_active_todo_context
from app.core.tools.adapters import register_tool_functions
from app.core.tools.registry import ToolRegistry, ToolSpec
from app.eval.schema import RunJudgement
from app.tool.todo_tool.todo_tool import _parse_task_file, load_todo_tools


class RuntimeTodoRecoveryIntegrationTests(unittest.TestCase):
    def test_runtime_disables_llm_recovery_planner_by_default_for_mock_provider(self):
        provider = MockModelProvider(scripted_outputs=[])
        runtime = AgentRuntime(model_provider=provider, tool_registry=ToolRegistry())
        self.assertFalse(runtime.enable_llm_recovery_planner)

    def test_update_active_todo_context_preserves_retry_guidance_across_reopen(self):
        ctx = update_active_todo_context(
            current_context={},
            executions=[
                {
                    "tool": "record_task_fallback",
                    "args": {
                        "todo_id": "todo_1",
                        "subtask_number": 1,
                        "retry_guidance": ["Generate one section at a time."],
                    },
                    "success": True,
                    "payload": {"subtask_id": "st_1", "fallback_record": {"retry_guidance": ["Generate one section at a time."]}},
                },
                {
                    "tool": "reopen_subtask",
                    "args": {"todo_id": "todo_1", "subtask_number": 1},
                    "success": True,
                    "payload": {"todo_id": "todo_1", "subtask_id": "st_1", "subtask_number": 1},
                },
            ],
        )
        self.assertEqual(ctx.get("active_retry_guidance"), ["Generate one section at a time."])
        self.assertEqual(ctx.get("execution_phase"), "executing")

    def test_system_prompt_includes_retry_guidance_for_active_subtask(self):
        runtime = AgentRuntime(model_provider=MockModelProvider(scripted_outputs=[]), tool_registry=ToolRegistry())
        runtime._active_todo_context = {
            "todo_id": "todo_1",
            "active_subtask_number": 2,
            "active_retry_guidance": ["Generate one section at a time.", "Write each section before continuing."],
        }
        prompt = runtime._build_system_prompt()
        self.assertIn("Retry Guidance:", prompt)
        self.assertIn("Active todo: todo_1", prompt)
        self.assertIn("Active subtask: 2", prompt)
        self.assertIn("Generate one section at a time.", prompt)
        self.assertIn("Write each section before continuing.", prompt)

    def test_runtime_rejects_duplicate_create_task_when_active_todo_is_bound(self):
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
                                            "id": "call_create_1",
                                            "type": "function",
                                            "function": {
                                                "name": "create_task",
                                                "arguments": (
                                                    '{"task_name":"Demo Todo","context":"Runtime duplicate guard",'
                                                    '"split_reason":"Need a todo",'
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
                                            "id": "call_create_2",
                                            "type": "function",
                                            "function": {
                                                "name": "create_task",
                                                "arguments": (
                                                    '{"task_name":"Second Todo","context":"Should be rejected",'
                                                    '"split_reason":"Should not create another todo",'
                                                    '"subtasks":[{"name":"Another step","description":"Do the other work"}]}'
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
        runtime = AgentRuntime(model_provider=provider, tool_registry=registry, max_steps=3, enable_verification_handoff_llm=False)

        with tempfile.TemporaryDirectory() as tmpdir:
            with (
                patch("app.tool.todo_tool.todo_tool._get_todo_dir", return_value=tmpdir),
                patch("app.tool.todo_tool.todo_tool._generate_todo_id", return_value="20260416_999999_demo"),
            ):
                final = runtime.run(
                    "Please create a todo and then create another one.",
                    task_id="runtime_todo_duplicate_guard_task",
                    run_id="runtime_todo_duplicate_guard_run",
                )

            self.assertIn("任务未完成", final)
            self.assertIn("create_task", final)
            parsed = _parse_task_file(Path(tmpdir) / "20260416_999999_demo.md")
            self.assertEqual(len(parsed["subtasks"]), 1)

    def test_runtime_restores_todo_binding_from_history_before_duplicate_create_task(self):
        registry = ToolRegistry()
        register_tool_functions(registry, load_todo_tools().get_tools())

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "runtime_memory.db")
            store = SQLiteMemoryStore(db_file=db_path, summarize_threshold=9999)

            first_provider = MockModelProvider(
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
                                                "id": "call_create_history",
                                                "type": "function",
                                                "function": {
                                                    "name": "create_task",
                                                    "arguments": (
                                                        '{"task_name":"Demo Todo","context":"Create tracked work",'
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
                        "content": "todo created",
                        "raw": {
                            "choices": [
                                {
                                    "finish_reason": "stop",
                                    "message": {"role": "assistant", "content": "todo created"},
                                }
                            ]
                        },
                    },
                ]
            )

            second_provider = MockModelProvider(
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
                                                "id": "call_create_again",
                                                "type": "function",
                                                "function": {
                                                    "name": "create_task",
                                                    "arguments": (
                                                        '{"task_name":"Second Todo","context":"Should reuse history-bound todo",'
                                                        '"split_reason":"Should not create another todo",'
                                                        '"subtasks":[{"name":"Another step","description":"Do the other work"}]}'
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
                                    "finish_reason": "stop",
                                    "message": {"role": "assistant", "content": ""},
                                }
                            ]
                        },
                    },
                ]
            )

            first_runtime = AgentRuntime(
                model_provider=first_provider,
                tool_registry=registry,
                memory_store=store,
                max_steps=2,
                enable_verification_handoff_llm=False,
            )
            second_runtime = AgentRuntime(
                model_provider=second_provider,
                tool_registry=registry,
                memory_store=store,
                max_steps=2,
                enable_verification_handoff_llm=False,
            )

            with (
                patch("app.tool.todo_tool.todo_tool._get_todo_dir", return_value=tmpdir),
                patch("app.tool.todo_tool.todo_tool._generate_todo_id", return_value="20260416_999999_demo"),
            ):
                first_runtime.run(
                    "Please create a tracked todo for this task.",
                    task_id="runtime_cross_run_restore_task",
                    run_id="runtime_cross_run_restore_run_1",
                )
                final = second_runtime.run(
                    "Please continue the same task.",
                    task_id="runtime_cross_run_restore_task",
                    run_id="runtime_cross_run_restore_run_2",
                )

            self.assertIn("任务未完成", final)
            self.assertIn("create_task", final)
            self.assertIn("20260416_999999_demo", final)
            parsed = _parse_task_file(Path(tmpdir) / "20260416_999999_demo.md")
            self.assertEqual(len(parsed["subtasks"]), 1)

    def test_runtime_returns_strong_error_for_create_task_without_subtasks(self):
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
                                            "id": "call_create_invalid",
                                            "type": "function",
                                            "function": {
                                                "name": "create_task",
                                                "arguments": (
                                                    '{"task_name":"Demo Todo","context":"Missing subtasks envelope",'
                                                    '"split_reason":"Still incomplete"}'
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
        runtime = AgentRuntime(model_provider=provider, tool_registry=registry, max_steps=2, enable_verification_handoff_llm=False)

        final = runtime.run(
            "Please create a tracked todo.",
            task_id="runtime_create_task_arg_guard_task",
            run_id="runtime_create_task_arg_guard_run",
        )

        self.assertIn("任务未完成", final)
        self.assertIn("create_task", final)
        self.assertIn("subtasks", final)

    def test_runtime_reports_orphan_failure_when_todo_is_unbound(self):
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
                                                    '{"task_name":"Demo Todo","context":"Runtime orphan demo",'
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

        runtime = AgentRuntime(model_provider=provider, tool_registry=registry, max_steps=3, enable_verification_handoff_llm=False)

        with tempfile.TemporaryDirectory() as tmpdir:
            with (
                patch("app.tool.todo_tool.todo_tool._get_todo_dir", return_value=tmpdir),
                patch("app.tool.todo_tool.todo_tool._generate_todo_id", return_value="20260416_999999_demo"),
            ):
                final = runtime.run(
                    "Please create a todo and execute the implementation step.",
                    task_id="runtime_todo_orphan_task",
                    run_id="runtime_todo_orphan_run",
                )

            self.assertIn("恢复摘要:", final)
            self.assertIn("todo: 20260416_999999_demo", final)
            self.assertIn("failure: failed / orphan_subtask_unbound", final)
            self.assertIn("next: decision_handoff / agent_decide", final)
            self.assertNotIn("subtask:", final)
            parsed = _parse_task_file(Path(tmpdir) / "20260416_999999_demo.md")
            self.assertEqual(parsed["subtasks"][0]["status"], "pending")

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
            self.assertEqual(parsed["subtasks"][0]["fallback_record"]["reason_code"], "tool_invocation_error")
            self.assertEqual(len(parsed["subtasks"]), 1)

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
        self.assertTrue(recovery.get("subtask_id", "").startswith("st_"))
        self.assertEqual(recovery.get("fallback_record", {}).get("reason_code"), "tool_invocation_error")
        self.assertEqual(recovery.get("recovery_decision", {}).get("primary_action"), "retry_with_fix")
        self.assertTrue(recovery.get("recovery_decision", {}).get("can_resume_in_place"))
        self.assertFalse(recovery.get("recovery_decision", {}).get("needs_derived_recovery_subtask"))

    def test_runtime_uses_independent_llm_recovery_planner_when_enabled(self):
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
                json.dumps(
                    {
                        "failure_label": "tool_failure_needing_split",
                        "reason_code": "tool_invocation_error",
                        "reason_detail": "The tool failure looks like a narrow execution issue that should be diagnosed before retrying.",
                        "confidence": 0.76,
                        "retryable": True,
                        "evidence": ["always_fail returned a forced failure", "original task can be retried after diagnosis"],
                        "suspected_root_causes": ["tool invocation needs narrower correction"],
                        "recovery_risks": ["retrying without diagnosis will likely repeat the same failure"],
                        "can_resume_in_place": True,
                        "needs_derived_recovery_subtask": True,
                        "primary_action": "split",
                        "recommended_actions": ["split", "retry_with_fix"],
                        "decision_level": "auto",
                        "rationale": "The failure suggests splitting out a smaller diagnostic follow-up before retrying.",
                        "resume_condition": "A smaller diagnostic follow-up is prepared.",
                        "stop_auto_recovery": False,
                        "suggested_owner": "main",
                        "next_subtasks": [
                            {
                                "name": "Diagnose the failing tool invocation",
                                "goal": "Find the smallest fix before retrying the original subtask",
                                "description": "Inspect the failing tool call and prepare a minimal correction step.",
                                "kind": "diagnose",
                                "owner": "main",
                                "depends_on": [1],
                                "acceptance_criteria": ["Minimal fix path identified"],
                            }
                        ],
                        "retry_guidance": ["Narrow the failing step before retrying the original execution path."],
                    },
                    ensure_ascii=False,
                ),
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

        runtime = AgentRuntime(
            model_provider=provider,
            tool_registry=registry,
            max_steps=4,
            enable_verification_handoff_llm=False,
            enable_llm_recovery_planner=True,
            enable_memory_recall_reranker=False,
            enable_memory_card_metadata_llm=False,
            enable_llm_clarification_judge=False,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            with (
                patch("app.tool.todo_tool.todo_tool._get_todo_dir", return_value=tmpdir),
                patch("app.tool.todo_tool.todo_tool._generate_todo_id", return_value="20260416_999999_demo"),
            ):
                final = runtime.run(
                    "Please create a todo and execute the implementation step.",
                    task_id="runtime_todo_llm_recovery_task",
                    run_id="runtime_todo_llm_recovery_run",
                )

            self.assertIn("next: split / auto", final)
            parsed = _parse_task_file(Path(tmpdir) / "20260416_999999_demo.md")
            self.assertEqual(len(parsed["subtasks"]), 2)
            self.assertEqual(parsed["subtasks"][1]["origin_subtask_number"], "1")
            self.assertEqual(parsed["subtasks"][1]["origin_subtask_id"], parsed["subtasks"][0]["subtask_id"])
            self.assertEqual(runtime._latest_todo_recovery["recovery_decision"]["planner_source"], "llm")
            self.assertEqual(runtime._latest_todo_recovery["failure_interpretation"]["classification_source"], "llm")
            self.assertEqual(
                runtime._latest_todo_recovery["recovery_decision"]["retry_guidance"],
                ["Narrow the failing step before retrying the original execution path."],
            )
            self.assertGreaterEqual(len(provider.requests), 5)
            self.assertTrue(
                any("recovery_assessment" in req["messages"][1]["content"] for req in provider.requests if len(req["messages"]) > 1)
            )

    def test_runtime_recovery_planner_falls_back_to_rule_when_llm_output_is_invalid(self):
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
                "not-json",
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

        runtime = AgentRuntime(
            model_provider=provider,
            tool_registry=registry,
            max_steps=4,
            enable_verification_handoff_llm=False,
            enable_llm_recovery_planner=True,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            with (
                patch("app.tool.todo_tool.todo_tool._get_todo_dir", return_value=tmpdir),
                patch("app.tool.todo_tool.todo_tool._generate_todo_id", return_value="20260416_999999_demo"),
            ):
                final = runtime.run(
                    "Please create a todo and execute the implementation step.",
                    task_id="runtime_todo_llm_recovery_invalid_task",
                    run_id="runtime_todo_llm_recovery_invalid_run",
                )

            self.assertIn("next: retry_with_fix / auto", final)
            parsed = _parse_task_file(Path(tmpdir) / "20260416_999999_demo.md")
            self.assertEqual(len(parsed["subtasks"]), 1)
            self.assertEqual(runtime._latest_todo_recovery["recovery_decision"]["planner_source"], "rule")
            self.assertEqual(runtime._latest_todo_recovery["failure_interpretation"]["classification_source"], "rule")
            self.assertGreaterEqual(len(provider.requests), 5)

    def test_runtime_failure_interpreter_can_reclassify_model_504_into_oversized_generation_request(self):
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
                                                    '{"task_name":"Long-form Writing","context":"Generate a long paper section",'
                                                    '"split_reason":"Need tracked writing subtasks",'
                                                    '"subtasks":[{"name":"Draft full paper","description":"Generate the whole paper body"}]}'
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
                "__RAISE_504__",
                json.dumps(
                    {
                        "failure_label": "generation_overload",
                        "reason_code": "oversized_generation_request",
                        "reason_detail": "The request likely failed because the task was trying to generate too much long-form content in a single attempt.",
                        "confidence": 0.9,
                        "retryable": True,
                        "evidence": ["stop_reason=model_failed", "error contains HTTP 504", "task context asks for long-form generation"],
                        "suspected_root_causes": ["single request too large for long-form output"],
                        "recovery_risks": ["retrying unchanged will likely hit the same 504 again"],
                        "can_resume_in_place": False,
                        "needs_derived_recovery_subtask": True,
                        "primary_action": "split",
                        "recommended_actions": ["split", "retry_with_fix"],
                        "decision_level": "auto",
                        "rationale": "The long-form generation task should be split into smaller writing slices before retrying.",
                        "resume_condition": "A smaller writing slice is prepared.",
                        "retry_guidance": ["Generate one section at a time.", "Write each section to markdown before continuing."],
                        "stop_auto_recovery": False,
                        "suggested_owner": "main",
                        "next_subtasks": [
                            {
                                "name": "Draft only the introduction",
                                "goal": "Reduce the generation load by starting with one section",
                                "description": "Generate the introduction section only and write it before proceeding to later sections.",
                                "kind": "diagnose",
                                "owner": "main",
                                "depends_on": [1],
                                "acceptance_criteria": ["Introduction section generated"],
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
            ]
        )
        original_generate = provider.generate

        def _generate_with_error(messages, tools, config=None):
            if provider._outputs and provider._outputs[0] == "__RAISE_504__":
                provider.requests.append(
                    {
                        "messages": [dict(m) for m in messages],
                        "tools": [dict(t) for t in tools],
                        "config": config,
                    }
                )
                provider._outputs.pop(0)
                raise RuntimeError(
                    'Model request failed after retries: HTTP 504 error: {"error":{"message":"openai_error","type":"bad_response_status_code","param":"","code":"bad_response_status_code"}}'
                )
            return original_generate(messages, tools, config)

        provider.generate = _generate_with_error

        registry = ToolRegistry()
        register_tool_functions(registry, load_todo_tools().get_tools())
        runtime = AgentRuntime(
            model_provider=provider,
            tool_registry=registry,
            max_steps=4,
            enable_verification_handoff_llm=False,
            enable_llm_recovery_planner=True,
            enable_memory_recall_reranker=False,
            enable_memory_card_metadata_llm=False,
            enable_llm_clarification_judge=False,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            with (
                patch("app.tool.todo_tool.todo_tool._get_todo_dir", return_value=tmpdir),
                patch("app.tool.todo_tool.todo_tool._generate_todo_id", return_value="20260416_999999_demo"),
            ):
                final = runtime.run(
                    "Write the whole paper in one go.",
                    task_id="runtime_todo_oversized_generation_task",
                    run_id="runtime_todo_oversized_generation_run",
                )

            self.assertIn("next: split / auto", final)
            parsed = _parse_task_file(Path(tmpdir) / "20260416_999999_demo.md")
            self.assertEqual(parsed["subtasks"][0]["fallback_record"]["reason_code"], "oversized_generation_request")
            self.assertEqual(
                parsed["subtasks"][0]["fallback_record"]["failure_interpretation"]["classification_source"],
                "llm",
            )
            self.assertEqual(runtime._latest_todo_recovery["failure_interpretation"]["reason_code"], "oversized_generation_request")
            self.assertEqual(runtime._latest_todo_recovery["fallback_record"]["reason_code"], "oversized_generation_request")
            self.assertEqual(runtime._latest_todo_recovery["recovery_decision"]["primary_action"], "split")
            self.assertEqual(
                runtime._latest_todo_recovery["recovery_decision"]["retry_guidance"],
                ["Generate one section at a time.", "Write each section to markdown before continuing."],
            )
            self.assertGreaterEqual(len(parsed["subtasks"]), 1)


if __name__ == "__main__":
    unittest.main()
