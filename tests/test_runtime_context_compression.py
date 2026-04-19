import json
import tempfile
import unittest
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import patch

from app.config.runtime_config import RuntimeCompressionConfig, load_runtime_compression_config
from app.core.memory.compressor_factory import build_context_compressor
from app.core.memory.context_compressor import ContextCompressor
from app.core.memory.llm_context_compressor import LLMContextCompressor
from app.core.memory.sqlite_memory_store import SQLiteMemoryStore
from app.core.model.mock_provider import MockModelProvider
from app.core.runtime.agent_runtime import AgentRuntime
from app.core.runtime.runtime_compaction_policy import finalize_memory_compaction
from app.core.runtime.task_token_store import TaskTokenStore
from app.core.tools.registry import ToolRegistry, ToolSpec
from app.core.runtime.runtime_compaction_policy import maybe_compact_mid_run


class _InMemoryStore:
    def __init__(self):
        self.rows: List[Dict[str, Any]] = []
        self.compact_mid_run_calls = 0
        self.compact_final_calls = 0

    def append_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        tool_call_id: str = "",
        tool_calls: Optional[List[Dict[str, Any]]] = None,
        run_id: str = "",
        step_id: str = "",
    ) -> None:
        self.rows.append(
            {
                "conversation_id": conversation_id,
                "role": role,
                "content": content,
                "tool_call_id": tool_call_id,
                "tool_calls": tool_calls or [],
                "run_id": run_id,
                "step_id": step_id,
            }
        )

    def get_recent_messages(self, conversation_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        scoped = [x for x in self.rows if x["conversation_id"] == conversation_id]
        scoped = scoped[-max(limit, 1):]
        out: List[Dict[str, Any]] = []
        for row in scoped:
            role = row["role"]
            if role == "assistant":
                item: Dict[str, Any] = {"role": role, "content": row["content"]}
                if row["tool_calls"]:
                    item["tool_calls"] = row["tool_calls"]
                out.append(item)
            elif role == "tool":
                out.append(
                    {
                        "role": "tool",
                        "content": row["content"],
                        "tool_call_id": row["tool_call_id"],
                    }
                )
            else:
                out.append({"role": role, "content": row["content"]})
        return out

    def compact(self, conversation_id: str) -> None:
        return None

    def compact_mid_run(self, conversation_id: str, trigger: str = "round", mode: str = "") -> Dict[str, Any]:
        self.compact_mid_run_calls += 1
        return {"success": True, "applied": False, "trigger": trigger, "mode": mode}

    def compact_final(self, conversation_id: str) -> Dict[str, Any]:
        self.compact_final_calls += 1
        return {"success": True, "applied": False}

    def build_compaction_observability_payload(self, mode: str, token_budget: int | None = None) -> Dict[str, Any]:
        return {
            "budget_split_kind": "live_plus_summary",
            "live_keep_ratio": 0.20,
            "summary_keep_ratio": 0.25,
            "total_keep_ratio": 0.45,
            "target_keep_tokens": 24,
            "live_budget_tokens": 24,
            "summary_budget_tokens": 30,
            "compaction_budget_total_tokens": 54,
        }


class RuntimeContextCompressionTests(unittest.TestCase):
    def test_runtime_compression_config_loads_dual_window_defaults(self):
        with patch.dict(os.environ, {}, clear=True):
            config = load_runtime_compression_config()
        self.assertEqual(config.model_context_window_tokens, 160000)
        self.assertEqual(config.compression_trigger_window_tokens, 120000)
        self.assertEqual(config.context_window_tokens, 120000)
        self.assertEqual(config.target_keep_ratio_midrun, 0.45)
        self.assertEqual(config.target_keep_ratio_finalize, 0.45)
        self.assertFalse(config.enable_finalize_compaction)

    def test_runtime_compression_config_falls_back_to_legacy_context_window(self):
        with patch.dict(os.environ, {"COMPACTION_CONTEXT_WINDOW_TOKENS": "64000"}, clear=True):
            config = load_runtime_compression_config()
        self.assertEqual(config.model_context_window_tokens, 64000)
        self.assertEqual(config.compression_trigger_window_tokens, 64000)
        self.assertEqual(config.context_window_tokens, 64000)

    def test_finalize_memory_compaction_skips_compact_final_when_disabled(self):
        store = _InMemoryStore()
        finalize_memory_compaction(
            task_id="task_finalize_off",
            final_answer="done",
            final_answer_written=False,
            memory_store=store,
            enable_finalize_compaction=False,
        )
        self.assertEqual(store.compact_final_calls, 0)
        self.assertEqual(len(store.rows), 1)
        self.assertEqual(store.rows[0]["content"], "done")

    def test_finalize_memory_compaction_calls_compact_final_when_enabled(self):
        store = _InMemoryStore()
        finalize_memory_compaction(
            task_id="task_finalize_on",
            final_answer="done",
            final_answer_written=False,
            memory_store=store,
            enable_finalize_compaction=True,
        )
        self.assertEqual(store.compact_final_calls, 1)

    def test_agent_runtime_estimate_context_usage_uses_trigger_window(self):
        provider = MockModelProvider(scripted_outputs=[])
        runtime = AgentRuntime(
            model_provider=provider,
            tool_registry=ToolRegistry(),
            compression_config=RuntimeCompressionConfig(
                enabled_mid_run=True,
                round_interval=4,
                midrun_token_ratio=0.82,
                model_context_window_tokens=160000,
                compression_trigger_window_tokens=1000,
                keep_recent_turns=8,
                tool_burst_threshold=5,
                consistency_guard=True,
                enable_finalize_compaction=False,
                target_keep_ratio_midrun=0.40,
                target_keep_ratio_finalize=0.40,
                min_keep_turns=3,
                compressor_kind="auto",
                compressor_llm_max_tokens=800,
                event_summarizer_kind="auto",
                event_summarizer_max_tokens=280,
            ),
            enable_llm_judge=False,
        )
        self.assertAlmostEqual(runtime._estimate_context_usage(500), 500 / 1024)

    def test_sqlite_memory_store_persists_run_id_and_step_id_and_writes_source_anchor(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = str(Path(td) / "runtime_memory_anchor.db")
            store = SQLiteMemoryStore(
                db_file=db_path,
                summarize_threshold=3,
                context_window_tokens=120,
                target_keep_ratio_finalize=0.3,
                min_keep_turns=1,
            )
            task_id = "anchor_task"
            store.append_message(task_id, "system", "必须遵守审批流程", run_id="run_1", step_id="1")
            store.append_message(task_id, "user", "请完成任务A", run_id="run_1", step_id="1")
            store.append_message(task_id, "assistant", "先读取文件", run_id="run_1", step_id="1")
            store.append_message(task_id, "tool", "{\"success\": true}", tool_call_id="call_1", run_id="run_1", step_id="1")
            store.append_message(task_id, "assistant", "已经修改完成", run_id="run_1", step_id="2")
            store.append_message(task_id, "assistant", "准备验证", run_id="run_1", step_id="2")

            recalled = store.get_messages_for_run_step(task_id, "run_1", "1")
            self.assertEqual(len(recalled), 4)
            self.assertEqual(recalled[0]["run_id"], "run_1")
            self.assertEqual(recalled[0]["step_id"], "1")

            result = store.compact_final(task_id)
            self.assertTrue(bool(result.get("success")))
            self.assertTrue(bool(result.get("applied")))

            with store._connect() as conn:
                row = conn.execute(
                    "SELECT summary_json FROM summaries WHERE conversation_id = ?",
                    (task_id,),
                ).fetchone()
            self.assertIsNotNone(row)
            summary = json.loads(row[0])
            decisions = summary.get("decisions") or []
            constraints = summary.get("constraints") or []
            artifacts = summary.get("artifacts") or []
            anchored_items = decisions + constraints + artifacts
            self.assertTrue(any((item.get("source_anchor") or {}).get("step_id") == "1" for item in anchored_items))
            self.assertTrue(any((item.get("source_anchor") or {}).get("run_id") == "run_1" for item in anchored_items))

    def test_compressor_factory_auto_falls_back_to_rule_for_mock_provider(self):
        provider = MockModelProvider(scripted_outputs=[])
        compressor = build_context_compressor(kind="auto", model_provider=provider, llm_max_tokens=800)
        self.assertIsInstance(compressor, ContextCompressor)
        self.assertNotIsInstance(compressor, LLMContextCompressor)

    def test_llm_compressor_writes_summary_json_from_model_output(self):
        provider = MockModelProvider(
            scripted_outputs=[
                json.dumps(
                    {
                        "version": "v1_llm",
                        "task_state": {
                            "goal": "完成任务A",
                            "progress": "已读取文件并完成修改",
                            "next_step": "运行验证",
                            "completion": 0.8,
                        },
                        "decisions": [{"id": "d_1", "what": "先读文件再修改", "why": "降低风险", "turn": 1, "confidence": "high"}],
                        "constraints": [{"id": "c_1", "rule": "必须遵守审批流程", "source": "system", "immutable": True}],
                        "artifacts": [{"id": "a_1", "type": "file", "ref": "work/a.py", "summary": "已完成修改", "turn": 1}],
                        "open_questions": [],
                    }
                )
            ]
        )
        compressor = LLMContextCompressor(model_provider=provider, max_tokens=800)
        with tempfile.TemporaryDirectory() as td:
            db_path = str(Path(td) / "runtime_memory_llm.db")
            store = SQLiteMemoryStore(
                db_file=db_path,
                summarize_threshold=3,
                context_window_tokens=120,
                target_keep_ratio_finalize=0.3,
                min_keep_turns=1,
                compressor=compressor,
            )
            task_id = "llm_compress_task"
            store.append_message(task_id, "system", "必须遵守审批流程")
            store.append_message(task_id, "user", "请完成任务A")
            store.append_message(task_id, "assistant", "先读取文件")
            store.append_message(task_id, "assistant", "已经修改完成")

            result = store.compact_final(task_id)
            self.assertTrue(bool(result.get("success")))
            self.assertTrue(bool(result.get("applied")))

            with store._connect() as conn:
                row = conn.execute(
                    "SELECT schema_version, summary_json FROM summaries WHERE conversation_id = ?",
                    (task_id,),
                ).fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row[0], "v1_llm")
            summary = json.loads(row[1])
            self.assertEqual(summary.get("version"), "v1_llm")
            self.assertEqual(summary.get("task_state", {}).get("next_step"), "运行验证")
            self.assertEqual(summary.get("compression_meta", {}).get("compressor_kind_applied"), "llm")

    def test_llm_compressor_falls_back_to_rule_on_invalid_json(self):
        provider = MockModelProvider(scripted_outputs=["not-json"])
        compressor = LLMContextCompressor(model_provider=provider, max_tokens=800)
        with tempfile.TemporaryDirectory() as td:
            db_path = str(Path(td) / "runtime_memory_llm_fallback.db")
            store = SQLiteMemoryStore(
                db_file=db_path,
                summarize_threshold=3,
                context_window_tokens=120,
                target_keep_ratio_finalize=0.3,
                min_keep_turns=1,
                compressor=compressor,
            )
            task_id = "llm_fallback_task"
            store.append_message(task_id, "system", "必须遵守审批流程")
            store.append_message(task_id, "user", "请完成任务A")
            store.append_message(task_id, "assistant", "先读取文件")
            store.append_message(task_id, "assistant", "已经修改完成")

            result = store.compact_final(task_id)
            self.assertTrue(bool(result.get("success")))
            self.assertTrue(bool(result.get("applied")))

            with store._connect() as conn:
                row = conn.execute(
                    "SELECT schema_version, summary_json FROM summaries WHERE conversation_id = ?",
                    (task_id,),
                ).fetchone()
            self.assertIsNotNone(row)
            summary = json.loads(row[1])
            self.assertEqual(row[0], "v1")
            self.assertEqual(summary.get("compression_meta", {}).get("compressor_kind_applied"), "rule")
            self.assertTrue(bool(summary.get("compression_meta", {}).get("compressor_fallback_used")))

    def test_llm_compressor_falls_back_to_rule_on_consistency_failure(self):
        provider = MockModelProvider(
            scripted_outputs=[
                json.dumps(
                    {
                        "version": "v1_llm",
                        "task_state": {"goal": "请完成任务A", "progress": "已完成", "next_step": "准备收尾", "completion": 1.0},
                        "decisions": [],
                        "constraints": [],
                        "artifacts": [],
                        "open_questions": [],
                    }
                )
            ]
        )
        compressor = LLMContextCompressor(model_provider=provider, max_tokens=800)
        with tempfile.TemporaryDirectory() as td:
            db_path = str(Path(td) / "runtime_memory_llm_consistency.db")
            store = SQLiteMemoryStore(
                db_file=db_path,
                summarize_threshold=3,
                context_window_tokens=120,
                target_keep_ratio_finalize=0.3,
                min_keep_turns=1,
                compressor=compressor,
            )
            task_id = "llm_consistency_task"
            store.append_message(task_id, "user", "请完成任务A " + ("a " * 80))
            store.append_message(task_id, "assistant", "处理中 " + ("b " * 80))
            store.append_message(task_id, "assistant", "阶段一完成 " + ("c " * 80))
            store.append_message(task_id, "user", "继续收尾 " + ("d " * 80))
            store.append_message(task_id, "assistant", "已经修改完成 " + ("e " * 80))
            store.append_message(task_id, "assistant", "准备收尾 " + ("f " * 80))
            with store._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO summaries (conversation_id, summary, schema_version, summary_json, last_anchor_msg_id, updated_at)
                    VALUES (?, ?, ?, ?, ?, datetime('now','localtime'))
                    """,
                    (
                        task_id,
                        "历史摘要",
                        "v1",
                        json.dumps(
                            {
                                "version": "v1",
                                "task_state": {"goal": "请完成任务A", "progress": "", "next_step": "", "completion": 0.0},
                                "decisions": [],
                                "constraints": [
                                    {
                                        "id": "c_1",
                                        "rule": "必须遵守审批流程",
                                        "source": "system",
                                        "immutable": True,
                                    }
                                ],
                                "artifacts": [],
                                "open_questions": [],
                            },
                            ensure_ascii=False,
                        ),
                        0,
                    ),
                )
                conn.commit()

            result = store.compact_final(task_id)
            self.assertTrue(bool(result.get("success")))
            self.assertTrue(bool(result.get("applied")))
            self.assertEqual(result.get("compressor_kind_applied"), "rule")
            self.assertTrue(bool(result.get("compressor_fallback_used")))

    def test_get_recent_messages_filters_orphan_tool_message(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = str(Path(td) / "runtime_memory_orphan.db")
            store = SQLiteMemoryStore(db_file=db_path, keep_recent=2, summarize_threshold=3)
            task_id = "orphan_task"

            store.append_message(task_id, "tool", "{\"success\": true}", tool_call_id="call_orphan")
            store.append_message(
                task_id,
                "assistant",
                "",
                tool_calls=[
                    {
                        "id": "call_ok",
                        "type": "function",
                        "function": {"name": "echo", "arguments": "{\"text\":\"ok\"}"},
                    }
                ],
            )
            store.append_message(task_id, "tool", "{\"success\": true}", tool_call_id="call_ok")

            recent = store.get_recent_messages(task_id, limit=20)
            tool_call_ids = [str(m.get("tool_call_id", "")) for m in recent if m.get("role") == "tool"]
            self.assertIn("call_ok", tool_call_ids)
            self.assertNotIn("call_orphan", tool_call_ids)

    def test_compact_final_keeps_recent_assistant_turns_together(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = str(Path(td) / "runtime_memory_turns.db")
            store = SQLiteMemoryStore(
                db_file=db_path,
                keep_recent=2,
                summarize_threshold=3,
                context_window_tokens=120,
                target_keep_ratio_finalize=0.35,
                min_keep_turns=2,
            )
            task_id = "turn_task"

            store.append_message(
                task_id,
                "assistant",
                "plan_a " + ("x " * 60),
                tool_calls=[
                    {
                        "id": "call_a",
                        "type": "function",
                        "function": {"name": "echo", "arguments": "{\"text\":\"a\"}"},
                    }
                ],
            )
            store.append_message(task_id, "tool", "{\"success\": true, \"data\": \"" + ("x" * 120) + "\"}", tool_call_id="call_a")
            store.append_message(
                task_id,
                "assistant",
                "plan_b " + ("y " * 60),
                tool_calls=[
                    {
                        "id": "call_b",
                        "type": "function",
                        "function": {"name": "echo", "arguments": "{\"text\":\"b\"}"},
                    }
                ],
            )
            store.append_message(task_id, "tool", "{\"success\": true, \"data\": \"" + ("y" * 120) + "\"}", tool_call_id="call_b")
            store.append_message(task_id, "assistant", "done " + ("z " * 20))

            result = store.compact_final(task_id)
            self.assertTrue(bool(result.get("success")))
            self.assertTrue(bool(result.get("applied")))

            with store._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT role, content, tool_call_id, tool_calls_json
                    FROM messages
                    WHERE conversation_id = ?
                    ORDER BY id ASC
                    """,
                    (task_id,),
                ).fetchall()

            self.assertEqual(len(rows), 3)
            self.assertEqual(rows[0][0], "assistant")
            self.assertIsNotNone(rows[0][3])  # tool_calls_json of the kept assistant turn
            self.assertEqual(rows[1][0], "tool")
            self.assertEqual(rows[1][2], "call_b")
            self.assertEqual(rows[2][0], "assistant")

            recent = store.get_recent_messages(task_id, limit=20)
            for msg in recent:
                if msg.get("role") != "tool":
                    continue
                call_id = str(msg.get("tool_call_id", "")).strip()
                matched = False
                for a in recent:
                    if a.get("role") != "assistant":
                        continue
                    for call in a.get("tool_calls", []) or []:
                        if str(call.get("id", "")).strip() == call_id:
                            matched = True
                            break
                    if matched:
                        break
                self.assertTrue(matched)

    def test_sqlite_memory_store_compact_writes_structured_summary(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = str(Path(td) / "runtime_memory.db")
            store = SQLiteMemoryStore(
                db_file=db_path,
                keep_recent=2,
                summarize_threshold=3,
                context_window_tokens=120,
                target_keep_ratio_finalize=0.3,
                min_keep_turns=1,
            )
            task_id = "compress_task"

            store.append_message(task_id, "system", "必须遵守审批流程")
            store.append_message(task_id, "user", "请完成任务A")
            store.append_message(task_id, "assistant", "计划先读取文件")
            store.append_message(task_id, "tool", "{\"success\": true}", tool_call_id="call_1")
            store.append_message(task_id, "assistant", "任务完成")

            result = store.compact_final(task_id)
            self.assertTrue(result.get("success"))
            self.assertTrue(result.get("applied"))
            self.assertGreaterEqual(int(result.get("immutable_constraints_count") or 0), 1)
            self.assertGreaterEqual(int(result.get("immutable_hits_count") or 0), 1)

            with store._connect() as conn:
                row = conn.execute(
                    "SELECT schema_version, summary_json FROM summaries WHERE conversation_id = ?",
                    (task_id,),
                ).fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row[0], "v1")
            summary = json.loads(row[1])
            self.assertEqual(summary.get("version"), "v1")
            self.assertNotIn("anchors", summary)

            recent = store.get_recent_messages(task_id, limit=20)
            self.assertTrue(recent)
            self.assertEqual(recent[0].get("role"), "system")
            self.assertIn("结构化历史摘要", str(recent[0].get("content", "")))

    def test_compact_final_uses_latest_turns_for_token_budget(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = str(Path(td) / "runtime_memory_turn_budget.db")
            store = SQLiteMemoryStore(
                db_file=db_path,
                summarize_threshold=3,
                context_window_tokens=120,
                target_keep_ratio_finalize=0.35,
                min_keep_turns=1,
            )
            task_id = "turn_budget_task"

            store.append_message(task_id, "user", "turn1 " + ("a " * 80))
            store.append_message(task_id, "assistant", "ack1 " + ("b " * 20))
            store.append_message(task_id, "user", "turn2 " + ("c " * 80))
            store.append_message(task_id, "assistant", "ack2 " + ("d " * 20))
            store.append_message(task_id, "user", "turn3 latest " + ("e " * 80))
            store.append_message(task_id, "assistant", "ack3 " + ("f " * 20))

            result = store.compact_final(task_id)
            self.assertTrue(bool(result.get("success")))
            self.assertTrue(bool(result.get("applied")))
            self.assertEqual(result.get("trim_strategy"), "token_budget")

            with store._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT role, content FROM messages
                    WHERE conversation_id = ?
                    ORDER BY id ASC
                    """,
                    (task_id,),
                ).fetchall()
            self.assertTrue(rows)
            self.assertIn("turn3 latest", rows[0][1])

    def test_compact_final_keeps_at_least_min_keep_turns(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = str(Path(td) / "runtime_memory_turn_guard.db")
            store = SQLiteMemoryStore(
                db_file=db_path,
                summarize_threshold=3,
                context_window_tokens=120,
                target_keep_ratio_finalize=0.05,
                min_keep_turns=3,
            )
            task_id = "turn_guard_task"

            store.append_message(task_id, "user", "turn1 " + ("a " * 40))
            store.append_message(task_id, "assistant", "ack1 " + ("b " * 20))
            store.append_message(task_id, "user", "turn2 " + ("c " * 40))
            store.append_message(task_id, "assistant", "ack2 " + ("d " * 20))
            store.append_message(task_id, "user", "turn3 " + ("e " * 40))
            store.append_message(task_id, "assistant", "ack3 " + ("f " * 20))
            store.append_message(task_id, "user", "turn4 latest " + ("g " * 40))
            store.append_message(task_id, "assistant", "ack4 " + ("h " * 20))

            result = store.compact_final(task_id)
            self.assertTrue(bool(result.get("success")))
            self.assertTrue(bool(result.get("applied")))
            self.assertEqual(result.get("cut_adjustment_reason"), "min_keep_guard")

            with store._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT role, content
                    FROM messages
                    WHERE conversation_id = ?
                    ORDER BY id ASC
                    """,
                    (task_id,),
                ).fetchall()

            self.assertEqual(len(rows), 6)
            self.assertIn("turn2", rows[0][1])
            self.assertIn("turn4 latest", rows[-2][1])

    def test_compact_final_prefers_step_budget_when_step_tokens_available(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = str(Path(td) / "runtime_memory_step_budget.db")
            token_db_path = str(Path(td) / "task_token_ledger.db")
            token_store = TaskTokenStore(db_file=token_db_path)
            store = SQLiteMemoryStore(
                db_file=db_path,
                summarize_threshold=3,
                context_window_tokens=120,
                target_keep_ratio_finalize=0.45,
                min_keep_turns=1,
                task_token_store=token_store,
            )
            task_id = "step_budget_task"
            run_id = "run_step_budget"

            for step in range(1, 5):
                token_store.record_step_metrics(
                    task_id=task_id,
                    run_id=run_id,
                    step=step,
                    metrics={
                        "model": "gpt-4-turbo",
                        "encoding": "cl100k_base",
                        "token_counter_kind": "tiktoken",
                        "messages_tokens": 100,
                        "tools_tokens": 0,
                        "step_input_tokens": 8,
                        "input_tokens": 100,
                        "reserved_output_tokens": 0,
                        "total_window_claim_tokens": 100,
                        "context_usage_ratio": 0.1,
                        "compression_trigger_window_tokens": 120,
                        "model_context_window_tokens": 160000,
                    },
                )
                store.append_message(
                    task_id,
                    "user",
                    f"step{step} user " + ("x " * 80),
                    run_id=run_id,
                    step_id=str(step),
                )
                store.append_message(
                    task_id,
                    "assistant",
                    f"step{step} assistant " + ("y " * 80),
                    run_id=run_id,
                    step_id=str(step),
                )

            result = store.compact_final(task_id)
            self.assertTrue(bool(result.get("success")))
            self.assertTrue(bool(result.get("applied")))
            self.assertEqual(result.get("cut_adjustment_reason"), "step_budget")
            self.assertEqual(result.get("target_keep_tokens"), 24)
            self.assertEqual(result.get("summary_budget_tokens"), 30)

            with store._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT role, content, run_id, step_id
                    FROM messages
                    WHERE conversation_id = ?
                    ORDER BY id ASC
                    """,
                    (task_id,),
                ).fetchall()
            self.assertEqual(len(rows), 6)
            self.assertEqual(str(rows[0][3]), "2")
            self.assertEqual(str(rows[-1][3]), "4")

    def test_compact_final_bounds_summary_to_summary_budget(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = str(Path(td) / "runtime_memory_summary_budget.db")
            store = SQLiteMemoryStore(
                db_file=db_path,
                summarize_threshold=3,
                context_window_tokens=1200,
                target_keep_ratio_finalize=0.45,
                min_keep_turns=1,
            )
            task_id = "summary_budget_task"

            for idx in range(1, 9):
                store.append_message(task_id, "system", f"必须遵守审批流程 {idx} " + ("s " * 40))
                store.append_message(task_id, "user", f"question {idx}? " + ("u " * 40))
                store.append_message(task_id, "assistant", f"answer {idx} " + ("a " * 40))
                store.append_message(task_id, "tool", "{\"success\": true, \"payload\": \"" + ("x" * 200) + "\"}")

            result = store.compact_final(task_id)
            self.assertTrue(bool(result.get("success")))
            self.assertTrue(bool(result.get("applied")))

            with store._connect() as conn:
                row = conn.execute(
                    "SELECT summary_json FROM summaries WHERE conversation_id = ?",
                    (task_id,),
                ).fetchone()
            self.assertIsNotNone(row)
            summary = json.loads(row[0])
            self.assertLessEqual(
                store._estimate_summary_tokens(summary),
                int(result.get("summary_budget_tokens") or 0),
            )

    def test_event_compaction_replaces_tool_chain_without_summary(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = str(Path(td) / "runtime_memory_event_replace.db")
            store = SQLiteMemoryStore(
                db_file=db_path,
                summarize_threshold=3,
                context_window_tokens=16000,
                min_keep_turns=1,
                keep_recent_event_tool_pairs=0,
            )
            task_id = "event_replace_task"

            store.append_message(task_id, "user", "帮我处理这个任务")
            store.append_message(
                task_id,
                "assistant",
                "",
                tool_calls=[
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "read_file", "arguments": "{\"path\":\"a.txt\"}"},
                    }
                ],
            )
            store.append_message(task_id, "tool", "{\"success\": true, \"content\": \"A\"}", tool_call_id="call_1")
            store.append_message(
                task_id,
                "assistant",
                "",
                tool_calls=[
                    {
                        "id": "call_2",
                        "type": "function",
                        "function": {"name": "write_file", "arguments": "{\"path\":\"b.txt\"}"},
                    }
                ],
            )
            store.append_message(task_id, "tool", "{\"success\": false, \"error\": \"permission denied\"}", tool_call_id="call_2")

            result = store.compact_mid_run(task_id, trigger="event", mode="event")
            self.assertTrue(bool(result.get("success")))
            self.assertTrue(bool(result.get("applied")))
            self.assertEqual(result.get("trim_strategy"), "tool_chain_replace")

            with store._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT role, content, tool_call_id, tool_calls_json
                    FROM messages
                    WHERE conversation_id = ?
                    ORDER BY id ASC
                    """,
                    (task_id,),
                ).fetchall()
                summary_row = conn.execute(
                    "SELECT summary_json FROM summaries WHERE conversation_id = ?",
                    (task_id,),
                ).fetchone()

            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0][0], "user")
            self.assertEqual(rows[1][0], "assistant")
            self.assertIn("[tool-chain-compact]", str(rows[1][1]))
            self.assertIsNone(summary_row)

    def test_event_compaction_skips_stateful_tool_units(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = str(Path(td) / "runtime_memory_event_stateful.db")
            store = SQLiteMemoryStore(
                db_file=db_path,
                summarize_threshold=3,
                keep_recent_event_tool_pairs=0,
            )
            task_id = "event_stateful_task"
            store.append_message(task_id, "user", "创建并推进 todo")
            store.append_message(
                task_id,
                "assistant",
                "",
                tool_calls=[
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "plan_task", "arguments": "{\"task_name\":\"x\"}"},
                    }
                ],
            )
            store.append_message(
                task_id,
                "tool",
                "{\"success\": true, \"result\": {\"todo_id\": \"todo_123\"}}",
                tool_call_id="call_1",
            )

            result = store.compact_mid_run(task_id, trigger="event", mode="event")
            self.assertTrue(bool(result.get("success")))
            self.assertFalse(bool(result.get("applied")))
            self.assertIn(str(result.get("reason")), {"no_eligible_tool_chain", "below_threshold", "nothing_to_cut"})

    def test_event_compaction_uses_llm_summary_with_mini_model_override(self):
        provider = MockModelProvider(
            scripted_outputs=[
                json.dumps(
                    {
                        "summary": "读取了两个关键文件并尝试执行测试，测试失败暴露出压缩链路中的回归点。",
                        "key_results": [
                            "定位到 runtime 与 memory compaction 两个核心实现位置",
                            "测试执行失败并返回具体错误摘要",
                        ],
                        "failures": ["1 failed, 12 passed"],
                    }
                )
            ]
        )
        with tempfile.TemporaryDirectory() as td:
            db_path = str(Path(td) / "runtime_memory_event_llm.db")
            with patch("app.core.memory.llm_tool_chain_summarizer.load_runtime_model_config") as mock_cfg:
                mock_cfg.return_value = type("Cfg", (), {"mini_model_id": "mini-test-model"})()
                store = SQLiteMemoryStore(
                    db_file=db_path,
                    summarize_threshold=3,
                    keep_recent_event_tool_pairs=0,
                    event_summarizer_kind="llm",
                    event_summarizer_max_tokens=180,
                    event_summarizer_model_provider=provider,
                )
                task_id = "event_llm_task"
                store.append_message(task_id, "user", "帮我处理这个任务")
                store.append_message(
                    task_id,
                    "assistant",
                    "",
                    tool_calls=[
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {"name": "read_file", "arguments": "{\"path\":\"a.txt\"}"},
                        }
                    ],
                )
                store.append_message(task_id, "tool", "{\"success\": true, \"content\": \"A\"}", tool_call_id="call_1")
                store.append_message(
                    task_id,
                    "assistant",
                    "",
                    tool_calls=[
                        {
                            "id": "call_2",
                            "type": "function",
                            "function": {"name": "bash", "arguments": "{\"command\":\"pytest\"}"},
                        }
                    ],
                )
                store.append_message(task_id, "tool", "{\"success\": false, \"error\": \"1 failed, 12 passed\"}", tool_call_id="call_2")

                result = store.compact_mid_run(task_id, trigger="event", mode="event")
                self.assertTrue(bool(result.get("success")))
                self.assertTrue(bool(result.get("applied")))
                self.assertEqual(result.get("tool_chain_summary_applied"), "llm")
                self.assertEqual(result.get("tool_chain_summary_model"), "mini-test-model")

                with store._connect() as conn:
                    rows = conn.execute(
                        """
                        SELECT role, content
                        FROM messages
                        WHERE conversation_id = ?
                        ORDER BY id ASC
                        """,
                        (task_id,),
                    ).fetchall()

                self.assertIn("读取了两个关键文件并尝试执行测试", str(rows[1][1]))
                cfg = provider.requests[-1]["config"]
                self.assertEqual(str(cfg.provider_options.get("model")), "mini-test-model")

    def test_event_compaction_falls_back_to_rule_on_invalid_llm_json(self):
        provider = MockModelProvider(scripted_outputs=["not-json"])
        with tempfile.TemporaryDirectory() as td:
            db_path = str(Path(td) / "runtime_memory_event_llm_fallback.db")
            store = SQLiteMemoryStore(
                db_file=db_path,
                summarize_threshold=3,
                keep_recent_event_tool_pairs=0,
                event_summarizer_kind="llm",
                event_summarizer_model_provider=provider,
            )
            task_id = "event_llm_fallback_task"
            store.append_message(task_id, "user", "帮我处理这个任务")
            store.append_message(
                task_id,
                "assistant",
                "",
                tool_calls=[
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "read_file", "arguments": "{\"path\":\"a.txt\"}"},
                    }
                ],
            )
            store.append_message(task_id, "tool", "{\"success\": true, \"content\": \"A\"}", tool_call_id="call_1")
            store.append_message(
                task_id,
                "assistant",
                "",
                tool_calls=[
                    {
                        "id": "call_2",
                        "type": "function",
                        "function": {"name": "write_file", "arguments": "{\"path\":\"b.txt\"}"},
                    }
                ],
            )
            store.append_message(task_id, "tool", "{\"success\": false, \"error\": \"permission denied\"}", tool_call_id="call_2")

            result = store.compact_mid_run(task_id, trigger="event", mode="event")
            self.assertTrue(bool(result.get("success")))
            self.assertTrue(bool(result.get("applied")))
            self.assertEqual(result.get("tool_chain_summary_applied"), "rule")
            self.assertTrue(bool(result.get("tool_chain_summary_fallback_used")))
            self.assertIn("llm_error", str(result.get("tool_chain_summary_fallback_reason")))

            with store._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT role, content
                    FROM messages
                    WHERE conversation_id = ?
                    ORDER BY id ASC
                    """,
                    (task_id,),
                ).fetchall()

            self.assertIn("- summary:", str(rows[1][1]))

    def test_runtime_triggers_mid_run_compaction_by_event(self):
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
                                            "id": "call_1",
                                            "type": "function",
                                            "function": {
                                                "name": "echo",
                                                "arguments": "{\"text\": \"hello\"}",
                                            },
                                        }
                                    ],
                                },
                            }
                        ]
                    },
                },
                {
                    "content": "done",
                    "raw": {
                        "choices": [
                            {
                                "finish_reason": "stop",
                                "message": {"role": "assistant", "content": "done"},
                            }
                        ]
                    },
                },
            ]
        )

        registry = ToolRegistry()
        registry.register(
            ToolSpec(
                name="echo",
                description="echo",
                handler=lambda text: {"success": True, "text": text},
                parameters={
                    "type": "object",
                    "properties": {"text": {"type": "string"}},
                    "required": ["text"],
                },
            )
        )

        memory_store = _InMemoryStore()
        compression_config = RuntimeCompressionConfig(
            enabled_mid_run=True,
            round_interval=4,
            midrun_token_ratio=0.99,
            model_context_window_tokens=16000,
            compression_trigger_window_tokens=100,
            keep_recent_turns=8,
            tool_burst_threshold=1,
            consistency_guard=True,
            enable_finalize_compaction=False,
            target_keep_ratio_midrun=0.35,
            target_keep_ratio_finalize=0.50,
            min_keep_turns=3,
            compressor_kind="auto",
            compressor_llm_max_tokens=800,
            event_summarizer_kind="auto",
            event_summarizer_max_tokens=280,
        )

        runtime = AgentRuntime(
            model_provider=provider,
            tool_registry=registry,
            max_steps=4,
            memory_store=memory_store,
            compression_config=compression_config,
            enable_llm_judge=False,
        )

        result = runtime.run("test mid run", task_id="task_compact", run_id="run_compact")
        self.assertEqual(result, "done")
        self.assertGreaterEqual(memory_store.compact_mid_run_calls, 1)
        self.assertEqual(memory_store.rows[0]["run_id"], "run_compact")
        self.assertEqual(memory_store.rows[0]["step_id"], "1")
        self.assertTrue(any(row["role"] == "tool" and row["step_id"] == "1" for row in memory_store.rows))

    def test_maybe_compact_mid_run_emits_budget_rich_observability_payloads(self):
        memory_store = _InMemoryStore()
        events: List[Dict[str, Any]] = []

        def _fake_emit_event(**kwargs):
            events.append(kwargs)
            return kwargs

        messages = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "world"},
        ]

        out = maybe_compact_mid_run(
            step=2,
            task_id="task_obs_compact",
            run_id="run_obs_compact",
            messages=messages,
            tools=[],
            consecutive_tool_calls=10,
            memory_store=memory_store,
            compression_config=RuntimeCompressionConfig(
                enabled_mid_run=True,
                round_interval=4,
                midrun_token_ratio=0.99,
                model_context_window_tokens=160000,
                compression_trigger_window_tokens=120000,
                keep_recent_turns=8,
                tool_burst_threshold=1,
                consistency_guard=True,
                enable_finalize_compaction=False,
                target_keep_ratio_midrun=0.45,
                target_keep_ratio_finalize=0.45,
                min_keep_turns=3,
                compressor_kind="auto",
                compressor_llm_max_tokens=1200,
                event_summarizer_kind="auto",
                event_summarizer_max_tokens=280,
            ),
            estimate_context_tokens=lambda _messages, _tools: 1000,
            estimate_context_usage=lambda estimated: estimated / 120000,
            build_system_prompt=lambda: "sys",
            emit_event=_fake_emit_event,
        )

        self.assertEqual(out, messages)
        start_event = next(e for e in events if e.get("event_type") == "context_compression_started")
        start_payload = start_event.get("payload", {})
        self.assertEqual(start_payload.get("budget_split_kind"), "live_plus_summary")
        self.assertEqual(start_payload.get("live_budget_tokens"), 24)
        self.assertEqual(start_payload.get("summary_budget_tokens"), 30)
        self.assertEqual(start_payload.get("compaction_budget_total_tokens"), 54)

        success_event = next(e for e in events if e.get("event_type") == "context_compression_succeeded")
        success_payload = success_event.get("payload", {})
        self.assertEqual(success_payload.get("budget_split_kind"), "live_plus_summary")
        self.assertEqual(success_payload.get("target_keep_tokens"), 24)
        self.assertEqual(success_payload.get("summary_budget_tokens"), 30)
        self.assertEqual(success_payload.get("applied"), False)

    def test_consistency_guard_toggle_controls_blocking(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = str(Path(td) / "runtime_memory_guard.db")
            task_id = "guard_task"

            guarded = SQLiteMemoryStore(
                db_file=db_path,
                keep_recent=2,
                summarize_threshold=3,
                consistency_guard=True,
                context_window_tokens=120,
                target_keep_ratio_finalize=0.3,
                min_keep_turns=1,
            )
            guarded.append_message(task_id, "system", "必须遵守审批流程")
            guarded.append_message(task_id, "user", "任务A")
            guarded.append_message(task_id, "assistant", "处理中")
            guarded.append_message(task_id, "assistant", "完成")
            with patch.object(guarded.compressor, "validate_consistency", return_value=False):
                blocked = guarded.compact_final(task_id)
            self.assertFalse(bool(blocked.get("success")))
            self.assertEqual(blocked.get("reason"), "consistency_check_failed")

            unguarded = SQLiteMemoryStore(
                db_file=str(Path(td) / "runtime_memory_no_guard.db"),
                keep_recent=2,
                summarize_threshold=3,
                consistency_guard=False,
                context_window_tokens=120,
                target_keep_ratio_finalize=0.3,
                min_keep_turns=1,
            )
            unguarded.append_message(task_id, "system", "必须遵守审批流程")
            unguarded.append_message(task_id, "user", "任务A")
            unguarded.append_message(task_id, "assistant", "处理中")
            unguarded.append_message(task_id, "assistant", "完成")
            with patch.object(unguarded.compressor, "validate_consistency", return_value=False):
                passed = unguarded.compact_final(task_id)
            self.assertTrue(bool(passed.get("success")))
            self.assertTrue(bool(passed.get("applied")))


if __name__ == "__main__":
    unittest.main()
