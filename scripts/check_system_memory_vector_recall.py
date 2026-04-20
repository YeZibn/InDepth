import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from dotenv import load_dotenv

from app.config import load_runtime_system_memory_vector_config
from app.core.memory.embedding_provider import build_system_memory_embedding_provider
from app.core.memory.vector_index_store import build_system_memory_vector_index_store


def main() -> int:
    load_dotenv()
    cfg = load_runtime_system_memory_vector_config()
    print("[Config]")
    print(f"enabled={cfg.enabled}")
    print(f"embedding_model_id={cfg.embedding_model_id or '<empty>'}")
    print(f"embedding_base_url={cfg.embedding_base_url or '<empty>'}")
    print(f"embedding_api_key={'<set>' if cfg.embedding_api_key else '<empty>'}")
    print(f"milvus_uri={cfg.milvus_uri or '<empty>'}")
    print(f"collection_name={cfg.collection_name}")
    print(f"embedding_dim={cfg.embedding_dim}")
    print(f"search_top_n={cfg.search_top_n}")
    print(f"recall_top_k={cfg.recall_top_k}")
    print(f"min_score={cfg.min_score}")

    if not cfg.enabled:
        print("\n[Skip] ENABLE_SYSTEM_MEMORY_VECTOR_RECALL is false.")
        return 1

    embedding_provider = build_system_memory_embedding_provider(cfg)
    if embedding_provider is None:
        print("\n[Error] Failed to build embedding provider. Check LLM_* and LLM_EMBEDDING_MODEL_ID.")
        return 2

    vector_index = build_system_memory_vector_index_store(cfg)
    if vector_index is None:
        print("\n[Error] Failed to build Milvus vector index store. Check SYSTEM_MEMORY_MILVUS_URI.")
        return 3

    print("\n[Check] Requesting query embedding...")
    query = "系统记忆向量召回连通性检查"
    try:
        embedding = embedding_provider.embed_text(query)
    except Exception as exc:
        print(f"[Error] Embedding request failed: {exc}")
        return 4
    print(f"[OK] Embedding length={len(embedding)}")

    print("[Check] Querying Milvus collection...")
    try:
        hits = vector_index.search_memory_vectors(query_embedding=embedding, top_k=1)
    except Exception as exc:
        print(f"[Error] Milvus query failed: {exc}")
        return 5
    print(f"[OK] Milvus reachable. hits={len(hits)}")
    print("\nSystem memory vector recall dependencies look ready.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
