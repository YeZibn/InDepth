import json
from typing import Any, Dict, List, Optional

from app.config import load_runtime_model_config


def _require_tiktoken():
    try:
        import tiktoken  # type: ignore
    except ImportError as exc:  # pragma: no cover - exercised via tests with module patching
        raise RuntimeError(
            "tiktoken is required for runtime token counting. "
            "Install project dependencies to enable step-level context accounting."
        ) from exc
    return tiktoken


def resolve_request_model_id(
    config: Any = None,
    model_provider: Any = None,
    default_model: str = "",
) -> str:
    provider_options = getattr(config, "provider_options", {}) if config is not None else {}
    if isinstance(provider_options, dict):
        override = str(provider_options.get("model", "") or "").strip()
        if override:
            return override
    provider_config = getattr(model_provider, "config", None) if model_provider is not None else None
    provider_model = str(getattr(provider_config, "model_id", "") or "").strip()
    if provider_model:
        return provider_model
    try:
        runtime_cfg = load_runtime_model_config()
    except Exception:
        runtime_cfg = None
    model_id = str(getattr(runtime_cfg, "model_id", "") or "").strip() if runtime_cfg is not None else ""
    if model_id:
        return model_id
    if default_model:
        return str(default_model).strip()
    raise RuntimeError("Unable to resolve request model id for token counting.")


def resolve_encoding_name(model: str) -> str:
    tiktoken = _require_tiktoken()
    try:
        encoding = tiktoken.encoding_for_model(model)
    except KeyError as exc:
        raise RuntimeError(f"Unsupported model for tiktoken encoding resolution: {model}") from exc
    return str(getattr(encoding, "name", "") or model)


def _get_encoding(model: str):
    tiktoken = _require_tiktoken()
    try:
        return tiktoken.encoding_for_model(model)
    except KeyError as exc:
        raise RuntimeError(f"Unsupported model for tiktoken encoding resolution: {model}") from exc


def _stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _stringify_message_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (dict, list)):
        return _stable_json(value)
    return str(value)


def count_text_tokens(text: str, model: str) -> int:
    encoding = _get_encoding(model)
    return len(encoding.encode(text or ""))


def count_chat_messages_tokens(messages: List[Dict[str, Any]], model: str) -> int:
    encoding = _get_encoding(model)
    tokens_per_message = 3
    tokens_per_name = 1
    total = 0
    for message in messages or []:
        total += tokens_per_message
        for key, value in (message or {}).items():
            if key == "tool_calls" and isinstance(value, list):
                encoded_value = _stable_json(value)
            else:
                encoded_value = _stringify_message_value(value)
            total += len(encoding.encode(encoded_value))
            if key == "name":
                total += tokens_per_name
    total += 3
    return max(total, 1)


def count_chat_tools_tokens(tools: List[Dict[str, Any]], model: str) -> int:
    if not tools:
        return 0
    encoding = _get_encoding(model)
    rendered = _stable_json(tools)
    return len(encoding.encode(rendered))


def count_chat_input_tokens(messages: List[Dict[str, Any]], tools: List[Dict[str, Any]], model: str) -> int:
    return count_chat_messages_tokens(messages=messages, model=model) + count_chat_tools_tokens(
        tools=tools,
        model=model,
    )


def build_request_token_metrics(
    messages: List[Dict[str, Any]],
    tools: List[Dict[str, Any]],
    model: str,
    max_output_tokens: Optional[int] = None,
) -> Dict[str, Any]:
    messages_tokens = count_chat_messages_tokens(messages=messages, model=model)
    tools_tokens = count_chat_tools_tokens(tools=tools, model=model)
    input_tokens = messages_tokens + tools_tokens
    reserved_output_tokens = max(int(max_output_tokens or 0), 0)
    return {
        "model": model,
        "encoding": resolve_encoding_name(model),
        "token_counter_kind": "tiktoken",
        "messages_tokens": messages_tokens,
        "tools_tokens": tools_tokens,
        "input_tokens": input_tokens,
        "reserved_output_tokens": reserved_output_tokens,
        "total_window_claim_tokens": input_tokens + reserved_output_tokens,
    }
