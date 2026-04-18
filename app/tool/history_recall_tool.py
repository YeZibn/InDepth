from typing import Any, Dict, List

from app.core.memory.sqlite_memory_store import SQLiteMemoryStore
from app.core.tools import tool


@tool(
    name="history_recall",
    description="Recall raw runtime history for one execution step using task_id, run_id, and step_id.",
    stop_after_tool_call=False,
    requires_confirmation=False,
    cache_results=False,
)
def history_recall(
    step_id: str,
    run_id: str = "",
    task_id: str = "",
    include_neighbor_steps: bool = False,
    db_file: str = "db/runtime_memory_cli.db",
) -> Dict[str, Any]:
    task_id_norm = str(task_id or "").strip()
    run_id_norm = str(run_id or "").strip()
    step_id_norm = str(step_id or "").strip()
    if not task_id_norm:
        return {"success": False, "error": "task_id is required"}
    if not run_id_norm:
        return {"success": False, "error": "run_id is required"}
    if not step_id_norm:
        return {"success": False, "error": "step_id is required"}

    store = SQLiteMemoryStore(db_file=db_file or "db/runtime_memory_cli.db")
    messages = store.get_messages_for_run_step(
        conversation_id=task_id_norm,
        run_id=run_id_norm,
        step_id=step_id_norm,
    )
    if not messages:
        return {
            "success": True,
            "found": False,
            "task_id": task_id_norm,
            "run_id": run_id_norm,
            "step_id": step_id_norm,
            "reason": "missing_step_metadata_or_no_messages",
            "messages": [],
            "neighbor_steps": [],
        }

    neighbor_steps: List[Dict[str, Any]] = []
    if include_neighbor_steps:
        neighbor_steps = _load_neighbor_step_previews(
            db_file=str(db_file or "db/runtime_memory_cli.db"),
            conversation_id=task_id_norm,
            run_id=run_id_norm,
            step_id=step_id_norm,
        )

    return {
        "success": True,
        "found": True,
        "task_id": task_id_norm,
        "run_id": run_id_norm,
        "step_id": step_id_norm,
        "messages": messages,
        "neighbor_steps": neighbor_steps,
    }


def _load_neighbor_step_previews(
    db_file: str,
    conversation_id: str,
    run_id: str,
    step_id: str,
) -> List[Dict[str, Any]]:
    target = _step_sort_key(step_id)
    if target is None:
        return []
    store = SQLiteMemoryStore(db_file=db_file)
    with store._connect() as conn:
        rows = conn.execute(
            """
            SELECT step_id, MIN(id) AS first_id
            FROM messages
            WHERE conversation_id = ?
              AND run_id = ?
              AND step_id IS NOT NULL
              AND step_id != ''
            GROUP BY step_id
            ORDER BY first_id ASC
            """,
            (conversation_id, run_id),
        ).fetchall()
    ordered = [str(r[0] or "").strip() for r in rows if str(r[0] or "").strip()]
    if step_id not in ordered:
        return []
    idx = ordered.index(step_id)
    out: List[Dict[str, Any]] = []
    for offset in (-1, 1):
        pos = idx + offset
        if pos < 0 or pos >= len(ordered):
            continue
        neighbor_step_id = ordered[pos]
        neighbor_messages = store.get_messages_for_run_step(
            conversation_id=conversation_id,
            run_id=run_id,
            step_id=neighbor_step_id,
        )
        if not neighbor_messages:
            continue
        preview = " ".join([str(x.get("content", "")).strip() for x in neighbor_messages[:2]]).strip()
        out.append(
            {
                "step_id": neighbor_step_id,
                "preview": preview[:200],
                "message_count": len(neighbor_messages),
            }
        )
    return out


def _step_sort_key(step_id: str) -> Any:
    raw = str(step_id or "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return raw
