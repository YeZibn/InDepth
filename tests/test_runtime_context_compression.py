import json
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import patch

from app.config.runtime_config import RuntimeCompressionConfig
from app.core.memory.sqlite_memory_store import SQLiteMemoryStore
from app.core.model.mock_provider import MockModelProvider
from app.core.runtime.agent_runtime import AgentRuntime
from app.core.tools.registry import ToolRegistry, ToolSpec


class _InMemoryStore:
    def __init__(self):
        self.rows: List[Dict[str, Any]] = []
        self.compact_mid_run_calls = 0

    def append_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        tool_call_id: str = "",
        tool_calls: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        self.rows.append(
            {
                "conversation_id": conversation_id,
                "role": role,
                "content": content,
                "tool_call_id": tool_call_id,
                "tool_calls": tool_calls or [],
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

    def compact_mid_run(self, conversation_id: str, trigger: str = "round", mode: str = "light") -> Dict[str, Any]:
        self.compact_mid_run_calls += 1
        return {"success": True, "applied": False, "trigger": trigger, "mode": mode}

    def compact_final(self, conversation_id: str) -> Dict[str, Any]:
        return {"success": True, "applied": False}


class RuntimeContextCompressionTests(unittest.TestCase):
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
            store = SQLiteMemoryStore(db_file=db_path, keep_recent=2, summarize_threshold=3)
            task_id = "turn_task"

            store.append_message(
                task_id,
                "assistant",
                "",
                tool_calls=[
                    {
                        "id": "call_a",
                        "type": "function",
                        "function": {"name": "echo", "arguments": "{\"text\":\"a\"}"},
                    }
                ],
            )
            store.append_message(task_id, "tool", "{\"success\": true}", tool_call_id="call_a")
            store.append_message(
                task_id,
                "assistant",
                "",
                tool_calls=[
                    {
                        "id": "call_b",
                        "type": "function",
                        "function": {"name": "echo", "arguments": "{\"text\":\"b\"}"},
                    }
                ],
            )
            store.append_message(task_id, "tool", "{\"success\": true}", tool_call_id="call_b")
            store.append_message(task_id, "assistant", "done")

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
            store = SQLiteMemoryStore(db_file=db_path, keep_recent=2, summarize_threshold=3)
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
            self.assertTrue(summary.get("anchors"))

            recent = store.get_recent_messages(task_id, limit=20)
            self.assertTrue(recent)
            self.assertEqual(recent[0].get("role"), "system")
            self.assertIn("结构化历史摘要", str(recent[0].get("content", "")))

    def test_runtime_triggers_mid_run_compaction_by_round_interval(self):
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
            round_interval=1,
            light_token_ratio=0.95,
            strong_token_ratio=0.99,
            context_window_tokens=16000,
            keep_recent_turns=8,
            tool_burst_threshold=10,
            consistency_guard=True,
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

    def test_consistency_guard_toggle_controls_blocking(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = str(Path(td) / "runtime_memory_guard.db")
            task_id = "guard_task"

            guarded = SQLiteMemoryStore(
                db_file=db_path,
                keep_recent=2,
                summarize_threshold=3,
                consistency_guard=True,
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
