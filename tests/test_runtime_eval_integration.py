import unittest
from unittest.mock import patch

from app.core.model.mock_provider import MockModelProvider
from app.core.runtime.agent_runtime import AgentRuntime
from app.core.tools.registry import ToolRegistry


class RuntimeEvalIntegrationTests(unittest.TestCase):
    def test_runtime_does_not_inject_system_memory_context_by_default(self):
        provider = MockModelProvider(
            scripted_outputs=[
                {
                    "content": "任务正常完成",
                    "raw": {
                        "choices": [
                            {
                                "finish_reason": "stop",
                                "message": {"role": "assistant", "content": "任务正常完成"},
                            }
                        ]
                    },
                }
            ]
        )

        with patch("app.core.runtime.agent_runtime.SystemMemoryStore") as mock_store_cls:
            mock_store = mock_store_cls.return_value
            runtime = AgentRuntime(model_provider=provider, tool_registry=ToolRegistry(), max_steps=2)
            result = runtime.run("请执行任务", task_id="runtime_mem_task", run_id="runtime_mem_run")

        self.assertEqual(result, "任务正常完成")
        self.assertTrue(provider.requests)
        first_messages = provider.requests[0]["messages"]
        memory_msgs = [
            m for m in first_messages
            if m.get("role") == "system" and "系统记忆召回" in str(m.get("content", ""))
        ]
        self.assertEqual(len(memory_msgs), 0)
        self.assertFalse(mock_store.search_cards.called)

    def test_runtime_forces_task_end_memory_finalization(self):
        provider = MockModelProvider(
            scripted_outputs=[
                {
                    "content": "发布检查已完成",
                    "raw": {
                        "choices": [
                            {
                                "finish_reason": "stop",
                                "message": {"role": "assistant", "content": "发布检查已完成"},
                            }
                        ]
                    },
                }
            ]
        )

        with patch("app.core.runtime.agent_runtime.SystemMemoryStore") as mock_store_cls:
            mock_store = mock_store_cls.return_value
            runtime = AgentRuntime(model_provider=provider, tool_registry=ToolRegistry(), max_steps=2)
            result = runtime.run("请做上线前发布检查", task_id="runtime_pre_release_task", run_id="runtime_pre_release_run")

        self.assertEqual(result, "发布检查已完成")
        self.assertTrue(mock_store.upsert_card.called)
        upsert_card = mock_store.upsert_card.call_args.args[0]
        self.assertEqual(upsert_card.get("memory_type"), "experience")
        self.assertEqual(upsert_card.get("scenario", {}).get("stage"), "postmortem")

    def test_runtime_emits_verification_events_and_judgement_payload(self):
        provider = MockModelProvider(
            scripted_outputs=[
                {
                    "content": "任务已完成",
                    "raw": {
                        "choices": [
                            {
                                "finish_reason": "stop",
                                "message": {"role": "assistant", "content": "任务已完成"},
                            }
                        ]
                    },
                }
            ]
        )
        captured = []

        def _capture_emit_event(*args, **kwargs):
            captured.append(kwargs)
            return {}

        with patch("app.core.runtime.agent_runtime.emit_event", side_effect=_capture_emit_event):
            runtime = AgentRuntime(model_provider=provider, tool_registry=ToolRegistry(), max_steps=2)
            result = runtime.run("verification case", task_id="runtime_eval_task", run_id="runtime_eval_run")

        self.assertEqual(result, "任务已完成")
        self.assertTrue(any(e.get("event_type") == "verification_started" for e in captured))
        self.assertTrue(any(e.get("event_type") == "task_judged" for e in captured))

        finished = [e for e in captured if e.get("event_type") == "task_finished"]
        self.assertEqual(len(finished), 1)
        payload = finished[0].get("payload", {})
        self.assertEqual(payload.get("verified_success"), True)
        self.assertEqual(payload.get("final_status"), "pass")

    def test_runtime_marks_task_finished_error_when_verification_fails(self):
        provider = MockModelProvider(
            scripted_outputs=[
                {
                    "content": "任务已完成",
                    "raw": {
                        "choices": [
                            {
                                "finish_reason": "stop",
                                "message": {"role": "assistant", "content": "任务已完成"},
                            }
                        ]
                    },
                },
                {
                    "content": '{"passed": false, "score": 0.1, "reason": "missing evidence", "checks": []}',
                    "raw": {"mock": True},
                },
            ]
        )
        captured = []

        def _capture_emit_event(*args, **kwargs):
            captured.append(kwargs)
            return {}

        with patch("app.core.runtime.agent_runtime.emit_event", side_effect=_capture_emit_event):
            runtime = AgentRuntime(
                model_provider=provider,
                tool_registry=ToolRegistry(),
                max_steps=2,
                enable_llm_judge=True,
            )
            runtime.run(
                "verification fail case",
                task_id="runtime_eval_task2",
                run_id="runtime_eval_run2",
            )

        finished = [e for e in captured if e.get("event_type") == "task_finished"]
        self.assertEqual(len(finished), 1)
        self.assertEqual(finished[0].get("status"), "error")
        self.assertEqual(finished[0].get("payload", {}).get("verified_success"), False)
        self.assertTrue(any(e.get("event_type") == "verification_failed" for e in captured))

    def test_runtime_can_enable_llm_judge(self):
        provider = MockModelProvider(
            scripted_outputs=[
                {
                    "content": "任务已完成",
                    "raw": {
                        "choices": [
                            {
                                "finish_reason": "stop",
                                "message": {"role": "assistant", "content": "任务已完成"},
                            }
                        ]
                    },
                },
                {
                    "content": '{"passed": true, "score": 0.9, "reason": "quality good"}',
                    "raw": {"mock": True},
                },
            ]
        )
        captured = []

        def _capture_emit_event(*args, **kwargs):
            captured.append(kwargs)
            return {}

        with patch("app.core.runtime.agent_runtime.emit_event", side_effect=_capture_emit_event):
            runtime = AgentRuntime(
                model_provider=provider,
                tool_registry=ToolRegistry(),
                max_steps=2,
                enable_llm_judge=True,
            )
            runtime.run("llm judge case", task_id="runtime_eval_task3", run_id="runtime_eval_run3")

        judged = [e for e in captured if e.get("event_type") == "task_judged"]
        self.assertEqual(len(judged), 1)
        breakdown = judged[0].get("payload", {}).get("verifier_breakdown", [])
        self.assertTrue(any(x.get("verifier_name") == "verifier_agent_judge" for x in breakdown))


if __name__ == "__main__":
    unittest.main()
