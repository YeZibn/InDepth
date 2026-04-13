import unittest
from unittest.mock import patch

from app.agent.runtime_agent import build_runtime_cli_agent


class RuntimeAgentPromptAlignmentTests(unittest.TestCase):
    @patch("app.agent.runtime_agent.BaseAgent")
    def test_build_runtime_cli_agent_uses_base_agent(self, mock_base_agent):
        build_runtime_cli_agent()
        mock_base_agent.assert_called_once_with(
            name="runtime_cli",
            description="Runtime CLI agent powered by BaseAgent",
            instructions="遵守 InDepth 协议，优先结构化回答。",
            tools=[],
            load_default_tools=True,
            skills="app/skills",
            load_memory_knowledge=True,
        )


if __name__ == "__main__":
    unittest.main()
