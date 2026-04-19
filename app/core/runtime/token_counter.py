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
    encoding = _get_encoding(model)
    return str(getattr(encoding, "name", "") or model)


def _candidate_model_aliases(model: str) -> List[str]:
    model_norm = str(model or "").strip()
    if not model_norm:
        return []
    aliases: List[str] = [model_norm]

    # Family-level fallback for versioned GPT-5 names such as gpt-5.4, gpt-5-mini-2026-01-01, etc.
    lower = model_norm.lower()
    if lower.startswith("gpt-5"):
        aliases.append("gpt-5")

    # Drop dated/provider suffixes conservatively: foo-bar-2026-01-01 -> foo-bar
    parts = model_norm.split("-")
    if len(parts) >= 4 and all(part.isdigit() for part in parts[-3:]):
        aliases.append("-".join(parts[:-3]))

    deduped: List[str] = []
    seen = set()
    for alias in aliases:
        key = alias.strip()
        if not key or key in seen:
            continue
        deduped.append(key)
        seen.add(key)
    return deduped


def _get_encoding(model: str):
    tiktoken = _require_tiktoken()
    last_error: Exception | None = None
    for candidate in _candidate_model_aliases(model):
        try:
            return tiktoken.encoding_for_model(candidate)
        except KeyError as exc:
            last_error = exc
            continue
    raise RuntimeError(f"Unsupported model for tiktoken encoding resolution: {model}") from last_error


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


def count_chat_message_tokens(message: Dict[str, Any], model: str) -> int:
    encoding = _get_encoding(model)
    tokens_per_message = 3
    tokens_per_name = 1
    total = tokens_per_message
    for key, value in (message or {}).items():
        if key == "tool_calls" and isinstance(value, list):
            encoded_value = _stable_json(value)
        else:
            encoded_value = _stringify_message_value(value)
        total += len(encoding.encode(encoded_value))
        if key == "name":
            total += tokens_per_name
    return max(total, 1)


def count_chat_messages_tokens(
    messages: List[Dict[str, Any]],
    model: str,
    *,
    include_reply_primer: bool = True,
) -> int:
    total = sum(count_chat_message_tokens(message=message, model=model) for message in (messages or []))
    if include_reply_primer:
        total += 3
    return max(total, 1 if include_reply_primer else 0)


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
    input_tokens = messages_tokens
    reserved_output_tokens = max(int(max_output_tokens or 0), 0)
    return {
        "model": model,
        "encoding": resolve_encoding_name(model),
        "token_counter_kind": "tiktoken",
        "messages_tokens": messages_tokens,
        "tools_tokens": tools_tokens,
        "input_tokens": input_tokens,
        "reserved_output_tokens": reserved_output_tokens,
        "total_window_claim_tokens": input_tokens + tools_tokens + reserved_output_tokens,
    }
