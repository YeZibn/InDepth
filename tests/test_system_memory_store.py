import tempfile
import unittest
from pathlib import Path
from datetime import date, timedelta

from app.core.memory.system_memory_store import SystemMemoryStore


class _FakeEmbeddingProvider:
    def __init__(self, embedding):
        self.embedding = embedding
        self.calls = []

    def embed_text(self, text):
        self.calls.append(text)
        return list(self.embedding)


class _FakeVectorIndex:
    def __init__(self):
        self.upserts = []

    def upsert_memory_vector(self, memory_id, vector_text, embedding, model):
        self.upserts.append(
            {
                "memory_id": memory_id,
                "vector_text": vector_text,
                "embedding": list(embedding),
                "model": model,
            }
        )


class SystemMemoryStoreTests(unittest.TestCase):
    def test_upsert_and_search_cards(self):
        with tempfile.TemporaryDirectory() as td:
            db = str(Path(td) / "system_memory.db")
            store = SystemMemoryStore(db_file=db)

            card = {
                "id": "mem_payment_idempotency_retry_001",
                "title": "支付重试必须幂等键先行",
                "recall_hint": "支付重试场景先验证幂等键，再执行扣款写操作",
                "content": "支付重试链路必须先建立幂等键与唯一约束，避免重复扣款。",
                "status": "active",
                "expire_at": "2026-10-10",
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
                    "content": "一条即将过期的经验卡。",
                    "status": "active",
                    "expire_at": tomorrow,
                }
            )
            due = store.list_due_review_cards(within_days=2)
            self.assertEqual(len(due), 1)
            self.assertEqual(due[0]["id"], "mem_due_001")

    def test_search_cards_matches_lightweight_fields(self):
        with tempfile.TemporaryDirectory() as td:
            db = str(Path(td) / "system_memory.db")
            store = SystemMemoryStore(db_file=db)
            store.upsert_card(
                {
                    "id": "mem_title_only_001",
                    "title": "支付重试语义索引标题",
                    "recall_hint": "这里包含关键词并发锁",
                    "content": "正文里没有并发锁，只有支付重试相关内容。",
                    "status": "active",
                    "expire_at": (date.today() + timedelta(days=30)).isoformat(),
                }
            )

            hit = store.search_cards(query="重试", limit=5)
            self.assertEqual(len(hit), 1)
            self.assertEqual(hit[0]["id"], "mem_title_only_001")

            hit_by_hint = store.search_cards(query="并发锁", limit=5)
            self.assertEqual(len(hit_by_hint), 1)
            self.assertEqual(hit_by_hint[0]["id"], "mem_title_only_001")

    def test_store_composes_structured_recall_hint_when_missing(self):
        with tempfile.TemporaryDirectory() as td:
            db = str(Path(td) / "system_memory.db")
            store = SystemMemoryStore(db_file=db)
            store.upsert_card(
                {
                    "id": "mem_structured_hint_001",
                    "title": "任务 runtime_cli_20260414 总结",
                    "status": "active",
                    "expire_at": (date.today() + timedelta(days=30)).isoformat(),
                    "scenario": {"trigger_hint": "发布链路失败"},
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

    def test_store_migrates_legacy_schema_to_lightweight_schema(self):
        with tempfile.TemporaryDirectory() as td:
            db = str(Path(td) / "system_memory.db")
            import sqlite3

            conn = sqlite3.connect(db)
            try:
                conn.execute(
                    """
                    CREATE TABLE memory_card (
                        id TEXT PRIMARY KEY,
                        title TEXT NOT NULL,
                        recall_hint TEXT NOT NULL DEFAULT '',
                        memory_type TEXT NOT NULL,
                        domain TEXT NOT NULL,
                        tags_json TEXT NOT NULL,
                        scenario_stage TEXT NOT NULL,
                        trigger_hint TEXT NOT NULL,
                        problem_pattern_json TEXT NOT NULL,
                        solution_json TEXT NOT NULL,
                        constraints_json TEXT NOT NULL,
                        anti_pattern_json TEXT NOT NULL,
                        evidence_json TEXT NOT NULL,
                        impact_json TEXT NOT NULL,
                        owner_team TEXT NOT NULL,
                        owner_primary TEXT NOT NULL,
                        owner_reviewers_json TEXT NOT NULL,
                        status TEXT NOT NULL,
                        version TEXT NOT NULL,
                        effective_from TEXT,
                        expire_at TEXT,
                        last_reviewed_at TEXT,
                        confidence TEXT NOT NULL,
                        payload_json TEXT NOT NULL,
                        created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
                        updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
                    )
                    """
                )
                conn.execute(
                    """
                    INSERT INTO memory_card (
                        id, title, recall_hint, memory_type, domain, tags_json, scenario_stage, trigger_hint,
                        problem_pattern_json, solution_json, constraints_json, anti_pattern_json,
                        evidence_json, impact_json, owner_team, owner_primary, owner_reviewers_json,
                        status, version, effective_from, expire_at, last_reviewed_at, confidence, payload_json, updated_at
                    ) VALUES (
                        'mem_legacy_001', '旧卡片', '', 'experience', 'runtime', '[]', 'postmortem', '旧触发',
                        '{}', '{}', '{}', '{}',
                        '{}', '{}', 'runtime', 'agent', '[]',
                        'active', 'v1.0', '2026-04-20', '2026-10-20', '2026-04-20', 'B',
                        '{"title":"旧卡片","recall_hint":"旧提示","content":"旧内容"}',
                        datetime('now','localtime')
                    )
                    """
                )
                conn.commit()
            finally:
                conn.close()

            store = SystemMemoryStore(db_file=db)
            card = store.get_card("mem_legacy_001")
            self.assertIsNotNone(card)
            self.assertEqual(card.get("title"), "旧卡片")
            self.assertEqual(card.get("recall_hint"), "旧提示")
            self.assertEqual(card.get("content"), "旧内容")

    def test_upsert_card_syncs_vector_index_when_provider_is_configured(self):
        with tempfile.TemporaryDirectory() as td:
            db = str(Path(td) / "system_memory.db")
            vector_index = _FakeVectorIndex()
            embedding_provider = _FakeEmbeddingProvider([0.11, 0.22, 0.33])
            store = SystemMemoryStore(
                db_file=db,
                vector_index=vector_index,
                embedding_provider=embedding_provider,
                embedding_model_id="text-embedding-test",
            )

            store.upsert_card(
                {
                    "id": "mem_vector_sync_001",
                    "title": "支付重试必须幂等键先行",
                    "recall_hint": "支付重试前先校验幂等键，再执行扣款写操作",
                    "content": "测试内容",
                    "status": "active",
                }
            )

            self.assertEqual(len(embedding_provider.calls), 1)
            self.assertIn("title: 支付重试必须幂等键先行", embedding_provider.calls[0])
            self.assertIn("recall_hint: 支付重试前先校验幂等键，再执行扣款写操作", embedding_provider.calls[0])
            self.assertEqual(len(vector_index.upserts), 1)
            self.assertEqual(vector_index.upserts[0]["memory_id"], "mem_vector_sync_001")
            self.assertEqual(vector_index.upserts[0]["embedding"], [0.11, 0.22, 0.33])
            self.assertEqual(vector_index.upserts[0]["model"], "text-embedding-test")


if __name__ == "__main__":
    unittest.main()
