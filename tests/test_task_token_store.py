import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.config.runtime_config import RuntimeCompressionConfig
from app.core.model.mock_provider import MockModelProvider
from app.core.runtime.agent_runtime import AgentRuntime
from app.core.runtime.task_token_store import TaskTokenStore
from app.core.tools.registry import ToolRegistry


class TaskTokenStoreTests(unittest.TestCase):
    def test_task_token_store_records_step_metrics(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = str(Path(td) / "task_token_ledger.db")
            store = TaskTokenStore(db_file=db_path)
            store.record_step_metrics(
                task_id="task_a",
                run_id="run_a",
                step=1,
                metrics={
                    "model": "gpt-4-turbo",
                    "encoding": "cl100k_base",
                    "token_counter_kind": "tiktoken",
                    "messages_tokens": 10,
                    "tools_tokens": 5,
                    "step_input_tokens": 6,
                    "input_tokens": 10,
                    "reserved_output_tokens": 20,
                    "total_window_claim_tokens": 35,
                    "context_usage_ratio": 0.1,
                    "compression_trigger_window_tokens": 120000,
                    "model_context_window_tokens": 160000,
                },
            )
            rows = store.list_task_steps("task_a")
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["step"], 1)
            self.assertEqual(rows[0]["input_tokens"], 10)
            self.assertEqual(rows[0]["step_input_tokens"], 6)

    def test_task_token_store_updates_task_summary(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = str(Path(td) / "task_token_ledger.db")
            store = TaskTokenStore(db_file=db_path)
            for step, request_input_tokens, step_input_tokens in [(1, 15, 8), (2, 25, 12)]:
                store.record_step_metrics(
                    task_id="task_sum",
                    run_id="run_sum",
                    step=step,
                    metrics={
                        "model": "gpt-4-turbo",
                        "encoding": "cl100k_base",
                        "token_counter_kind": "tiktoken",
                        "messages_tokens": request_input_tokens,
                        "tools_tokens": 0,
                        "step_input_tokens": step_input_tokens,
                        "input_tokens": request_input_tokens,
                        "reserved_output_tokens": 10,
                        "total_window_claim_tokens": request_input_tokens + 10,
                        "context_usage_ratio": 0.1,
                        "compression_trigger_window_tokens": 120000,
                        "model_context_window_tokens": 160000,
                    },
                )
            summary = store.get_task_summary("task_sum")
            self.assertEqual(summary.get("total_step_input_tokens"), 20)
            self.assertEqual(summary.get("total_input_tokens"), 40)
            self.assertEqual(summary.get("total_reserved_output_tokens"), 20)
            self.assertEqual(summary.get("total_window_claim_tokens"), 60)
            self.assertEqual(summary.get("peak_step_input_tokens"), 12)
            self.assertEqual(summary.get("peak_input_tokens"), 25)
            self.assertEqual(summary.get("step_count"), 2)

    def test_task_token_store_uses_delta_when_rewriting_same_step(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = str(Path(td) / "task_token_ledger.db")
            store = TaskTokenStore(db_file=db_path)
            initial = {
                "model": "gpt-4-turbo",
                "encoding": "cl100k_base",
                "token_counter_kind": "tiktoken",
                "messages_tokens": 10,
                "tools_tokens": 5,
                "step_input_tokens": 6,
                "input_tokens": 10,
                "reserved_output_tokens": 20,
                "total_window_claim_tokens": 35,
                "context_usage_ratio": 0.1,
                "compression_trigger_window_tokens": 120000,
                "model_context_window_tokens": 160000,
            }
            updated = dict(initial)
            updated["messages_tokens"] = 20
            updated["step_input_tokens"] = 9
            updated["input_tokens"] = 20
            updated["total_window_claim_tokens"] = 45
            store.record_step_metrics(task_id="task_delta", run_id="run_delta", step=1, metrics=initial)
            store.record_step_metrics(task_id="task_delta", run_id="run_delta", step=1, metrics=updated)
            summary = store.get_task_summary("task_delta")
            self.assertEqual(summary.get("total_step_input_tokens"), 9)
            self.assertEqual(summary.get("total_input_tokens"), 20)
            self.assertEqual(summary.get("total_reserved_output_tokens"), 20)
            self.assertEqual(summary.get("total_window_claim_tokens"), 45)
            self.assertEqual(summary.get("step_count"), 1)

    def test_agent_runtime_writes_task_token_step_before_model_generate(self):
        provider = MockModelProvider(
            scripted_outputs=[
                {
                    "content": "done",
                    "raw": {"choices": [{"finish_reason": "stop", "message": {"content": "done"}}]},
                }
            ]
        )
        with tempfile.TemporaryDirectory() as td:
            store = TaskTokenStore(db_file=str(Path(td) / "task_token_ledger.db"))
            runtime = AgentRuntime(
                model_provider=provider,
                tool_registry=ToolRegistry(),
                compression_config=RuntimeCompressionConfig(
                    enabled_mid_run=False,
                    round_interval=4,
                    midrun_token_ratio=0.82,
                    model_context_window_tokens=160000,
                    compression_trigger_window_tokens=120000,
                    keep_recent_turns=8,
                    tool_burst_threshold=5,
                    consistency_guard=True,
                    enable_finalize_compaction=False,
                    target_keep_ratio_midrun=0.40,
                    target_keep_ratio_finalize=0.40,
                    min_keep_turns=3,
                    compressor_kind="auto",
                    compressor_llm_max_tokens=1200,
                    event_summarizer_kind="auto",
                    event_summarizer_max_tokens=280,
                ),
                enable_llm_judge=False,
                trace_steps=False,
                task_token_store=store,
            )
            with patch.object(
                runtime,
                "_build_request_token_metrics",
                return_value={
                    "model": "gpt-4-turbo",
                    "encoding": "cl100k_base",
                    "token_counter_kind": "tiktoken",
                    "messages_tokens": 10,
                    "tools_tokens": 5,
                    "step_input_tokens": 7,
                    "input_tokens": 10,
                    "reserved_output_tokens": 0,
                    "total_window_claim_tokens": 15,
                    "context_usage_ratio": 0.01,
                    "compression_trigger_window_tokens": 120000,
                    "model_context_window_tokens": 160000,
                },
            ), patch.object(runtime, "_count_step_input_tokens", return_value=7):
                answer = runtime.run("hello", task_id="task_runtime_tokens", run_id="run_runtime_tokens")
            self.assertEqual(answer, "done")
            rows = store.list_task_steps("task_runtime_tokens")
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["run_id"], "run_runtime_tokens")
            self.assertEqual(rows[0]["step"], 1)
            self.assertEqual(rows[0]["input_tokens"], 10)
            self.assertEqual(rows[0]["step_input_tokens"], 7)

    def test_task_token_summary_aggregates_multiple_runs_under_same_task(self):
        with tempfile.TemporaryDirectory() as td:
            store = TaskTokenStore(db_file=str(Path(td) / "task_token_ledger.db"))
            store.record_step_metrics(
                task_id="task_multi",
                run_id="run_1",
                step=1,
                metrics={
                    "model": "gpt-4-turbo",
                    "encoding": "cl100k_base",
                    "token_counter_kind": "tiktoken",
                    "messages_tokens": 10,
                    "tools_tokens": 0,
                    "step_input_tokens": 6,
                    "input_tokens": 10,
                    "reserved_output_tokens": 5,
                    "total_window_claim_tokens": 15,
                    "context_usage_ratio": 0.01,
                    "compression_trigger_window_tokens": 120000,
                    "model_context_window_tokens": 160000,
                },
            )
            store.record_step_metrics(
                task_id="task_multi",
                run_id="run_2",
                step=1,
                metrics={
                    "model": "gpt-4-turbo",
                    "encoding": "cl100k_base",
                    "token_counter_kind": "tiktoken",
                    "messages_tokens": 20,
                    "tools_tokens": 0,
                    "step_input_tokens": 8,
                    "input_tokens": 20,
                    "reserved_output_tokens": 5,
                    "total_window_claim_tokens": 25,
                    "context_usage_ratio": 0.02,
                    "compression_trigger_window_tokens": 120000,
                    "model_context_window_tokens": 160000,
                },
            )
            summary = store.get_task_summary("task_multi")
            self.assertEqual(summary.get("total_step_input_tokens"), 14)
            self.assertEqual(summary.get("total_input_tokens"), 30)
            self.assertEqual(summary.get("step_count"), 2)
            self.assertEqual(summary.get("last_run_id"), "run_2")


if __name__ == "__main__":
    unittest.main()
