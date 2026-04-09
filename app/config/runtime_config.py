import os
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class RuntimeModelConfig:
    model_id: str
    mini_model_id: str
    api_key: str
    base_url: str


def _first_non_empty(*values: Optional[str]) -> str:
    for value in values:
        if value and value.strip():
            return value.strip()
    return ""


def _required(name: str, value: str) -> str:
    if not value:
        raise ValueError(
            f"Missing required model config: {name}. "
            "Please set environment variables CODEX_* or fallback LLM_* values."
        )
    return value


def load_runtime_model_config() -> RuntimeModelConfig:
    model_id = _first_non_empty(
        os.getenv("CODEX_MODEL_ID"),
        os.getenv("LLM_MODEL_ID"),
    )
    mini_model_id = _first_non_empty(
        os.getenv("CODEX_MODEL_MINI_ID"),
        os.getenv("LLM_MODEL_MINI_ID"),
        model_id,
    )
    api_key = _first_non_empty(
        os.getenv("CODEX_API_KEY"),
        os.getenv("LLM_API_KEY"),
    )
    base_url = _first_non_empty(
        os.getenv("CODEX_BASE_URL"),
        os.getenv("LLM_BASE_URL"),
    )

    return RuntimeModelConfig(
        model_id=_required("CODEX_MODEL_ID/LLM_MODEL_ID", model_id),
        mini_model_id=_required("CODEX_MODEL_MINI_ID/LLM_MODEL_MINI_ID", mini_model_id),
        api_key=_required("CODEX_API_KEY/LLM_API_KEY", api_key),
        base_url=_required("CODEX_BASE_URL/LLM_BASE_URL", base_url),
    )
