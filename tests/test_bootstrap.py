import unittest
from unittest.mock import patch

from app.core.bootstrap import create_runtime


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


class BootstrapTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
