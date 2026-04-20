from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol

from app.config import RuntimeSystemMemoryVectorConfig


@dataclass(frozen=True)
class MemoryVectorSearchHit:
    memory_id: str
    score: float


class MemoryVectorIndexStore(Protocol):
    def upsert_memory_vector(
        self,
        memory_id: str,
        vector_text: str,
        embedding: List[float],
        model: str,
    ) -> None:
        """Persist or overwrite a memory vector index row."""

    def search_memory_vectors(self, query_embedding: List[float], top_k: int) -> List[MemoryVectorSearchHit]:
        """Search memory vectors by query embedding."""

    def delete_memory_vector(self, memory_id: str) -> None:
        """Delete a memory vector by its bound memory_id."""


class MilvusMemoryIndexStore:
    """Milvus-backed vector index for system memory cards."""

    def __init__(self, vector_config: RuntimeSystemMemoryVectorConfig):
        self.vector_config = vector_config
        self._client = None

    def upsert_memory_vector(
        self,
        memory_id: str,
        vector_text: str,
        embedding: List[float],
        model: str,
    ) -> None:
        client = self._get_client()
        self._ensure_collection(client)
        client.upsert(
            collection_name=self.vector_config.collection_name,
            data=[
                {
                    "memory_id": str(memory_id or "").strip(),
                    "embedding": [float(x) for x in embedding],
                    "vector_text": str(vector_text or "").strip(),
                    "vector_model": str(model or "").strip(),
                }
            ],
        )

    def search_memory_vectors(self, query_embedding: List[float], top_k: int) -> List[MemoryVectorSearchHit]:
        client = self._get_client()
        self._ensure_collection(client)
        results = client.search(
            collection_name=self.vector_config.collection_name,
            data=[[float(x) for x in query_embedding]],
            limit=max(1, int(top_k)),
            output_fields=["memory_id"],
        )
        rows = results[0] if isinstance(results, list) and results else []
        hits: List[MemoryVectorSearchHit] = []
        for row in rows:
            entity = row.get("entity", {}) if isinstance(row, dict) else {}
            memory_id = str(entity.get("memory_id", "") or row.get("id", "") or "").strip()
            if not memory_id:
                continue
            try:
                score = float(row.get("distance", row.get("score", 0.0)) or 0.0)
            except Exception:
                score = 0.0
            hits.append(MemoryVectorSearchHit(memory_id=memory_id, score=score))
        hits.sort(key=lambda item: item.score, reverse=True)
        return hits

    def delete_memory_vector(self, memory_id: str) -> None:
        target = str(memory_id or "").strip()
        if not target:
            return
        client = self._get_client()
        self._ensure_collection(client)
        client.delete(collection_name=self.vector_config.collection_name, ids=[target])

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            from pymilvus import MilvusClient
        except Exception as exc:
            raise RuntimeError(f"pymilvus unavailable: {exc}")
        kwargs: Dict[str, Any] = {"uri": self.vector_config.milvus_uri}
        token = str(self.vector_config.milvus_token or "").strip()
        if token:
            kwargs["token"] = token
        self._client = MilvusClient(**kwargs)
        return self._client

    def _ensure_collection(self, client: Any) -> None:
        if client.has_collection(collection_name=self.vector_config.collection_name):
            return
        client.create_collection(
            collection_name=self.vector_config.collection_name,
            dimension=int(self.vector_config.embedding_dim),
            primary_field_name="memory_id",
            id_type="string",
            max_length=255,
            vector_field_name="embedding",
            metric_type="COSINE",
            auto_id=False,
            enable_dynamic_field=True,
        )


def build_system_memory_vector_index_store(
    vector_config: Optional[RuntimeSystemMemoryVectorConfig],
) -> Optional[MemoryVectorIndexStore]:
    cfg = vector_config
    if cfg is None or not cfg.enabled:
        return None
    if not str(cfg.milvus_uri or "").strip():
        return None
    try:
        return MilvusMemoryIndexStore(vector_config=cfg)
    except Exception:
        return None
