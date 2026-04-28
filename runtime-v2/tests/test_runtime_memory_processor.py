import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from rtv2.memory import (
    ReflexionTrigger,
    ReplanSignal,
    RuntimeMemoryEntry,
    RuntimeMemoryEntryType,
    RuntimeMemoryProcessor,
    RuntimeMemoryProcessorInput,
    RuntimeMemoryRole,
    SQLiteRuntimeMemoryStore,
)


class RuntimeMemoryProcessorTests(unittest.TestCase):
    def create_store(self) -> SQLiteRuntimeMemoryStore:
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        db_file = str(Path(tmpdir.name) / "runtime_memory.db")
        return SQLiteRuntimeMemoryStore(db_file=db_file)

    def test_build_prompt_context_text_returns_minimal_anchor_when_memory_is_empty(self):
        store = self.create_store()
        processor = RuntimeMemoryProcessor(memory_store=store)

        output = processor.build_prompt_context_text(
            RuntimeMemoryProcessorInput(
                task_id="task-1",
                run_id="run-1",
                current_phase="execute",
                active_node_id="node-1",
                user_input="Continue the task.",
            )
        )

        self.assertIn("Runtime Context Anchor:", output.prompt_context_text)
        self.assertIn("- task_id: task-1", output.prompt_context_text)
        self.assertIn("(no runtime memory entries)", output.prompt_context_text)

    def test_build_prompt_context_text_groups_task_entries_by_run_and_keeps_user_inputs(self):
        store = self.create_store()
        processor = RuntimeMemoryProcessor(memory_store=store)
        store.append_entry(
            RuntimeMemoryEntry(
                entry_id="entry-1",
                task_id="task-1",
                run_id="run-1",
                step_id="step-1",
                node_id="",
                entry_type=RuntimeMemoryEntryType.CONTEXT,
                role=RuntimeMemoryRole.USER,
                content="First run user input.",
                created_at="2026-04-28T21:10:00+08:00",
            )
        )
        store.append_entry(
            RuntimeMemoryEntry(
                entry_id="entry-2",
                task_id="task-1",
                run_id="run-1",
                step_id="step-1",
                node_id="node-1",
                entry_type=RuntimeMemoryEntryType.CONTEXT,
                role=RuntimeMemoryRole.ASSISTANT,
                content="First run assistant reasoning.",
                created_at="2026-04-28T21:10:01+08:00",
            )
        )
        store.append_entry(
            RuntimeMemoryEntry(
                entry_id="entry-3",
                task_id="task-1",
                run_id="run-2",
                step_id="step-1",
                node_id="",
                entry_type=RuntimeMemoryEntryType.CONTEXT,
                role=RuntimeMemoryRole.USER,
                content="Second run user input.",
                created_at="2026-04-28T21:10:02+08:00",
            )
        )

        output = processor.build_prompt_context_text(
            RuntimeMemoryProcessorInput(
                task_id="task-1",
                run_id="run-2",
                current_phase="execute",
                active_node_id="node-2",
                user_input="Second run user input.",
            )
        )

        self.assertIn("## Run run-1", output.prompt_context_text)
        self.assertIn("## Run run-2", output.prompt_context_text)
        self.assertIn("First run user input.", output.prompt_context_text)
        self.assertIn("Second run user input.", output.prompt_context_text)

    def test_build_prompt_context_text_expands_reflexion_fields(self):
        store = self.create_store()
        processor = RuntimeMemoryProcessor(memory_store=store)
        store.append_entry(
            RuntimeMemoryEntry(
                entry_id="entry-1",
                task_id="task-1",
                run_id="run-1",
                step_id="step-2",
                node_id="node-1",
                entry_type=RuntimeMemoryEntryType.REFLEXION,
                role=RuntimeMemoryRole.SYSTEM,
                content="Need a different approach.",
                reflexion_trigger=ReflexionTrigger.FAILED,
                reflexion_reason="tool output was insufficient",
                next_try_hint="inspect file before calling tool again",
                replan_signal=ReplanSignal.SUGGESTED,
                created_at="2026-04-28T21:10:03+08:00",
            )
        )

        output = processor.build_prompt_context_text(
            RuntimeMemoryProcessorInput(
                task_id="task-1",
                run_id="run-1",
                current_phase="execute",
                active_node_id="node-1",
                user_input="Continue the task.",
            )
        )

        self.assertIn("[reflexion][trigger=failed]", output.prompt_context_text)
        self.assertIn("reason=tool output was insufficient", output.prompt_context_text)
        self.assertIn("next_try_hint=inspect file before calling tool again", output.prompt_context_text)
        self.assertIn("replan_signal=suggested", output.prompt_context_text)

    def test_build_prompt_context_text_renders_tool_metadata(self):
        store = self.create_store()
        processor = RuntimeMemoryProcessor(memory_store=store)
        store.append_entry(
            RuntimeMemoryEntry(
                entry_id="entry-1",
                task_id="task-1",
                run_id="run-1",
                step_id="step-1",
                node_id="node-1",
                entry_type=RuntimeMemoryEntryType.CONTEXT,
                role=RuntimeMemoryRole.TOOL,
                content="echo:hello",
                tool_name="echo_text",
                tool_call_id="call-1",
                created_at="2026-04-28T21:10:04+08:00",
            )
        )

        output = processor.build_prompt_context_text(
            RuntimeMemoryProcessorInput(
                task_id="task-1",
                run_id="run-1",
                current_phase="execute",
                active_node_id="node-1",
                user_input="Continue the task.",
            )
        )

        self.assertIn("[tool=echo_text][tool_call_id=call-1] echo:hello", output.prompt_context_text)
