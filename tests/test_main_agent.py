import unittest
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


if __name__ == "__main__":
    unittest.main()
