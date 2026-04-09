import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx
from ddgs import DDGS
from app.core.tools import tool
from app.observability.events import emit_event


@dataclass
class SearchSession:
    task_id: str
    time_basis: str
    question_ids: List[str]
    questions: List[str]
    stop_threshold: str
    max_rounds: int
    max_seconds: int
    created_at: float = field(default_factory=time.time)
    rounds_used: int = 0
    stopped: bool = False
    stop_reason: str = ""
    answered_question_ids: List[str] = field(default_factory=list)
    stable_conclusion: bool = False
    logs: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def elapsed_seconds(self) -> int:
        return int(time.time() - self.created_at)

    @property
    def rounds_left(self) -> int:
        return max(self.max_rounds - self.rounds_used, 0)

    @property
    def seconds_left(self) -> int:
        return max(self.max_seconds - self.elapsed_seconds, 0)


class SearchGuardManager:
    def __init__(self) -> None:
        self._sessions: Dict[str, SearchSession] = {}

    def init_session(
        self,
        task_id: str,
        time_basis: str,
        question_ids: List[str],
        questions: List[str],
        max_rounds: int,
        max_seconds: int,
        stop_threshold: str,
    ) -> SearchSession:
        session = SearchSession(
            task_id=task_id,
            time_basis=time_basis,
            question_ids=question_ids,
            questions=questions,
            stop_threshold=stop_threshold,
            max_rounds=max_rounds,
            max_seconds=max_seconds,
        )
        self._sessions[task_id] = session
        return session

    def get_session(self, task_id: str) -> Optional[SearchSession]:
        return self._sessions.get(task_id)

    def check_gate(self, task_id: str) -> Optional[str]:
        session = self.get_session(task_id)
        if not session:
            return "Search gate not initialized. Call init_search_guard first."
        if session.stopped:
            return f"Search is stopped: {session.stop_reason or 'threshold reached'}"
        if session.rounds_used >= session.max_rounds:
            session.stopped = True
            session.stop_reason = "round budget exhausted"
            return "Search blocked: round budget exhausted."
        if session.elapsed_seconds >= session.max_seconds:
            session.stopped = True
            session.stop_reason = "time budget exhausted"
            return "Search blocked: time budget exhausted."
        return None

    def add_log(self, task_id: str, log: Dict[str, Any]) -> None:
        session = self.get_session(task_id)
        if not session:
            return
        session.logs.append(log)
        session.rounds_used += 1
        if session.rounds_used >= session.max_rounds:
            session.stopped = True
            session.stop_reason = "round budget exhausted"
        elif session.elapsed_seconds >= session.max_seconds:
            session.stopped = True
            session.stop_reason = "time budget exhausted"

    def update_progress(
        self,
        task_id: str,
        answered_question_ids: List[str],
        stable_conclusion: bool,
        new_evidence_count: int,
        dedup_count: int,
        note: str,
    ) -> Dict[str, Any]:
        session = self.get_session(task_id)
        if not session:
            return {"success": False, "error": "Session not found"}

        known_ids = set(session.question_ids)
        valid_ids = [qid for qid in answered_question_ids if qid in known_ids]
        session.answered_question_ids = sorted(set(valid_ids))
        session.stable_conclusion = stable_conclusion
        session.logs.append(
            {
                "type": "progress_update",
                "timestamp": int(time.time()),
                "answered_question_ids": session.answered_question_ids,
                "stable_conclusion": stable_conclusion,
                "new_evidence_count": new_evidence_count,
                "dedup_count": dedup_count,
                "note": note,
            }
        )

        if stable_conclusion and len(session.answered_question_ids) == len(session.questions):
            session.stopped = True
            session.stop_reason = "threshold reached: questions covered and conclusion stable"

        return {
            "success": True,
            "stopped": session.stopped,
            "stop_reason": session.stop_reason,
            "answered": f"{len(session.answered_question_ids)}/{len(session.questions)}",
        }

    def override_budget(
        self,
        task_id: str,
        extra_rounds: int,
        extra_seconds: int,
        reason: str,
        expected_gain: str,
    ) -> Dict[str, Any]:
        session = self.get_session(task_id)
        if not session:
            return {"success": False, "error": "Session not found"}
        if extra_rounds < 0 or extra_seconds < 0:
            return {"success": False, "error": "extra_rounds/extra_seconds must be non-negative"}
        session.max_rounds += extra_rounds
        session.max_seconds += extra_seconds
        session.stopped = False
        session.stop_reason = ""
        session.logs.append(
            {
                "type": "budget_override",
                "timestamp": int(time.time()),
                "extra_rounds": extra_rounds,
                "extra_seconds": extra_seconds,
                "reason": reason,
                "expected_gain": expected_gain,
            }
        )
        return {
            "success": True,
            "max_rounds": session.max_rounds,
            "max_seconds": session.max_seconds,
        }

    def status(self, task_id: str) -> Dict[str, Any]:
        session = self.get_session(task_id)
        if not session:
            return {"success": False, "error": "Session not found"}
        return {
            "success": True,
            "task_id": session.task_id,
            "time_basis": session.time_basis,
            "question_ids": session.question_ids,
            "questions": session.questions,
            "stop_threshold": session.stop_threshold,
            "rounds_used": session.rounds_used,
            "max_rounds": session.max_rounds,
            "rounds_left": session.rounds_left,
            "elapsed_seconds": session.elapsed_seconds,
            "seconds_left": session.seconds_left,
            "stopped": session.stopped,
            "stop_reason": session.stop_reason,
            "answered_question_ids": session.answered_question_ids,
            "stable_conclusion": session.stable_conclusion,
            "log_count": len(session.logs),
        }


_guard = SearchGuardManager()


def _emit_obs(
    task_id: str,
    event_type: str,
    status: str = "ok",
    duration_ms: Optional[int] = None,
    payload: Optional[Dict[str, Any]] = None,
) -> None:
    """Best-effort observability hook. Never break business flow."""
    try:
        emit_event(
            task_id=task_id,
            run_id=task_id,
            actor="subagent",
            role="researcher",
            event_type=event_type,
            status=status,
            duration_ms=duration_ms,
            payload=payload or {},
        )
    except Exception:
        pass


def _format_guard_header(session: SearchSession) -> str:
    return (
        f"[search-guard] task_id={session.task_id} "
        f"round={session.rounds_used + 1}/{session.max_rounds} "
        f"elapsed={session.elapsed_seconds}s/{session.max_seconds}s "
        f"time_basis={session.time_basis}"
    )


@tool(
    name="init_search_guard",
    description="Initialize required search gate before any search. Must define time basis, question list, budgets, and stop threshold.",
    stop_after_tool_call=False,
    requires_confirmation=False,
    cache_results=False,
)
def init_search_guard(
    task_id: str,
    time_basis: str,
    questions_json: str,
    stop_threshold: str,
    max_rounds: int = 3,
    max_seconds: int = 900,
) -> str:
    """
    Initialize a guarded search session with time basis, questions, and budgets.

    Args:
        task_id: Session identifier, usually the parent task id.
        time_basis: Explicit time baseline (timezone + cutoff).
        questions_json: JSON array of focused search questions.
        stop_threshold: Human-readable stop criteria.
        max_rounds: Max search rounds allowed for this session.
        max_seconds: Max elapsed seconds allowed for this session.

    Returns:
        JSON string with initialized session metadata or error message.
    """
    if not task_id.strip():
        return "Error: task_id is required."
    if not time_basis.strip():
        return "Error: time_basis is required."
    try:
        questions = json.loads(questions_json)
    except json.JSONDecodeError as e:
        return f"Error: questions_json must be valid JSON array. {e}"
    if not isinstance(questions, list) or not questions:
        return "Error: questions_json must be a non-empty JSON array."
    if len(questions) > 8:
        return "Error: question list too long. Keep at most 8 focused questions."
    normalized_ids: List[str] = []
    normalized_questions: List[str] = []
    for idx, q in enumerate(questions, 1):
        if isinstance(q, dict):
            qid = str(q.get("id") or idx).strip()
            qtext = str(q.get("question") or q.get("text") or "").strip()
            if not qid or not qtext:
                continue
            normalized_ids.append(qid)
            normalized_questions.append(qtext)
            continue
        qtext = str(q).strip()
        if not qtext:
            continue
        normalized_ids.append(str(idx))
        normalized_questions.append(qtext)

    if len(normalized_questions) < 1:
        return "Error: at least one valid question is required."
    if max_rounds < 1 or max_rounds > 8:
        return "Error: max_rounds must be between 1 and 8."
    if max_seconds < 60 or max_seconds > 3600:
        return "Error: max_seconds must be between 60 and 3600."

    session = _guard.init_session(
        task_id=task_id.strip(),
        time_basis=time_basis.strip(),
        question_ids=normalized_ids,
        questions=normalized_questions,
        max_rounds=max_rounds,
        max_seconds=max_seconds,
        stop_threshold=stop_threshold.strip(),
    )
    _emit_obs(
        task_id=session.task_id,
        event_type="search_guard_initialized",
        payload={
            "max_rounds": session.max_rounds,
            "max_seconds": session.max_seconds,
            "question_count": len(session.questions),
            "time_basis": session.time_basis,
        },
    )
    return json.dumps(
        {
            "success": True,
            "task_id": session.task_id,
            "time_basis": session.time_basis,
            "question_ids": session.question_ids,
            "questions": session.questions,
            "max_rounds": session.max_rounds,
            "max_seconds": session.max_seconds,
            "stop_threshold": session.stop_threshold,
            "message": "Search gate initialized. Use guarded_ddg_search/guarded_url_search only.",
        },
        ensure_ascii=False,
        indent=2,
    )


@tool(
    name="guarded_ddg_search",
    description="Budget-enforced DDG search. Requires init_search_guard first.",
    stop_after_tool_call=False,
    requires_confirmation=False,
    cache_results=False,
)
def guarded_ddg_search(task_id: str, query: str, num_results: int = 5) -> str:
    """
    Run DDG search under guard budget and session gate checks.

    Args:
        task_id: Existing guarded search session id.
        query: Search query text.
        num_results: Number of results to return (1-10).

    Returns:
        Guard header plus formatted search results, or error message.
    """
    gate_error = _guard.check_gate(task_id)
    if gate_error:
        _emit_obs(
            task_id=task_id,
            event_type="search_stopped",
            status="error",
            payload={"reason": gate_error},
        )
        return f"Error: {gate_error}"
    session = _guard.get_session(task_id)
    if not session:
        return "Error: Search session not found."
    if not query.strip():
        return "Error: query is required."
    if num_results < 1 or num_results > 10:
        return "Error: num_results must be between 1 and 10."

    try:
        start_perf = time.time()
        _emit_obs(
            task_id=task_id,
            event_type="search_round_started",
            payload={"engine": "ddg", "query": query, "num_results": num_results},
        )
        results = []
        with DDGS() as ddgs:
            for i, r in enumerate(ddgs.text(query, max_results=num_results), 1):
                title = r.get("title", "No title")
                body = r.get("body", "No description")
                href = r.get("href", "No link")
                results.append(f"{i}. {title}\n   {body}\n   Link: {href}")
        if not results:
            body_text = "No results found."
        else:
            body_text = "\n\n".join(results)
        _guard.add_log(
            task_id,
            {
                "type": "ddg_search",
                "timestamp": int(time.time()),
                "query": query,
                "num_results": num_results,
                "returned_results": len(results),
            },
        )
        duration_ms = int((time.time() - start_perf) * 1000)
        _emit_obs(
            task_id=task_id,
            event_type="search_round_finished",
            duration_ms=duration_ms,
            payload={"engine": "ddg", "query": query, "returned_results": len(results)},
        )
        return _format_guard_header(session) + "\n\n" + body_text
    except Exception as e:
        _guard.add_log(
            task_id,
            {"type": "ddg_search_error", "timestamp": int(time.time()), "query": query, "error": str(e)},
        )
        _emit_obs(
            task_id=task_id,
            event_type="search_round_finished",
            status="error",
            payload={"engine": "ddg", "query": query, "error": str(e)},
        )
        return f"Error searching DuckDuckGo: {str(e)}"


@tool(
    name="guarded_url_search",
    description="Budget-enforced URL fetch. Requires init_search_guard first.",
    stop_after_tool_call=False,
    requires_confirmation=False,
    cache_results=False,
)
def guarded_url_search(task_id: str, url: str, max_length: int = 2000) -> str:
    """
    Fetch URL content under guard budget and session gate checks.

    Args:
        task_id: Existing guarded search session id.
        url: Target URL to fetch.
        max_length: Maximum response content length to keep.

    Returns:
        Guard header plus fetched content (possibly truncated), or error.
    """
    gate_error = _guard.check_gate(task_id)
    if gate_error:
        _emit_obs(
            task_id=task_id,
            event_type="search_stopped",
            status="error",
            payload={"reason": gate_error},
        )
        return f"Error: {gate_error}"
    session = _guard.get_session(task_id)
    if not session:
        return "Error: Search session not found."
    if not url.strip():
        return "Error: url is required."
    if max_length < 200 or max_length > 10000:
        return "Error: max_length must be between 200 and 10000."

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/91.0.4472.124 Safari/537.36"
        )
    }
    try:
        start_perf = time.time()
        _emit_obs(
            task_id=task_id,
            event_type="search_round_started",
            payload={"engine": "url_fetch", "url": url, "max_length": max_length},
        )
        with httpx.Client(timeout=15, follow_redirects=True, max_redirects=5) as client:
            response = client.get(url, headers=headers)
            if response.status_code != 200:
                text = f"Error: HTTP {response.status_code} for URL: {url}"
            else:
                content = response.text
                if len(content) > max_length:
                    content = content[:max_length] + "\n... (truncated)"
                text = content
        _guard.add_log(
            task_id,
            {"type": "url_search", "timestamp": int(time.time()), "url": url, "status_code": response.status_code},
        )
        duration_ms = int((time.time() - start_perf) * 1000)
        _emit_obs(
            task_id=task_id,
            event_type="search_round_finished",
            duration_ms=duration_ms,
            payload={"engine": "url_fetch", "url": url, "status_code": response.status_code},
        )
        return _format_guard_header(session) + "\n\n" + text
    except Exception as e:
        _guard.add_log(
            task_id,
            {"type": "url_search_error", "timestamp": int(time.time()), "url": url, "error": str(e)},
        )
        _emit_obs(
            task_id=task_id,
            event_type="search_round_finished",
            status="error",
            payload={"engine": "url_fetch", "url": url, "error": str(e)},
        )
        return f"Error fetching URL: {str(e)}"


@tool(
    name="update_search_progress",
    description="Record per-round search progress and trigger threshold-based stop.",
    stop_after_tool_call=False,
    requires_confirmation=False,
    cache_results=False,
)
def update_search_progress(
    task_id: str,
    answered_question_ids_json: str,
    stable_conclusion: bool,
    new_evidence_count: int,
    dedup_count: int,
    note: str = "",
) -> str:
    """
    Update guarded search progress and optionally trigger threshold-based stop.

    Args:
        task_id: Existing guarded search session id.
        answered_question_ids_json: JSON array of answered question indices.
        stable_conclusion: Whether conclusion is considered stable.
        new_evidence_count: Number of new evidence items found in this round.
        dedup_count: Number of duplicated items removed.
        note: Optional progress note.

    Returns:
        JSON string with updated progress and stop status.
    """
    try:
        answered_question_ids = json.loads(answered_question_ids_json)
    except json.JSONDecodeError as e:
        return f"Error: answered_question_ids_json must be JSON array. {e}"
    if not isinstance(answered_question_ids, list):
        return "Error: answered_question_ids_json must be JSON array."
    normalized_ids: List[str] = []
    for x in answered_question_ids:
        xid = str(x).strip()
        if xid:
            normalized_ids.append(xid)
    result = _guard.update_progress(
        task_id=task_id,
        answered_question_ids=normalized_ids,
        stable_conclusion=stable_conclusion,
        new_evidence_count=max(new_evidence_count, 0),
        dedup_count=max(dedup_count, 0),
        note=note,
    )
    if result.get("stopped"):
        _emit_obs(
            task_id=task_id,
            event_type="search_stopped",
            payload={"reason": result.get("stop_reason", ""), "answered": result.get("answered", "")},
        )
    return json.dumps(result, ensure_ascii=False, indent=2)


@tool(
    name="get_search_guard_status",
    description="Get current guard status including budgets, rounds, answered questions, and stop reason.",
    stop_after_tool_call=False,
    requires_confirmation=False,
    cache_results=False,
)
def get_search_guard_status(task_id: str) -> str:
    """
    Get current guarded search session status.

    Args:
        task_id: Existing guarded search session id.

    Returns:
        JSON string with budgets, elapsed usage, and stop metadata.
    """
    return json.dumps(_guard.status(task_id), ensure_ascii=False, indent=2)


@tool(
    name="request_search_budget_override",
    description="Request and apply controlled search budget override with required reason and expected gain.",
    stop_after_tool_call=False,
    requires_confirmation=False,
    cache_results=False,
)
def request_search_budget_override(
    task_id: str,
    extra_rounds: int,
    extra_seconds: int,
    reason: str,
    expected_gain: str,
) -> str:
    """
    Extend guarded search budget with explicit reason and expected gain.

    Args:
        task_id: Existing guarded search session id.
        extra_rounds: Additional allowed rounds.
        extra_seconds: Additional allowed seconds.
        reason: Why the current budget is insufficient.
        expected_gain: What additional value the extra budget will bring.

    Returns:
        JSON string with updated budget or error details.
    """
    if not reason.strip():
        return "Error: reason is required."
    if not expected_gain.strip():
        return "Error: expected_gain is required."
    result = _guard.override_budget(
        task_id=task_id,
        extra_rounds=extra_rounds,
        extra_seconds=extra_seconds,
        reason=reason.strip(),
        expected_gain=expected_gain.strip(),
    )
    return json.dumps(result, ensure_ascii=False, indent=2)


@tool(
    name="build_search_conclusion",
    description=(
        "Build structured final output from search results with evidence cap validation. "
        "Input claims_json: [{\"conclusion\":\"...\",\"evidence\":[\"...\",\"...\"],\"gaps\":[\"...\"],\"next_steps\":[\"...\"]}]"
    ),
    stop_after_tool_call=False,
    requires_confirmation=False,
    cache_results=False,
)
def build_search_conclusion(task_id: str, claims_json: str) -> str:
    """
    Build structured final search conclusion with evidence-count validation.

    Args:
        task_id: Existing guarded search session id.
        claims_json: JSON array of claim objects containing conclusion/evidence.

    Returns:
        Formatted markdown-style conclusion text or validation error message.
    """
    session = _guard.get_session(task_id)
    if not session:
        return "Error: Search session not found."
    try:
        claims = json.loads(claims_json)
    except json.JSONDecodeError as e:
        return f"Error: claims_json must be valid JSON array. {e}"
    if not isinstance(claims, list) or not claims:
        return "Error: claims_json must be a non-empty JSON array."

    lines = []
    lines.append("## 核心结论")
    for idx, claim in enumerate(claims, 1):
        if not isinstance(claim, dict):
            return f"Error: claim[{idx}] must be an object."
        conclusion = str(claim.get("conclusion", "")).strip()
        evidence = claim.get("evidence", [])
        gaps = claim.get("gaps", [])
        next_steps = claim.get("next_steps", [])

        if not conclusion:
            return f"Error: claim[{idx}].conclusion is required."
        if not isinstance(evidence, list) or len(evidence) < 1:
            return f"Error: claim[{idx}].evidence must contain at least 1 item."
        if len(evidence) > 3:
            return f"Error: claim[{idx}] has {len(evidence)} evidence items. Max allowed is 3."

        lines.append(f"{idx}. {conclusion}")
        lines.append("   - 关键证据:")
        for ev in evidence:
            lines.append(f"     - {str(ev).strip()}")

        if isinstance(gaps, list) and gaps:
            lines.append("   - 信息缺口:")
            for g in gaps:
                lines.append(f"     - {str(g).strip()}")
        if isinstance(next_steps, list) and next_steps:
            lines.append("   - 下一步建议:")
            for s in next_steps:
                lines.append(f"     - {str(s).strip()}")

    _guard.add_log(
        task_id,
        {
            "type": "build_search_conclusion",
            "timestamp": int(time.time()),
            "claim_count": len(claims),
        },
    )
    session.stopped = True
    if not session.stop_reason:
        session.stop_reason = "conclusion built"
    _emit_obs(
        task_id=task_id,
        event_type="search_stopped",
        payload={"reason": session.stop_reason, "claim_count": len(claims)},
    )
    return "\n".join(lines)


def get_guarded_search_tools() -> List[Any]:
    return [
        init_search_guard,
        guarded_ddg_search,
        guarded_url_search,
        update_search_progress,
        get_search_guard_status,
        request_search_budget_override,
        build_search_conclusion,
    ]
