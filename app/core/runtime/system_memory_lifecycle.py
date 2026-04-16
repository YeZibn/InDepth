from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

from app.core.memory.memory_metadata_service import (
    build_memory_metadata_config,
    build_semantic_memory_title,
    extract_title_topic,
    generate_memory_card_metadata_llm,
)
from app.core.memory.recall_service import (
    build_memory_reranker_config,
    build_recall_query,
    render_memory_recall_block,
    rerank_memory_candidates_llm,
)
from app.core.memory.system_memory_store import SystemMemoryStore
from app.core.model.base import ModelProvider


# 这个模块保留在 runtime 下，是因为它表达的是“system memory 在 runtime 生命周期中的触发时机”。
# 真正的 recall / rerank / metadata 能力已经下沉到 memory 目录，本模块只负责装配它们。


def finalize_task_memory(
    task_id: str,
    run_id: str,
    user_input: str,
    final_answer: str,
    stop_reason: str,
    runtime_status: str,
    tool_failures: List[Dict[str, str]],
    system_memory_store: Optional[SystemMemoryStore],
    model_provider: ModelProvider,
    enable_memory_card_metadata_llm: bool,
    parse_json_dict: Callable[[str], Dict[str, Any]],
    preview: Callable[[str, int], str],
    slug: Callable[[str], str],
    emit_event: Callable[..., Dict[str, Any]],
) -> None:
    try:
        store = system_memory_store or SystemMemoryStore()
    except Exception:
        return

    now = datetime.now().astimezone()
    today = now.date().isoformat()
    expire_at = (now.date() + timedelta(days=180)).isoformat()
    mem_id = f"mem_task_{slug(task_id)}_{slug(run_id)}"
    stage = "postmortem"
    risk_level = "P1" if runtime_status == "error" else "P3"
    short_answer = preview(final_answer, 500)
    failure_brief = "; ".join(
        [f"{x.get('tool', 'unknown')}: {x.get('error', '')}" for x in (tool_failures or [])[:3]]
    ).strip()
    fallback_title = build_semantic_memory_title(
        user_input=user_input,
        runtime_status=runtime_status,
        stop_reason=stop_reason,
        extract_title_topic=lambda user_input: extract_title_topic(user_input=user_input, preview=preview),
        preview=preview,
    )
    fallback_recall_hint = preview(
        f"任务结束状态={runtime_status}，优先复用本次成功路径并规避失败工具链：{failure_brief or short_answer}",
        200,
    )
    generated = generate_memory_card_metadata_llm(
        model_provider=model_provider,
        enabled=enable_memory_card_metadata_llm,
        build_memory_metadata_config=build_memory_metadata_config,
        parse_json_dict=parse_json_dict,
        preview=preview,
        mode="finalize",
        user_input=user_input,
        runtime_status=runtime_status,
        stop_reason=stop_reason,
        failure_brief=failure_brief,
        answer_brief=short_answer,
        fallback_title=fallback_title,
        fallback_recall_hint=fallback_recall_hint,
    )
    generated_title = str(generated.get("title", "") or "").strip()
    generated_recall_hint = str(generated.get("recall_hint", "") or "").strip()

    card = {
        "id": mem_id,
        "title": generated_title or fallback_title,
        "recall_hint": generated_recall_hint or fallback_recall_hint,
        "memory_type": "experience",
        "domain": "runtime",
        "tags": ["task-finish", runtime_status, stop_reason],
        "scenario": {
            "stage": stage,
            "trigger_hint": f"Task {task_id} finished with status={runtime_status}",
            "roles": ["dev", "reviewer", "verifier"],
        },
        "problem_pattern": {
            "symptoms": [preview(user_input, 200) or "task request"],
            "root_cause_hypothesis": failure_brief or "See task output summary",
            "risk_level": risk_level,
        },
        "solution": {
            "steps": [
                "Review final answer and runtime stop reason",
                "Reuse successful pattern or avoid failed tool path in similar tasks",
            ],
            "expected_outcome": short_answer or "Task finished with no explicit answer.",
            "rollback": "Fallback to manual troubleshooting when similar failures repeat",
        },
        "constraints": {
            "applicable_if": ["Same or similar runtime task context appears"],
            "dependencies": [],
        },
        "anti_pattern": {
            "not_applicable_if": ["Task scope differs significantly from this run context"],
            "danger_signals": [failure_brief] if failure_brief else [],
        },
        "evidence": {
            "source_links": [f"urn:runtime:{task_id}:{run_id}"],
            "verified_at": now.isoformat(),
            "verifier": "runtime-framework",
        },
        "impact": {},
        "owner": {"team": "runtime", "primary": "main-agent", "reviewers": []},
        "lifecycle": {
            "status": "active",
            "version": "v1.0",
            "effective_from": today,
            "expire_at": expire_at,
            "last_reviewed_at": today,
            "change_log": [
                {
                    "version": "v1.0",
                    "changed_at": now.isoformat(),
                    "summary": "Auto-finalized by runtime framework at task completion",
                }
            ],
        },
        "confidence": "B" if runtime_status == "ok" else "C",
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
                    "reason": "framework forced finalization",
                    "stage": stage,
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
