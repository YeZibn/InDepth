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
    midrun_token_ratio: float
    model_context_window_tokens: int
    compression_trigger_window_tokens: int
    keep_recent_turns: int
    tool_burst_threshold: int
    consistency_guard: bool
    enable_finalize_compaction: bool
    target_keep_ratio_midrun: float
    target_keep_ratio_finalize: float
    min_keep_turns: int
    compressor_kind: str
    compressor_llm_max_tokens: int
    event_summarizer_kind: str
    event_summarizer_max_tokens: int

    @property
    def context_window_tokens(self) -> int:
        # Legacy alias retained for gradual migration; maps to trigger budget semantics.
        return self.compression_trigger_window_tokens


@dataclass(frozen=True)
class RuntimeUserPreferenceConfig:
    enabled: bool
    file_path: str
    recall_top_k: int
    always_include_keys: tuple[str, ...]
    max_inject_chars: int
    enable_llm_extract: bool
    auto_write_min_confidence: float
    conflict_min_confidence: float


@dataclass(frozen=True)
class RuntimeSystemMemoryVectorConfig:
    enabled: bool
    embedding_model_id: str
    embedding_api_key: str
    embedding_base_url: str
    milvus_uri: str
    milvus_token: str
    collection_name: str
    embedding_dim: int
    search_top_n: int
    recall_top_k: int
    min_score: float


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


def _env_float_alias(
    primary_name: str,
    legacy_name: str,
    default: float,
    min_value: float = 0.0,
    max_value: float = 1.0,
) -> float:
    primary_raw = (os.getenv(primary_name) or "").strip()
    if primary_raw:
        return _env_float(primary_name, default, min_value=min_value, max_value=max_value)
    legacy_raw = (os.getenv(legacy_name) or "").strip()
    if legacy_raw:
        return _env_float(legacy_name, default, min_value=min_value, max_value=max_value)
    return default


def load_runtime_compression_config() -> RuntimeCompressionConfig:
    legacy_context_window = _env_int("COMPACTION_CONTEXT_WINDOW_TOKENS", 0, min_value=1024)
    model_context_window_tokens = _env_int(
        "MODEL_CONTEXT_WINDOW_TOKENS",
        legacy_context_window or 160000,
        min_value=1024,
    )
    compression_trigger_window_tokens = _env_int(
        "COMPACTION_TRIGGER_WINDOW_TOKENS",
        legacy_context_window or 120000,
        min_value=1024,
    )
    return RuntimeCompressionConfig(
        enabled_mid_run=_env_bool("ENABLE_MID_RUN_COMPACTION", True),
        round_interval=_env_int("COMPACTION_ROUND_INTERVAL", 4, min_value=1),
        midrun_token_ratio=_env_float_alias("COMPACTION_MIDRUN_TOKEN_RATIO", "COMPACTION_STRONG_TOKEN_RATIO", 0.82),
        model_context_window_tokens=model_context_window_tokens,
        compression_trigger_window_tokens=compression_trigger_window_tokens,
        keep_recent_turns=_env_int("COMPACTION_KEEP_RECENT_TURNS", 8, min_value=1),
        tool_burst_threshold=_env_int("COMPACTION_TOOL_BURST_THRESHOLD", 5, min_value=1),
        consistency_guard=_env_bool("COMPACTION_CONSISTENCY_GUARD", True),
        enable_finalize_compaction=_env_bool("ENABLE_FINALIZE_COMPACTION", False),
        target_keep_ratio_midrun=_env_float_alias(
            "COMPACTION_TARGET_KEEP_RATIO_MIDRUN",
            "COMPACTION_TARGET_KEEP_RATIO_STRONG",
            0.45,
        ),
        target_keep_ratio_finalize=_env_float("COMPACTION_TARGET_KEEP_RATIO_FINALIZE", 0.45),
        min_keep_turns=_env_int("COMPACTION_MIN_KEEP_TURNS", 3, min_value=1),
        compressor_kind=(os.getenv("COMPACTION_COMPRESSOR_KIND") or "auto").strip().lower() or "auto",
        compressor_llm_max_tokens=_env_int("COMPACTION_COMPRESSOR_LLM_MAX_TOKENS", 1200, min_value=200),
        event_summarizer_kind=(os.getenv("COMPACTION_EVENT_SUMMARIZER_KIND") or "auto").strip().lower() or "auto",
        event_summarizer_max_tokens=_env_int("COMPACTION_EVENT_SUMMARIZER_MAX_TOKENS", 280, min_value=120),
    )


def load_runtime_user_preference_config() -> RuntimeUserPreferenceConfig:
    file_path = _first_non_empty(
        os.getenv("USER_PREFERENCE_FILE_PATH"),
        "memory/preferences/user-preferences.md",
    )
    keys_raw = _first_non_empty(
        os.getenv("USER_PREFERENCE_ALWAYS_INCLUDE_KEYS"),
        "language_preference,response_style",
    )
    keys = tuple([x.strip() for x in keys_raw.split(",") if x.strip()])
    return RuntimeUserPreferenceConfig(
        enabled=_env_bool("ENABLE_USER_PREFERENCE_MEMORY", True),
        file_path=file_path,
        recall_top_k=_env_int("USER_PREFERENCE_RECALL_TOP_K", 5, min_value=1),
        always_include_keys=keys,
        max_inject_chars=_env_int("USER_PREFERENCE_MAX_INJECT_CHARS", 240, min_value=40),
        enable_llm_extract=_env_bool("ENABLE_USER_PREFERENCE_LLM_EXTRACT", True),
        auto_write_min_confidence=_env_float("USER_PREFERENCE_AUTO_WRITE_MIN_CONFIDENCE", 0.75),
        conflict_min_confidence=_env_float("USER_PREFERENCE_CONFLICT_MIN_CONFIDENCE", 0.90),
    )


def load_runtime_system_memory_vector_config() -> RuntimeSystemMemoryVectorConfig:
    embedding_model_id = _first_non_empty(
        os.getenv("LLM_EMBEDDING_MODEL_ID"),
        os.getenv("LLM_MODEL_MINI_ID"),
        os.getenv("LLM_MODEL_ID"),
    )
    return RuntimeSystemMemoryVectorConfig(
        enabled=_env_bool("ENABLE_SYSTEM_MEMORY_VECTOR_RECALL", False),
        embedding_model_id=embedding_model_id,
        embedding_api_key=_first_non_empty(
            os.getenv("LLM_EMBEDDING_API_KEY"),
            os.getenv("LLM_API_KEY"),
        ),
        embedding_base_url=_first_non_empty(
            os.getenv("LLM_EMBEDDING_BASE_URL"),
            os.getenv("LLM_BASE_URL"),
        ),
        milvus_uri=_first_non_empty(os.getenv("SYSTEM_MEMORY_MILVUS_URI")),
        milvus_token=_first_non_empty(os.getenv("SYSTEM_MEMORY_MILVUS_TOKEN")),
        collection_name=_first_non_empty(
            os.getenv("SYSTEM_MEMORY_MILVUS_COLLECTION"),
            "system_memory_card_embedding",
        ),
        embedding_dim=_env_int("SYSTEM_MEMORY_EMBEDDING_DIM", 1536, min_value=8),
        search_top_n=_env_int("SYSTEM_MEMORY_VECTOR_TOP_N", 10, min_value=1),
        recall_top_k=_env_int("SYSTEM_MEMORY_RECALL_TOP_K", 5, min_value=1),
        min_score=_env_float("SYSTEM_MEMORY_RECALL_MIN_SCORE", 0.65),
    )
