import sys
import types
import unittest
from unittest.mock import patch

from app.config.runtime_config import RuntimeCompressionConfig
from app.core.model.base import ModelOutput
from app.core.model.mock_provider import MockModelProvider
from app.core.runtime.agent_runtime import AgentRuntime
from app.core.runtime.token_counter import (
    build_request_token_metrics,
    count_chat_input_tokens,
    count_chat_message_tokens,
    count_chat_messages_tokens,
    resolve_encoding_name,
)
from app.core.tools.registry import ToolRegistry


class _FakeEncoding:
    def __init__(self, name: str):
        self.name = name

    def encode(self, text: str):
        return list(text or "")


class _FakeTiktoken(types.SimpleNamespace):
    def encoding_for_model(self, model: str):
        if model in {"unsupported-model", "gpt-5.4"}:
            raise KeyError(model)
        return _FakeEncoding(name=f"enc:{model}")


class TokenCounterTests(unittest.TestCase):
    def test_count_chat_input_tokens_includes_tools_schema(self):
        fake_module = _FakeTiktoken()
        messages = [{"role": "user", "content": "hello"}]
        tools = [
            {
                "name": "read_file",
                "description": "Read a file from disk",
                "parameters": {"type": "object", "properties": {"path": {"type": "string"}}},
            }
        ]
        with patch.dict(sys.modules, {"tiktoken": fake_module}):
            message_tokens = count_chat_messages_tokens(messages=messages, model="gpt-4o-mini")
            total_tokens = count_chat_input_tokens(messages=messages, tools=tools, model="gpt-4o-mini")
        self.assertGreater(total_tokens, message_tokens)

    def test_build_request_token_metrics_excludes_tools_from_input_tokens(self):
        fake_module = _FakeTiktoken()
        messages = [{"role": "user", "content": "hello"}]
        tools = [{"name": "read_file", "parameters": {"type": "object"}}]
        with patch.dict(sys.modules, {"tiktoken": fake_module}):
            metrics = build_request_token_metrics(
                messages=messages,
                tools=tools,
                model="gpt-4o-mini",
                max_output_tokens=20,
            )
        self.assertEqual(metrics["input_tokens"], metrics["messages_tokens"])
        self.assertEqual(
            metrics["total_window_claim_tokens"],
            metrics["messages_tokens"] + metrics["tools_tokens"] + metrics["reserved_output_tokens"],
        )

    def test_count_chat_message_tokens_is_additive_without_reply_primer(self):
        fake_module = _FakeTiktoken()
        messages = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "world"},
        ]
        with patch.dict(sys.modules, {"tiktoken": fake_module}):
            per_message_total = sum(count_chat_message_tokens(message=message, model="gpt-4o-mini") for message in messages)
            full_total = count_chat_messages_tokens(messages=messages, model="gpt-4o-mini")
        self.assertEqual(full_total, per_message_total + 3)

    def test_count_chat_messages_tokens_fails_fast_for_unsupported_model(self):
        fake_module = _FakeTiktoken()
        with patch.dict(sys.modules, {"tiktoken": fake_module}):
            with self.assertRaises(RuntimeError):
                count_chat_messages_tokens(messages=[{"role": "user", "content": "hi"}], model="unsupported-model")

    def test_resolve_encoding_name_falls_back_from_versioned_gpt5_model(self):
        fake_module = _FakeTiktoken()
        with patch.dict(sys.modules, {"tiktoken": fake_module}):
            encoding_name = resolve_encoding_name("gpt-5.4")
        self.assertEqual(encoding_name, "enc:gpt-5")

    def test_count_chat_messages_tokens_falls_back_from_versioned_gpt5_model(self):
        fake_module = _FakeTiktoken()
        messages = [{"role": "user", "content": "hello"}]
        with patch.dict(sys.modules, {"tiktoken": fake_module}):
            total = count_chat_messages_tokens(messages=messages, model="gpt-5.4")
        self.assertGreater(total, 0)

    def test_agent_runtime_emits_model_request_started_before_generate(self):
        provider = MockModelProvider(
            scripted_outputs=[
                {
                    "content": "done",
                    "raw": {"choices": [{"finish_reason": "stop", "message": {"content": "done"}}]},
                }
            ]
        )
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
        )
        events = []

        def _fake_emit_event(**kwargs):
            events.append(kwargs)
            return kwargs

        with (
            patch.object(
                runtime,
                "_build_request_token_metrics",
                return_value={
                    "model": "gpt-4o-mini",
                    "encoding": "enc:gpt-4o-mini",
                    "token_counter_kind": "tiktoken",
                    "messages_tokens": 10,
                    "tools_tokens": 5,
                    "step_input_tokens": 4,
                    "input_tokens": 10,
                    "reserved_output_tokens": 0,
                    "total_window_claim_tokens": 15,
                },
            ),
            patch("app.core.runtime.agent_runtime.emit_event", side_effect=_fake_emit_event),
        ):
            answer = runtime.run("hello", task_id="task_step_tokens", run_id="run_step_tokens")

        self.assertEqual(answer, "done")
        request_events = [e for e in events if e.get("event_type") == "model_request_started"]
        self.assertEqual(len(request_events), 1)
        payload = request_events[0].get("payload", {})
        self.assertEqual(payload.get("step"), 1)
        self.assertEqual(payload.get("input_tokens"), 10)
        self.assertEqual(payload.get("tools_tokens"), 5)


if __name__ == "__main__":
    unittest.main()
