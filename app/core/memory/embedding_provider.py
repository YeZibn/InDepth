import time
from typing import List, Optional, Protocol

import httpx

from app.config import RuntimeSystemMemoryVectorConfig


class MemoryEmbeddingProvider(Protocol):
    def embed_text(self, text: str) -> List[float]:
        """Return a dense vector for the given text."""


class HttpEmbeddingModelProvider:
    """OpenAI-compatible embeddings provider used by system memory recall."""

    def __init__(
        self,
        vector_config: RuntimeSystemMemoryVectorConfig,
        timeout_seconds: int = 60,
        max_retries: int = 3,
        retry_backoff_seconds: float = 1.0,
    ):
        self.vector_config = vector_config
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.retry_backoff_seconds = retry_backoff_seconds

    def embed_text(self, text: str) -> List[float]:
        payload = {
            "model": self.vector_config.embedding_model_id,
            "input": str(text or "").strip(),
        }
        headers = {
            "Authorization": f"Bearer {self.vector_config.embedding_api_key}",
            "Content-Type": "application/json",
        }
        url = self.vector_config.embedding_base_url.rstrip("/") + "/embeddings"

        last_error = ""
        for attempt in range(self.max_retries + 1):
            try:
                with httpx.Client(timeout=self.timeout_seconds) as client:
                    response = client.post(url, headers=headers, json=payload)
                    if response.status_code >= 400:
                        raise RuntimeError(f"HTTP {response.status_code} error: {response.text[:800]}")
                    data = response.json()
                rows = data.get("data", [])
                if not rows:
                    raise RuntimeError("missing embedding data")
                embedding = rows[0].get("embedding", [])
                if not isinstance(embedding, list) or not embedding:
                    raise RuntimeError("invalid embedding payload")
                return [float(x) for x in embedding]
            except Exception as exc:
                last_error = str(exc)
                if attempt >= self.max_retries:
                    break
                time.sleep(self.retry_backoff_seconds * (2 ** attempt))
        raise RuntimeError(f"Embedding request failed after retries: {last_error}")


def build_system_memory_embedding_provider(
    vector_config: Optional[RuntimeSystemMemoryVectorConfig],
) -> Optional[MemoryEmbeddingProvider]:
    cfg = vector_config
    if cfg is None or not cfg.enabled:
        return None
    if not str(cfg.embedding_model_id or "").strip():
        return None
    if not str(cfg.embedding_api_key or "").strip():
        return None
    if not str(cfg.embedding_base_url or "").strip():
        return None
    try:
        return HttpEmbeddingModelProvider(vector_config=cfg)
    except Exception:
        return None
