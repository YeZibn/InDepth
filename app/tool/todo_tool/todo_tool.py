import glob
import json
import os
import re
import uuid
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
    "repair",
    "split",
    "fallback_path",
    "execution_handoff",
    "decision_handoff",
    "wait_user",
    "resolve_dependency",
    "pause",
    "degrade",
    "abandon",
}
FOLLOWUP_KINDS = {"diagnose", "repair", "retry", "verify", "handoff", "resume", "report"}
IN_PLACE_RECOVERY_ACTIONS = {"retry", "retry_with_fix", "repair", "wait_user", "resolve_dependency", "pause"}


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


def _generate_subtask_id() -> str:
    return f"st_{uuid.uuid4().hex[:10]}"


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
        "failure_state",
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

    for key in ["failure_facts", "failure_interpretation"]:
        value = record.get(key)
        if value is None:
            continue
        if not isinstance(value, dict):
            raise ValueError(f"{key} must be an object")
        normalized[key] = value

    retry_guidance = record.get("retry_guidance")
    if retry_guidance is not None:
        if isinstance(retry_guidance, str):
            retry_guidance = [retry_guidance]
        if not isinstance(retry_guidance, list):
            raise ValueError("retry_guidance must be a string or string array")
        normalized["retry_guidance"] = [str(item).strip() for item in retry_guidance if str(item).strip()]

    return normalized


def _render_subtask(subtask: Dict[str, Any]) -> str:
    number = subtask["number"]
    name = subtask["name"]
    subtask_id = str(subtask.get("subtask_id", "")).strip()
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
    origin_subtask_id = str(subtask.get("origin_subtask_id", "")).strip()
    origin_subtask_number = str(subtask.get("origin_subtask_number", "")).strip()

    lines = [
        f"### Task {number}: {name}",
        f"- **Subtask ID**: {subtask_id or _generate_subtask_id()}",
        f"- **Status**: {status}",
        f"- **Priority**: {priority}",
        f"- **Dependencies**: {deps_str}",
    ]
    if kind:
        lines.append(f"- **Kind**: {kind}")
    if owner:
        lines.append(f"- **Owner**: {owner}")
    if origin_subtask_id:
        lines.append(f"- **Origin Subtask ID**: {origin_subtask_id}")
    if origin_subtask_number:
        lines.append(f"- **Origin Subtask Number**: {origin_subtask_number}")
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
        subtask_id = _extract_simple_field(task_content, "Subtask ID") or f"legacy-task-{task_num}"
        split_rationale = _extract_simple_field(task_content, "Split Rationale")
        kind = _extract_simple_field(task_content, "Kind")
        owner = _extract_simple_field(task_content, "Owner")
        origin_subtask_id = _extract_simple_field(task_content, "Origin Subtask ID")
        origin_subtask_number = _extract_simple_field(task_content, "Origin Subtask Number")
        acceptance_criteria = _extract_json_field(task_content, "Acceptance Criteria", [])
        fallback_record = _extract_json_field(task_content, "Fallback Record", {})

        dependencies: List[str] = []
        if deps_str.strip() and deps_str.strip().lower() != "none":
            dependencies = re.findall(r"Task\s*(\d+)", deps_str)

        checklist_items = re.findall(r"- \*{1,2}\[(.)\]\*{1,2} (.*)", task_content)
        description = checklist_items[0][1].strip() if checklist_items else ""

        subtasks.append(
            {
                "number": task_num,
                "subtask_id": subtask_id,
                "name": task_name,
                "status": status,
                "priority": priority,
                "dependencies": dependencies,
                "description": description,
                "checklist": checklist_items,
                "split_rationale": split_rationale,
                "kind": kind,
                "owner": owner,
                "origin_subtask_id": origin_subtask_id,
                "origin_subtask_number": origin_subtask_number,
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
                "subtask_id": str(item.get("subtask_id") or "").strip() or _generate_subtask_id(),
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
                "origin_subtask_id": str(item.get("origin_subtask_id", "") or "").strip(),
                "origin_subtask_number": str(item.get("origin_subtask_number", "") or "").strip(),
                "acceptance_criteria": acceptance_criteria,
                "fallback_record": fallback_record,
            }
        )

    return normalized


def _normalize_plan_envelope(
    task_name: Any,
    context: Any,
    split_reason: Any,
    subtasks: Any,
) -> Dict[str, Any]:
    task_name_str = str(task_name or "").strip()
    context_str = str(context or "").strip()
    split_reason_str = str(split_reason or "").strip()
    if not task_name_str:
        raise ValueError("task_name must be a non-empty string")
    if not context_str:
        raise ValueError("context must be a non-empty string")
    if not split_reason_str:
        raise ValueError("split_reason must be a non-empty string")
    normalized_subtasks = _normalize_subtasks(subtasks)
    return {
        "task_name": task_name_str,
        "context": context_str,
        "split_reason": split_reason_str,
        "subtasks": normalized_subtasks,
    }


def _preview_text(value: Any, max_len: int = 80) -> str:
    text = str(value or "").replace("\n", " ").strip()
    if len(text) <= max_len:
        return text
    return text[:max_len].rstrip() + "..."


def _derive_prepare_task_name(task_name: Any, context: Any, active_todo_id: str = "") -> str:
    explicit = str(task_name or "").strip()
    if explicit:
        return explicit
    if active_todo_id:
        return f"Continue {active_todo_id}"
    summary = _preview_text(context, max_len=36)
    if not summary:
        return "Tracked Task"
    return summary


def _build_prepare_bootstrap_subtask(context: Any) -> Dict[str, Any]:
    context_preview = _preview_text(context, max_len=120) or "当前任务请求"
    return {
        "name": "澄清上下文并细化执行计划",
        "description": (
            "先读取现有材料、确认约束与交付物，再补充为可执行子任务并推进首个明确步骤。"
            f" 当前请求摘要：{context_preview}"
        ),
        "priority": "high",
        "acceptance_criteria": [
            "已形成首轮可执行拆分",
            "已确认当前任务的主要约束与交付物",
        ],
        "split_rationale": "Prepare 阶段先建立稳定执行骨架，避免在 plan_task 中现场过度设计。",
        "owner": "main",
    }


def _build_prepare_update_plan(
    context: Any,
    active_todo_id: str,
    active_subtask_number: int = 0,
    active_subtask_status: str = "",
) -> Dict[str, Any]:
    context_preview = _preview_text(context, max_len=160) or "当前任务请求"
    todo_id = str(active_todo_id or "").strip()
    active_number = int(active_subtask_number or 0)
    active_status = str(active_subtask_status or "").strip()
    update_reason = "根据最新请求细化已有 todo，避免重复 create。"
    if active_number:
        return {
            "update_reason": update_reason,
            "operations": [
                {
                    "type": "update_subtask",
                    "subtask_number": active_number,
                    "fields_to_update": {
                        "description": (
                            "继续沿当前子任务推进，并吸收本轮新增上下文。"
                            f" 最新请求摘要：{context_preview}"
                        ),
                        "acceptance_criteria": [
                            "当前子任务描述已反映最新请求",
                            "已基于更新后的执行说明继续推进",
                        ],
                    },
                    "update_reason": (
                        f"Active todo={todo_id}，active subtask={active_number}[{active_status or 'unknown'}]，"
                        "因此优先更新当前子任务而不是新增 todo。"
                    ),
                }
            ],
        }
    return {
        "update_reason": update_reason,
        "operations": [
            {
                "type": "append_subtasks",
                "subtasks": [
                    {
                        "name": "承接最新请求并继续推进",
                        "description": (
                            "在已有 todo 基础上追加一个后续步骤，承接本轮新增任务上下文。"
                            f" 最新请求摘要：{context_preview}"
                        ),
                        "priority": "high",
                        "acceptance_criteria": [
                            "后续步骤已写入 todo",
                            "已形成承接当前请求的执行锚点",
                        ],
                    }
                ],
            }
        ],
    }


def _build_active_todo_summary(todo_id: str, active_subtask_number: int = 0, active_subtask_status: str = "") -> str:
    todo_id = str(todo_id or "").strip()
    if not todo_id:
        return ""
    task_data = _get_task_by_todo_id(todo_id)
    if not task_data:
        return f"todo={todo_id} (summary unavailable)"

    metadata = task_data.get("metadata", {})
    subtasks = task_data.get("subtasks", [])
    completed, total, percentage = _calculate_progress(subtasks)
    summary = [
        f"todo={todo_id}",
        f"progress={completed}/{total} ({percentage}%)",
    ]
    if active_subtask_number:
        matched = next((item for item in subtasks if item.get("number") == str(active_subtask_number)), {})
        active_name = str(matched.get("name", "") or "").strip()
        active_status = str(active_subtask_status or matched.get("status", "") or "").strip()
        if active_name or active_status:
            summary.append(
                f"active_subtask={active_subtask_number}:{active_name or 'unnamed'}[{active_status or 'unknown'}]"
            )
    title = str(metadata.get("Task", "") or metadata.get("Title", "") or "").strip()
    if title:
        summary.append(f"title={_preview_text(title, 60)}")
    return "; ".join(summary)


def _should_use_todo_for_prepare(context: Any, active_todo_exists: bool, execution_intent: str = "") -> bool:
    if active_todo_exists:
        return True
    text = f"{str(context or '')} {str(execution_intent or '')}".lower()
    if len(text.strip()) >= 24:
        return True
    hints = [
        "写",
        "撰写",
        "论文",
        "报告",
        "设计",
        "计划",
        "分析",
        "整理",
        "实现",
        "修复",
        "重构",
        "调研",
        "测试",
        "review",
        "write",
        "draft",
        "analyze",
        "design",
        "implement",
        "fix",
        "refactor",
        "research",
    ]
    return any(hint in text for hint in hints)


@tool(
    name="prepare_task",
    description=(
        "Prepare a candidate execution plan before plan_task. "
        "This tool reads current todo context and returns a planning hint, but does not create or update todo state."
    ),
    stop_after_tool_call=False,
    requires_confirmation=False,
    cache_results=False,
    hidden=True,
    parameters={
        "type": "object",
        "properties": {
            "task_name": {"type": "string"},
            "context": {"type": "string"},
            "active_todo_id": {"type": "string"},
            "active_todo_exists": {"type": "boolean"},
            "active_todo_summary": {"type": "string"},
            "active_subtask_number": {"type": "integer"},
            "active_subtask_status": {"type": "string"},
            "execution_intent": {"type": "string"},
        },
        "required": ["context"],
    },
)
def prepare_task(
    context: str,
    task_name: str = "",
    active_todo_id: str = "",
    active_todo_exists: bool = False,
    active_todo_summary: str = "",
    active_subtask_number: int = 0,
    active_subtask_status: str = "",
    execution_intent: str = "",
) -> Dict[str, Any]:
    """Prepare a candidate plan before plan_task without mutating todo state."""
    context_str = str(context or "").strip()
    if not context_str:
        return {"success": False, "error": "context must be a non-empty string"}

    todo_id = str(active_todo_id or "").strip()
    todo_exists = bool(active_todo_exists or todo_id)
    resolved_task_name = _derive_prepare_task_name(task_name=task_name, context=context_str, active_todo_id=todo_id)
    resolved_summary = str(active_todo_summary or "").strip() or _build_active_todo_summary(
        todo_id=todo_id,
        active_subtask_number=int(active_subtask_number or 0),
        active_subtask_status=active_subtask_status,
    )
    should_use_todo = _should_use_todo_for_prepare(
        context=context_str,
        active_todo_exists=todo_exists,
        execution_intent=execution_intent,
    )
    recommended_mode = "update" if todo_exists else ("create" if should_use_todo else "skip")
    subtasks: List[Dict[str, Any]] = []
    split_reason = ""
    notes: List[str] = []
    planning_confidence = "medium"
    plan_ready = False
    update_plan: Dict[str, Any] = {}

    if should_use_todo and not todo_exists:
        subtasks = [_build_prepare_bootstrap_subtask(context=context_str)]
        split_reason = "先通过 Prepare 阶段建立最小执行骨架，再在执行中补充更细的子任务。"
        notes.append("当前无 active todo，建议先创建带 bootstrap subtask 的 todo。")
        plan_ready = True
        planning_confidence = "high"
    elif should_use_todo and todo_exists:
        split_reason = "当前已有 active todo，Prepare 阶段先提供 update 建议，由 plan_task 再做最终裁决。"
        notes.append("当前已有 active todo，建议优先沿用既有 todo，而不是重新 create。")
        if resolved_summary:
            notes.append(f"active todo summary: {resolved_summary}")
        update_plan = _build_prepare_update_plan(
            context=context_str,
            active_todo_id=todo_id,
            active_subtask_number=int(active_subtask_number or 0),
            active_subtask_status=active_subtask_status,
        )
        planning_confidence = "high"
        plan_ready = True
    else:
        split_reason = "当前任务规模较小，可视情况直接执行，无需立即建立 todo。"
        notes.append("Prepare 判断当前任务不一定需要 todo。")
        planning_confidence = "low"
        plan_ready = False

    result = {
        "success": True,
        "should_use_todo": should_use_todo,
        "plan_ready": plan_ready,
        "recommended_mode": recommended_mode,
        "task_name": resolved_task_name,
        "context": context_str,
        "split_reason": split_reason,
        "subtasks": subtasks,
        "planning_confidence": planning_confidence,
        "active_todo_id": todo_id,
        "active_todo_summary": resolved_summary,
        "notes": notes,
    }
    if should_use_todo and plan_ready and not todo_exists:
        result["recommended_plan_task_args"] = {
            "task_name": resolved_task_name,
            "context": context_str,
            "split_reason": split_reason,
            "subtasks": subtasks,
            "active_todo_id": todo_id,
        }
    if should_use_todo and plan_ready and todo_exists:
        result["update_plan"] = update_plan
        result["recommended_update_task_args"] = {
            "todo_id": todo_id,
            "update_reason": str(update_plan.get("update_reason", "") or "").strip(),
            "operations": update_plan.get("operations", []),
        }
    return result


def _append_create_style_subtasks(
    filepath: str,
    existing_subtasks: List[Dict[str, Any]],
    new_items: List[Dict[str, Any]],
    rationale_prefix: str,
) -> List[Dict[str, Any]]:
    subtasks = list(existing_subtasks or [])
    next_number = _next_subtask_number(subtasks)
    appended: List[Dict[str, Any]] = []
    for item in new_items:
        cloned = dict(item)
        cloned["number"] = str(next_number)
        if not str(cloned.get("split_rationale", "")).strip():
            cloned["split_rationale"] = f"{rationale_prefix} Added through structured todo update."
        subtasks.append(cloned)
        appended.append(cloned)
        next_number += 1
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    rendered_blocks = "\n\n".join(_render_subtask(item) for item in appended)
    content = re.sub(
        r"(\n## Dependencies)",
        "\n\n" + rendered_blocks + r"\1",
        content,
        count=1,
    )
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    _rewrite_task_file(filepath, subtasks)
    return appended


def _apply_update_task_operation(task_data: Dict[str, Any], operation: Dict[str, Any]) -> Dict[str, Any]:
    op = operation if isinstance(operation, dict) else {}
    op_type = str(op.get("type", "") or "").strip()
    todo_id = str(task_data.get("metadata", {}).get("Todo ID", task_data.get("metadata", {}).get("ID", "")) or "").strip()
    if not todo_id:
        todo_id = str(task_data.get("todo_id", "") or "").strip()

    if op_type == "update_subtask":
        fields_to_update = op.get("fields_to_update")
        if not isinstance(fields_to_update, dict) or not fields_to_update:
            raise ValueError("update_subtask operation requires a non-empty fields_to_update object")
        subtask_id = str(op.get("subtask_id", "") or "").strip()
        subtask_number = int(op.get("subtask_number") or 0)
        if not subtask_id and not subtask_number:
            raise ValueError("update_subtask operation requires subtask_id or subtask_number")
        result = update_subtask.entrypoint(
            todo_id=todo_id,
            subtask_id=subtask_id,
            subtask_number=subtask_number,
            fields_to_update=fields_to_update,
            update_reason=str(op.get("update_reason", "") or "").strip(),
        )
        if not result.get("success"):
            raise ValueError(str(result.get("error", "update_subtask failed")))
        return {
            "type": op_type,
            "subtask_id": result.get("subtask_id", ""),
            "subtask_number": result.get("subtask_number", ""),
            "updated_fields": result.get("updated_fields", []),
        }

    if op_type == "append_subtasks":
        subtasks = op.get("subtasks")
        normalized_subtasks = _normalize_subtasks(subtasks)
        appended = _append_create_style_subtasks(
            filepath=str(task_data["filepath"]),
            existing_subtasks=task_data.get("subtasks", []),
            new_items=normalized_subtasks,
            rationale_prefix="Structured update append.",
        )
        return {
            "type": op_type,
            "added_subtask_numbers": [item.get("number", "") for item in appended],
            "added_subtask_ids": [item.get("subtask_id", "") for item in appended],
            "count": len(appended),
        }

    if op_type == "reopen_subtask":
        subtask_id = str(op.get("subtask_id", "") or "").strip()
        subtask_number = int(op.get("subtask_number") or 0)
        if not subtask_id and not subtask_number:
            raise ValueError("reopen_subtask operation requires subtask_id or subtask_number")
        result = reopen_subtask.entrypoint(
            todo_id=todo_id,
            subtask_id=subtask_id,
            subtask_number=subtask_number,
            reason=str(op.get("reason", "") or "").strip(),
        )
        if not result.get("success"):
            raise ValueError(str(result.get("error", "reopen_subtask failed")))
        return {
            "type": op_type,
            "subtask_id": result.get("subtask_id", ""),
            "subtask_number": result.get("subtask_number", ""),
            "status": "in-progress",
        }

    raise ValueError(f"Unsupported update operation type: {op_type}")


def _create_todo_from_plan(envelope: Dict[str, Any], force_new_cycle: bool = False) -> Dict[str, Any]:
    return create_task.entrypoint(
        task_name=str(envelope.get("task_name", "") or "").strip(),
        context=str(envelope.get("context", "") or "").strip(),
        split_reason=str(envelope.get("split_reason", "") or "").strip(),
        subtasks=envelope.get("subtasks", []),
        force_new_cycle=bool(force_new_cycle),
    )


def _update_todo_from_plan(active_todo_id: str, envelope: Dict[str, Any]) -> Dict[str, Any]:
    return update_task.entrypoint(
        todo_id=str(active_todo_id or "").strip(),
        update_reason=str(envelope.get("split_reason", "") or "").strip(),
        operations=[
            {
                "type": "append_subtasks",
                "subtasks": envelope.get("subtasks", []),
            }
        ],
    )


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
                "subtask_id": str(item.get("subtask_id") or "").strip() or _generate_subtask_id(),
                "name": name.strip(),
                "description": description.strip(),
                "goal": goal.strip(),
                "kind": kind,
                "owner": owner,
                "priority": str(item.get("priority", "medium")).strip().lower() or "medium",
                "dependencies": dependencies,
                "source_task_refs": source_task_refs,
                "origin_subtask_id": str(item.get("origin_subtask_id", "") or "").strip(),
                "origin_subtask_number": str(item.get("origin_subtask_number", "") or "").strip(),
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
    def _pick_primary_action(record: Dict[str, Any], retryable_value: bool) -> str:
        suggested = str(record.get("suggested_next_action", "") or "").strip()
        if suggested in RECOVERY_ACTIONS:
            return suggested
        return "retry_with_fix" if retryable_value else "decision_handoff"

    def _recommended_actions_for(
        primary: str,
        retryable_value: bool,
        allow_degraded: bool,
        has_partial: bool,
    ) -> List[str]:
        actions: List[str] = [primary]
        if primary in {"retry", "retry_with_fix", "repair"}:
            actions.extend(["retry_with_fix", "repair", "split", "execution_handoff"])
        elif primary == "split":
            actions.extend(["split", "retry_with_fix", "execution_handoff", "decision_handoff"])
        elif primary == "execution_handoff":
            actions.extend(["execution_handoff", "retry_with_fix", "split", "decision_handoff"])
        elif primary == "wait_user":
            actions.extend(["wait_user", "decision_handoff", "pause"])
        elif primary == "resolve_dependency":
            actions.extend(["resolve_dependency", "pause", "split"])
        elif primary in {"degrade", "fallback_path"}:
            actions.extend(["degrade", "fallback_path", "split", "decision_handoff"])
        elif primary == "abandon":
            actions.extend(["abandon", "decision_handoff", "fallback_path"])
        else:
            actions.extend(["decision_handoff", "split", "retry_with_fix"])

        if retryable_value and "retry_with_fix" not in actions:
            actions.append("retry_with_fix")
        if allow_degraded and has_partial and "degrade" not in actions:
            actions.append("degrade")

        deduped: List[str] = []
        for item in actions:
            if item in RECOVERY_ACTIONS and item not in deduped:
                deduped.append(item)
        return deduped

    def _build_split_followup() -> List[Dict[str, Any]]:
        return [
            {
                "origin_subtask_id": subtask.get("subtask_id", ""),
                "origin_subtask_number": subtask["number"],
                "name": f"Derive a smaller recovery step for Task {subtask['number']}",
                "goal": "Create the next smaller recovery slice for the unfinished subtask",
                "description": "Narrow scope or rewrite the execution brief so the next attempt is materially safer than the failed one",
                "kind": "diagnose",
                "owner": "main",
                "depends_on": [subtask["number"]],
                "acceptance_criteria": ["Smaller recovery step defined"],
            }
        ]

    fallback_record = subtask.get("fallback_record", {}) or {}
    reason_code = str(fallback_record.get("reason_code", "")).strip()
    state = str(
        fallback_record.get("failure_state")
        or fallback_record.get("state")
        or subtask.get("status", "pending")
    ).strip()
    retry_count = int(fallback_record.get("retry_count", 0) or 0)
    retryable = bool(fallback_record.get("retryable", True))
    partial_artifacts = fallback_record.get("partial_artifacts", [])
    has_partial_value = bool(partial_artifacts) or state == "partial"
    preserve_artifacts = list(partial_artifacts)
    suggested_owner = "main"
    escalation_reason = ""
    stop_auto_recovery = False
    can_resume_in_place = True
    needs_derived_recovery_subtask = False

    primary_action = _pick_primary_action(fallback_record, retryable)
    recommended_actions = _recommended_actions_for(
        primary=primary_action,
        retryable_value=retryable,
        allow_degraded=allowed_degraded_delivery,
        has_partial=has_partial_value,
    )
    decision_level = "auto"
    rationale = "Prefer recovering the original subtask in place before deriving new recovery work."
    next_subtasks: List[Dict[str, Any]] = []
    resume_condition = "The original subtask can resume with a narrower corrective action."

    if reason_code == "dependency_unmet":
        primary_action = "resolve_dependency"
        rationale = "Dependencies are not satisfied yet, so the original subtask should wait or have prerequisites resolved first."
        resume_condition = "All prerequisite subtasks are completed."
    elif reason_code == "waiting_user_input":
        primary_action = "wait_user"
        decision_level = "user_confirm"
        rationale = "The original subtask is blocked on missing information and should resume only after the input arrives."
        escalation_reason = "Missing input changes how the task should proceed."
        suggested_owner = "user"
        stop_auto_recovery = True
        resume_condition = "Required user input is provided."
    elif reason_code == "budget_exhausted" or state == "timed_out":
        can_resume_in_place = False
        needs_derived_recovery_subtask = primary_action not in {"degrade", "fallback_path", "abandon"}
        if primary_action in {"degrade", "fallback_path", "abandon"} and allowed_degraded_delivery and has_partial_value:
            decision_level = "agent_decide"
            rationale = "The budget is exhausted, and partial value exists, so the next step should explicitly decide whether degraded delivery is acceptable."
            escalation_reason = "Degraded delivery changes the completion promise."
            resume_condition = "Degraded delivery is explicitly accepted."
        else:
            primary_action = "split"
            needs_derived_recovery_subtask = True
            decision_level = "agent_decide"
            rationale = "Budget is exhausted, so recovery should shrink scope into smaller derived work."
            escalation_reason = "Further recovery needs explicit tradeoff handling."
            next_subtasks = _build_split_followup()
            resume_condition = "A smaller derived recovery step is defined."
        stop_auto_recovery = True
    elif reason_code == "orphan_subtask_unbound":
        can_resume_in_place = False
        needs_derived_recovery_subtask = False
        primary_action = "decision_handoff"
        decision_level = "agent_decide"
        rationale = "Runtime could not attribute the failure to a concrete subtask, so execution should not continue automatically."
        escalation_reason = "A concrete subtask must be bound before recovery can proceed."
        suggested_owner = "main"
        stop_auto_recovery = True
        next_subtasks = []
        resume_condition = "Select or create the correct subtask before resuming work."
    else:
        can_resume_in_place = primary_action in IN_PLACE_RECOVERY_ACTIONS
        needs_derived_recovery_subtask = primary_action in {"split", "execution_handoff"}
        if primary_action == "wait_user":
            decision_level = "user_confirm"
            suggested_owner = "user"
            stop_auto_recovery = True
            escalation_reason = "The next step depends on external input."
            rationale = "The recovery assessment indicates the task should pause for additional input before continuing."
            resume_condition = "Required external input is provided."
        elif primary_action == "resolve_dependency":
            rationale = "The recovery assessment indicates prerequisite work should be completed before retrying the original subtask."
            resume_condition = "Dependencies are resolved."
        elif primary_action in {"split", "execution_handoff"}:
            can_resume_in_place = False
            needs_derived_recovery_subtask = True
            decision_level = "agent_decide"
            stop_auto_recovery = True
            if primary_action == "split":
                rationale = "The recovery assessment recommends narrowing scope before the next attempt."
                next_subtasks = _build_split_followup()
                resume_condition = "A smaller recovery slice is defined."
            else:
                rationale = "The recovery assessment recommends changing the executor before continuing."
                resume_condition = "A safer execution owner is selected."
                escalation_reason = "Recovery requires choosing a different execution owner."
        elif primary_action in {"degrade", "fallback_path", "abandon"}:
            can_resume_in_place = False
            decision_level = "agent_decide"
            stop_auto_recovery = True
            rationale = "The recovery assessment recommends changing the delivery path rather than continuing the original subtask unchanged."
            resume_condition = "The alternative delivery path is explicitly accepted."
        else:
            suggested_owner = subtask.get("owner") or "main"
            rationale = "The recovery assessment recommends a targeted in-place correction before introducing new recovery work."
            resume_condition = "Apply the targeted fix and retry the original subtask."

    if retry_budget_remaining <= 0 or retry_count >= 2:
        if can_resume_in_place and primary_action in {"retry", "retry_with_fix", "repair"}:
            can_resume_in_place = False
            needs_derived_recovery_subtask = True
            primary_action = "split"
            rationale = "Automatic retry budget is exhausted, so recovery should derive a smaller or different path."
            next_subtasks = _build_split_followup()
            resume_condition = "A smaller derived recovery step is defined."
        decision_level = "agent_decide"
        stop_auto_recovery = True
        escalation_reason = escalation_reason or "Automatic recovery budget is exhausted."

    if is_on_critical_path and primary_action in {"degrade", "abandon", "fallback_path"}:
        decision_level = "user_confirm"
        stop_auto_recovery = True
        escalation_reason = "Critical-path recovery would change delivery commitments."

    if decision_level not in RECOVERY_DECISION_LEVELS:
        decision_level = "agent_decide"

    recommended_actions = _recommended_actions_for(
        primary=primary_action,
        retryable_value=retryable,
        allow_degraded=allowed_degraded_delivery,
        has_partial=has_partial_value,
    )

    return {
        "todo_id": task_data.get("metadata", {}).get("Todo ID", ""),
        "subtask_id": subtask.get("subtask_id", ""),
        "subtask_number": subtask["number"],
        "can_resume_in_place": can_resume_in_place,
        "needs_derived_recovery_subtask": needs_derived_recovery_subtask,
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
    name="plan_task",
    description=(
        "Validate and normalize a structured task plan before create_task or update_task. "
        "This tool is the planning prerequisite for both paths and decides mode=create/update based on active todo state."
    ),
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
            "active_todo_id": {"type": "string"},
        },
        "required": ["task_name", "context", "split_reason", "subtasks"],
    },
)
def plan_task(
    task_name: str,
    context: str,
    split_reason: str,
    subtasks: List[Dict[str, Any]],
    active_todo_id: str = "",
) -> Dict[str, Any]:
    """Normalize a task plan, decide mode, and execute the internal create/update path."""
    try:
        envelope = _normalize_plan_envelope(
            task_name=task_name,
            context=context,
            split_reason=split_reason,
            subtasks=subtasks,
        )
        active_todo_id = str(active_todo_id or "").strip()
        mode = "update" if active_todo_id else "create"
        execution_result = (
            _update_todo_from_plan(active_todo_id=active_todo_id, envelope=envelope)
            if mode == "update"
            else _create_todo_from_plan(envelope=envelope)
        )
        if not execution_result.get("success"):
            return {
                "success": False,
                "mode": mode,
                "active_todo_id": active_todo_id,
                "task_plan": envelope,
                "error": str(execution_result.get("error", "plan execution failed")),
                "execution_result": execution_result,
            }
        return {
            "success": True,
            "mode": mode,
            "active_todo_id": active_todo_id,
            "task_plan": envelope,
            "execution_result": execution_result,
            "subtask_count": len(envelope["subtasks"]),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@tool(
    name="create_task",
    description=(
        "Create a new tracked todo from a strict task plan. "
        "Use plan_task first to validate the envelope, then call create_task only when there is no active todo."
    ),
    stop_after_tool_call=False,
    requires_confirmation=False,
    cache_results=False,
    hidden=True,
    parameters={
        "type": "object",
        "properties": {
            "task_name": {"type": "string"},
            "context": {"type": "string"},
            "split_reason": {"type": "string"},
            "force_new_cycle": {"type": "boolean"},
            "subtasks": {"type": "array", "items": {"type": "object"}},
        },
        "required": ["task_name", "context", "split_reason", "subtasks"],
    },
)
def create_task(
    task_name: str,
    context: str,
    split_reason: str,
    subtasks: List[Dict[str, Any]],
    force_new_cycle: bool = False,
) -> Dict[str, Any]:
    """Create a markdown task file with structured subtasks and dependency metadata."""
    try:
        envelope = _normalize_plan_envelope(
            task_name=task_name,
            context=context,
            split_reason=split_reason,
            subtasks=subtasks,
        )
        _ensure_todo_dir()
        todo_id = _generate_todo_id(envelope["task_name"])
        filepath = os.path.join(_get_todo_dir(), f"{todo_id}.md")
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        metadata = f"""# Task: {envelope['task_name']}

## Metadata
- **Todo ID**: {todo_id}
- **Status**: pending
- **Priority**: high
- **Created**: {now}
- **Updated**: {now}
- **Progress**: 0/{len(envelope['subtasks'])} (0%)
"""
        context_section = f"""
## Context
**Goal**: {envelope['context']}
**Split Reason**: {envelope['split_reason']}

**Acceptance Criteria**:
- Task completion criteria will be defined during execution
"""

        subtask_blocks: List[str] = []
        for index, subtask in enumerate(envelope["subtasks"], 1):
            subtask["number"] = str(index)
            if not str(subtask.get("split_rationale", "")).strip():
                subtask["split_rationale"] = _default_split_rationale(subtask, index, len(envelope["subtasks"]))
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
                "task_name": envelope["task_name"],
                "subtask_count": len(envelope["subtasks"]),
                "filepath": filepath,
                "todo_id": todo_id,
                "split_reason": envelope["split_reason"],
            },
        )
        return {
            "success": True,
            "filepath": filepath,
            "todo_id": todo_id,
            "subtask_count": len(envelope["subtasks"]),
            "subtask_ids": [item.get("subtask_id", "") for item in envelope["subtasks"]],
            "todo_bound_at": now,
        }
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
    subtask = next((item for item in updated_task.get("subtasks", []) if item.get("number") == str(subtask_number)), {})
    _emit_obs(
        todo_id=todo_id,
        event_type="status_updated",
        payload={
            "tool": "update_task_status",
            "todo_id": todo_id,
            "subtask_number": subtask_number,
            "subtask_id": subtask.get("subtask_id", ""),
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
        "subtask_id": subtask.get("subtask_id", ""),
        "all_completed": total > 0 and completed == total,
    }


@tool(
    name="reopen_subtask",
    description="Reopen a previously failed, blocked, partial, timed out, or completed subtask and mark it in-progress again.",
    stop_after_tool_call=False,
    requires_confirmation=False,
    cache_results=False,
    parameters={
        "type": "object",
        "properties": {
            "todo_id": {"type": "string"},
            "subtask_id": {"type": "string"},
            "subtask_number": {"type": "integer"},
            "reason": {"type": "string"},
        },
        "required": ["todo_id"],
    },
)
def reopen_subtask(todo_id: str, subtask_id: str = "", subtask_number: int = 0, reason: str = "") -> Dict[str, Any]:
    task_data = _get_task_by_todo_id(todo_id)
    if not task_data:
        return {"success": False, "error": f"Todo not found: {todo_id}"}

    target = None
    if subtask_id:
        target = next((item for item in task_data.get("subtasks", []) if item.get("subtask_id") == str(subtask_id).strip()), None)
    if target is None and subtask_number:
        target = next((item for item in task_data.get("subtasks", []) if item.get("number") == str(subtask_number)), None)
    if target is None:
        return {"success": False, "error": "Subtask not found for the given subtask_id/subtask_number"}

    reopen_number = str(target.get("number"))
    ok, error = _update_task_status(task_data["filepath"], reopen_number, "in-progress")
    if not ok:
        return {"success": False, "error": error or "Failed to reopen subtask"}

    updated_task = _parse_task_file(task_data["filepath"])
    saved = next((item for item in updated_task.get("subtasks", []) if item.get("number") == reopen_number), target)
    _emit_obs(
        todo_id=todo_id,
        event_type="subtask_reopened",
        payload={
            "tool": "reopen_subtask",
            "todo_id": todo_id,
            "subtask_id": saved.get("subtask_id", ""),
            "subtask_number": saved.get("number", ""),
            "reason": str(reason or "").strip(),
        },
    )
    return {
        "success": True,
        "subtask_id": saved.get("subtask_id", ""),
        "subtask_number": saved.get("number", ""),
        "status": saved.get("status", ""),
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
    failure_state: str = "",
    reason_detail: str = "",
    impact_scope: str = "",
    retryable: bool = True,
    required_input: Optional[List[str]] = None,
    suggested_next_action: str = "",
    evidence: Optional[List[str]] = None,
    owner: str = "",
    retry_count: int = 0,
    retry_budget_remaining: int = 2,
    failure_facts: Optional[Dict[str, Any]] = None,
    failure_interpretation: Optional[Dict[str, Any]] = None,
    retry_guidance: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Record structured fallback metadata for an unfinished subtask."""
    task_data = _get_task_by_todo_id(todo_id)
    if not task_data:
        return {"success": False, "error": f"Todo not found: {todo_id}"}

    try:
        fallback_record = _normalize_fallback_record(
            {
                "state": state,
                "failure_state": failure_state or state,
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
                "failure_facts": failure_facts or {},
                "failure_interpretation": failure_interpretation or {},
                "retry_guidance": retry_guidance or [],
            }
        )
    except ValueError as exc:
        return {"success": False, "error": str(exc)}

    ok, error = _update_subtask_fallback(task_data["filepath"], str(subtask_number), fallback_record)
    if not ok:
        return {"success": False, "error": error or f"Failed to record fallback for subtask {subtask_number}"}

    updated_task = _parse_task_file(task_data["filepath"])
    subtask = next((item for item in updated_task.get("subtasks", []) if item.get("number") == str(subtask_number)), {})
    _emit_obs(
        todo_id=todo_id,
        event_type="task_fallback_recorded",
        payload={
            "tool": "record_task_fallback",
            "todo_id": todo_id,
            "subtask_number": subtask_number,
            "subtask_id": subtask.get("subtask_id", ""),
            "fallback_record": fallback_record,
        },
    )
    return {"success": True, "fallback_record": fallback_record, "subtask_id": subtask.get("subtask_id", "")}


@tool(
    name="update_task",
    description=(
        "Apply a strict, structured update package to an existing todo. "
        "Use this tool only when a todo already exists; operations must be explicit and complete."
    ),
    stop_after_tool_call=False,
    requires_confirmation=False,
    cache_results=False,
    hidden=True,
    parameters={
        "type": "object",
        "properties": {
            "todo_id": {"type": "string"},
            "update_reason": {"type": "string"},
            "operations": {"type": "array", "items": {"type": "object"}},
        },
        "required": ["todo_id", "update_reason", "operations"],
    },
)
def update_task(todo_id: str, update_reason: str, operations: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Apply strict structured operations to an existing todo."""
    task_data = _get_task_by_todo_id(todo_id)
    if not task_data:
        return {"success": False, "error": f"Todo not found: {todo_id}"}
    if not isinstance(update_reason, str) or not update_reason.strip():
        return {"success": False, "error": "update_reason must be a non-empty string"}
    if not isinstance(operations, list) or not operations:
        return {"success": False, "error": "operations must be a non-empty array"}

    results: List[Dict[str, Any]] = []
    for idx, operation in enumerate(operations, 1):
        if not isinstance(operation, dict):
            return {"success": False, "error": f"operations[{idx}] must be an object"}
        op_type = str(operation.get("type", "") or "").strip()
        if not op_type:
            return {"success": False, "error": f"operations[{idx}] missing required field: type"}
        try:
            current_task_data = _get_task_by_todo_id(todo_id)
            if not current_task_data:
                return {"success": False, "error": f"Todo not found during update: {todo_id}"}
            result = _apply_update_task_operation(current_task_data, operation)
            results.append(result)
        except Exception as exc:
            return {"success": False, "error": f"operations[{idx}] failed: {str(exc)}"}

    refreshed = _get_task_by_todo_id(todo_id) or task_data
    subtasks = refreshed.get("subtasks", [])
    _emit_obs(
        todo_id=todo_id,
        event_type="task_updated",
        payload={
            "tool": "update_task",
            "todo_id": todo_id,
            "update_reason": update_reason.strip(),
            "operation_types": [str(item.get("type", "")) for item in operations],
            "operation_count": len(results),
        },
    )
    return {
        "success": True,
        "todo_id": todo_id,
        "update_reason": update_reason.strip(),
        "results": results,
        "subtask_count": len(subtasks),
    }


@tool(
    name="update_subtask",
    description="Patch selected subtask fields by subtask_id or subtask_number without rewriting the whole todo structure.",
    stop_after_tool_call=False,
    requires_confirmation=False,
    cache_results=False,
    parameters={
        "type": "object",
        "properties": {
            "todo_id": {"type": "string"},
            "subtask_id": {"type": "string"},
            "subtask_number": {"type": "integer"},
            "fields_to_update": {"type": "object"},
            "update_reason": {"type": "string"},
        },
        "required": ["todo_id", "fields_to_update"],
    },
)
def update_subtask(
    todo_id: str,
    fields_to_update: Dict[str, Any],
    subtask_id: str = "",
    subtask_number: int = 0,
    update_reason: str = "",
) -> Dict[str, Any]:
    task_data = _get_task_by_todo_id(todo_id)
    if not task_data:
        return {"success": False, "error": f"Todo not found: {todo_id}"}
    if not isinstance(fields_to_update, dict) or not fields_to_update:
        return {"success": False, "error": "fields_to_update must be a non-empty object"}

    subtasks = task_data.get("subtasks", [])
    target = None
    if subtask_id:
        target = next((item for item in subtasks if item.get("subtask_id") == str(subtask_id).strip()), None)
    if target is None and subtask_number:
        target = next((item for item in subtasks if item.get("number") == str(subtask_number)), None)
    if target is None:
        return {"success": False, "error": "Subtask not found for the given subtask_id/subtask_number"}

    patch = dict(fields_to_update)
    if "subtask_id" in patch and str(patch.get("subtask_id") or "").strip() != target.get("subtask_id", ""):
        return {"success": False, "error": "subtask_id is immutable"}

    for key in ["name", "title"]:
        if key in patch:
            name = str(patch.get(key) or "").strip()
            if not name:
                return {"success": False, "error": "name/title cannot be empty"}
            target["name"] = name
            break
    if "description" in patch:
        desc = str(patch.get("description") or "").strip()
        if not desc:
            return {"success": False, "error": "description cannot be empty"}
        target["description"] = desc
    if "status" in patch:
        try:
            target["status"] = _normalize_status(str(patch.get("status") or ""))
        except ValueError as exc:
            return {"success": False, "error": str(exc)}
    if "priority" in patch:
        target["priority"] = str(patch.get("priority") or "medium").strip().lower() or "medium"
    if "dependencies" in patch:
        dependencies = patch.get("dependencies")
        if isinstance(dependencies, str):
            return {"success": False, "error": "dependencies must be an array"}
        if not isinstance(dependencies, list):
            return {"success": False, "error": "dependencies must be an array"}
        target["dependencies"] = [str(dep).strip() for dep in dependencies if str(dep).strip()]
    if "acceptance_criteria" in patch:
        try:
            target["acceptance_criteria"] = _normalize_acceptance_criteria(patch.get("acceptance_criteria"))
        except ValueError as exc:
            return {"success": False, "error": str(exc)}
    for key in ["split_rationale", "owner", "kind", "origin_subtask_id", "origin_subtask_number"]:
        if key in patch:
            target[key] = str(patch.get(key) or "").strip()
    if "fallback_record" in patch:
        try:
            target["fallback_record"] = _normalize_fallback_record(patch.get("fallback_record"))
        except ValueError as exc:
            return {"success": False, "error": str(exc)}

    try:
        _rewrite_task_file(task_data["filepath"], subtasks)
    except Exception as exc:
        return {"success": False, "error": str(exc)}

    updated = _parse_task_file(task_data["filepath"])
    saved = next((item for item in updated.get("subtasks", []) if item.get("subtask_id") == target.get("subtask_id")), target)
    _emit_obs(
        todo_id=todo_id,
        event_type="subtask_updated",
        payload={
            "tool": "update_subtask",
            "todo_id": todo_id,
            "subtask_id": saved.get("subtask_id", ""),
            "subtask_number": saved.get("number", ""),
            "updated_fields": sorted(list(fields_to_update.keys())),
            "update_reason": str(update_reason or "").strip(),
        },
    )
    return {
        "success": True,
        "subtask_id": saved.get("subtask_id", ""),
        "subtask_number": saved.get("number", ""),
        "updated_fields": sorted(list(fields_to_update.keys())),
    }


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
                "subtask_id": next_task.get("subtask_id", ""),
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
            prepare_task,
            plan_task,
            create_task,
            update_task,
            update_task_status,
            reopen_subtask,
            update_subtask,
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
            "prepare_task",
            "plan_task",
            "create_task",
            "update_task",
            "update_task_status",
            "reopen_subtask",
            "update_subtask",
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
