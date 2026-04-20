import unittest

from app.agent.sub_agent_runtime import SubAgentRuntime
from app.core.model.base import ModelOutput
from app.core.tools.registry import ToolRegistry


class _FakeProvider:
    def __init__(self):
        self.calls = []

    def generate(self, messages, tools, config=None):
        self.calls.append(
            {
                "messages": [dict(message) for message in messages],
                "tools": tools,
                "config": config,
            }
        )
        return ModelOutput(
            content="done",
            raw={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": "done"},
                    }
                ]
            },
        )


class SubAgentRuntimeTests(unittest.TestCase):
    def test_run_completes_without_prepare_phase_messages(self):
        provider = _FakeProvider()
        runtime = SubAgentRuntime(
            model_provider=provider,
            tool_registry=ToolRegistry(),
            system_prompt="system",
            max_steps=3,
        )

        result = runtime.run("hello", task_id="subagent_test", run_id="run_1")

        self.assertEqual(result, "done")
        sent_messages = provider.calls[0]["messages"]
        self.assertEqual(sent_messages[0]["content"], "system")
        self.assertEqual(sent_messages[-1]["content"], "hello")
        self.assertTrue(all("Prepare" not in str(message) for message in sent_messages))


if __name__ == "__main__":
    unittest.main()
