from datetime import datetime, timedelta
import re
from typing import List

from app.core.memory.system_memory_store import SystemMemoryStore
from app.core.tools import tool
from app.observability.events import emit_event


def _slug(value: str) -> str:
    text = (value or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text or "na"


def _parse_tags(raw: str) -> List[str]:
    if not raw.strip():
        return []
    out = []
    for item in raw.split(","):
        val = item.strip()
        if val and val not in out:
            out.append(val)
    return out


@tool(
    name="capture_runtime_memory_candidate",
    description="Capture a high-signal candidate memory discovered during execution. Use only when new reusable patterns or failure lessons emerge.",
    stop_after_tool_call=False,
    requires_confirmation=False,
    cache_results=False,
)
def capture_runtime_memory_candidate(
    task_id: str,
    run_id: str,
    title: str,
    observation: str,
    proposed_action: str = "",
    recall_hint: str = "",
    stage: str = "development",
    tags: str = "",
    db_file: str = "db/system_memory.db",
) -> str:
    now = datetime.now().astimezone()
    today = now.date().isoformat()
    expire_at = (now.date() + timedelta(days=120)).isoformat()
    mem_id = f"mem_candidate_{_slug(task_id)}_{_slug(title)}"

    card = {
        "id": mem_id,
        "title": title,
        "recall_hint": (recall_hint or observation or proposed_action or title)[:200],
        "memory_type": "experience",
        "domain": "runtime",
        "tags": ["candidate", stage] + _parse_tags(tags),
        "scenario": {
            "stage": stage,
            "trigger_hint": (observation or title)[:200],
            "roles": ["dev", "reviewer"],
        },
        "problem_pattern": {
            "symptoms": [(observation or "runtime observation")[:200]],
            "root_cause_hypothesis": (observation or "see observation")[:300],
            "risk_level": "P2",
        },
        "solution": {
            "steps": [
                (proposed_action or "Validate this candidate memory in similar future tasks")[:280],
            ],
            "expected_outcome": "Candidate memory is available for future evaluation and refinement.",
            "rollback": "Discard candidate if not reproducible",
        },
        "constraints": {
            "applicable_if": ["Similar runtime context appears"],
            "dependencies": [],
        },
        "anti_pattern": {
            "not_applicable_if": ["Observation is one-off and non-reproducible"],
            "danger_signals": [],
        },
        "evidence": {
            "source_links": [f"urn:runtime:candidate:{task_id}:{run_id}"],
            "verified_at": now.isoformat(),
            "verifier": "memory-knowledge-skill",
        },
        "impact": {},
        "owner": {"team": "runtime", "primary": "main-agent", "reviewers": []},
        "lifecycle": {
            "status": "draft",
            "version": "v0.1",
            "effective_from": today,
            "expire_at": expire_at,
            "last_reviewed_at": today,
            "change_log": [
                {
                    "version": "v0.1",
                    "changed_at": now.isoformat(),
                    "summary": "Candidate captured during runtime execution",
                }
            ],
        },
        "confidence": "C",
    }

    store = SystemMemoryStore(db_file=db_file)
    store.upsert_card(card)

    trigger_event = emit_event(
        task_id=task_id,
        run_id=run_id,
        actor="main",
        role="general",
        event_type="memory_triggered",
        payload={
            "stage": stage,
            "context_id": run_id,
            "risk_level": "P2",
            "source_event": "runtime_memory_harvest_skill",
        },
    )
    trigger_event_id = str(trigger_event.get("event_id", "")).strip()
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
                "score": 0.9,
                "stage": stage,
                "source": "memory_knowledge_skill",
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
                "decision": "captured",
                "reason": "candidate captured by memory-knowledge-skill",
                "stage": stage,
            },
        )

    return f"Captured candidate memory: {mem_id}"
