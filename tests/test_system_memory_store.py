import tempfile
import unittest
from pathlib import Path
from datetime import date, timedelta

from app.core.memory.system_memory_store import SystemMemoryStore


class SystemMemoryStoreTests(unittest.TestCase):
    def test_upsert_and_search_cards(self):
        with tempfile.TemporaryDirectory() as td:
            db = str(Path(td) / "system_memory.db")
            store = SystemMemoryStore(db_file=db)

            card = {
                "id": "mem_payment_idempotency_retry_001",
                "title": "支付重试必须幂等键先行",
                "memory_type": "experience",
                "domain": "payment",
                "tags": ["idempotency", "retry"],
                "scenario": {"stage": "pull_request", "trigger_hint": "支付改动"},
                "owner": {"team": "payment", "primary": "alice", "reviewers": ["bob"]},
                "lifecycle": {
                    "status": "active",
                    "version": "v1.0",
                    "effective_from": "2026-04-10",
                    "expire_at": "2026-10-10",
                    "last_reviewed_at": "2026-04-10",
                },
                "confidence": "A",
            }
            store.upsert_card(card)

            rows = store.search_cards(stage="pull_request", query="支付 重试", limit=3)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["id"], "mem_payment_idempotency_retry_001")
            self.assertGreater(rows[0].get("retrieval_score", 0), 0)

    def test_due_review_cards(self):
        with tempfile.TemporaryDirectory() as td:
            db = str(Path(td) / "system_memory.db")
            store = SystemMemoryStore(db_file=db)
            tomorrow = (date.today() + timedelta(days=1)).isoformat()

            store.upsert_card(
                {
                    "id": "mem_due_001",
                    "title": "即将过期卡片",
                    "memory_type": "principle",
                    "domain": "infra",
                    "scenario": {"stage": "pre_release", "trigger_hint": "发布前"},
                    "owner": {"team": "infra", "primary": "ops"},
                    "lifecycle": {
                        "status": "active",
                        "version": "v1.0",
                        "effective_from": date.today().isoformat(),
                        "expire_at": tomorrow,
                    },
                    "confidence": "B",
                }
            )
            due = store.list_due_review_cards(within_days=2)
            self.assertEqual(len(due), 1)
            self.assertEqual(due[0]["id"], "mem_due_001")


if __name__ == "__main__":
    unittest.main()
