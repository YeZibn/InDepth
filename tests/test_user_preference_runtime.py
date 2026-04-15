import tempfile
import unittest
from pathlib import Path

from app.config import RuntimeUserPreferenceConfig
from app.core.memory.user_preference_store import UserPreferenceStore
from app.core.model.mock_provider import MockModelProvider
from app.core.runtime.agent_runtime import AgentRuntime
from app.core.tools.registry import ToolRegistry


class UserPreferenceRuntimeTests(unittest.TestCase):
    def test_runtime_captures_preferences_via_llm_with_double_gate(self):
        provider = MockModelProvider(
            scripted_outputs=[
                {
                    "content": "好的，我会简洁回答。",
                    "raw": {
                        "choices": [
                            {
                                "finish_reason": "stop",
                                "message": {"role": "assistant", "content": "好的，我会简洁回答。"},
                            }
                        ]
                    },
                },
                {
                    "content": (
                        '{"updates":[{"key":"response_style","value":"简洁、结论先行","confidence":0.86,'
                        '"explicit":true,"action":"upsert","evidence_span":"回答简洁一点"}]}'
                    ),
                    "raw": {"mock": True},
                },
            ]
        )
        with tempfile.TemporaryDirectory() as td:
            pref_file = str(Path(td) / "memory" / "preferences" / "user-preferences.md")
            cfg = RuntimeUserPreferenceConfig(
                enabled=True,
                file_path=pref_file,
                recall_top_k=5,
                always_include_keys=("language_preference", "response_style"),
                max_inject_chars=240,
                enable_llm_extract=True,
                auto_write_min_confidence=0.75,
                conflict_min_confidence=0.90,
            )
            runtime = AgentRuntime(
                model_provider=provider,
                tool_registry=ToolRegistry(),
                max_steps=2,
                user_preference_config=cfg,
            )
            runtime.run("请回答简洁一点", task_id="pref_task_1", run_id="pref_run_1")
            store = UserPreferenceStore(file_path=pref_file)
            prefs = store.list_preferences()
            self.assertEqual(prefs.get("response_style", {}).get("value"), "简洁、结论先行")
            self.assertEqual(prefs.get("response_style", {}).get("source"), "llm_extract_v1")

    def test_runtime_skips_non_explicit_or_low_confidence_updates(self):
        provider = MockModelProvider(
            scripted_outputs=[
                {
                    "content": "收到",
                    "raw": {
                        "choices": [
                            {
                                "finish_reason": "stop",
                                "message": {"role": "assistant", "content": "收到"},
                            }
                        ]
                    },
                },
                {
                    "content": (
                        '{"updates":['
                        '{"key":"job_role","value":"后端工程师","confidence":0.95,"explicit":false,"action":"upsert","evidence_span":"推测"},'
                        '{"key":"response_style","value":"详细、步骤化","confidence":0.55,"explicit":true,"action":"upsert","evidence_span":"详细点"}'
                        ']}'
                    ),
                    "raw": {"mock": True},
                },
            ]
        )
        with tempfile.TemporaryDirectory() as td:
            pref_file = str(Path(td) / "memory" / "preferences" / "user-preferences.md")
            cfg = RuntimeUserPreferenceConfig(
                enabled=True,
                file_path=pref_file,
                recall_top_k=5,
                always_include_keys=("language_preference", "response_style"),
                max_inject_chars=240,
                enable_llm_extract=True,
                auto_write_min_confidence=0.75,
                conflict_min_confidence=0.90,
            )
            runtime = AgentRuntime(
                model_provider=provider,
                tool_registry=ToolRegistry(),
                max_steps=2,
                user_preference_config=cfg,
            )
            runtime.run("帮我看看这个方案", task_id="pref_task_2", run_id="pref_run_2")
            store = UserPreferenceStore(file_path=pref_file)
            prefs = store.list_preferences()
            self.assertFalse("job_role" in prefs)
            self.assertFalse("response_style" in prefs)

