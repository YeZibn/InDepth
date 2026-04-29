import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from rtv2.memory import RuntimeMemoryQuery, SQLiteRuntimeMemoryStore
from rtv2.model.base import ModelOutput
from rtv2.solver.react_step import ReActStepInput, ReActStepRunner
from rtv2.solver.models import StepStatusSignal
from rtv2.tools import ToolRegistry, tool


class SequenceModelProvider:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls = []

    def generate(self, messages, tools, config=None):
        self.calls.append({"messages": messages, "tools": tools, "config": config})
        if not self.outputs:
            raise AssertionError("No fake model outputs left")
        return self.outputs.pop(0)


@tool(
    name="echo_text",
    description="Echo text.",
    parameters={
        "type": "object",
        "properties": {
            "text": {"type": "string"},
        },
        "required": ["text"],
    },
)
def echo_text(text: str) -> str:
    return f"echo:{text}"


class ReActStepRunnerTests(unittest.TestCase):
    def test_run_step_sends_rendered_step_prompt_as_user_message(self):
        rendered_prompt = "\n".join(
            [
                "## Base Prompt",
                "base",
                "## Phase Prompt",
                "phase",
                "## Dynamic Injection",
                "dynamic",
            ]
        )
        provider = SequenceModelProvider([
            ModelOutput(
                content='{"thought":"need progress","action":"inspect state","observation":"state loaded","status_signal":"progressed","reason":""}',
                raw={},
            )
        ])
        runner = ReActStepRunner(model_provider=provider)

        runner.run_step(ReActStepInput(step_prompt=rendered_prompt))

        self.assertEqual(provider.calls[0]["messages"][1]["role"], "user")
        self.assertEqual(provider.calls[0]["messages"][1]["content"], rendered_prompt)

    def test_run_step_parses_valid_json_output_without_tool(self):
        provider = SequenceModelProvider([
            ModelOutput(
                content='{"thought":"need progress","action":"inspect state","observation":"state loaded","status_signal":"progressed","reason":""}',
                raw={},
            )
        ])
        runner = ReActStepRunner(model_provider=provider)

        output = runner.run_step(ReActStepInput(step_prompt="Do one step."))

        self.assertEqual(output.thought, "need progress")
        self.assertEqual(output.action, "inspect state")
        self.assertEqual(output.observation, "state loaded")
        self.assertIsNone(output.tool_call)
        self.assertIsNotNone(output.step_result)
        self.assertEqual(output.step_result.status_signal, StepStatusSignal.PROGRESSED)
        self.assertEqual(output.step_result.reason, "")
        self.assertEqual(provider.calls[0]["tools"], [])

    def test_run_step_executes_single_tool_call_and_returns_final_step_result(self):
        registry = ToolRegistry()
        registry.register(echo_text)
        provider = SequenceModelProvider([
            ModelOutput(
                content='{"thought":"need file data","action":"call tool","observation":"","tool_call":{"tool_name":"echo_text","arguments":{"text":"hello"}}}',
                raw={},
            ),
            ModelOutput(
                content='{"thought":"tool finished","action":"use tool result","observation":"echo:hello","status_signal":"ready_for_completion","reason":"tool provided enough information"}',
                raw={},
            ),
        ])
        runner = ReActStepRunner(model_provider=provider, tool_registry=registry)

        output = runner.run_step(ReActStepInput(step_prompt="Do one step."))

        self.assertEqual(len(provider.calls), 2)
        self.assertEqual(provider.calls[0]["tools"][0]["name"], "echo_text")
        self.assertEqual(provider.calls[1]["tools"], [])
        self.assertIsNotNone(output.tool_call)
        self.assertEqual(output.tool_call.tool_name, "echo_text")
        self.assertEqual(output.tool_call.arguments, {"text": "hello"})
        self.assertIsNotNone(output.step_result)
        self.assertEqual(output.step_result.status_signal, StepStatusSignal.READY_FOR_COMPLETION)
        self.assertEqual(output.observation, "echo:hello")
        self.assertIn("Tool result:\necho:hello", provider.calls[1]["messages"][-1]["content"])

    def test_run_step_marks_failed_when_json_is_invalid(self):
        provider = SequenceModelProvider([
            ModelOutput(content="not json", raw={})
        ])
        runner = ReActStepRunner(model_provider=provider)

        output = runner.run_step(ReActStepInput(step_prompt="Do one step."))

        self.assertIsNotNone(output.step_result)
        self.assertEqual(output.step_result.status_signal, StepStatusSignal.FAILED)
        self.assertEqual(output.step_result.reason, "react step output was not valid json")
        self.assertEqual(output.observation, "not json")

    def test_run_step_accepts_fenced_json(self):
        provider = SequenceModelProvider([
            ModelOutput(
                content='```json\n{"thought":"t","action":"a","observation":"o","status_signal":"blocked","reason":"need tool"}\n```',
                raw={},
            )
        ])
        runner = ReActStepRunner(model_provider=provider)

        output = runner.run_step(ReActStepInput(step_prompt="Do one step."))

        self.assertIsNotNone(output.step_result)
        self.assertEqual(output.step_result.status_signal, StepStatusSignal.BLOCKED)
        self.assertEqual(output.step_result.reason, "need tool")

    def test_run_step_fails_when_tool_requested_without_executor(self):
        provider = SequenceModelProvider([
            ModelOutput(
                content='{"thought":"need tool","action":"call tool","observation":"","tool_call":{"tool_name":"echo_text","arguments":{"text":"hello"}}}',
                raw={},
            )
        ])
        runner = ReActStepRunner(model_provider=provider)

        output = runner.run_step(ReActStepInput(step_prompt="Do one step."))

        self.assertIsNotNone(output.step_result)
        self.assertEqual(output.step_result.status_signal, StepStatusSignal.FAILED)
        self.assertEqual(
            output.step_result.reason,
            "react step requested a tool call but no tool executor is configured",
        )

    def test_run_step_fails_when_second_round_returns_another_tool_call(self):
        registry = ToolRegistry()
        registry.register(echo_text)
        provider = SequenceModelProvider([
            ModelOutput(
                content='{"thought":"need tool","action":"call tool","observation":"","tool_call":{"tool_name":"echo_text","arguments":{"text":"hello"}}}',
                raw={},
            ),
            ModelOutput(
                content='{"thought":"still need tool","action":"call another","observation":"","tool_call":{"tool_name":"echo_text","arguments":{"text":"again"}}}',
                raw={},
            ),
        ])
        runner = ReActStepRunner(model_provider=provider, tool_registry=registry)

        output = runner.run_step(ReActStepInput(step_prompt="Do one step."))

        self.assertIsNotNone(output.step_result)
        self.assertEqual(output.step_result.status_signal, StepStatusSignal.FAILED)
        self.assertEqual(
            output.step_result.reason,
            "react step returned an unexpected second tool call",
        )

    def test_run_step_persists_assistant_and_tool_entries_when_memory_store_is_configured(self):
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        memory_store = SQLiteRuntimeMemoryStore(db_file=str(Path(tmpdir.name) / "runtime_memory.db"))
        registry = ToolRegistry()
        registry.register(echo_text)
        provider = SequenceModelProvider([
            ModelOutput(
                content='{"thought":"need file data","action":"call tool","observation":"","tool_call":{"tool_name":"echo_text","arguments":{"text":"hello"}}}',
                raw={},
            ),
            ModelOutput(
                content='{"thought":"tool finished","action":"use tool result","observation":"echo:hello","status_signal":"ready_for_completion","reason":"tool provided enough information"}',
                raw={},
            ),
        ])
        runner = ReActStepRunner(
            model_provider=provider,
            tool_registry=registry,
            memory_store=memory_store,
        )

        runner.run_step(
            ReActStepInput(
                step_prompt="Do one step.",
                task_id="task-1",
                run_id="run-1",
                step_id="step-1",
                node_id="node-1",
            )
        )

        entries = memory_store.list_entries(RuntimeMemoryQuery(task_id="task-1", run_id="run-1"))
        self.assertEqual(len(entries), 3)
        self.assertEqual(entries[0].role.value, "assistant")
        self.assertEqual(entries[0].tool_name, "echo_text")
        self.assertEqual(entries[1].role.value, "tool")
        self.assertEqual(entries[1].content, "echo:hello")
        self.assertEqual(entries[2].role.value, "assistant")
        self.assertIn("thought: tool finished", entries[2].content)


if __name__ == "__main__":
    unittest.main()
