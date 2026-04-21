import unittest
from unittest.mock import patch

from app.config.runtime_config import RuntimeCompressionConfig
from app.core.bootstrap import build_agent_runtime_kwargs, create_runtime
from app.core.tools import tool


class _FakeRuntime:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class _FakeProvider:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs


class _FakeSkillsManager:
    def __init__(self, prompt: str, has_skills: bool = True):
        self._prompt = prompt
        self._has_skills = has_skills

    def get_system_prompt_snippet(self):
        return self._prompt

    def get_skill_names(self):
        return ["demo-skill"] if self._has_skills else []

    def get_tools(self):
        return ["SKILL_TOOL"]


@tool(name="demo_extra_tool", description="demo extra tool")
def _demo_extra_tool(query: str) -> str:
    return query


class BootstrapTests(unittest.TestCase):
    def test_build_agent_runtime_kwargs_uses_custom_memory_file_and_keeps_extra_tools_without_defaults(self):
        with (
            patch("app.core.bootstrap.HttpChatModelProvider", _FakeProvider),
            patch(
                "app.core.bootstrap.build_skills_manager",
                return_value=_FakeSkillsManager("", has_skills=False),
            ),
        ):
            runtime_kwargs = build_agent_runtime_kwargs(
                system_prompt="hello",
                load_default_tools=False,
                extra_tools=[_demo_extra_tool],
                memory_db_file="db/custom_runtime_memory.db",
                enable_llm_judge=False,
            )

        registry = runtime_kwargs["tool_registry"]
        self.assertTrue(registry.has("demo_extra_tool"))
        self.assertFalse(registry.has("plan_task"))
        self.assertEqual(runtime_kwargs["memory_store"].db_file, "db/custom_runtime_memory.db")
        self.assertEqual(runtime_kwargs["system_prompt"], "hello")
        self.assertEqual(runtime_kwargs["enable_llm_judge"], False)

    def test_build_agent_runtime_kwargs_registers_skill_tools_on_top_of_default_registry(self):
        with (
            patch("app.core.bootstrap.HttpChatModelProvider", _FakeProvider),
            patch(
                "app.core.bootstrap.build_skills_manager",
                return_value=_FakeSkillsManager("SKILL-SYSTEM-PROMPT", has_skills=True),
            ),
        ):
            runtime_kwargs = build_agent_runtime_kwargs(
                system_prompt="hello",
                enable_llm_judge=False,
            )

        registry = runtime_kwargs["tool_registry"]
        self.assertTrue(registry.has("plan_task"))
        self.assertEqual(runtime_kwargs["skill_prompt"], "SKILL-SYSTEM-PROMPT")

    def test_create_runtime_uses_system_skill_prompt_and_registers_skill_tools(self):
        with (
            patch("app.core.bootstrap.AgentRuntime", _FakeRuntime),
            patch("app.core.bootstrap.HttpChatModelProvider", _FakeProvider),
            patch(
                "app.core.bootstrap.build_skills_manager",
                return_value=_FakeSkillsManager("SKILL-SYSTEM-PROMPT", has_skills=True),
            ) as mock_builder,
            patch("app.core.bootstrap.register_tool_functions") as mock_register,
        ):
            runtime = create_runtime(
                system_prompt="hello",
                skill_paths=["app/skills/skill-creator"],
                enable_llm_judge=False,
            )

        mock_builder.assert_called_once_with(["app/skills/skill-creator"], validate=False)
        mock_register.assert_called_once()
        self.assertEqual(runtime.kwargs["skill_prompt"], "SKILL-SYSTEM-PROMPT")

    def test_create_runtime_wires_trigger_window_into_memory_store(self):
        compression_config = RuntimeCompressionConfig(
            enabled_mid_run=True,
            round_interval=4,
            midrun_token_ratio=0.82,
            model_context_window_tokens=160000,
            compression_trigger_window_tokens=120000,
            keep_recent_turns=8,
            tool_burst_threshold=5,
            consistency_guard=True,
            enable_finalize_compaction=False,
            target_keep_ratio_midrun=0.40,
            target_keep_ratio_finalize=0.40,
            min_keep_turns=3,
            compressor_kind="auto",
            compressor_llm_max_tokens=1200,
            event_summarizer_kind="auto",
            event_summarizer_max_tokens=280,
        )
        with (
            patch("app.core.bootstrap.AgentRuntime", _FakeRuntime),
            patch("app.core.bootstrap.HttpChatModelProvider", _FakeProvider),
            patch("app.core.bootstrap.load_runtime_compression_config", return_value=compression_config),
            patch(
                "app.core.bootstrap.build_skills_manager",
                return_value=_FakeSkillsManager("", has_skills=False),
            ),
        ):
            runtime = create_runtime(system_prompt="hello", enable_llm_judge=False)

        self.assertEqual(runtime.kwargs["compression_config"].model_context_window_tokens, 160000)
        self.assertEqual(runtime.kwargs["memory_store"].context_window_tokens, 120000)


if __name__ == "__main__":
    unittest.main()
