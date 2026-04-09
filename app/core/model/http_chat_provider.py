import json
import time
from typing import Any, Dict, Iterator, List, Optional

import httpx

from app.config import load_runtime_model_config
from app.core.model.base import GenerationConfig, ModelOutput


class HttpChatModelProvider:
    """OpenAI-compatible chat completions provider via HTTP."""

    def __init__(
        self,
        timeout_seconds: int = 120,
        max_retries: int = 4,
        retry_backoff_seconds: float = 1.2,
        default_config: Optional[GenerationConfig] = None,
    ):
        self.config = load_runtime_model_config()
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.retry_backoff_seconds = retry_backoff_seconds
        self.default_config = default_config or GenerationConfig(temperature=0.2)

    def generate(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        config: Optional[GenerationConfig] = None,
    ) -> ModelOutput:
        payload = self._build_payload(messages=messages, tools=tools, stream=False, config=config)
        return self._post_chat(payload)

    def generate_stream(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        config: Optional[GenerationConfig] = None,
    ) -> Iterator[str]:
        payload = self._build_payload(messages=messages, tools=tools, stream=True, config=config)
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }
        url = self.config.base_url.rstrip("/") + "/chat/completions"

        with httpx.Client(timeout=self.timeout_seconds) as client:
            with client.stream("POST", url, headers=headers, json=payload) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if not line:
                        continue
                    if not line.startswith("data: "):
                        continue
                    data_line = line[6:].strip()
                    if data_line == "[DONE]":
                        break
                    try:
                        data = json.loads(data_line)
                    except Exception:
                        continue
                    delta = (
                        data.get("choices", [{}])[0]
                        .get("delta", {})
                        .get("content", "")
                    )
                    if delta:
                        yield delta

    def _post_chat(self, payload: Dict[str, Any]) -> ModelOutput:
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }
        url = self.config.base_url.rstrip("/") + "/chat/completions"

        last_error: str = ""
        for attempt in range(self.max_retries + 1):
            try:
                with httpx.Client(timeout=self.timeout_seconds) as client:
                    response = client.post(url, headers=headers, json=payload)
                    if response.status_code >= 400:
                        raise RuntimeError(
                            f"HTTP {response.status_code} error: {response.text[:1200]}"
                        )
                    data = response.json()
                content = ""
                choices = data.get("choices", [])
                if choices:
                    message = choices[0].get("message", {}) or {}
                    content = message.get("content", "") or ""
                return ModelOutput(content=content, raw=data)
            except Exception as e:
                last_error = str(e)
                if attempt >= self.max_retries:
                    break
                sleep_seconds = self.retry_backoff_seconds * (2 ** attempt)
                time.sleep(sleep_seconds)

        raise RuntimeError(f"Model request failed after retries: {last_error}")

    def _to_openai_tools(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for tool in tools or []:
            name = str(tool.get("name", "")).strip()
            if not name:
                continue
            out.append(
                {
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": tool.get("description", "") or "",
                        "parameters": tool.get("parameters", {"type": "object", "properties": {}}),
                    },
                }
            )
        return out

    def _build_payload(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        stream: bool,
        config: Optional[GenerationConfig] = None,
    ) -> Dict[str, Any]:
        cfg = config or getattr(self, "default_config", GenerationConfig(temperature=0.2))
        payload: Dict[str, Any] = {
            "model": self.config.model_id,
            "messages": messages,
        }
        if cfg.temperature is not None:
            payload["temperature"] = cfg.temperature
        if cfg.top_p is not None:
            payload["top_p"] = cfg.top_p
        if cfg.presence_penalty is not None:
            payload["presence_penalty"] = cfg.presence_penalty
        if cfg.frequency_penalty is not None:
            payload["frequency_penalty"] = cfg.frequency_penalty
        if cfg.stop is not None:
            payload["stop"] = cfg.stop
        if cfg.seed is not None:
            payload["seed"] = cfg.seed
        if cfg.n is not None:
            payload["n"] = cfg.n
        if cfg.max_tokens is not None:
            payload["max_tokens"] = cfg.max_tokens
        if cfg.enable_thinking is not None:
            # Provider-specific optional flag. Only sent when explicitly configured.
            payload["enable_thinking"] = cfg.enable_thinking
        if cfg.provider_options:
            payload.update(cfg.provider_options)
        if stream:
            payload["stream"] = True

        serialized_tools = self._to_openai_tools(tools)
        # Some providers reject empty tools array; only send tools when non-empty.
        if serialized_tools:
            payload["tools"] = serialized_tools
            payload["tool_choice"] = "auto"
        return payload
