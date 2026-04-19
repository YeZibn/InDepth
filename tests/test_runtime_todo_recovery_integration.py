import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.core.model.mock_provider import MockModelProvider
from app.core.memory.sqlite_memory_store import SQLiteMemoryStore
from app.core.runtime.agent_runtime import AgentRuntime
from app.core.runtime.todo_runtime_lifecycle import update_active_todo_context
from app.core.tools.adapters import register_tool_functions
from app.core.tools.registry import ToolRegistry
from app.tool.todo_tool.todo_tool import _parse_task_file, load_todo_tools, plan_task


class RuntimeTodoRecoveryIntegrationTests(unittest.TestCase):
    def _build_runtime(self, provider: MockModelProvider, max_steps: int = 1, memory_store=None, **kwargs) -> AgentRuntime:
        registry = ToolRegistry()
        register_tool_functions(registry, load_todo_tools().get_tools())
        return AgentRuntime(
            model_provider=provider,
            tool_registry=registry,
            memory_store=memory_store,
            max_steps=max_steps,
            enable_verification_handoff_llm=False,
            **kwargs,
        )

    def test_runtime_emits_phase_transition_events(self):
        provider = MockModelProvider(
            scripted_outputs=[
                {
                    "content": "",
                    "raw": {
                        "choices": [
                            {
                                "finish_reason": "stop",
                                "message": {"role": "assistant", "content": "已完成。"},
                            }
                        ]
                    },
                }
            ]
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = self._build_runtime(provider=provider)
            with patch("app.core.runtime.agent_runtime.emit_event") as mock_emit:
                runtime.run(
                    "请根据已有材料先准备计划，再决定是否创建 todo。",
                    task_id="runtime_phase_events_task",
                    run_id="runtime_phase_events_run",
                )

            phase_events = [
                call.kwargs
                for call in mock_emit.call_args_list
                if call.kwargs.get("event_type") in {"phase_started", "phase_completed"}
            ]
            started = [item["payload"]["phase"] for item in phase_events if item.get("event_type") == "phase_started"]
            completed = [item["payload"]["phase"] for item in phase_events if item.get("event_type") == "phase_completed"]
            self.assertIn("preparing", started)
            self.assertIn("executing", started)
            self.assertIn("finalizing", started)
            self.assertIn("preparing", completed)
            self.assertIn("executing", completed)

    def test_runtime_enters_finalizing_before_verification_starts(self):
        provider = MockModelProvider(
            scripted_outputs=[
                {
                    "content": "",
                    "raw": {
                        "choices": [
                            {
                                "finish_reason": "stop",
                                "message": {"role": "assistant", "content": "已完成。"},
                            }
                        ]
                    },
                }
            ]
        )
        runtime = self._build_runtime(provider=provider)

        with patch("app.core.runtime.agent_runtime.emit_event") as mock_emit:
            runtime.run(
                "请直接完成任务并结束。",
                task_id="runtime_finalizing_order_task",
                run_id="runtime_finalizing_order_run",
            )

        finalizing_index = next(
            i
            for i, call in enumerate(mock_emit.call_args_list)
            if call.kwargs.get("event_type") == "phase_started"
            and call.kwargs.get("payload", {}).get("phase") == "finalizing"
        )
        verification_index = next(
            i for i, call in enumerate(mock_emit.call_args_list) if call.kwargs.get("event_type") == "verification_started"
        )
        self.assertLess(finalizing_index, verification_index)

    def test_runtime_enters_finalizing_before_pause_closeout(self):
        provider = MockModelProvider(
            scripted_outputs=[
                {
                    "content": "我需要先确认一下：你希望输出中文还是英文？",
                    "raw": {
                        "choices": [
                            {
                                "finish_reason": "stop",
                                "message": {"role": "assistant", "content": "我需要先确认一下：你希望输出中文还是英文？"},
                            }
                        ]
                    },
                }
            ]
        )
        runtime = self._build_runtime(provider=provider)

        with patch("app.core.runtime.agent_runtime.emit_event") as mock_emit:
            runtime.run(
                "请写一个摘要",
                task_id="runtime_finalizing_pause_task",
                run_id="runtime_finalizing_pause_run",
            )

        finalizing_index = next(
            i
            for i, call in enumerate(mock_emit.call_args_list)
            if call.kwargs.get("event_type") == "phase_started"
            and call.kwargs.get("payload", {}).get("phase") == "finalizing"
        )
        skipped_index = next(
            i for i, call in enumerate(mock_emit.call_args_list) if call.kwargs.get("event_type") == "verification_skipped"
        )
        self.assertLess(finalizing_index, skipped_index)

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

    def test_runtime_injects_prepare_phase_message_before_first_model_request(self):
        provider = MockModelProvider(
            scripted_outputs=[
                {
                    "content": "",
                    "raw": {
                        "choices": [
                            {
                                "finish_reason": "stop",
                                "message": {"role": "assistant", "content": "已完成。"},
                            }
                        ]
                    },
                }
            ]
        )
        runtime = self._build_runtime(provider=provider)

        runtime.run(
            "请根据已有材料先准备计划，再决定是否创建 todo。",
            task_id="runtime_prepare_phase_task",
            run_id="runtime_prepare_phase_run",
        )

        first_request = provider.requests[0]
        self.assertIn("You are currently in executing phase.", first_request["messages"][0]["content"])
        rendered_messages = "\n".join(str(msg.get("content", "")) for msg in first_request["messages"])
        self.assertIn("[Prepare Phase]", rendered_messages)
        self.assertIn("should_use_todo=True", rendered_messages)
        self.assertIn("prefer calling plan_task", rendered_messages)
        self.assertIn("澄清上下文并细化执行计划", rendered_messages)

    def test_runtime_prints_prepare_cli_summary_before_execution(self):
        provider = MockModelProvider(
            scripted_outputs=[
                {
                    "content": "",
                    "raw": {
                        "choices": [
                            {
                                "finish_reason": "stop",
                                "message": {"role": "assistant", "content": "已完成。"},
                            }
                        ]
                    },
                }
            ]
        )
        traced: list[str] = []
        runtime = self._build_runtime(provider=provider, trace_printer=traced.append)

        runtime.run(
            "请根据已有材料先准备计划，再决定是否创建 todo。",
            task_id="runtime_prepare_cli_task",
            run_id="runtime_prepare_cli_run",
        )

        joined = "\n".join(traced)
        self.assertIn("[Prepare]", joined)
        self.assertIn("任务目标：", joined)
        self.assertIn("决策：启用 todo", joined)
        self.assertIn("下一阶段：executing", joined)
        self.assertIn("拆分理由：", joined)
        self.assertIn("计划摘要：", joined)
        self.assertIn("计划明细：", joined)
        self.assertIn("1. 澄清上下文并细化执行计划", joined)
        self.assertIn("拆分依据：", joined)

    def test_runtime_prepare_message_includes_current_state_summary_for_active_todo(self):
        provider = MockModelProvider(
            scripted_outputs=[
                {
                    "content": "",
                    "raw": {
                        "choices": [
                            {
                                "finish_reason": "stop",
                                "message": {"role": "assistant", "content": "已完成。"},
                            }
                        ]
                    },
                }
            ]
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = self._build_runtime(provider=provider)
            with (
                patch("app.tool.todo_tool.todo_tool._get_todo_dir", return_value=tmpdir),
                patch("app.tool.todo_tool.todo_tool._emit_obs"),
                patch("app.tool.todo_tool.todo_tool._generate_todo_id", return_value="todo_123"),
                patch(
                    "app.core.runtime.agent_runtime.restore_active_todo_context_from_history",
                    return_value={
                        "todo_id": "todo_123",
                        "active_subtask_id": None,
                        "active_subtask_number": 1,
                        "execution_phase": "planning",
                        "binding_required": True,
                        "binding_state": "bound",
                        "todo_bound_at": "",
                        "active_retry_guidance": [],
                    },
                ),
            ):
                created = plan_task.entrypoint(
                    task_name="Base Task",
                    context="Create the original tracked todo",
                    split_reason="Need a shared todo first.",
                    subtasks=[{"name": "Main step", "description": "Do the main thing"}],
                )
                self.assertTrue(created["success"])
                runtime.run(
                    "继续推进这个任务",
                    task_id="runtime_prepare_active_todo_task",
                    run_id="runtime_prepare_active_todo_run",
                )

        first_request = provider.requests[0]
        rendered_messages = "\n".join(str(msg.get("content", "")) for msg in first_request["messages"])
        self.assertIn("current_state_summary=", rendered_messages)
        self.assertIn("当前 todo 进度", rendered_messages)

    def test_runtime_prepare_cli_summary_includes_current_state_for_active_todo(self):
        provider = MockModelProvider(
            scripted_outputs=[
                {
                    "content": "",
                    "raw": {
                        "choices": [
                            {
                                "finish_reason": "stop",
                                "message": {"role": "assistant", "content": "已完成。"},
                            }
                        ]
                    },
                }
            ]
        )
        traced: list[str] = []
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = self._build_runtime(provider=provider, trace_printer=traced.append)
            with (
                patch("app.tool.todo_tool.todo_tool._get_todo_dir", return_value=tmpdir),
                patch("app.tool.todo_tool.todo_tool._emit_obs"),
                patch("app.tool.todo_tool.todo_tool._generate_todo_id", return_value="todo_123"),
                patch(
                    "app.core.runtime.agent_runtime.restore_active_todo_context_from_history",
                    return_value={
                        "todo_id": "todo_123",
                        "active_subtask_id": None,
                        "active_subtask_number": 1,
                        "execution_phase": "planning",
                        "binding_required": True,
                        "binding_state": "bound",
                        "todo_bound_at": "",
                        "active_retry_guidance": [],
                    },
                ),
            ):
                created = plan_task.entrypoint(
                    task_name="Base Task",
                    context="Create the original tracked todo",
                    split_reason="Need a shared todo first.",
                    subtasks=[{"name": "Main step", "description": "Do the main thing"}],
                )
                self.assertTrue(created["success"])
                runtime.run(
                    "继续推进这个任务",
                    task_id="runtime_prepare_active_todo_cli_task",
                    run_id="runtime_prepare_active_todo_cli_run",
                )

        joined = "\n".join(traced)
        self.assertIn("当前现状：", joined)
        self.assertIn("当前 todo 进度", joined)

    def test_runtime_can_use_llm_prepare_without_tools(self):
        provider = MockModelProvider(
            scripted_outputs=[
                {
                    "content": (
                        '{"should_use_todo": true, "task_name": "Demo Plan", "context": "请先规划并建立 todo。", '
                        '"split_reason": "Need tracked work.", '
                        '"subtasks": [{"name": "Bootstrap", "description": "Create an initial tracked step."}], '
                        '"notes": ["llm planner used"]}'
                    ),
                    "raw": {"mock": True},
                },
                {
                    "content": "",
                    "raw": {
                        "choices": [
                            {
                                "finish_reason": "stop",
                                "message": {"role": "assistant", "content": "已完成。"},
                            }
                        ]
                    },
                },
            ]
        )
        runtime = self._build_runtime(provider=provider, enable_llm_todo_planner=True)

        with tempfile.TemporaryDirectory() as tmpdir:
            with (
                patch("app.tool.todo_tool.todo_tool._get_todo_dir", return_value=tmpdir),
                patch("app.tool.todo_tool.todo_tool._generate_todo_id", return_value="20260418_llm_prepare_demo"),
            ):
                runtime.run(
                    "请先规划并建立 todo。",
                    task_id="runtime_llm_prepare_task",
                    run_id="runtime_llm_prepare_run",
                )

        self.assertGreaterEqual(len(provider.requests), 2)
        prepare_request = provider.requests[0]
        self.assertEqual(prepare_request["tools"], [])
        self.assertIn("Runtime 的前置 Todo 规划器", prepare_request["messages"][0]["content"])
        self.assertIn("name、description、split_rationale", prepare_request["messages"][0]["content"])
        self.assertTrue(runtime._prepare_phase_completed)
        self.assertEqual(runtime._prepare_phase_result.get("planner_source"), "llm")
        self.assertEqual(runtime._prepare_phase_result["subtasks"][0]["split_rationale"], "Need tracked work.")

    def test_runtime_switches_system_prompt_to_executing_after_prepare(self):
        provider = MockModelProvider(
            scripted_outputs=[
                {
                    "content": "",
                    "raw": {
                        "choices": [
                            {
                                "finish_reason": "stop",
                                "message": {"role": "assistant", "content": "已完成。"},
                            }
                        ]
                    },
                }
            ]
        )
        runtime = self._build_runtime(provider=provider)

        runtime.run(
            "请根据已有材料先准备计划，再决定是否创建 todo。",
            task_id="runtime_phase_switch_task",
            run_id="runtime_phase_switch_run",
        )

        first_request = provider.requests[0]
        self.assertIn("You are currently in executing phase.", first_request["messages"][0]["content"])

    def test_runtime_llm_prepare_receives_active_todo_full_text(self):
        provider = MockModelProvider(
            scripted_outputs=[
                {
                    "content": (
                        '{"should_use_todo": true, "task_name": "Continue todo_123", '
                        '"context": "继续已有 todo。", "split_reason": "Continue tracked work.", '
                        '"subtasks": [{"name": "Continue", "description": "Append a next step."}], "notes": []}'
                    ),
                    "raw": {"mock": True},
                },
                {
                    "content": "",
                    "raw": {
                        "choices": [
                            {
                                "finish_reason": "stop",
                                "message": {"role": "assistant", "content": "已完成。"},
                            }
                        ]
                    },
                },
            ]
        )
        runtime = self._build_runtime(provider=provider, enable_llm_todo_planner=True)

        with tempfile.TemporaryDirectory() as tmpdir:
            with (
                patch("app.tool.todo_tool.todo_tool._get_todo_dir", return_value=tmpdir),
                patch("app.tool.todo_tool.todo_tool._generate_todo_id", return_value="todo_123"),
                patch(
                    "app.core.runtime.agent_runtime.restore_active_todo_context_from_history",
                    return_value={
                        "todo_id": "todo_123",
                        "active_subtask_id": "st_current",
                        "active_subtask_number": 1,
                        "execution_phase": "executing",
                        "binding_required": True,
                        "binding_state": "bound",
                        "todo_bound_at": "",
                        "active_retry_guidance": [],
                    },
                ),
            ):
                runtime.tool_registry.invoke(
                    "plan_task",
                    {
                        "task_name": "Base Task",
                        "context": "Create the original tracked todo",
                        "split_reason": "Need a shared todo first.",
                        "subtasks": [{"name": "Main step", "description": "Do the main thing"}],
                    },
                )
                runtime.run(
                    "继续已有 todo。",
                    task_id="runtime_llm_prepare_todo_text_task",
                    run_id="runtime_llm_prepare_todo_text_run",
                )

        prepare_request = provider.requests[0]
        prepare_payload = prepare_request["messages"][1]["content"]
        self.assertIn('"active_todo_id": "todo_123"', prepare_payload)
        self.assertIn("# Task: Base Task", prepare_payload)

    def test_runtime_auto_applies_prepared_create_plan_before_first_model_request(self):
        provider = MockModelProvider(
            scripted_outputs=[
                {
                    "content": "",
                    "raw": {
                        "choices": [
                            {
                                "finish_reason": "stop",
                                "message": {"role": "assistant", "content": "已完成。"},
                            }
                        ]
                    },
                }
            ]
        )
        runtime = self._build_runtime(provider=provider)

        with tempfile.TemporaryDirectory() as tmpdir:
            with (
                patch("app.tool.todo_tool.todo_tool._get_todo_dir", return_value=tmpdir),
                patch("app.tool.todo_tool.todo_tool._generate_todo_id", return_value="20260418_prepare_auto_demo"),
            ):
                runtime.run(
                    "请先准备并建立一个跟踪 todo，然后再继续执行。",
                    task_id="runtime_prepare_auto_plan_task",
                    run_id="runtime_prepare_auto_plan_run",
                )

                created = Path(tmpdir) / "20260418_prepare_auto_demo.md"
                self.assertTrue(created.exists())
                parsed = _parse_task_file(created)
                self.assertEqual(len(parsed["subtasks"]), 1)
                self.assertIn("澄清上下文", parsed["subtasks"][0]["name"])

        first_request = provider.requests[0]
        assistant_tool_msgs = [msg for msg in first_request["messages"] if msg.get("role") == "assistant" and msg.get("tool_calls")]
        tool_msgs = [msg for msg in first_request["messages"] if msg.get("role") == "tool"]
        self.assertTrue(any(call["function"]["name"] == "plan_task" for msg in assistant_tool_msgs for call in msg.get("tool_calls", [])))
        self.assertTrue(tool_msgs)

    def test_runtime_auto_applies_prepared_update_plan_before_first_model_request(self):
        provider = MockModelProvider(
            scripted_outputs=[
                {
                    "content": "",
                    "raw": {
                        "choices": [
                            {
                                "finish_reason": "stop",
                                "message": {"role": "assistant", "content": "已完成。"},
                            }
                        ]
                    },
                }
            ]
        )
        runtime = self._build_runtime(provider=provider)

        with tempfile.TemporaryDirectory() as tmpdir:
            with (
                patch("app.tool.todo_tool.todo_tool._get_todo_dir", return_value=tmpdir),
                patch("app.tool.todo_tool.todo_tool._generate_todo_id", return_value="todo_123"),
                patch("app.tool.todo_tool.todo_tool._emit_obs"),
                patch(
                    "app.core.runtime.agent_runtime.restore_active_todo_context_from_history",
                    return_value={
                        "todo_id": "todo_123",
                        "active_subtask_id": "st_current",
                        "active_subtask_number": 1,
                        "execution_phase": "executing",
                        "binding_required": True,
                        "binding_state": "bound",
                        "todo_bound_at": "",
                        "active_retry_guidance": [],
                    },
                ),
            ):
                registry = runtime.tool_registry
                created = registry.invoke(
                    "plan_task",
                    {
                        "task_name": "Base Task",
                        "context": "Create the original tracked todo",
                        "split_reason": "Need a shared todo first.",
                        "subtasks": [{"name": "Main step", "description": "Do the main thing"}],
                    },
                )
                self.assertTrue(created["success"])

                runtime.run(
                    "请基于已有 todo 继续推进，不要新建。",
                    task_id="runtime_prepare_auto_update_task",
                    run_id="runtime_prepare_auto_update_run",
                )

                parsed = _parse_task_file(Path(tmpdir) / "todo_123.md")
                self.assertIn("当前请求摘要", parsed["subtasks"][1]["description"])

        first_request = provider.requests[0]
        assistant_tool_msgs = [msg for msg in first_request["messages"] if msg.get("role") == "assistant" and msg.get("tool_calls")]
        self.assertTrue(any(call["function"]["name"] == "plan_task" for msg in assistant_tool_msgs for call in msg.get("tool_calls", [])))

    def test_runtime_blocks_planning_tools_when_prepare_phase_not_completed(self):
        runtime = self._build_runtime(provider=MockModelProvider(scripted_outputs=[]))
        runtime._prepare_phase_completed = False
        runtime._prepare_phase_result = {}

        messages = []
        tool_calls = [
            {
                "id": "call_plan_without_prepare",
                "type": "function",
                "function": {
                    "name": "plan_task",
                    "arguments": (
                        '{"task_name":"Demo","context":"Need tracked work",'
                        '"split_reason":"Need todo","subtasks":[{"name":"Step 1","description":"Do it"}]}'
                    ),
                },
            }
        ]
        outcome = runtime._handle_native_tool_calls(
            tool_calls=tool_calls,
            messages=messages,
            task_id="runtime_prepare_guard_task",
            run_id="runtime_prepare_guard_run",
            step_id="1",
        )

        self.assertEqual(len(outcome["failures"]), 1)
        self.assertIn("Prepare phase not completed", outcome["failures"][0]["error"])
        self.assertEqual(outcome["executions"][0]["tool"], "plan_task")
        self.assertFalse(outcome["executions"][0]["success"])

if __name__ == "__main__":
    unittest.main()
