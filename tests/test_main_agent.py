import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from app.agent.agent import BaseAgent
from app.core.tools import tool


class _FakeRuntime:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.run_calls = []

    def run(self, **kwargs):
        self.run_calls.append(kwargs)
        return "ok-from-runtime"


class _FakeProvider:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs


class _FakeRuntimeClarify:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.run_calls = []
        self.last_runtime_state = "idle"

    def run(self, **kwargs):
        self.run_calls.append(kwargs)
        if len(self.run_calls) == 1:
            self.last_runtime_state = "awaiting_user_input"
            return "请确认输出语言。"
        self.last_runtime_state = "completed"
        return "已完成。"


@tool(name="dummy_tool", description="dummy tool for main agent tests")
def _dummy_tool(query: str) -> str:
    return query


class MainAgentTests(unittest.TestCase):
    def test_main_agent_registers_only_supplied_tools(self):
        with (
            patch("app.agent.agent.AgentRuntime", _FakeRuntime),
            patch("app.agent.agent.HttpChatModelProvider", _FakeProvider),
        ):
            agent = BaseAgent(
                name="main_agent",
                description="test agent",
                instructions="hello",
                tools=[_dummy_tool],
                load_memory_knowledge=False,
                enable_llm_judge=False,
            )

        registry = agent.runtime.kwargs["tool_registry"]
        self.assertTrue(registry.has("dummy_tool"))
        self.assertFalse(registry.has("non_existing_tool"))

    def test_chat_delegates_to_runtime_with_expected_task_and_run_id(self):
        with (
            patch("app.agent.agent.AgentRuntime", _FakeRuntime),
            patch("app.agent.agent.HttpChatModelProvider", _FakeProvider),
            patch("app.agent.agent.uuid.uuid4", return_value=SimpleNamespace(hex="abcdef1234567890")),
        ):
            agent = BaseAgent(
                name="main_agent",
                description="test agent",
                instructions="hello",
                tools=[_dummy_tool],
                load_memory_knowledge=False,
                enable_llm_judge=False,
            )
            result = agent.chat("ping")

        self.assertEqual(result, "ok-from-runtime")
        self.assertEqual(len(agent.runtime.run_calls), 1)
        call = agent.runtime.run_calls[0]
        self.assertEqual(call["user_input"], "ping")
        self.assertEqual(call["task_id"], "main_agent_task")
        self.assertEqual(call["run_id"], "main_agent_abcdef12")
        self.assertEqual(call["resume_from_waiting"], False)

    def test_chat_reuses_same_run_id_when_waiting_for_user_clarification(self):
        with (
            patch("app.agent.agent.AgentRuntime", _FakeRuntimeClarify),
            patch("app.agent.agent.HttpChatModelProvider", _FakeProvider),
            patch(
                "app.agent.agent.uuid.uuid4",
                side_effect=[
                    SimpleNamespace(hex="aaaabbbbccccdddd"),
                    SimpleNamespace(hex="eeeeffff00001111"),
                ],
            ),
        ):
            agent = BaseAgent(
                name="main_agent",
                description="test agent",
                instructions="hello",
                tools=[_dummy_tool],
                load_memory_knowledge=False,
                enable_llm_judge=False,
            )
            first = agent.chat("先做个草稿")
            second = agent.chat("中文即可")

        self.assertIn("确认", first)
        self.assertIn("完成", second)
        self.assertEqual(len(agent.runtime.run_calls), 2)
        call1 = agent.runtime.run_calls[0]
        call2 = agent.runtime.run_calls[1]
        self.assertEqual(call1["run_id"], "main_agent_aaaabbbb")
        self.assertEqual(call2["run_id"], "main_agent_aaaabbbb")
        self.assertEqual(call1["resume_from_waiting"], False)
        self.assertEqual(call2["resume_from_waiting"], True)

    def test_load_memory_knowledge_switch_controls_system_prompt(self):
        with (
            patch("app.agent.agent.AgentRuntime", _FakeRuntime),
            patch("app.agent.agent.HttpChatModelProvider", _FakeProvider),
            patch("app.agent.agent.load_indepth_content", return_value="INDEPTH-CONTENT"),
        ):
            with_memory = BaseAgent(
                name="with_mem",
                description="with memory",
                instructions="USER-INSTR",
                tools=[],
                load_memory_knowledge=True,
                enable_llm_judge=False,
            )
            without_memory = BaseAgent(
                name="without_mem",
                description="without memory",
                instructions="USER-INSTR",
                tools=[],
                load_memory_knowledge=False,
                enable_llm_judge=False,
            )

        self.assertIn("INDEPTH-CONTENT", with_memory.instructions)
        self.assertIn("USER-INSTR", with_memory.instructions)
        self.assertEqual(without_memory.instructions, "USER-INSTR")

    def test_extract_skill_paths_accepts_list_and_string(self):
        with (
            patch("app.agent.agent.AgentRuntime", _FakeRuntime),
            patch("app.agent.agent.HttpChatModelProvider", _FakeProvider),
        ):
            agent_str = BaseAgent(
                name="s1",
                description="x",
                instructions="x",
                tools=[],
                skills="app/skills/memory-knowledge-skill",
                load_memory_knowledge=False,
                enable_llm_judge=False,
            )
            agent_list = BaseAgent(
                name="s2",
                description="x",
                instructions="x",
                tools=[],
                skills=["a", "b"],
                load_memory_knowledge=False,
                enable_llm_judge=False,
            )

        self.assertEqual(agent_str.skill_paths, ["app/skills/memory-knowledge-skill"])
        self.assertEqual(agent_list.skill_paths, ["a", "b"])

    def test_main_agent_with_skills_uses_system_prompt_and_registers_skill_tools(self):
        with TemporaryDirectory() as td:
            skill_dir = Path(td) / "demo-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text(
                "---\nname: demo-skill\ndescription: demo\n---\n\n# Demo Skill\n\nUse this skill.\n",
                encoding="utf-8",
            )
            with (
                patch("app.agent.agent.AgentRuntime", _FakeRuntime),
                patch("app.agent.agent.HttpChatModelProvider", _FakeProvider),
            ):
                agent = BaseAgent(
                    name="s1",
                    description="x",
                    instructions="x",
                    tools=[],
                    skills=str(skill_dir),
                    load_memory_knowledge=False,
                    enable_llm_judge=False,
                )
        self.assertIn("<skills_system>", agent.skill_prompt)
        registry = agent.runtime.kwargs["tool_registry"]
        self.assertTrue(registry.has("get_skill_instructions"))
        self.assertTrue(registry.has("get_skill_reference"))
        self.assertTrue(registry.has("get_skill_script"))

if __name__ == "__main__":
    unittest.main()
