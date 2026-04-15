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
                "recall_hint": "支付重试场景先验证幂等键，再执行扣款写操作",
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

            summary_rows = store.search_cards(stage="incident_response", query="幂等键", limit=3)
            self.assertEqual(len(summary_rows), 1)
            self.assertEqual(summary_rows[0]["id"], "mem_payment_idempotency_retry_001")
            self.assertIn("幂等键", str(summary_rows[0].get("recall_hint", "")))

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

    def test_search_cards_matches_title_only(self):
        with tempfile.TemporaryDirectory() as td:
            db = str(Path(td) / "system_memory.db")
            store = SystemMemoryStore(db_file=db)
            store.upsert_card(
                {
                    "id": "mem_title_only_001",
                    "title": "支付重试语义索引标题",
                    "recall_hint": "这里包含关键词并发锁",
                    "memory_type": "experience",
                    "domain": "payment",
                    "scenario": {"stage": "development", "trigger_hint": "支付改动"},
                    "owner": {"team": "payment", "primary": "alice"},
                    "lifecycle": {
                        "status": "active",
                        "version": "v1.0",
                        "effective_from": date.today().isoformat(),
                        "expire_at": (date.today() + timedelta(days=30)).isoformat(),
                    },
                    "confidence": "B",
                }
            )

            hit = store.search_cards(query="重试", limit=5)
            self.assertEqual(len(hit), 1)
            self.assertEqual(hit[0]["id"], "mem_title_only_001")

            miss = store.search_cards(query="并发锁", limit=5)
            self.assertEqual(len(miss), 0)

    def test_store_composes_structured_recall_hint_when_missing(self):
        with tempfile.TemporaryDirectory() as td:
            db = str(Path(td) / "system_memory.db")
            store = SystemMemoryStore(db_file=db)
            store.upsert_card(
                {
                    "id": "mem_structured_hint_001",
                    "title": "任务 runtime_cli_20260414 总结",
                    "memory_type": "experience",
                    "domain": "runtime",
                    "scenario": {"stage": "development", "trigger_hint": "发布链路失败"},
                    "problem_pattern": {
                        "symptoms": ["发布前依赖状态不一致导致中断"],
                        "root_cause_hypothesis": "依赖探针缺失",
                    },
                    "solution": {
                        "steps": ["先做依赖健康检查再执行发布"],
                        "expected_outcome": "降低回滚概率",
                    },
                    "constraints": {"applicable_if": ["多服务联动发布场景"]},
                    "anti_pattern": {"not_applicable_if": ["单服务静态资源发布"]},
                    "owner": {"team": "runtime", "primary": "main-agent"},
                    "lifecycle": {
                        "status": "active",
                        "version": "v1.0",
                        "effective_from": date.today().isoformat(),
                        "expire_at": (date.today() + timedelta(days=30)).isoformat(),
                    },
                    "confidence": "B",
                }
            )

            rows = store.search_cards(query="", limit=5)
            self.assertEqual(len(rows), 1)
            card = rows[0]
            self.assertNotIn("runtime_cli_20260414", str(card.get("title", "")))
            recall_hint = str(card.get("recall_hint", ""))
            self.assertIn("问题：", recall_hint)
            self.assertIn("适用：", recall_hint)
            self.assertIn("动作：", recall_hint)
            self.assertIn("风险：", recall_hint)


if __name__ == "__main__":
    unittest.main()
