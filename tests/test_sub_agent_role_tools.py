import unittest
from unittest.mock import patch

from app.agent.sub_agent import SubAgent


class _FakeRuntime:
    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def run(self, **kwargs):
        return "ok"


class _FakeProvider:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs


class SubAgentRoleToolsTests(unittest.TestCase):
    def _build_agent(self, role: str) -> SubAgent:
        with (
            patch("app.agent.sub_agent.AgentRuntime", _FakeRuntime),
            patch("app.agent.sub_agent.HttpChatModelProvider", _FakeProvider),
        ):
            return SubAgent(
                name=f"{role}_agent",
                description="test",
                task="test task",
                role=role,
            )

    def test_researcher_reviewer_verifier_have_memory_search_tool(self):
        for role in ["researcher", "reviewer", "verifier"]:
            agent = self._build_agent(role)
            registry = agent.runtime.kwargs["tool_registry"]
            self.assertTrue(registry.has("search_memory_cards"), msg=f"{role} should have search_memory_cards")

    def test_builder_and_general_do_not_have_memory_search_tool(self):
        for role in ["builder", "general"]:
            agent = self._build_agent(role)
            registry = agent.runtime.kwargs["tool_registry"]
            self.assertFalse(registry.has("search_memory_cards"), msg=f"{role} should not have search_memory_cards")


if __name__ == "__main__":
    unittest.main()
