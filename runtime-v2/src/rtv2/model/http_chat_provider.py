"""OpenAI-compatible HTTP chat provider for runtime-v2."""

from __future__ import annotations

import os
import time

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:  # pragma: no cover - optional dependency in minimal test env
    def load_dotenv() -> bool:
        return False

from rtv2.model.base import GenerationConfig, ModelOutput


class HttpChatModelProvider:
    """Minimal OpenAI-compatible chat completions provider."""

    def __init__(
        self,
        *,
        model_id: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout_seconds: int = 120,
        max_retries: int = 4,
        retry_backoff_seconds: float = 1.2,
        default_config: GenerationConfig | None = None,
    ) -> None:
        load_dotenv()

        resolved_model_id = (model_id or os.getenv("LLM_MODEL_ID") or "").strip()
        resolved_api_key = (api_key or os.getenv("LLM_API_KEY") or "").strip()
        resolved_base_url = (base_url or os.getenv("LLM_BASE_URL") or "").strip()

        if not resolved_model_id:
            raise ValueError("Missing required env: LLM_MODEL_ID")
        if not resolved_api_key:
            raise ValueError("Missing required env: LLM_API_KEY")
        if not resolved_base_url:
            raise ValueError("Missing required env: LLM_BASE_URL")

        self.model_id = resolved_model_id
        self.api_key = resolved_api_key
        self.base_url = resolved_base_url
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.retry_backoff_seconds = retry_backoff_seconds
        self.default_config = default_config or GenerationConfig(temperature=0.2, max_tokens=800)

    def generate(
        self,
        messages: list[dict[str, object]],
        tools: list[dict[str, object]],
        config: GenerationConfig | None = None,
    ) -> ModelOutput:
        payload = self._build_payload(messages=messages, tools=tools, config=config)
        return self._post_chat(payload)

    def _build_payload(
        self,
        *,
        messages: list[dict[str, object]],
        tools: list[dict[str, object]],
        config: GenerationConfig | None,
    ) -> dict[str, object]:
        cfg = config or self.default_config
        payload: dict[str, object] = {
            "model": self.model_id,
            "messages": messages,
        }
        if cfg.temperature is not None:
            payload["temperature"] = cfg.temperature
        if cfg.top_p is not None:
            payload["top_p"] = cfg.top_p
        if cfg.max_tokens is not None:
            payload["max_tokens"] = cfg.max_tokens
        if cfg.stop is not None:
            payload["stop"] = cfg.stop
        if cfg.provider_options:
            payload.update(cfg.provider_options)

        serialized_tools = self._to_openai_tools(tools)
        if serialized_tools:
            payload["tools"] = serialized_tools
            payload["tool_choice"] = "auto"
        return payload

    def _post_chat(self, payload: dict[str, object]) -> ModelOutput:
        import httpx

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        url = self.base_url.rstrip("/") + "/chat/completions"

        last_error = ""
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
            except Exception as exc:
                last_error = str(exc)
                if attempt >= self.max_retries:
                    break
                time.sleep(self.retry_backoff_seconds * (2**attempt))

        raise RuntimeError(f"Model request failed after retries: {last_error}")

    @staticmethod
    def _to_openai_tools(tools: list[dict[str, object]]) -> list[dict[str, object]]:
        out: list[dict[str, object]] = []
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
