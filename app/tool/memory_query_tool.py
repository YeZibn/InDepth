from typing import Any, Dict

from app.core.memory.system_memory_store import SystemMemoryStore
from app.core.tools import tool


@tool(
    name="search_memory_cards",
    description="Search structured system memory cards by stage and query. Read-only.",
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
        stage=stage or "",
        query=query or "",
        limit=safe_limit,
        only_active=not include_inactive,
    )
    return {
        "success": True,
        "count": len(rows),
        "cards": rows,
    }
