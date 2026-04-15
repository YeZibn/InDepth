import json
import re
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

from app.config import load_runtime_model_config
from app.core.memory.system_memory_store import SystemMemoryStore
from app.core.model.base import GenerationConfig, ModelProvider


def finalize_task_memory(
    task_id: str,
    run_id: str,
    user_input: str,
    final_answer: str,
    stop_reason: str,
    runtime_status: str,
    tool_failures: List[Dict[str, str]],
    system_memory_store: Optional[SystemMemoryStore],
    preview: Callable[[str, int], str],
    slug: Callable[[str], str],
    build_semantic_memory_title: Callable[[str, str, str], str],
    generate_memory_card_metadata_llm: Callable[..., Dict[str, str]],
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
    )
    fallback_recall_hint = preview(
        f"任务结束状态={runtime_status}，优先复用本次成功路径并规避失败工具链：{failure_brief or short_answer}",
        200,
    )
    generated = generate_memory_card_metadata_llm(
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
    enable_memory_recall_reranker: bool,
    rerank_memory_candidates_llm: Callable[[str, List[Dict[str, Any]]], List[Dict[str, Any]]],
    render_memory_recall_block: Callable[[List[Dict[str, Any]]], str],
    build_recall_query: Callable[[str], str],
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
        reranked = rerank_memory_candidates_llm(user_input=user_input, candidates=rows)
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
    memory_block = render_memory_recall_block(selected)
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


def build_recall_query(user_input: str) -> str:
    base = f"{user_input}".lower()
    tokens = re.findall(r"[a-z0-9_\-\u4e00-\u9fff]+", base)
    stop = {
        "the",
        "a",
        "an",
        "and",
        "or",
        "to",
        "for",
        "of",
        "in",
        "on",
        "with",
        "请",
        "帮我",
        "一下",
        "麻烦",
        "需要",
        "现在",
        "这个",
        "那个",
        "进行",
        "完成",
    }
    out: List[str] = []
    for token in tokens:
        val = token.strip()
        if not val or len(val) <= 1:
            continue
        if val in stop:
            continue
        if val not in out:
            out.append(val)
        if len(out) >= 12:
            break
    return " ".join(out)


def render_memory_recall_block(cards: List[Dict[str, Any]], preview: Callable[[str, int], str]) -> str:
    if not cards:
        return ""
    lines: List[str] = ["系统记忆召回（轻注入：memory_id + recall_hint，最多5条）"]
    for idx, card in enumerate(cards, 1):
        memory_id = str(card.get("id", "") or "").strip()
        recall_hint = str(card.get("recall_hint", "") or "").strip()
        if not recall_hint:
            scenario = card.get("scenario", {}) if isinstance(card.get("scenario", {}), dict) else {}
            recall_hint = str(scenario.get("trigger_hint", "") or "").strip()
        if not memory_id:
            continue
        lines.append(f"{idx}. memory_id={memory_id}")
        if recall_hint:
            lines.append(f"   - recall_hint={preview(recall_hint, 200)}")
    return "\n".join(lines).strip()


def rerank_memory_candidates_llm(
    model_provider: ModelProvider,
    user_input: str,
    candidates: List[Dict[str, Any]],
    start_recall_candidate_pool: int,
    start_recall_top_k: int,
    build_memory_reranker_config: Callable[[], GenerationConfig],
    parse_json_dict: Callable[[str], Dict[str, Any]],
) -> List[Dict[str, Any]]:
    if not candidates:
        return []
    entries = []
    for card in candidates[:start_recall_candidate_pool]:
        cid = str(card.get("id", "")).strip()
        title = str(card.get("title", "")).strip()
        if not cid or not title:
            continue
        entries.append({"id": cid, "title": title})
    if not entries:
        return []

    prompt = {
        "task": "memory_recall_rerank",
        "instruction": (
            "Given user_input and memory card titles, return the most relevant cards. "
            "Match by semantic relevance only. Return strict JSON."
        ),
        "user_input": user_input,
        "top_k": start_recall_top_k,
        "candidates": entries,
        "output_schema": {"selected": [{"id": "memory_id", "score": "0~1 float", "reason": "short reason"}]},
    }
    try:
        output = model_provider.generate(
            messages=[
                {"role": "system", "content": "You are a precise memory recall ranker. Output JSON only."},
                {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
            ],
            tools=[],
            config=build_memory_reranker_config(),
        )
    except Exception:
        return []
    text = str(getattr(output, "content", "") or "").strip()
    parsed = parse_json_dict(text)
    if not isinstance(parsed, dict):
        return []
    selected = parsed.get("selected", [])
    if not isinstance(selected, list):
        return []
    out: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for item in selected:
        if not isinstance(item, dict):
            continue
        mid = str(item.get("id", "")).strip()
        if not mid or mid in seen:
            continue
        try:
            score = float(item.get("score", 0.0) or 0.0)
        except Exception:
            score = 0.0
        out.append(
            {
                "id": mid,
                "score": max(0.0, min(score, 1.0)),
                "reason": str(item.get("reason", "") or "").strip(),
            }
        )
        seen.add(mid)
        if len(out) >= start_recall_top_k:
            break
    out.sort(key=lambda x: x.get("score", 0.0), reverse=True)
    return out


def build_memory_reranker_config() -> GenerationConfig:
    options: Dict[str, Any] = {}
    try:
        model_cfg = load_runtime_model_config()
        mini_id = str(getattr(model_cfg, "mini_model_id", "") or "").strip()
        if mini_id:
            options["model"] = mini_id
    except Exception:
        pass
    return GenerationConfig(
        temperature=0.0,
        max_tokens=800,
        provider_options=options,
    )


def generate_memory_card_metadata_llm(
    model_provider: ModelProvider,
    enabled: bool,
    build_memory_metadata_config: Callable[[], GenerationConfig],
    parse_json_dict: Callable[[str], Dict[str, Any]],
    preview: Callable[[str, int], str],
    mode: str,
    user_input: str,
    runtime_status: str,
    stop_reason: str,
    failure_brief: str,
    answer_brief: str,
    fallback_title: str,
    fallback_recall_hint: str,
    task_id: str = "",
    run_id: str = "",
) -> Dict[str, str]:
    if not enabled:
        return {}
    payload = {
        "task": "memory_card_metadata_generation",
        "instruction": (
            "Generate concise high-signal memory card metadata in Chinese. "
            "Return strict JSON only with fields: title, recall_hint. "
            "title should be stable and semantic, follow <问题对象/场景> + <关键动作/原则>, "
            "and no task_id/run_id/timestamp noise. "
            "recall_hint should follow: 问题; 适用条件; 建议动作; 风险提示."
        ),
        "mode": mode,
        "task_id": task_id,
        "run_id": run_id,
        "user_input": user_input,
        "runtime_status": runtime_status,
        "stop_reason": stop_reason,
        "failure_brief": failure_brief,
        "answer_brief": answer_brief,
        "fallback": {"title": fallback_title, "recall_hint": fallback_recall_hint},
        "constraints": {"title_max_len": 40, "recall_hint_max_len": 220},
        "output_schema": {"title": "string", "recall_hint": "string"},
    }
    try:
        output = model_provider.generate(
            messages=[
                {
                    "role": "system",
                    "content": "You generate memory metadata. Output JSON only.",
                },
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            tools=[],
            config=build_memory_metadata_config(),
        )
    except Exception:
        return {}
    parsed = parse_json_dict(str(getattr(output, "content", "") or ""))
    if not isinstance(parsed, dict):
        return {}
    title = preview(str(parsed.get("title", "") or "").strip(), 40)
    recall_hint = preview(str(parsed.get("recall_hint", "") or "").strip(), 220)
    if not title and not recall_hint:
        return {}
    return {"title": title, "recall_hint": recall_hint}


def build_memory_metadata_config() -> GenerationConfig:
    options: Dict[str, Any] = {}
    try:
        model_cfg = load_runtime_model_config()
        mini_id = str(getattr(model_cfg, "mini_model_id", "") or "").strip()
        if mini_id:
            options["model"] = mini_id
    except Exception:
        pass
    return GenerationConfig(
        temperature=0.1,
        max_tokens=400,
        provider_options=options,
    )


def build_semantic_memory_title(
    user_input: str,
    runtime_status: str,
    stop_reason: str,
    extract_title_topic: Callable[[str], str],
    preview: Callable[[str, int], str],
) -> str:
    topic = extract_title_topic(user_input=user_input)
    _ = stop_reason
    suffix = "复用策略" if runtime_status == "ok" else "排查与修复策略"
    raw = f"{topic}{suffix}"
    return preview(raw, 40)


def extract_title_topic(user_input: str, preview: Callable[[str, int], str]) -> str:
    text = (user_input or "").strip()
    if not text:
        return "任务执行"
    compact = re.sub(r"\s+", " ", text)
    return preview(compact, 40)
