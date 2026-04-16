import glob
import json
import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from app.core.tools import tool
from app.observability.events import emit_event


VALID_SUBTASK_STATUSES = [
    "pending",
    "in-progress",
    "completed",
    "blocked",
    "failed",
    "partial",
    "awaiting_input",
    "timed_out",
    "abandoned",
]
READY_SUBTASK_STATUSES = {"pending"}
TERMINAL_SUBTASK_STATUSES = {"completed", "abandoned"}
ACTIVE_TODO_STATUSES = {
    "in-progress",
    "blocked",
    "failed",
    "partial",
    "awaiting_input",
    "timed_out",
}
STATUS_ICONS = {
    "completed": "✓",
    "in-progress": "→",
    "pending": "○",
    "blocked": "!",
    "failed": "x",
    "partial": "~",
    "awaiting_input": "?",
    "timed_out": "⌛",
    "abandoned": "-",
}
RECOVERY_DECISION_LEVELS = {"auto", "agent_decide", "user_confirm"}
RECOVERY_ACTIONS = {
    "retry",
    "retry_with_fix",
    "split",
    "fallback_path",
    "execution_handoff",
    "decision_handoff",
    "pause",
    "degrade",
    "abandon",
}
FOLLOWUP_KINDS = {"diagnose", "repair", "retry", "verify", "handoff", "resume", "report"}


def _find_project_root() -> str:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    while current_dir != os.path.dirname(current_dir):
        if os.path.isdir(os.path.join(current_dir, ".git")):
            return current_dir
        if os.path.isdir(os.path.join(current_dir, "app", "skills")):
            return current_dir
        current_dir = os.path.dirname(current_dir)
    return os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))


def _emit_obs(todo_id: str, event_type: str, status: str = "ok", payload: Optional[Dict[str, Any]] = None) -> None:
    """Best-effort observability hook. Never break business flow."""
    try:
        raw = (todo_id or "").strip()
        obs_task_id = raw if raw.startswith("todo-id:") else f"todo-id:{raw or 'unknown'}"
        emit_event(
            task_id=obs_task_id,
            run_id=obs_task_id,
            actor="main",
            role="general",
            event_type=event_type,
            status=status,
            payload=payload or {},
        )
    except Exception:
        pass


def _get_todo_dir() -> str:
    return os.path.join(_find_project_root(), "todo")


def _ensure_todo_dir() -> None:
    os.makedirs(_get_todo_dir(), exist_ok=True)


def _generate_todo_id(task_name: str) -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    sanitized_name = re.sub(r"[^\w\s-]", "", task_name.lower())
    sanitized_name = re.sub(r"[\s]+", "_", sanitized_name).strip("_")
    return f"{timestamp}_{sanitized_name}"


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _json_loads(text: str, default: Any) -> Any:
    try:
        return json.loads(text)
    except Exception:
        return default


def _extract_simple_field(task_content: str, label: str) -> str:
    match = re.search(rf"\*\*{re.escape(label)}\*\*:\s*(.*?)\n", task_content)
    return match.group(1).strip() if match else ""


def _extract_json_field(task_content: str, label: str, default: Any) -> Any:
    raw = _extract_simple_field(task_content, label)
    if not raw:
        return default
    return _json_loads(raw, default)


def _normalize_status(status: str) -> str:
    status_norm = (status or "").strip()
    if not status_norm:
        raise ValueError("status must be a non-empty string")
    status_norm = status_norm.replace("awaiting-input", "awaiting_input")
    if status_norm not in VALID_SUBTASK_STATUSES:
        valid = ", ".join(VALID_SUBTASK_STATUSES)
        raise ValueError(f"Invalid status '{status}'. Valid: {valid}")
    return status_norm


def _normalize_followup_kind(kind: str) -> str:
    kind_norm = (kind or "").strip().lower()
    if not kind_norm:
        return "repair"
    if kind_norm not in FOLLOWUP_KINDS:
        allowed = ", ".join(sorted(FOLLOWUP_KINDS))
        raise ValueError(f"Invalid follow-up subtask kind '{kind}'. Allowed: {allowed}")
    return kind_norm


def _normalize_acceptance_criteria(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        raise ValueError("acceptance_criteria must be a string or string array")
    items = [str(item).strip() for item in value if str(item).strip()]
    return items


def _normalize_fallback_record(record: Any) -> Dict[str, Any]:
    if not record:
        return {}
    if not isinstance(record, dict):
        raise ValueError("fallback_record must be an object")

    normalized: Dict[str, Any] = {}
    state = record.get("state")
    if state:
        normalized["state"] = _normalize_status(str(state))

    for key in [
        "reason_code",
        "reason_detail",
        "impact_scope",
        "suggested_next_action",
        "last_attempt_summary",
        "owner",
        "failure_stage",
        "resume_condition",
    ]:
        value = record.get(key)
        if value not in (None, ""):
            normalized[key] = str(value).strip()

    for key in ["retryable", "degraded_delivery_allowed"]:
        if key in record:
            normalized[key] = bool(record.get(key))

    for key in ["retry_count", "retry_budget_remaining"]:
        if key in record and record.get(key) is not None:
            try:
                normalized[key] = int(record.get(key))
            except Exception as exc:
                raise ValueError(f"{key} must be an integer") from exc

    for key in ["required_input", "evidence", "partial_artifacts", "recommended_actions"]:
        value = record.get(key)
        if value is None:
            continue
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            raise ValueError(f"{key} must be a string or string array")
        normalized[key] = [str(item).strip() for item in value if str(item).strip()]

    return normalized


def _render_subtask(subtask: Dict[str, Any]) -> str:
    number = subtask["number"]
    name = subtask["name"]
    status = subtask.get("status", "pending")
    priority = subtask.get("priority", "medium")
    dependencies = subtask.get("dependencies", [])
    deps_str = ", ".join([f"Task {dep}" for dep in dependencies]) if dependencies else "None"
    split_rationale = str(subtask.get("split_rationale", "")).strip()
    description = str(subtask.get("description", "")).strip()
    kind = str(subtask.get("kind", "")).strip()
    owner = str(subtask.get("owner", "")).strip()
    acceptance_criteria = _normalize_acceptance_criteria(subtask.get("acceptance_criteria", []))
    fallback_record = _normalize_fallback_record(subtask.get("fallback_record", {}))

    lines = [
        f"### Task {number}: {name}",
        f"- **Status**: {status}",
        f"- **Priority**: {priority}",
        f"- **Dependencies**: {deps_str}",
    ]
    if kind:
        lines.append(f"- **Kind**: {kind}")
    if owner:
        lines.append(f"- **Owner**: {owner}")
    if split_rationale:
        lines.append(f"- **Split Rationale**: {split_rationale}")
    if acceptance_criteria:
        lines.append(f"- **Acceptance Criteria**: {_json_dumps(acceptance_criteria)}")
    if fallback_record:
        lines.append(f"- **Fallback Record**: {_json_dumps(fallback_record)}")
    lines.append(f"- **[ ]** {description}")
    return "\n".join(lines)


def _parse_task_file(filepath: str) -> Dict[str, Any]:
    if not os.path.exists(filepath):
        return {}

    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    metadata: Dict[str, str] = {}
    metadata_pattern = r"## Metadata\s*\n(.*?)(?=\n## |\Z)"
    metadata_match = re.search(metadata_pattern, content, re.DOTALL)
    if metadata_match:
        for line in metadata_match.group(1).strip().split("\n"):
            line = line.strip()
            if line.startswith("- ") and ":" in line:
                line = line[2:]
                key, value = line.split(":", 1)
                metadata[key.strip().replace("**", "").strip()] = value.strip()

    subtasks: List[Dict[str, Any]] = []
    subtask_pattern = r"### Task (\d+): (.*?)\n(.*?)(?=\n### Task|\n## |\Z)"
    for match in re.finditer(subtask_pattern, content, re.DOTALL):
        task_num = match.group(1)
        task_name = match.group(2).strip()
        task_content = match.group(3).strip()

        status = _extract_simple_field(task_content, "Status") or "pending"
        priority = _extract_simple_field(task_content, "Priority") or "medium"
        deps_str = _extract_simple_field(task_content, "Dependencies")
        split_rationale = _extract_simple_field(task_content, "Split Rationale")
        kind = _extract_simple_field(task_content, "Kind")
        owner = _extract_simple_field(task_content, "Owner")
        acceptance_criteria = _extract_json_field(task_content, "Acceptance Criteria", [])
        fallback_record = _extract_json_field(task_content, "Fallback Record", {})

        dependencies: List[str] = []
        if deps_str.strip() and deps_str.strip().lower() != "none":
            dependencies = re.findall(r"Task\s*(\d+)", deps_str)

        checklist_items = re.findall(r"- \*\[(.)\]\* (.*)", task_content)
        description = checklist_items[0][1] if checklist_items else ""

        subtasks.append(
            {
                "number": task_num,
                "name": task_name,
                "status": status,
                "priority": priority,
                "dependencies": dependencies,
                "description": description,
                "checklist": checklist_items,
                "split_rationale": split_rationale,
                "kind": kind,
                "owner": owner,
                "acceptance_criteria": acceptance_criteria if isinstance(acceptance_criteria, list) else [],
                "fallback_record": fallback_record if isinstance(fallback_record, dict) else {},
            }
        )

    return {
        "metadata": metadata,
        "subtasks": subtasks,
        "filename": os.path.basename(filepath),
        "filepath": filepath,
    }


def _calculate_progress(subtasks: List[Dict[str, Any]]) -> Tuple[int, int, int]:
    total = len(subtasks)
    completed = sum(1 for task in subtasks if task.get("status") == "completed")
    percentage = int((completed / total) * 100) if total > 0 else 0
    return completed, total, percentage


def _compute_overall_status(subtasks: List[Dict[str, Any]]) -> str:
    if not subtasks:
        return "pending"
    statuses = [task.get("status", "pending") for task in subtasks]
    if all(status == "completed" for status in statuses):
        return "completed"
    if any(status in ACTIVE_TODO_STATUSES for status in statuses):
        return "in-progress"
    if any(status == "completed" for status in statuses):
        return "in-progress"
    return "pending"


def _list_all_tasks() -> List[Dict[str, Any]]:
    todo_dir = _get_todo_dir()
    if not os.path.exists(todo_dir):
        return []

    tasks: List[Dict[str, Any]] = []
    for filepath in glob.glob(os.path.join(todo_dir, "*.md")):
        parsed = _parse_task_file(filepath)
        if parsed:
            tasks.append(parsed)
    tasks.sort(key=lambda item: item["metadata"].get("Created", ""), reverse=True)
    return tasks


def _get_task_by_todo_id(todo_id: str) -> Optional[Dict[str, Any]]:
    filepath = os.path.join(_get_todo_dir(), f"{todo_id}.md")
    if os.path.exists(filepath):
        return _parse_task_file(filepath)

    for task in _list_all_tasks():
        metadata = task.get("metadata", {})
        meta_todo_id = metadata.get("Todo ID", "") or metadata.get("ID", "")
        if todo_id in meta_todo_id:
            return task
    return None


def _get_next_task(subtasks: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    completed_tasks = {task["number"] for task in subtasks if task.get("status") == "completed"}
    for task in subtasks:
        if task.get("status") in READY_SUBTASK_STATUSES:
            if all(dep in completed_tasks for dep in task.get("dependencies", [])):
                return task
    return None


def _calculate_blocked_status(subtasks: List[Dict[str, Any]]) -> Dict[str, Any]:
    completed_tasks = {task["number"] for task in subtasks if task.get("status") == "completed"}
    blocked = []
    ready = []
    blocking = []
    incomplete = []

    for task in subtasks:
        number = task["number"]
        name = task["name"]
        deps = task.get("dependencies", [])
        status = task.get("status", "pending")

        if status in READY_SUBTASK_STATUSES:
            unmet = [dep for dep in deps if dep not in completed_tasks]
            if unmet:
                blocked.append((number, name, unmet))
            else:
                ready.append((number, name))
        elif status in {"blocked", "failed", "partial", "awaiting_input", "timed_out"}:
            reason = task.get("fallback_record", {}).get("reason_code", status)
            blocked.append((number, name, [reason]))

        if status not in TERMINAL_SUBTASK_STATUSES:
            blocks = [other["number"] for other in subtasks if number in other.get("dependencies", [])]
            if blocks:
                blocking.append((number, name, blocks))

        if status != "completed":
            incomplete.append(
                {
                    "number": number,
                    "name": name,
                    "status": status,
                    "fallback_record": task.get("fallback_record", {}),
                }
            )

    return {"blocked": blocked, "ready": ready, "blocking": blocking, "incomplete": incomplete}


def _generate_dependencies_section(subtasks: List[Dict[str, Any]]) -> str:
    status = _calculate_blocked_status(subtasks)
    lines = ["## Dependencies"]

    if status["blocked"]:
        lines.append("- **Blocked subtasks**:")
        for number, name, deps in status["blocked"]:
            wait_for = ", ".join([f"Task {dep}" if str(dep).isdigit() else str(dep) for dep in deps])
            lines.append(f"  - Task {number} ({name}) - waiting for {wait_for}")
    else:
        lines.append("- **Blocked subtasks**: None")

    if status["ready"]:
        lines.append("- **Ready subtasks**:")
        for number, name in status["ready"]:
            lines.append(f"  - Task {number} ({name})")
    else:
        lines.append("- **Ready subtasks**: None")

    if status["blocking"]:
        lines.append("- **Blocking subtasks**:")
        for number, name, blocks in status["blocking"]:
            blocks_str = ", ".join([f"Task {block}" for block in blocks])
            lines.append(f"  - Task {number} ({name}) - blocks {blocks_str}")
    else:
        lines.append("- **Blocking subtasks**: None")

    return "\n".join(lines)


def _has_unmet_dependencies(subtasks: List[Dict[str, Any]], task_number: str) -> List[str]:
    target = next((task for task in subtasks if task["number"] == task_number), None)
    if not target:
        return []
    completed = {task["number"] for task in subtasks if task.get("status") == "completed"}
    return [dep for dep in target.get("dependencies", []) if dep not in completed]


def _replace_subtask_block(content: str, task_number: str, rendered_block: str) -> Tuple[str, bool]:
    subtask_pattern = rf"### Task {task_number}:.*?(?=\n### Task|\n## |\Z)"
    new_content, count = re.subn(subtask_pattern, rendered_block + "\n", content, flags=re.DOTALL)
    return new_content, count > 0


def _rewrite_task_file(
    filepath: str,
    updated_subtasks: List[Dict[str, Any]],
    metadata_status: Optional[str] = None,
) -> Tuple[int, int, int]:
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    for task in updated_subtasks:
        rendered = _render_subtask(task)
        content, replaced = _replace_subtask_block(content, str(task["number"]), rendered)
        if not replaced:
            raise ValueError(f"Failed to locate task block for Task {task['number']}")

    completed, total, percentage = _calculate_progress(updated_subtasks)
    overall_status = metadata_status or _compute_overall_status(updated_subtasks)

    content = re.sub(
        r"(\*\*Progress\*\*:\s*)\d+/\d+\s*\(\d+%\)",
        rf"\g<1>{completed}/{total} ({percentage}%)",
        content,
    )
    content = re.sub(
        r"(\*\*Status\*\*:\s*)(\w+(?:[-_]\w+)*)",
        rf"\g<1>{overall_status}",
        content,
        count=1,
    )
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    content = re.sub(
        r"(\*\*Updated\*\*:\s*)\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}",
        rf"\g<1>{now}",
        content,
    )
    deps_section = _generate_dependencies_section(updated_subtasks)
    content = re.sub(
        r"## Dependencies\n.*?(?=\n## |\Z)",
        deps_section + "\n",
        content,
        flags=re.DOTALL,
    )

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    return completed, total, percentage


def _update_task_status(filepath: str, task_number: str, new_status: str) -> Tuple[bool, Optional[str]]:
    if not os.path.exists(filepath):
        return False, "Task file not found"

    try:
        new_status = _normalize_status(new_status)
    except ValueError as exc:
        return False, str(exc)

    parsed = _parse_task_file(filepath)
    subtasks = parsed.get("subtasks", [])

    target = next((task for task in subtasks if task["number"] == task_number), None)
    if not target:
        return False, f"Subtask {task_number} not found"

    if new_status in {"in-progress", "completed", "partial"}:
        unmet = _has_unmet_dependencies(subtasks, task_number)
        if unmet:
            deps = ", ".join([f"Task {dep}" for dep in unmet])
            return False, f"Subtask {task_number} is blocked by {deps}"

    target["status"] = new_status
    if new_status == "completed":
        target["fallback_record"] = {}

    try:
        _rewrite_task_file(filepath, subtasks)
    except Exception as exc:
        return False, str(exc)
    return True, None


def _update_subtask_fallback(filepath: str, task_number: str, fallback_record: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    if not os.path.exists(filepath):
        return False, "Task file not found"

    parsed = _parse_task_file(filepath)
    subtasks = parsed.get("subtasks", [])
    target = next((task for task in subtasks if task["number"] == task_number), None)
    if not target:
        return False, f"Subtask {task_number} not found"

    try:
        normalized = _normalize_fallback_record(fallback_record)
    except ValueError as exc:
        return False, str(exc)

    target["fallback_record"] = normalized
    fallback_state = normalized.get("state")
    if fallback_state:
        target["status"] = fallback_state

    try:
        _rewrite_task_file(filepath, subtasks)
    except Exception as exc:
        return False, str(exc)
    return True, None


def _normalize_subtasks(subtasks: Any) -> List[Dict[str, Any]]:
    if not isinstance(subtasks, list) or not subtasks:
        raise ValueError("subtasks must be a non-empty array")

    normalized: List[Dict[str, Any]] = []
    for idx, item in enumerate(subtasks, 1):
        if not isinstance(item, dict):
            raise ValueError(f"subtasks[{idx}] must be an object")

        name = item.get("name") or item.get("title")
        description = item.get("description") or item.get("desc")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"subtasks[{idx}] is missing required field: name/title")
        if not isinstance(description, str) or not description.strip():
            raise ValueError(f"subtasks[{idx}] is missing required field: description")

        priority = item.get("priority", "medium")
        if not isinstance(priority, str) or not priority.strip():
            priority = "medium"

        dependencies = item.get("dependencies", [])
        if isinstance(dependencies, str):
            if not dependencies.strip() or dependencies.strip().lower() == "none":
                dependencies = []
            else:
                raise ValueError(f"subtasks[{idx}].dependencies must be an array")
        if not isinstance(dependencies, list):
            raise ValueError(f"subtasks[{idx}].dependencies must be an array")

        normalized_deps: List[str] = []
        for dep in dependencies:
            dep_str = str(dep).strip()
            if not dep_str.isdigit():
                raise ValueError(f"subtasks[{idx}].dependencies contains invalid value: {dep}")
            normalized_deps.append(dep_str)

        status = _normalize_status(str(item.get("status", "pending")))
        kind = _normalize_followup_kind(str(item.get("kind", "repair"))) if item.get("kind") else ""
        owner = str(item.get("owner", "")).strip()
        acceptance_criteria = _normalize_acceptance_criteria(item.get("acceptance_criteria", []))
        fallback_record = _normalize_fallback_record(item.get("fallback_record", {}))

        normalized.append(
            {
                "name": name.strip(),
                "description": description.strip(),
                "status": status,
                "priority": priority.strip().lower(),
                "dependencies": normalized_deps,
                "split_rationale": (
                    item.get("split_rationale")
                    or item.get("split_reason")
                    or item.get("rationale")
                    or item.get("reason")
                    or ""
                ),
                "kind": kind,
                "owner": owner,
                "acceptance_criteria": acceptance_criteria,
                "fallback_record": fallback_record,
            }
        )

    return normalized


def _default_split_rationale(subtask: Dict[str, Any], task_index: int, total: int) -> str:
    deps = subtask.get("dependencies", [])
    if deps:
        deps_text = ", ".join([f"Task {dep}" for dep in deps])
        return f"This step is separated to respect execution order and wait for prerequisite outputs from {deps_text}."
    if task_index == 1:
        return "This is isolated as the first step to establish context and reduce downstream rework risk."
    if task_index == total:
        return "This final step is split out to consolidate outputs and verify completion criteria."
    return "This is split as an independently verifiable action to improve traceability and status tracking."


def _next_subtask_number(subtasks: List[Dict[str, Any]]) -> int:
    if not subtasks:
        return 1
    return max(int(task["number"]) for task in subtasks) + 1


def _normalize_followup_subtasks(subtasks: Any) -> List[Dict[str, Any]]:
    if not isinstance(subtasks, list) or not subtasks:
        raise ValueError("follow_up_subtasks must be a non-empty array")

    normalized: List[Dict[str, Any]] = []
    for idx, item in enumerate(subtasks, 1):
        if not isinstance(item, dict):
            raise ValueError(f"follow_up_subtasks[{idx}] must be an object")
        name = item.get("name")
        goal = item.get("goal") or item.get("description")
        description = item.get("description") or item.get("goal")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"follow_up_subtasks[{idx}] missing name")
        if not isinstance(goal, str) or not goal.strip():
            raise ValueError(f"follow_up_subtasks[{idx}] missing goal/description")
        kind = _normalize_followup_kind(str(item.get("kind", "repair")))
        owner = str(item.get("owner", "")).strip()
        acceptance_criteria = _normalize_acceptance_criteria(item.get("acceptance_criteria", []))
        depends_on = item.get("depends_on", [])
        if isinstance(depends_on, str):
            depends_on = [depends_on]
        if not isinstance(depends_on, list):
            raise ValueError(f"follow_up_subtasks[{idx}].depends_on must be an array")
        dependencies: List[str] = []
        source_task_refs: List[str] = []
        for dep in depends_on:
            dep_str = str(dep).strip()
            if dep_str.isdigit():
                dependencies.append(dep_str)
            elif dep_str:
                source_task_refs.append(dep_str)

        normalized.append(
            {
                "name": name.strip(),
                "description": description.strip(),
                "goal": goal.strip(),
                "kind": kind,
                "owner": owner,
                "priority": str(item.get("priority", "medium")).strip().lower() or "medium",
                "dependencies": dependencies,
                "source_task_refs": source_task_refs,
                "acceptance_criteria": acceptance_criteria,
                "status": "pending",
            }
        )
    return normalized


def _build_recovery_decision(
    task_data: Dict[str, Any],
    subtask: Dict[str, Any],
    retry_budget_remaining: int,
    time_budget_remaining: str,
    available_roles: List[str],
    allowed_degraded_delivery: bool,
    is_on_critical_path: bool,
) -> Dict[str, Any]:
    fallback_record = subtask.get("fallback_record", {}) or {}
    reason_code = str(fallback_record.get("reason_code", "")).strip()
    state = str(fallback_record.get("state") or subtask.get("status", "pending")).strip()
    retry_count = int(fallback_record.get("retry_count", 0) or 0)
    partial_artifacts = fallback_record.get("partial_artifacts", [])
    has_partial_value = bool(partial_artifacts) or state == "partial"
    preserve_artifacts = list(partial_artifacts)
    suggested_owner = "main"
    escalation_reason = ""
    stop_auto_recovery = False

    primary_action = "split"
    recommended_actions = ["split", "retry_with_fix", "execution_handoff"]
    decision_level = "auto"
    rationale = "Default to narrowing the problem before attempting a broad retry."
    next_subtasks: List[Dict[str, Any]] = [
        {
            "name": f"Diagnose recovery path for Task {subtask['number']}",
            "goal": "Identify the smallest safe next step to recover this unfinished task",
            "description": "Review current failure evidence, isolate the cause, and recommend the next action",
            "kind": "diagnose",
            "owner": "main",
            "depends_on": [subtask["number"]],
            "acceptance_criteria": ["Root cause summary produced", "Next action chosen"],
        }
    ]
    resume_condition = "A smaller recovery step is ready for execution."

    if reason_code == "dependency_unmet":
        primary_action = "pause"
        recommended_actions = ["pause", "split"]
        rationale = "Dependencies are not satisfied yet, so the safest next step is to wait or create a prerequisite task."
        next_subtasks = []
        resume_condition = "All prerequisite subtasks are completed."
    elif reason_code == "tool_error":
        primary_action = "retry_with_fix"
        recommended_actions = ["retry_with_fix", "split"]
        rationale = "A tool error usually benefits from a targeted fix before another attempt."
        next_subtasks = [
            {
                "name": f"Diagnose tool error for Task {subtask['number']}",
                "goal": "Identify whether the failure came from arguments, environment, or execution path",
                "description": "Inspect the failing tool output and isolate the smallest corrective change",
                "kind": "diagnose",
                "owner": "main",
                "depends_on": [subtask["number"]],
                "acceptance_criteria": ["Tool error root cause identified", "Recovery action selected"],
            },
            {
                "name": f"Retry Task {subtask['number']} with fix",
                "goal": "Re-run the task after applying the narrowest safe fix",
                "description": "Apply the identified fix and retry the failed path once",
                "kind": "retry",
                "owner": subtask.get("owner") or "main",
                "depends_on": ["diagnose:tool-error"],
                "acceptance_criteria": ["Retry completed", "Outcome recorded"],
            },
        ]
    elif reason_code == "validation_failed":
        primary_action = "split"
        recommended_actions = ["split", "execution_handoff"]
        rationale = "Validation failure means the work likely needs diagnosis plus a focused repair and re-check."
        suggested_owner = "main"
        next_subtasks = [
            {
                "name": f"Diagnose validation failure for Task {subtask['number']}",
                "goal": "Determine why the result failed acceptance checks",
                "description": "Inspect failed outputs and produce a precise repair plan",
                "kind": "diagnose",
                "owner": "main",
                "depends_on": [subtask["number"]],
                "acceptance_criteria": ["Validation gap identified", "Repair scope defined"],
            },
            {
                "name": f"Repair Task {subtask['number']} after validation failure",
                "goal": "Address the failed validation gaps without changing the main objective",
                "description": "Implement the smallest repair that satisfies the acceptance checks",
                "kind": "repair",
                "owner": "subagent:builder" if "builder" in available_roles else "main",
                "depends_on": ["diagnose:validation-failure"],
                "acceptance_criteria": ["Repair applied", "Ready for verification"],
            },
            {
                "name": f"Verify repaired output for Task {subtask['number']}",
                "goal": "Confirm the repair closes the validation gap",
                "description": "Run focused verification on the repaired result",
                "kind": "verify",
                "owner": "subagent:verifier" if "verifier" in available_roles else "main",
                "depends_on": ["repair:validation-failure"],
                "acceptance_criteria": ["Verification result recorded"],
            },
        ]
        resume_condition = "Repair and focused verification have both completed."
    elif reason_code in {"missing_context", "waiting_user_input"}:
        primary_action = "decision_handoff"
        recommended_actions = ["decision_handoff", "pause"]
        decision_level = "user_confirm"
        rationale = "The task needs new information before the system can safely continue."
        escalation_reason = "Missing input changes how the task should proceed."
        suggested_owner = "user"
        stop_auto_recovery = True
        next_subtasks = []
        resume_condition = "Required user input is provided."
    elif reason_code == "budget_exhausted" or state == "timed_out":
        if allowed_degraded_delivery and has_partial_value and not is_on_critical_path:
            primary_action = "degrade"
            recommended_actions = ["degrade", "split", "abandon"]
            decision_level = "agent_decide"
            rationale = "The budget is exhausted, but partial value exists and may be deliverable."
            escalation_reason = "Degraded delivery changes the completion promise."
        else:
            primary_action = "split"
            recommended_actions = ["split", "degrade", "abandon"]
            decision_level = "agent_decide"
            rationale = "Budget is exhausted, so the next step should be smaller or explicitly de-scoped."
            escalation_reason = "Further recovery needs explicit tradeoff handling."
        stop_auto_recovery = True
    elif reason_code == "subagent_empty_result":
        primary_action = "split"
        recommended_actions = ["split", "retry_with_fix", "execution_handoff"]
        rationale = "An empty sub-agent result usually means the brief should be narrowed before retrying."
        next_subtasks = [
            {
                "name": f"Rewrite sub-agent brief for Task {subtask['number']}",
                "goal": "Create a narrower, more actionable instruction set for the failed sub-agent task",
                "description": "Shrink scope and make the expected output explicit before re-dispatching",
                "kind": "diagnose",
                "owner": "main",
                "depends_on": [subtask["number"]],
                "acceptance_criteria": ["Updated sub-agent brief prepared"],
            },
            {
                "name": f"Re-dispatch Task {subtask['number']} to a narrowed sub-agent task",
                "goal": "Retry the failed sub-agent path with a smaller objective",
                "description": "Run the task again with the narrowed brief",
                "kind": "handoff",
                "owner": "subagent:general",
                "depends_on": ["diagnose:rewrite-brief"],
                "acceptance_criteria": ["New sub-agent result recorded"],
            },
        ]
    elif reason_code == "subagent_execution_error":
        primary_action = "execution_handoff"
        recommended_actions = ["execution_handoff", "retry_with_fix", "split"]
        rationale = "The current executor is likely a poor fit for the failure mode, so responsibility should move first."
        suggested_owner = "main"
        next_subtasks = [
            {
                "name": f"Review sub-agent execution error for Task {subtask['number']}",
                "goal": "Determine whether the failure came from role mismatch, context loss, or task size",
                "description": "Inspect the sub-agent error and choose a safer execution owner",
                "kind": "diagnose",
                "owner": "main",
                "depends_on": [subtask["number"]],
                "acceptance_criteria": ["New execution owner selected"],
            }
        ]

    if retry_budget_remaining <= 0 or retry_count >= 2:
        decision_level = "agent_decide"
        stop_auto_recovery = True
        escalation_reason = escalation_reason or "Automatic recovery budget is exhausted."

    if is_on_critical_path and primary_action in {"degrade", "abandon", "fallback_path"}:
        decision_level = "user_confirm"
        stop_auto_recovery = True
        escalation_reason = "Critical-path recovery would change delivery commitments."

    if decision_level not in RECOVERY_DECISION_LEVELS:
        decision_level = "agent_decide"

    return {
        "todo_id": task_data.get("metadata", {}).get("Todo ID", ""),
        "subtask_number": subtask["number"],
        "primary_action": primary_action,
        "recommended_actions": recommended_actions,
        "decision_level": decision_level,
        "rationale": rationale,
        "preserve_artifacts": preserve_artifacts,
        "next_subtasks": next_subtasks,
        "resume_condition": resume_condition,
        "escalation_reason": escalation_reason,
        "stop_auto_recovery": stop_auto_recovery,
        "suggested_owner": suggested_owner,
        "retry_budget_remaining": retry_budget_remaining,
        "time_budget_remaining": time_budget_remaining,
        "has_partial_value": has_partial_value,
    }


@tool(
    name="create_task",
    description="Create a new task with structured subtasks and dependency metadata, subtasks is must be provided.",
    stop_after_tool_call=False,
    requires_confirmation=False,
    cache_results=False,
    parameters={
        "type": "object",
        "properties": {
            "task_name": {"type": "string"},
            "context": {"type": "string"},
            "split_reason": {"type": "string"},
            "subtasks": {"type": "array", "items": {"type": "object"}},
        },
        "required": ["task_name", "context", "split_reason", "subtasks"],
    },
)
def create_task(task_name: str, context: str, split_reason: str, subtasks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Create a markdown task file with structured subtasks and dependency metadata."""
    try:
        if not isinstance(split_reason, str) or not split_reason.strip():
            raise ValueError("split_reason must be a non-empty string")

        normalized_subtasks = _normalize_subtasks(subtasks)
        _ensure_todo_dir()
        todo_id = _generate_todo_id(task_name)
        filepath = os.path.join(_get_todo_dir(), f"{todo_id}.md")
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        metadata = f"""# Task: {task_name}

## Metadata
- **Todo ID**: {todo_id}
- **Status**: pending
- **Priority**: high
- **Created**: {now}
- **Updated**: {now}
- **Progress**: 0/{len(normalized_subtasks)} (0%)
"""
        context_section = f"""
## Context
**Goal**: {context}
**Split Reason**: {split_reason.strip()}

**Acceptance Criteria**:
- Task completion criteria will be defined during execution
"""

        subtask_blocks: List[str] = []
        for index, subtask in enumerate(normalized_subtasks, 1):
            subtask["number"] = str(index)
            if not str(subtask.get("split_rationale", "")).strip():
                subtask["split_rationale"] = _default_split_rationale(subtask, index, len(normalized_subtasks))
            subtask_blocks.append(_render_subtask(subtask))
        subtasks_section = "\n## Subtasks\n\n" + "\n\n".join(subtask_blocks) + "\n"

        dependencies_section = """
## Dependencies
- **Blocked subtasks**: None
- **Ready subtasks**: None
- **Blocking subtasks**: None
"""
        notes_section = """
## Notes
Task created automatically. Update as needed during execution.
"""

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(metadata + context_section + subtasks_section + dependencies_section + notes_section)

        created = _parse_task_file(filepath)
        refreshed_deps = _generate_dependencies_section(created.get("subtasks", []))
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        content = re.sub(r"## Dependencies\n.*?(?=\n## |\Z)", refreshed_deps + "\n", content, flags=re.DOTALL)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

        _emit_obs(
            todo_id=todo_id,
            event_type="task_started",
            payload={
                "tool": "create_task",
                "task_name": task_name,
                "subtask_count": len(normalized_subtasks),
                "filepath": filepath,
                "todo_id": todo_id,
                "split_reason": split_reason.strip(),
            },
        )
        return {"success": True, "filepath": filepath, "todo_id": todo_id, "subtask_count": len(normalized_subtasks)}
    except Exception as e:
        _emit_obs(
            todo_id="unknown",
            event_type="tool_failed",
            status="error",
            payload={"tool": "create_task", "task_name": task_name, "error": str(e)},
        )
        return {"success": False, "error": str(e)}


@tool(
    name="update_task_status",
    description="Update a subtask status. Enforces dependency constraints before state transitions.",
    stop_after_tool_call=False,
    requires_confirmation=False,
    cache_results=False,
)
def update_task_status(todo_id: str, subtask_number: int, status: str) -> Dict[str, Any]:
    """Update a subtask status while enforcing dependency constraints."""
    try:
        status = _normalize_status(status)
    except ValueError as exc:
        return {"success": False, "error": str(exc)}

    task_data = _get_task_by_todo_id(todo_id)
    if not task_data:
        return {"success": False, "error": f"Todo not found: {todo_id}"}

    ok, error = _update_task_status(task_data["filepath"], str(subtask_number), status)
    if not ok:
        return {"success": False, "error": error or f"Failed to update subtask {subtask_number}"}

    updated_task = _parse_task_file(task_data["filepath"])
    completed, total, percentage = _calculate_progress(updated_task.get("subtasks", []))
    _emit_obs(
        todo_id=todo_id,
        event_type="status_updated",
        payload={
            "tool": "update_task_status",
            "todo_id": todo_id,
            "subtask_number": subtask_number,
            "status": status,
            "progress": f"{completed}/{total} ({percentage}%)",
        },
    )
    if total > 0 and completed == total:
        _emit_obs(
            todo_id=todo_id,
            event_type="task_finished",
            payload={"tool": "update_task_status", "todo_id": todo_id, "progress": f"{completed}/{total} ({percentage}%)"},
        )
    return {
        "success": True,
        "message": f"Subtask {subtask_number} updated to: {status}",
        "progress": f"{completed}/{total} ({percentage}%)",
    }


@tool(
    name="record_task_fallback",
    description="Attach a structured fallback record to a subtask and optionally move it into an unfinished state.",
    stop_after_tool_call=False,
    requires_confirmation=False,
    cache_results=False,
)
def record_task_fallback(
    todo_id: str,
    subtask_number: int,
    state: str,
    reason_code: str,
    reason_detail: str = "",
    impact_scope: str = "",
    retryable: bool = True,
    required_input: Optional[List[str]] = None,
    suggested_next_action: str = "",
    evidence: Optional[List[str]] = None,
    owner: str = "",
    retry_count: int = 0,
    retry_budget_remaining: int = 2,
) -> Dict[str, Any]:
    """Record structured fallback metadata for an unfinished subtask."""
    task_data = _get_task_by_todo_id(todo_id)
    if not task_data:
        return {"success": False, "error": f"Todo not found: {todo_id}"}

    try:
        fallback_record = _normalize_fallback_record(
            {
                "state": state,
                "reason_code": reason_code,
                "reason_detail": reason_detail,
                "impact_scope": impact_scope,
                "retryable": retryable,
                "required_input": required_input or [],
                "suggested_next_action": suggested_next_action,
                "evidence": evidence or [],
                "owner": owner or "main",
                "retry_count": retry_count,
                "retry_budget_remaining": retry_budget_remaining,
            }
        )
    except ValueError as exc:
        return {"success": False, "error": str(exc)}

    ok, error = _update_subtask_fallback(task_data["filepath"], str(subtask_number), fallback_record)
    if not ok:
        return {"success": False, "error": error or f"Failed to record fallback for subtask {subtask_number}"}

    _emit_obs(
        todo_id=todo_id,
        event_type="task_fallback_recorded",
        payload={
            "tool": "record_task_fallback",
            "todo_id": todo_id,
            "subtask_number": subtask_number,
            "fallback_record": fallback_record,
        },
    )
    return {"success": True, "fallback_record": fallback_record}


@tool(
    name="plan_task_recovery",
    description="Build a rule-based recovery decision for a failed or unfinished subtask.",
    stop_after_tool_call=False,
    requires_confirmation=False,
    cache_results=False,
)
def plan_task_recovery(
    todo_id: str,
    subtask_number: int,
    retry_budget_remaining: int = 2,
    time_budget_remaining: str = "",
    available_roles: Optional[List[str]] = None,
    allowed_degraded_delivery: bool = False,
    is_on_critical_path: bool = False,
) -> Dict[str, Any]:
    """Create a minimal structured recovery decision from fallback metadata."""
    task_data = _get_task_by_todo_id(todo_id)
    if not task_data:
        return {"success": False, "error": f"Todo not found: {todo_id}"}

    subtask = next((task for task in task_data.get("subtasks", []) if task["number"] == str(subtask_number)), None)
    if not subtask:
        return {"success": False, "error": f"Subtask {subtask_number} not found"}

    decision = _build_recovery_decision(
        task_data=task_data,
        subtask=subtask,
        retry_budget_remaining=int(retry_budget_remaining),
        time_budget_remaining=str(time_budget_remaining or ""),
        available_roles=[str(role).strip() for role in (available_roles or []) if str(role).strip()],
        allowed_degraded_delivery=bool(allowed_degraded_delivery),
        is_on_critical_path=bool(is_on_critical_path),
    )
    _emit_obs(
        todo_id=todo_id,
        event_type="task_recovery_planned",
        payload={
            "tool": "plan_task_recovery",
            "todo_id": todo_id,
            "subtask_number": subtask_number,
            "decision": {
                "primary_action": decision["primary_action"],
                "decision_level": decision["decision_level"],
                "stop_auto_recovery": decision["stop_auto_recovery"],
            },
        },
    )
    return {"success": True, "recovery_decision": decision}


@tool(
    name="append_followup_subtasks",
    description="Append follow-up subtasks, typically generated from a recovery decision.",
    stop_after_tool_call=False,
    requires_confirmation=False,
    cache_results=False,
)
def append_followup_subtasks(todo_id: str, follow_up_subtasks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Append new follow-up subtasks to an existing todo file."""
    task_data = _get_task_by_todo_id(todo_id)
    if not task_data:
        return {"success": False, "error": f"Todo not found: {todo_id}"}

    try:
        new_items = _normalize_followup_subtasks(follow_up_subtasks)
    except ValueError as exc:
        return {"success": False, "error": str(exc)}

    filepath = task_data["filepath"]
    subtasks = task_data.get("subtasks", [])
    next_number = _next_subtask_number(subtasks)
    added_numbers: List[str] = []

    for item in new_items:
        item["number"] = str(next_number)
        item["split_rationale"] = f"Recovery follow-up generated to progress unfinished work via {item['kind']}."
        item["dependencies"] = item.get("dependencies", [])
        item["description"] = item["description"]
        item["status"] = "pending"
        subtasks.append(item)
        added_numbers.append(item["number"])
        next_number += 1

    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    rendered_blocks = "\n\n".join(_render_subtask(item) for item in new_items)
    content = re.sub(
        r"(\n## Dependencies)",
        "\n\n" + rendered_blocks + r"\1",
        content,
        count=1,
    )
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    try:
        _rewrite_task_file(filepath, subtasks)
    except Exception as exc:
        return {"success": False, "error": str(exc)}

    _emit_obs(
        todo_id=todo_id,
        event_type="followup_subtasks_appended",
        payload={
            "tool": "append_followup_subtasks",
            "todo_id": todo_id,
            "subtask_numbers": added_numbers,
            "count": len(added_numbers),
        },
    )
    return {"success": True, "added_subtask_numbers": added_numbers, "count": len(added_numbers)}


@tool(
    name="list_tasks",
    description="List all task summaries in the todo directory.",
    stop_after_tool_call=False,
    requires_confirmation=False,
    cache_results=False,
)
def list_tasks() -> Dict[str, Any]:
    """List task summaries in the todo directory."""
    try:
        tasks = _list_all_tasks()
        summaries = []
        for task in tasks:
            meta = task.get("metadata", {})
            summaries.append(
                {
                    "todo_id": meta.get("Todo ID", meta.get("ID", "N/A")),
                    "status": meta.get("Status", "N/A"),
                    "priority": meta.get("Priority", "N/A"),
                    "progress": meta.get("Progress", "N/A"),
                    "file": task.get("filename", "N/A"),
                }
            )
        return {"success": True, "tasks": summaries, "count": len(summaries)}
    except Exception as e:
        return {"success": False, "error": str(e)}


@tool(
    name="get_next_task",
    description="Return the next executable subtask based on dependency constraints.",
    stop_after_tool_call=False,
    requires_confirmation=False,
    cache_results=False,
)
def get_next_task_item(todo_id: str) -> Dict[str, Any]:
    """Get the next executable pending subtask based on dependency satisfaction."""
    task_data = _get_task_by_todo_id(todo_id)
    if not task_data:
        return {"success": False, "status": "not_found", "error": f"Todo not found: {todo_id}"}

    next_task = _get_next_task(task_data.get("subtasks", []))
    if next_task:
        return {
            "success": True,
            "status": "ready",
            "next_task": {
                "number": next_task["number"],
                "name": next_task["name"],
                "description": next_task.get("description", ""),
                "priority": next_task.get("priority", "medium"),
                "dependencies": next_task.get("dependencies", []),
                "owner": next_task.get("owner", ""),
                "kind": next_task.get("kind", ""),
            },
        }

    all_done = all(task.get("status") in TERMINAL_SUBTASK_STATUSES for task in task_data.get("subtasks", []))
    if all_done:
        return {"success": True, "status": "all_completed", "message": "All tasks completed or explicitly abandoned."}
    return {"success": True, "status": "blocked", "message": "No tasks ready (dependencies not met or unfinished tasks need recovery)"}


@tool(
    name="get_task_progress",
    description="Get progress with completed, ready, blocked, and incomplete subtask breakdown.",
    stop_after_tool_call=False,
    requires_confirmation=False,
    cache_results=False,
)
def get_task_progress(todo_id: str) -> Dict[str, Any]:
    """Get progress summary including completed, ready, blocked, and incomplete subtasks."""
    task_data = _get_task_by_todo_id(todo_id)
    if not task_data:
        return {"success": False, "error": f"Todo not found: {todo_id}"}

    completed, total, percentage = _calculate_progress(task_data.get("subtasks", []))
    blocked_status = _calculate_blocked_status(task_data.get("subtasks", []))
    metadata = task_data.get("metadata", {})
    resolved_todo_id = metadata.get("Todo ID", metadata.get("ID", todo_id))
    return {
        "success": True,
        "todo_id": resolved_todo_id,
        "progress": f"{completed}/{total} ({percentage}%)",
        "completed_tasks": [{"number": task["number"], "name": task["name"]} for task in task_data["subtasks"] if task["status"] == "completed"],
        "ready_tasks": [{"number": number, "name": name} for number, name in blocked_status["ready"]],
        "blocked_tasks": [{"number": number, "name": name, "waiting_for": deps} for number, name, deps in blocked_status["blocked"]],
        "incomplete_tasks": blocked_status["incomplete"],
    }


@tool(
    name="generate_task_report",
    description="Generate a formatted task report with progress bar and blocked summary.",
    stop_after_tool_call=False,
    requires_confirmation=False,
    cache_results=False,
)
def generate_task_report(todo_id: str) -> Dict[str, Any]:
    """Generate a formatted plain-text progress report for a task."""
    task_data = _get_task_by_todo_id(todo_id)
    if not task_data:
        return {"success": False, "error": f"Todo not found: {todo_id}"}

    metadata = task_data.get("metadata", {})
    subtasks = task_data.get("subtasks", [])
    completed, total, percentage = _calculate_progress(subtasks)

    lines = [
        "=" * 44,
        "TASK PROGRESS REPORT",
        "=" * 44,
        f"Todo ID: {metadata.get('Todo ID', metadata.get('ID', 'N/A'))}",
        f"Status: {metadata.get('Status', 'N/A')}",
        f"Priority: {metadata.get('Priority', 'N/A')}",
        f"Created: {metadata.get('Created', 'N/A')}",
        f"Updated: {metadata.get('Updated', 'N/A')}",
        "",
        f"PROGRESS: {completed}/{total} ({percentage}%)",
        f"{'█' * (percentage // 10)}{'░' * (10 - percentage // 10)} {percentage}%",
        "",
        "-" * 44,
        "SUBTASKS:",
        "-" * 44,
    ]
    for subtask in subtasks:
        status = subtask.get("status", "pending")
        icon = STATUS_ICONS.get(status, "?")
        deps = ", ".join(subtask.get("dependencies", [])) if subtask.get("dependencies") else "None"
        owner = subtask.get("owner") or "unassigned"
        lines.append(f"Task {subtask['number']}: {subtask['name']} [{icon}] {status}")
        lines.append(f"  Priority: {subtask.get('priority', 'N/A')}, Deps: {deps}, Owner: {owner}")
        fallback_record = subtask.get("fallback_record", {})
        if fallback_record:
            lines.append(
                f"  Fallback: {fallback_record.get('reason_code', 'n/a')} - {fallback_record.get('reason_detail', '')}".rstrip()
            )

    blocked = _calculate_blocked_status(subtasks)["blocked"]
    if blocked:
        lines.extend(["", "-" * 44, f"BLOCKED: {', '.join([item[0] for item in blocked])}", "These tasks are waiting on dependencies or recovery."])
    lines.append("=" * 44)
    return {"success": True, "report": "\n".join(lines)}


class TodoTools:
    @staticmethod
    def get_tools():
        return [
            create_task,
            update_task_status,
            record_task_fallback,
            plan_task_recovery,
            append_followup_subtasks,
            list_tasks,
            get_next_task_item,
            get_task_progress,
            generate_task_report,
        ]

    @staticmethod
    def get_tool_names():
        return [
            "create_task",
            "update_task_status",
            "record_task_fallback",
            "plan_task_recovery",
            "append_followup_subtasks",
            "list_tasks",
            "get_next_task",
            "get_task_progress",
            "generate_task_report",
        ]


def load_todo_tools():
    """Compatibility shim for existing callers."""
    return TodoTools
