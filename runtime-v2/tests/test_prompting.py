import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from rtv2.prompting import (
    ExecutionNodePromptContext,
    ExecutionPromptAssembler,
    ExecutionPromptInput,
    FinalizePromptInput,
    PreparePromptInput,
)
from rtv2.state.models import RunPhase


class ExecutionPromptAssemblerTests(unittest.TestCase):
    def test_build_execution_prompt_returns_three_prompt_blocks(self):
        assembler = ExecutionPromptAssembler()

        prompt = assembler.build_execution_prompt(
            ExecutionPromptInput(
                phase=RunPhase.EXECUTE,
                node_context=ExecutionNodePromptContext(
                    user_input="Finish the current task.",
                    goal="Complete runtime-v2 prompting.",
                    active_node_id="node-1",
                    active_node_name="Prompting",
                    active_node_description="Build the prompting module.",
                    active_node_status="running",
                    dependency_summaries=["node-0 | Setup | completed"],
                    artifacts=["artifact-1 | text | prompt draft"],
                    evidence=["evidence-1 | note | discussion summary"],
                    notes=["Keep the prompt light."],
                ),
                runtime_memory_text="## Run run-1\n[user] previous context",
                tool_capability_text="- echo_text: Echo text.",
                finalize_return_input="Verification summary: retry if needed",
            )
        )

        self.assertTrue(prompt.base_prompt.strip())
        self.assertTrue(prompt.phase_prompt.strip())
        self.assertTrue(prompt.dynamic_injection.strip())
        self.assertIn("main runtime-v2 agent executor", prompt.base_prompt)
        self.assertIn("Current phase: execute.", prompt.phase_prompt)
        self.assertIn("User input: Finish the current task.", prompt.dynamic_injection)
        self.assertIn("node-0 | Setup | completed", prompt.dynamic_injection)
        self.assertIn("## Runtime Memory", prompt.dynamic_injection)
        self.assertIn("## Tool Capability Summary", prompt.dynamic_injection)
        self.assertIn("## Finalize Return Input", prompt.dynamic_injection)

    def test_build_execution_prompt_uses_empty_markers_for_missing_dynamic_sections(self):
        assembler = ExecutionPromptAssembler()

        prompt = assembler.build_execution_prompt(
            ExecutionPromptInput(
                phase=RunPhase.EXECUTE,
                node_context=ExecutionNodePromptContext(user_input="Only input."),
            )
        )

        self.assertIn("Goal: (empty)", prompt.dynamic_injection)
        self.assertIn("Dependencies:\n(empty)", prompt.dynamic_injection)
        self.assertIn("Artifacts:\n(empty)", prompt.dynamic_injection)
        self.assertIn("Evidence:\n(empty)", prompt.dynamic_injection)
        self.assertIn("Notes:\n(empty)", prompt.dynamic_injection)
        self.assertIn("## Runtime Memory\n(empty)", prompt.dynamic_injection)
        self.assertIn("## Tool Capability Summary\n(empty)", prompt.dynamic_injection)
        self.assertNotIn("## Finalize Return Input", prompt.dynamic_injection)

    def test_build_prepare_prompt_returns_prepare_specific_contract(self):
        assembler = ExecutionPromptAssembler()

        prepare_prompt = assembler.build_prepare_prompt(
            PreparePromptInput(
                user_input="Plan the runtime work.",
                current_goal="",
                graph_snapshot_text="(empty graph)",
                runtime_memory_text="## Task task-1\n[user] previous context",
                capability_text="- echo_text: Echo text.",
                finalize_return_input="Verification summary: none",
            )
        )
        self.assertIn("Current phase: prepare.", prepare_prompt.phase_prompt)
        self.assertIn("Return JSON only.", prepare_prompt.phase_prompt)
        self.assertIn("User input: Plan the runtime work.", prepare_prompt.dynamic_injection)
        self.assertIn("## Current Graph Snapshot", prepare_prompt.dynamic_injection)
        self.assertIn("## Runtime Memory", prepare_prompt.dynamic_injection)
        self.assertIn("## Capability Summary", prepare_prompt.dynamic_injection)
        self.assertIn("## Finalize Return Input", prepare_prompt.dynamic_injection)

    def test_build_finalize_prompt_returns_finalize_specific_contract(self):
        assembler = ExecutionPromptAssembler()
        finalize_prompt = assembler.build_finalize_prompt(
            FinalizePromptInput(
                user_input="Wrap up the task.",
                goal="Deliver the final result.",
                graph_snapshot_text="Graph id: graph-1",
                runtime_memory_text="## Task task-1\n[user] prior context",
                capability_text="- echo_text: Echo text.",
            )
        )

        self.assertIn("Current phase: finalize.", finalize_prompt.phase_prompt)
        self.assertIn("Return JSON only.", finalize_prompt.phase_prompt)
        self.assertIn("Required top-level keys: final_output, graph_summary.", finalize_prompt.phase_prompt)
        self.assertIn("Goal: Deliver the final result.", finalize_prompt.dynamic_injection)
        self.assertIn("## Current Graph Snapshot", finalize_prompt.dynamic_injection)
        self.assertIn("## Runtime Memory", finalize_prompt.dynamic_injection)


if __name__ == "__main__":
    unittest.main()
