import unittest
from unittest.mock import patch

from app.core.model.mock_provider import MockModelProvider
from app.core.runtime.agent_runtime import AgentRuntime
from app.core.tools.registry import ToolRegistry
from app.eval.schema import RunJudgement


class RuntimeEvalIntegrationTests(unittest.TestCase):
    def test_runtime_uses_llm_generated_verification_handoff_when_enabled(self):
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
                    "content": (
                        '{"goal":"完成接口文档与测试补充","constraints":["保留原有 API 行为"],'
                        '"expected_artifacts":[{"path":"doc/api.md","must_exist":true,"non_empty":true}],'
                        '"claimed_done_items":["补充了接口说明","补充了回归测试"],'
                        '"key_tool_results":[{"tool":"read_file","status":"ok","summary":"已读取关键文件"}],'
                        '"known_gaps":["尚未执行全量回归"],'
                        '"self_confidence":0.92,"soft_score_threshold":0.75,'
                        '"rubric":"优先检查需求覆盖与证据充分性"}'
                    ),
                    "raw": {"mock": True},
                },
            ]
        )

        class _CaptureOrchestrator:
            def __init__(self):
                self.last_run_outcome = None

            def evaluate(self, run_outcome):
                self.last_run_outcome = run_outcome
                return RunJudgement(
                    self_reported_success=True,
                    verified_success=True,
                    final_status="pass",
                    failure_type=None,
                    overclaim=False,
                    confidence=0.9,
                    verifier_breakdown=[],
                )

        orchestrator = _CaptureOrchestrator()
        runtime = AgentRuntime(
            model_provider=provider,
            tool_registry=ToolRegistry(),
            max_steps=2,
            eval_orchestrator=orchestrator,
            enable_verification_handoff_llm=True,
        )
        runtime.run("请完善接口文档并补充测试", task_id="runtime_eval_task_handoff", run_id="runtime_eval_run_handoff")

        handoff = orchestrator.last_run_outcome.verification_handoff
        self.assertEqual(handoff.get("goal"), "完成接口文档与测试补充")
        self.assertEqual(handoff.get("constraints"), ["保留原有 API 行为"])
        self.assertEqual(handoff.get("expected_artifacts", [])[0].get("path"), "doc/api.md")
        self.assertEqual(handoff.get("soft_score_threshold"), 0.75)
        self.assertEqual(handoff.get("self_confidence"), 0.92)

    def test_runtime_verification_handoff_falls_back_when_llm_output_is_invalid(self):
        provider = MockModelProvider(
            scripted_outputs=[
                {
                    "content": "接口文档已更新",
                    "raw": {
                        "choices": [
                            {
                                "finish_reason": "stop",
                                "message": {"role": "assistant", "content": "接口文档已更新"},
                            }
                        ]
                    },
                },
                {
                    "content": "not-json",
                    "raw": {"mock": True},
                },
            ]
        )

        class _CaptureOrchestrator:
            def __init__(self):
                self.last_run_outcome = None

            def evaluate(self, run_outcome):
                self.last_run_outcome = run_outcome
                return RunJudgement(
                    self_reported_success=True,
                    verified_success=True,
                    final_status="pass",
                    failure_type=None,
                    overclaim=False,
                    confidence=0.8,
                    verifier_breakdown=[],
                )

        orchestrator = _CaptureOrchestrator()
        runtime = AgentRuntime(
            model_provider=provider,
            tool_registry=ToolRegistry(),
            max_steps=2,
            eval_orchestrator=orchestrator,
            enable_verification_handoff_llm=True,
        )
        runtime.run("请更新接口文档", task_id="runtime_eval_task_handoff_fallback", run_id="runtime_eval_run_handoff_fallback")

        handoff = orchestrator.last_run_outcome.verification_handoff
        self.assertEqual(handoff.get("goal"), "请更新接口文档")
        self.assertEqual(handoff.get("constraints"), [])
        self.assertEqual(handoff.get("expected_artifacts"), [])
        self.assertEqual(handoff.get("claimed_done_items"), ["接口文档已更新"])
        self.assertEqual(handoff.get("soft_score_threshold"), 0.7)

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
                    "content": '{"selected":[{"id":"mem_high_1","score":0.91,"reason":"payment retry semantic match"}]}',
                    "raw": {"mock": True},
                },
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
                    "recall_hint": "支付重试前先校验幂等键",
                    "retrieval_score": 0.88,
                },
                {
                    "id": "mem_low_1",
                    "title": "低相关卡片",
                    "retrieval_score": 0.4,
                },
            ]
            runtime = AgentRuntime(
                model_provider=provider,
                tool_registry=ToolRegistry(),
                max_steps=2,
                enable_memory_recall_reranker=True,
            )
            result = runtime.run("请执行支付重试逻辑检查", task_id="runtime_mem_task", run_id="runtime_mem_run")

        self.assertEqual(result, "任务正常完成")
        self.assertTrue(provider.requests)
        joined = ""
        for req in provider.requests:
            msgs = req.get("messages", [])
            system_blocks = [m.get("content", "") for m in msgs if m.get("role") == "system"]
            text = "\n".join([str(x) for x in system_blocks])
            if "系统记忆召回" in text:
                joined = text
                break
        self.assertIn("系统记忆召回", joined)
        self.assertIn("memory_id=mem_high_1", joined)
        self.assertIn("recall_hint=支付重试前先校验幂等键", joined)
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

    def test_runtime_finalize_uses_llm_generated_memory_metadata_when_enabled(self):
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
                },
                {
                    "content": '{"title":"发布检查失败回滚前先校验依赖状态","recall_hint":"问题：发布前依赖状态不一致导致流程中断；适用：涉及多服务联动发布；动作：先校验依赖健康再执行发布；风险：跳过前置检查会触发连锁回滚。"}',
                    "raw": {"mock": True},
                },
            ]
        )

        with patch("app.core.runtime.agent_runtime.SystemMemoryStore") as mock_store_cls:
            mock_store = mock_store_cls.return_value
            runtime = AgentRuntime(
                model_provider=provider,
                tool_registry=ToolRegistry(),
                max_steps=2,
                enable_memory_card_metadata_llm=True,
            )
            runtime.run("请做上线前发布检查", task_id="runtime_pre_release_task", run_id="runtime_pre_release_run")

        upsert_card = mock_store.upsert_card.call_args.args[0]
        self.assertEqual(upsert_card.get("title"), "发布检查失败回滚前先校验依赖状态")
        self.assertIn("适用：涉及多服务联动发布", str(upsert_card.get("recall_hint", "")))

    def test_runtime_finalize_falls_back_when_llm_metadata_is_invalid(self):
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
                },
                {
                    "content": "not-json",
                    "raw": {"mock": True},
                },
            ]
        )

        with patch("app.core.runtime.agent_runtime.SystemMemoryStore") as mock_store_cls:
            mock_store = mock_store_cls.return_value
            runtime = AgentRuntime(
                model_provider=provider,
                tool_registry=ToolRegistry(),
                max_steps=2,
                enable_memory_card_metadata_llm=True,
            )
            runtime.run("请做上线前发布检查", task_id="runtime_pre_release_task", run_id="runtime_pre_release_run")

        upsert_card = mock_store.upsert_card.call_args.args[0]
        self.assertIn("复用策略", str(upsert_card.get("title", "")))
        self.assertIn("任务结束状态", str(upsert_card.get("recall_hint", "")))

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
        started = [e for e in captured if e.get("event_type") == "verification_started"]
        self.assertEqual(len(started), 1)
        self.assertEqual(started[0].get("payload", {}).get("handoff_source"), "fallback_rule")
        judged = [e for e in captured if e.get("event_type") == "task_judged"]
        self.assertEqual(len(judged), 1)
        payload = judged[0].get("payload", {})
        self.assertEqual(payload.get("verified_success"), True)
        self.assertEqual(payload.get("final_status"), "pass")
        self.assertEqual(payload.get("verification_handoff_source"), "fallback_rule")
        handoff = payload.get("verification_handoff", {})
        self.assertIsInstance(handoff, dict)
        self.assertEqual(handoff.get("goal"), "verification case")
        self.assertEqual(handoff.get("claimed_done_items"), ["任务已完成"])

    def test_runtime_emits_handoff_source_llm_when_llm_generation_is_used(self):
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
                    "content": '{"goal":"测试任务","constraints":[],"expected_artifacts":[],"claimed_done_items":["任务已完成"],"key_tool_results":[],"known_gaps":[],"self_confidence":0.9,"soft_score_threshold":0.7,"rubric":"评估任务完成度、约束满足度、证据充分性。"}',
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
                enable_verification_handoff_llm=True,
            )
            runtime.run("llm handoff source case", task_id="runtime_eval_task_handoff_source", run_id="runtime_eval_run_handoff_source")

        started = [e for e in captured if e.get("event_type") == "verification_started"]
        self.assertEqual(len(started), 1)
        self.assertEqual(started[0].get("payload", {}).get("handoff_source"), "llm")
        judged = [e for e in captured if e.get("event_type") == "task_judged"]
        self.assertEqual(len(judged), 1)
        self.assertEqual(judged[0].get("payload", {}).get("verification_handoff_source"), "llm")
        handoff = judged[0].get("payload", {}).get("verification_handoff", {})
        self.assertIsInstance(handoff, dict)
        self.assertEqual(handoff.get("goal"), "测试任务")

    def test_runtime_builds_verification_handoff_before_task_finished_event(self):
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
        sequence = []

        def _capture_emit_event(*args, **kwargs):
            sequence.append(str(kwargs.get("event_type", "")))
            return {}

        runtime = AgentRuntime(model_provider=provider, tool_registry=ToolRegistry(), max_steps=2)
        original_build = runtime._build_verification_handoff

        def _wrapped_build(*args, **kwargs):
            sequence.append("handoff_built")
            return original_build(*args, **kwargs)

        with patch("app.core.runtime.agent_runtime.emit_event", side_effect=_capture_emit_event):
            with patch.object(runtime, "_build_verification_handoff", side_effect=_wrapped_build):
                runtime.run("step handoff case", task_id="runtime_eval_task_handoff_step", run_id="runtime_eval_run_handoff_step")

        self.assertIn("handoff_built", sequence)
        self.assertIn("task_finished", sequence)
        self.assertLess(sequence.index("handoff_built"), sequence.index("task_finished"))

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
