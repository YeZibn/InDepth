import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from app.core.memory.system_memory_store import SystemMemoryStore
from app.tool.memory_query_tool import get_memory_card_by_id


class MemoryQueryToolTests(unittest.TestCase):
    def test_get_memory_card_by_id_returns_full_card(self):
        with tempfile.TemporaryDirectory() as td:
            db = str(Path(td) / "system_memory.db")
            store = SystemMemoryStore(db_file=db)
            store.upsert_card(
                {
                    "id": "mem_tool_fetch_001",
                    "title": "工具拉取完整记忆",
                    "recall_hint": "当注入记忆关键时，按 id 拉完整卡片",
                    "content": "当召回记忆变得关键时，可以按 id 拉完整记忆内容。",
                    "status": "active",
                    "expire_at": (date.today() + timedelta(days=30)).isoformat(),
                }
            )
            result = get_memory_card_by_id.entrypoint(memory_id="mem_tool_fetch_001", db_file=db)
            self.assertTrue(result.get("success"))
            self.assertTrue(result.get("found"))
            self.assertEqual(result.get("card", {}).get("id"), "mem_tool_fetch_001")

    def test_get_memory_card_by_id_respects_only_active_default(self):
        with tempfile.TemporaryDirectory() as td:
            db = str(Path(td) / "system_memory.db")
            store = SystemMemoryStore(db_file=db)
            store.upsert_card(
                {
                    "id": "mem_tool_fetch_002",
                    "title": "已归档记忆",
                    "recall_hint": "不应默认返回",
                    "content": "这是一条已归档记忆。",
                    "status": "archived",
                    "expire_at": (date.today() - timedelta(days=1)).isoformat(),
                }
            )
            miss = get_memory_card_by_id.entrypoint(memory_id="mem_tool_fetch_002", db_file=db)
            self.assertTrue(miss.get("success"))
            self.assertFalse(miss.get("found"))

            hit = get_memory_card_by_id.entrypoint(
                memory_id="mem_tool_fetch_002",
                include_inactive=True,
                db_file=db,
            )
            self.assertTrue(hit.get("found"))


if __name__ == "__main__":
    unittest.main()
