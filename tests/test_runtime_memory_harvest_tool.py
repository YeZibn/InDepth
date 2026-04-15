import tempfile
import unittest
from pathlib import Path

from app.core.memory.system_memory_store import SystemMemoryStore
from app.tool.runtime_memory_harvest_tool import capture_runtime_memory_candidate


class RuntimeMemoryHarvestToolTests(unittest.TestCase):
    def test_capture_runtime_memory_candidate_writes_draft_card(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = str(Path(td) / "system_memory.db")
            result = capture_runtime_memory_candidate.entrypoint(
                task_id="task_x",
                run_id="run_x",
                title="缓存重建顺序导致瞬时失败",
                observation="部署后先清缓存再重建导致读放大",
                proposed_action="先预热再切流",
                stage="pre_release",
                tags="cache,release",
                db_file=db_path,
            )
            self.assertIn("Captured candidate memory", result)

            rows = SystemMemoryStore(db_file=db_path).search_cards(
                stage="pre_release",
                query="缓存 重建",
                limit=5,
                only_active=False,
            )
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].get("lifecycle", {}).get("status"), "draft")
            self.assertEqual(rows[0].get("confidence"), "C")

    def test_capture_runtime_memory_candidate_accepts_recall_hint_override(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = str(Path(td) / "system_memory.db")
            capture_runtime_memory_candidate.entrypoint(
                task_id="task_y",
                run_id="run_y",
                title="发布前依赖检查",
                observation="观察文本",
                proposed_action="建议文本",
                recall_hint="问题：依赖状态不一致；适用：多服务联动发布；动作：先做依赖健康检查；风险：跳过会触发连锁回滚。",
                stage="pre_release",
                tags="release",
                db_file=db_path,
            )

            rows = SystemMemoryStore(db_file=db_path).search_cards(
                query="依赖 检查",
                limit=5,
                only_active=False,
            )
            self.assertEqual(len(rows), 1)
            self.assertIn("适用：多服务联动发布", str(rows[0].get("recall_hint", "")))


if __name__ == "__main__":
    unittest.main()
