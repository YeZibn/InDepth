import tempfile
import unittest
from pathlib import Path

from app.core.memory.sqlite_memory_store import SQLiteMemoryStore
from app.tool.history_recall_tool import history_recall


class HistoryRecallToolTests(unittest.TestCase):
    def test_history_recall_returns_messages_for_run_and_step(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = str(Path(td) / "runtime_memory_history_tool.db")
            store = SQLiteMemoryStore(db_file=db_path)
            task_id = "history_task"
            store.append_message(task_id, "user", "请处理这个任务", run_id="run_1", step_id="1")
            store.append_message(task_id, "assistant", "正在读取文件", run_id="run_1", step_id="1")
            store.append_message(task_id, "tool", "{\"success\": true}", tool_call_id="call_1", run_id="run_1", step_id="1")
            store.append_message(task_id, "assistant", "处理完成", run_id="run_1", step_id="2")

            result = history_recall.entrypoint(
                task_id=task_id,
                run_id="run_1",
                step_id="1",
                db_file=db_path,
            )

        self.assertTrue(bool(result.get("success")))
        self.assertTrue(bool(result.get("found")))
        self.assertEqual(len(result.get("messages") or []), 3)
        self.assertEqual(result["messages"][0]["role"], "user")
        self.assertEqual(result["messages"][1]["step_id"], "1")

    def test_history_recall_returns_structured_failure_when_missing(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = str(Path(td) / "runtime_memory_history_tool_missing.db")
            store = SQLiteMemoryStore(db_file=db_path)
            store.append_message("history_task", "assistant", "done", run_id="run_1", step_id="2")

            result = history_recall.entrypoint(
                task_id="history_task",
                run_id="run_1",
                step_id="99",
                db_file=db_path,
            )

        self.assertTrue(bool(result.get("success")))
        self.assertFalse(bool(result.get("found")))
        self.assertEqual(result.get("reason"), "missing_step_metadata_or_no_messages")


if __name__ == "__main__":
    unittest.main()
