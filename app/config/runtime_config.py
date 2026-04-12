import os
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class RuntimeModelConfig:
    model_id: str
    mini_model_id: str
    api_key: str
    base_url: str


@dataclass(frozen=True)
class RuntimeCompressionConfig:
    enabled_mid_run: bool
    round_interval: int
    light_token_ratio: float
    strong_token_ratio: float
    context_window_tokens: int
    keep_recent_turns: int
    tool_burst_threshold: int
    consistency_guard: bool


def _first_non_empty(*values: Optional[str]) -> str:
    for value in values:
        if value and value.strip():
            return value.strip()
    return ""


def _required(name: str, value: str) -> str:
    if not value:
        raise ValueError(
            f"Missing required model config: {name}. "
            "Please set environment variables LLM_* values."
        )
    return value


def load_runtime_model_config() -> RuntimeModelConfig:
    model_id = _first_non_empty(
        os.getenv("LLM_MODEL_ID"),
    )
    mini_model_id = _first_non_empty(
        os.getenv("LLM_MODEL_MINI_ID"),
        model_id,
    )
    api_key = _first_non_empty(
        os.getenv("LLM_API_KEY"),
    )
    base_url = _first_non_empty(
        os.getenv("LLM_BASE_URL"),
    )

    return RuntimeModelConfig(
        model_id=_required("LLM_MODEL_ID", model_id),
        mini_model_id=_required("LLM_MODEL_MINI_ID", mini_model_id),
        api_key=_required("LLM_API_KEY", api_key),
        base_url=_required("LLM_BASE_URL", base_url),
    )


def _env_bool(name: str, default: bool) -> bool:
    value = (os.getenv(name) or "").strip().lower()
    if not value:
        return default
    return value in {"1", "true", "yes", "y", "on"}


def _env_int(name: str, default: int, min_value: int = 0) -> int:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(value, min_value)


def _env_float(name: str, default: float, min_value: float = 0.0, max_value: float = 1.0) -> float:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    if value < min_value:
        return min_value
    if value > max_value:
        return max_value
    return value


def load_runtime_compression_config() -> RuntimeCompressionConfig:
    return RuntimeCompressionConfig(
        enabled_mid_run=_env_bool("ENABLE_MID_RUN_COMPACTION", True),
        round_interval=_env_int("COMPACTION_ROUND_INTERVAL", 4, min_value=1),
        light_token_ratio=_env_float("COMPACTION_LIGHT_TOKEN_RATIO", 0.70),
        strong_token_ratio=_env_float("COMPACTION_STRONG_TOKEN_RATIO", 0.82),
        context_window_tokens=_env_int("COMPACTION_CONTEXT_WINDOW_TOKENS", 16000, min_value=1024),
        keep_recent_turns=_env_int("COMPACTION_KEEP_RECENT_TURNS", 8, min_value=1),
        tool_burst_threshold=_env_int("COMPACTION_TOOL_BURST_THRESHOLD", 3, min_value=1),
        consistency_guard=_env_bool("COMPACTION_CONSISTENCY_GUARD", True),
    )
