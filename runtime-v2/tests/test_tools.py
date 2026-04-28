import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from rtv2.tools import LocalToolExecutor, ToolCall, ToolRegistry, tool


@tool(
    name="echo_text",
    description="Echo the provided text.",
    parameters={
        "type": "object",
        "properties": {
            "text": {"type": "string"},
        },
        "required": ["text"],
    },
)
def echo_text(text: str) -> str:
    return text


def uppercase_input_hook(tool_name, args, next_handler):
    updated_args = dict(args)
    if "text" in updated_args and isinstance(updated_args["text"], str):
        updated_args["text"] = str(updated_args["text"]).upper()
    return next_handler(updated_args)


def suffix_output_hook(tool_name, args, next_handler):
    result = next_handler(args)
    return f"{result} [{tool_name}]"


@tool(
    name="echo_with_hooks",
    description="Echo text with hook chain.",
    parameters={
        "type": "object",
        "properties": {
            "text": {"type": "string"},
        },
        "required": ["text"],
    },
    hooks=[uppercase_input_hook, suffix_output_hook],
)
def echo_with_hooks(text: str) -> str:
    return text


@tool(
    name="structured_echo",
    description="Return a structured object.",
    parameters={
        "type": "object",
        "properties": {
            "text": {"type": "string"},
        },
        "required": ["text"],
    },
)
def structured_echo(text: str) -> dict[str, str]:
    return {"echo": text}


class LocalToolExecutorTests(unittest.TestCase):
    def create_executor(self) -> LocalToolExecutor:
        registry = ToolRegistry()
        registry.register(echo_text)
        registry.register(echo_with_hooks)
        registry.register(structured_echo)
        return LocalToolExecutor(tool_registry=registry)

    def test_tool_registry_lists_registered_tool_schemas(self):
        registry = ToolRegistry()
        registry.register(echo_text)

        schemas = registry.list_tool_schemas()

        self.assertEqual(len(schemas), 1)
        self.assertEqual(schemas[0]["name"], "echo_text")
        self.assertEqual(schemas[0]["description"], "Echo the provided text.")

    def test_execute_runs_registered_tool(self):
        executor = self.create_executor()

        result = executor.execute(ToolCall(tool_name="echo_text", arguments={"text": "hello"}))

        self.assertTrue(result.success)
        self.assertEqual(result.output_text, "hello")
        self.assertEqual(result.error, "")

    def test_execute_returns_error_for_unknown_tool(self):
        executor = self.create_executor()

        result = executor.execute(ToolCall(tool_name="missing_tool", arguments={}))

        self.assertFalse(result.success)
        self.assertEqual(result.error, "Unknown tool: missing_tool")

    def test_execute_returns_error_when_required_fields_are_missing(self):
        executor = self.create_executor()

        result = executor.execute(ToolCall(tool_name="echo_text", arguments={}))

        self.assertFalse(result.success)
        self.assertEqual(result.error, "Tool arguments missing required fields: text")

    def test_execute_applies_hook_chain_to_args_and_result(self):
        executor = self.create_executor()

        result = executor.execute(ToolCall(tool_name="echo_with_hooks", arguments={"text": "hello"}))

        self.assertTrue(result.success)
        self.assertEqual(result.output_text, "HELLO [echo_with_hooks]")

    def test_execute_serializes_non_string_result_to_output_text(self):
        executor = self.create_executor()

        result = executor.execute(ToolCall(tool_name="structured_echo", arguments={"text": "hello"}))

        self.assertTrue(result.success)
        self.assertEqual(result.output_text, '{"echo": "hello"}')


if __name__ == "__main__":
    unittest.main()
