from app.core.memory.context_compressor import ContextCompressor
from app.core.memory.llm_context_compressor import LLMContextCompressor
from app.core.model.base import ModelProvider


def build_context_compressor(
    kind: str,
    model_provider: ModelProvider,
    llm_max_tokens: int,
):
    kind_norm = str(kind or "auto").strip().lower()
    if kind_norm == "rule":
        return ContextCompressor()
    if kind_norm == "llm":
        return LLMContextCompressor(
            model_provider=model_provider,
            fallback=ContextCompressor(),
            max_tokens=llm_max_tokens,
        )
    if model_provider.__class__.__name__ == "MockModelProvider":
        return ContextCompressor()
    return LLMContextCompressor(
        model_provider=model_provider,
        fallback=ContextCompressor(),
        max_tokens=llm_max_tokens,
    )
