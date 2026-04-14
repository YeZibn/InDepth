import unittest
from unittest.mock import patch

from app.core.model.mock_provider import MockModelProvider
from app.core.runtime.agent_runtime import AgentRuntime
from app.core.tools.registry import ToolRegistry


class RuntimeEvalIntegrationTests(unittest.TestCase):
    def test_runtime_start_recall_skips_injection_without_high_precision_matches(self):
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
            mock_store.search_cards.return_value = []
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
        self.assertTrue(mock_store.search_cards.called)

    def test_runtime_start_recall_injects_memory_block_for_high_precision_matches(self):
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
            mock_store.search_cards.return_value = [
                {
                    "id": "mem_high_1",
                    "title": "支付重试幂等检查",
                    "retrieval_score": 0.88,
                    "scenario": {"trigger_hint": "涉及重试时触发"},
                    "solution": {"steps": ["校验幂等键", "使用唯一约束"]},
                    "anti_pattern": {"not_applicable_if": ["纯查询接口"]},
                },
                {
                    "id": "mem_low_1",
                    "title": "低相关卡片",
                    "retrieval_score": 0.4,
                },
            ]
            runtime = AgentRuntime(model_provider=provider, tool_registry=ToolRegistry(), max_steps=2)
            result = runtime.run("请执行支付重试逻辑检查", task_id="runtime_mem_task", run_id="runtime_mem_run")

        self.assertEqual(result, "任务正常完成")
        self.assertTrue(provider.requests)
        first_messages = provider.requests[0]["messages"]
        system_blocks = [m.get("content", "") for m in first_messages if m.get("role") == "system"]
        joined = "\n".join([str(x) for x in system_blocks])
        self.assertIn("系统记忆召回", joined)
        self.assertIn("支付重试幂等检查", joined)
        self.assertNotIn("低相关卡片", joined)

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
        judged = [e for e in captured if e.get("event_type") == "task_judged"]
        self.assertEqual(len(judged), 1)
        payload = judged[0].get("payload", {})
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
        self.assertEqual(finished[0].get("status"), "ok")
        judged = [e for e in captured if e.get("event_type") == "task_judged"]
        self.assertEqual(len(judged), 1)
        self.assertEqual(judged[0].get("status"), "error")
        self.assertEqual(judged[0].get("payload", {}).get("verified_success"), False)
        self.assertTrue(any(e.get("event_type") == "verification_failed" for e in captured))

    def test_runtime_skips_evaluation_when_clarification_is_requested(self):
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
        captured = []

        def _capture_emit_event(*args, **kwargs):
            captured.append(kwargs)
            return {}

        with patch("app.core.runtime.agent_runtime.emit_event", side_effect=_capture_emit_event):
            runtime = AgentRuntime(model_provider=provider, tool_registry=ToolRegistry(), max_steps=2)
            result = runtime.run("请写一个摘要", task_id="runtime_eval_task4", run_id="runtime_eval_run4")

        self.assertIn("确认", result)
        self.assertTrue(any(e.get("event_type") == "clarification_requested" for e in captured))
        self.assertTrue(any(e.get("event_type") == "verification_skipped" for e in captured))
        self.assertFalse(any(e.get("event_type") == "verification_started" for e in captured))
        self.assertFalse(any(e.get("event_type") == "task_judged" for e in captured))

    def test_runtime_resumes_same_run_after_user_clarification(self):
        provider = MockModelProvider(
            scripted_outputs=[
                {
                    "content": "请确认是否需要包含测试报告？",
                    "raw": {
                        "choices": [
                            {
                                "finish_reason": "stop",
                                "message": {"role": "assistant", "content": "请确认是否需要包含测试报告？"},
                            }
                        ]
                    },
                },
                {
                    "content": "已完成并包含测试报告。",
                    "raw": {
                        "choices": [
                            {
                                "finish_reason": "stop",
                                "message": {"role": "assistant", "content": "已完成并包含测试报告。"},
                            }
                        ]
                    },
                },
            ]
        )
        captured = []

        def _capture_emit_event(*args, **kwargs):
            captured.append(kwargs)
            return {}

        with patch("app.core.runtime.agent_runtime.emit_event", side_effect=_capture_emit_event):
            runtime = AgentRuntime(model_provider=provider, tool_registry=ToolRegistry(), max_steps=2)
            first = runtime.run("请产出发布说明", task_id="runtime_eval_task5", run_id="runtime_eval_run5")
            second = runtime.run(
                "需要包含测试报告",
                task_id="runtime_eval_task5",
                run_id="runtime_eval_run5",
                resume_from_waiting=True,
            )

        self.assertIn("确认", first)
        self.assertIn("完成", second)
        self.assertTrue(any(e.get("event_type") == "run_resumed" for e in captured))
        self.assertTrue(any(e.get("event_type") == "user_clarification_received" for e in captured))
        judged = [e for e in captured if e.get("event_type") == "task_judged"]
        self.assertEqual(len(judged), 1)

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
