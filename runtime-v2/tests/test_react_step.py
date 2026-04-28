import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from rtv2.model.base import ModelOutput
from rtv2.solver.react_step import ReActStepInput, ReActStepRunner
from rtv2.solver.models import StepStatusSignal


class FakeModelProvider:
    def __init__(self, content: str) -> None:
        self.content = content

    def generate(self, messages, tools, config=None):
        return ModelOutput(content=self.content, raw={"messages": messages, "tools": tools})


class ReActStepRunnerTests(unittest.TestCase):
    def test_run_step_parses_valid_json_output(self):
        provider = FakeModelProvider(
            '{"thought":"need progress","action":"inspect state","observation":"state loaded","status_signal":"progressed","reason":""}'
        )
        runner = ReActStepRunner(model_provider=provider)

        output = runner.run_step(ReActStepInput(step_prompt="Do one step."))

        self.assertEqual(output.thought, "need progress")
        self.assertEqual(output.action, "inspect state")
        self.assertEqual(output.observation, "state loaded")
        self.assertEqual(output.step_result.status_signal, StepStatusSignal.PROGRESSED)
        self.assertEqual(output.step_result.reason, "")

    def test_run_step_marks_failed_when_json_is_invalid(self):
        provider = FakeModelProvider("not json")
        runner = ReActStepRunner(model_provider=provider)

        output = runner.run_step(ReActStepInput(step_prompt="Do one step."))

        self.assertEqual(output.step_result.status_signal, StepStatusSignal.FAILED)
        self.assertEqual(output.step_result.reason, "react step output was not valid json")
        self.assertEqual(output.observation, "not json")

    def test_run_step_accepts_fenced_json(self):
        provider = FakeModelProvider(
            '```json\n{"thought":"t","action":"a","observation":"o","status_signal":"blocked","reason":"need tool"}\n```'
        )
        runner = ReActStepRunner(model_provider=provider)

        output = runner.run_step(ReActStepInput(step_prompt="Do one step."))

        self.assertEqual(output.step_result.status_signal, StepStatusSignal.BLOCKED)
        self.assertEqual(output.step_result.reason, "need tool")


if __name__ == "__main__":
    unittest.main()
