from typing import Any, Dict

from app.core.memory.system_memory_store import SystemMemoryStore
from app.core.tools import tool
from app.observability.events import emit_event


@tool(
    name="search_memory_cards",
    description="Search structured system memory cards by query. Read-only.",
    stop_after_tool_call=False,
    requires_confirmation=False,
    cache_results=False,
)
def search_memory_cards(
    query: str = "",
    stage: str = "",
    limit: int = 5,
    include_inactive: bool = False,
    db_file: str = "db/system_memory.db",
) -> Dict[str, Any]:
    safe_limit = max(1, min(int(limit), 50))
    store = SystemMemoryStore(db_file=db_file)
    rows = store.search_cards(
        stage=stage or "",  # kept for backward compatibility; search is stage-agnostic.
        query=query or "",
        limit=safe_limit,
        only_active=not include_inactive,
    )
    return {
        "success": True,
        "count": len(rows),
        "cards": rows,
    }


@tool(
    name="get_memory_card_by_id",
    description="Get one full system memory card by id. Read-only.",
    stop_after_tool_call=False,
    requires_confirmation=False,
    cache_results=False,
)
def get_memory_card_by_id(
    memory_id: str,
    include_inactive: bool = False,
    task_id: str = "",
    run_id: str = "",
    db_file: str = "db/system_memory.db",
) -> Dict[str, Any]:
    store = SystemMemoryStore(db_file=db_file)
    card = store.get_card(card_id=memory_id, only_active=not include_inactive)
    task_id_norm = (task_id or "").strip()
    run_id_norm = (run_id or "").strip()
    if task_id_norm and run_id_norm:
        emit_event(
            task_id=task_id_norm,
            run_id=run_id_norm,
            actor="main",
            role="general",
            event_type="memory_retrieved",
            payload={
                "memory_id": memory_id,
                "score": 1.0 if card else 0.0,
                "mode": "full_fetch",
                "source": "tool_get_memory_card_by_id",
            },
        )
    if not card:
        return {
            "success": True,
            "found": False,
            "memory_id": memory_id,
            "card": None,
        }
    return {
        "success": True,
        "found": True,
        "memory_id": memory_id,
        "card": card,
    }
