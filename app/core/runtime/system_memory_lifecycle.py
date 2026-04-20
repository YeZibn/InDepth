from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

from app.core.memory.memory_metadata_service import extract_title_topic
from app.core.memory.recall_service import (
    build_memory_reranker_config,
    build_recall_query,
    render_memory_recall_block,
    rerank_memory_candidates_llm,
)
from app.core.memory.system_memory_store import SystemMemoryStore
from app.core.model.base import ModelProvider


# 这个模块保留在 runtime 下，是因为它表达的是“system memory 在 runtime 生命周期中的触发时机”。
# 真正的 recall / rerank 能力已经下沉到 memory 目录，本模块只负责装配它们。


def finalize_task_memory(
    task_id: str,
    run_id: str,
    user_input: str,
    final_answer: str,
    stop_reason: str,
    runtime_status: str,
    tool_failures: List[Dict[str, str]],
    verification_handoff: Dict[str, Any],
    system_memory_store: Optional[SystemMemoryStore],
    preview: Callable[[str, int], str],
    slug: Callable[[str], str],
    emit_event: Callable[..., Dict[str, Any]],
) -> None:
    try:
        store = system_memory_store or SystemMemoryStore()
    except Exception:
        return

    now = datetime.now().astimezone()
    expire_at = (now.date() + timedelta(days=180)).isoformat()
    mem_id = f"mem_task_{slug(task_id)}_{slug(run_id)}"
    stage = "postmortem"
    handoff = verification_handoff if isinstance(verification_handoff, dict) else {}
    memory_seed = handoff.get("memory_seed", {}) if isinstance(handoff.get("memory_seed", {}), dict) else {}
    title = preview(str(memory_seed.get("title", "") or "").strip(), 120)
    recall_hint = preview(str(memory_seed.get("recall_hint", "") or "").strip(), 220)
    content = preview(str(memory_seed.get("content", "") or "").strip(), 500)
    if not any([title, recall_hint, content]):
        return
    risk_level = "P1" if runtime_status == "error" else "P3"

    card = {
        "id": mem_id,
        "title": title,
        "recall_hint": recall_hint,
        "content": content,
        "lifecycle": {
            "status": "active",
            "expire_at": expire_at,
        },
    }
    try:
        store.upsert_card(card)
    except Exception:
        return

    try:
        triggered = emit_event(
            task_id=task_id,
            run_id=run_id,
            actor="main",
            role="general",
            event_type="memory_triggered",
            payload={
                "stage": stage,
                "context_id": run_id,
                "risk_level": risk_level,
                "source": "runtime_forced_finalize",
                "source_event": "runtime_forced_finalize",
            },
        )
        trigger_event_id = str(triggered.get("event_id", "")).strip()
        if trigger_event_id:
            emit_event(
                task_id=task_id,
                run_id=run_id,
                actor="main",
                role="general",
                event_type="memory_retrieved",
                payload={
                "trigger_event_id": trigger_event_id,
                "memory_id": mem_id,
                "score": 1.0,
                    "stage": stage,
                    "handoff_source": "verification_handoff",
                    "reason": "task_end_finalization",
                    "source": "runtime_finalize_upsert",
                },
            )
            emit_event(
                task_id=task_id,
                run_id=run_id,
                actor="main",
                role="general",
                event_type="memory_decision_made",
                payload={
                    "trigger_event_id": trigger_event_id,
                    "memory_id": mem_id,
                    "decision": "accepted",
                    "reason": "persisted_from_verification_handoff",
                    "stage": "postmortem",
                },
            )
    except Exception:
        pass


def inject_system_memory_recall(
    task_id: str,
    run_id: str,
    user_input: str,
    messages: List[Dict[str, Any]],
    system_memory_store: Optional[SystemMemoryStore],
    emit_event: Callable[..., Dict[str, Any]],
    model_provider: ModelProvider,
    enable_memory_recall_reranker: bool,
    parse_json_dict: Callable[[str], Dict[str, Any]],
    preview: Callable[[str, int], str],
    start_recall_candidate_pool: int,
    start_recall_top_k: int,
    start_recall_min_score: float,
) -> List[Dict[str, Any]]:
    if not messages:
        return messages
    try:
        store = system_memory_store or SystemMemoryStore()
    except Exception:
        return messages

    query = build_recall_query(user_input=user_input)
    triggered = emit_event(
        task_id=task_id,
        run_id=run_id,
        actor="main",
        role="general",
        event_type="memory_triggered",
        payload={
            "context_id": run_id,
            "risk_level": "P3",
            "source": "runtime_start_recall",
            "source_event": "runtime_start_recall",
            "query": query,
        },
    )
    trigger_event_id = str(triggered.get("event_id", "")).strip()

    try:
        rows = store.search_cards(
            query="",
            limit=max(start_recall_candidate_pool, start_recall_top_k),
            only_active=True,
        )
        if not isinstance(rows, list):
            rows = []
    except Exception as e:
        if trigger_event_id:
            emit_event(
                task_id=task_id,
                run_id=run_id,
                actor="main",
                role="general",
                event_type="memory_decision_made",
                status="error",
                payload={
                    "trigger_event_id": trigger_event_id,
                    "decision": "skipped",
                    "reason": f"recall_failed:{str(e)}",
                },
            )
        return messages

    selected: List[Dict[str, Any]] = []
    if rows and enable_memory_recall_reranker:
        reranked = rerank_memory_candidates_llm(
            model_provider=model_provider,
            user_input=user_input,
            candidates=rows,
            start_recall_candidate_pool=start_recall_candidate_pool,
            start_recall_top_k=start_recall_top_k,
            build_memory_reranker_config=build_memory_reranker_config,
            parse_json_dict=parse_json_dict,
        )
        card_map: Dict[str, Dict[str, Any]] = {
            str(card.get("id", "")).strip(): card for card in rows if str(card.get("id", "")).strip()
        }
        for item in reranked:
            mid = str(item.get("id", "")).strip()
            score = float(item.get("score", 0.0) or 0.0)
            if not mid or mid not in card_map:
                continue
            if score < start_recall_min_score:
                continue
            card = dict(card_map[mid])
            card["retrieval_score"] = score
            selected.append(card)
            if len(selected) >= start_recall_top_k:
                break

    if trigger_event_id:
        if not selected:
            emit_event(
                task_id=task_id,
                run_id=run_id,
                actor="main",
                role="general",
                event_type="memory_decision_made",
                payload={
                    "trigger_event_id": trigger_event_id,
                    "decision": "skipped",
                    "reason": "no_llm_recall_match",
                },
            )
        else:
            for card in selected:
                emit_event(
                    task_id=task_id,
                    run_id=run_id,
                    actor="main",
                    role="general",
                    event_type="memory_retrieved",
                    payload={
                        "trigger_event_id": trigger_event_id,
                        "memory_id": card.get("id", ""),
                        "score": float(card.get("retrieval_score", 0.0) or 0.0),
                        "source": "runtime_start_recall",
                    },
                )
            emit_event(
                task_id=task_id,
                run_id=run_id,
                actor="main",
                role="general",
                event_type="memory_decision_made",
                payload={
                    "trigger_event_id": trigger_event_id,
                    "decision": "accepted",
                    "reason": f"recalled_{len(selected)}_high_precision_cards",
                },
            )

    if not selected:
        return messages
    memory_block = render_memory_recall_block(selected, preview=preview)
    if not memory_block:
        return messages
    out = list(messages)
    first = out[0] if out else {}
    if isinstance(first, dict) and first.get("role") == "system":
        base = str(first.get("content", "") or "")
        first = dict(first)
        first["content"] = f"{base}\n\n{memory_block}".strip()
        out[0] = first
        return out
    return [{"role": "system", "content": memory_block}] + out
