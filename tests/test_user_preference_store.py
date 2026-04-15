import tempfile
import unittest
from pathlib import Path

from app.core.memory.user_preference_store import UserPreferenceStore


class UserPreferenceStoreTests(unittest.TestCase):
    def test_upsert_and_recall_block(self):
        with tempfile.TemporaryDirectory() as td:
            pref_file = str(Path(td) / "memory" / "preferences" / "user-preferences.md")
            store = UserPreferenceStore(file_path=pref_file)
            store.upsert_preference("job_role", "后端工程师")
            store.upsert_preference("response_style", "简洁、结论先行")
            block = store.render_recall_block(
                user_input="请给我一个后端优化建议",
                top_k=3,
                always_include_keys=["response_style"],
                max_chars=240,
            )
            self.assertIn("用户偏好召回", block)
            self.assertIn("response_style=简洁、结论先行", block)

    def test_capture_from_user_input_extracts_explicit_keys(self):
        with tempfile.TemporaryDirectory() as td:
            pref_file = str(Path(td) / "memory" / "preferences" / "user-preferences.md")
            store = UserPreferenceStore(file_path=pref_file)
            changed = store.capture_from_user_input("我是后端工程师，请用中文，回答简洁", allow_inferred_write=False)
            prefs = store.list_preferences()
            self.assertIn("job_role", changed)
            self.assertIn("language_preference", changed)
            self.assertIn("response_style", changed)
            self.assertEqual(prefs.get("job_role", {}).get("value"), "后端工程师")
            self.assertEqual(prefs.get("language_preference", {}).get("value"), "中文")
