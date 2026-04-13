import glob
import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from app.core.tools import tool
from app.observability.events import emit_event


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

        status_match = re.search(r"\*\*Status\*\*:\s*(\w+(?:-\w+)*)", task_content)
        priority_match = re.search(r"\*\*Priority\*\*:\s*(\w+)", task_content)
        deps_match = re.search(r"\*\*Dependencies\*\*:\s*(.*?)\n", task_content)

        status = status_match.group(1) if status_match else "pending"
        priority = priority_match.group(1) if priority_match else "medium"
        dependencies: List[str] = []
        if deps_match:
            deps_str = deps_match.group(1)
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
    completed = sum(1 for t in subtasks if t.get("status") == "completed")
    percentage = int((completed / total) * 100) if total > 0 else 0
    return completed, total, percentage


def _list_all_tasks() -> List[Dict[str, Any]]:
    todo_dir = _get_todo_dir()
    if not os.path.exists(todo_dir):
        return []

    tasks: List[Dict[str, Any]] = []
    for filepath in glob.glob(os.path.join(todo_dir, "*.md")):
        parsed = _parse_task_file(filepath)
        if parsed:
            tasks.append(parsed)
    tasks.sort(key=lambda x: x["metadata"].get("Created", ""), reverse=True)
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
    completed_tasks = {t["number"] for t in subtasks if t.get("status") == "completed"}
    for task in subtasks:
        if task.get("status") == "pending":
            if all(dep in completed_tasks for dep in task.get("dependencies", [])):
                return task
    return None


def _calculate_blocked_status(subtasks: List[Dict[str, Any]]) -> Dict[str, Any]:
    completed_tasks = {t["number"] for t in subtasks if t.get("status") == "completed"}
    blocked = []
    ready = []
    blocking = []

    for task in subtasks:
        num = task["number"]
        name = task["name"]
        deps = task.get("dependencies", [])
        status = task.get("status")

        if status == "pending":
            unmet = [d for d in deps if d not in completed_tasks]
            if unmet:
                blocked.append((num, name, unmet))
            else:
                ready.append((num, name))

        if status != "completed":
            blocks = [other["number"] for other in subtasks if num in other.get("dependencies", [])]
            if blocks:
                blocking.append((num, name, blocks))

    return {"blocked": blocked, "ready": ready, "blocking": blocking}


def _generate_dependencies_section(subtasks: List[Dict[str, Any]]) -> str:
    status = _calculate_blocked_status(subtasks)
    lines = ["## Dependencies"]

    if status["blocked"]:
        lines.append("- **Blocked subtasks**:")
        for num, name, deps in status["blocked"]:
            wait_for = ", ".join([f"Task {d}" for d in deps])
            lines.append(f"  - Task {num} ({name}) - waiting for {wait_for}")
    else:
        lines.append("- **Blocked subtasks**: None")

    if status["ready"]:
        lines.append("- **Ready subtasks**:")
        for num, name in status["ready"]:
            lines.append(f"  - Task {num} ({name})")
    else:
        lines.append("- **Ready subtasks**: None")

    if status["blocking"]:
        lines.append("- **Blocking subtasks**:")
        for num, name, blocks in status["blocking"]:
            blocks_str = ", ".join([f"Task {b}" for b in blocks])
            lines.append(f"  - Task {num} ({name}) - blocks {blocks_str}")
    else:
        lines.append("- **Blocking subtasks**: None")

    return "\n".join(lines)


def _has_unmet_dependencies(subtasks: List[Dict[str, Any]], task_number: str) -> List[str]:
    target = next((t for t in subtasks if t["number"] == task_number), None)
    if not target:
        return []
    completed = {t["number"] for t in subtasks if t.get("status") == "completed"}
    return [dep for dep in target.get("dependencies", []) if dep not in completed]


def _update_task_status(filepath: str, task_number: str, new_status: str) -> Tuple[bool, Optional[str]]:
    if not os.path.exists(filepath):
        return False, "Task file not found"

    parsed = _parse_task_file(filepath)
    subtasks = parsed.get("subtasks", [])

    target = next((t for t in subtasks if t["number"] == task_number), None)
    if not target:
        return False, f"Subtask {task_number} not found"

    if new_status in ("in-progress", "completed"):
        unmet = _has_unmet_dependencies(subtasks, task_number)
        if unmet:
            deps = ", ".join([f"Task {d}" for d in unmet])
            return False, f"Subtask {task_number} is blocked by {deps}"

    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    subtask_pattern = rf"(### Task {task_number}:.*?\*\*Status\*\*:\s*)(\w+(?:-\w+)*)(.*?)(?=\n### Task|\n## |\Z)"
    new_content = re.sub(
        subtask_pattern,
        lambda m: f"{m.group(1)}{new_status}{m.group(3)}",
        content,
        flags=re.DOTALL,
    )
    if new_content == content:
        return False, f"Failed to locate status block for subtask {task_number}"

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    new_content = re.sub(
        r"(\*\*Updated\*\*:\s*)\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}",
        rf"\g<1>{now}",
        new_content,
    )

    parsed_after = _parse_task_file(filepath)
    for st in parsed_after.get("subtasks", []):
        if st["number"] == task_number:
            st["status"] = new_status

    completed, total, percentage = _calculate_progress(parsed_after.get("subtasks", []))
    overall_status = "completed" if percentage == 100 else ("in-progress" if percentage > 0 else "pending")

    new_content = re.sub(
        r"(\*\*Progress\*\*:\s*)\d+/\d+\s*\(\d+%\)",
        rf"\g<1>{completed}/{total} ({percentage}%)",
        new_content,
    )
    new_content = re.sub(
        r"(\*\*Status\*\*:\s*)(\w+(?:-\w+)*)",
        rf"\g<1>{overall_status}",
        new_content,
        count=1,
    )

    deps_section = _generate_dependencies_section(parsed_after.get("subtasks", []))
    new_content = re.sub(
        r"## Dependencies\n.*?(?=\n## |\Z)",
        deps_section + "\n",
        new_content,
        flags=re.DOTALL,
    )

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(new_content)

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

        normalized_deps: List[int] = []
        for dep in dependencies:
            dep_str = str(dep).strip()
            if not dep_str.isdigit():
                raise ValueError(f"subtasks[{idx}].dependencies contains invalid value: {dep}")
            normalized_deps.append(int(dep_str))

        normalized.append(
            {
                "name": name.strip(),
                "description": description.strip(),
                "priority": priority.strip().lower(),
                "dependencies": normalized_deps,
            }
        )

    return normalized


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
            "subtasks": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "title": {"type": "string"},
                        "description": {"type": "string"},
                        "priority": {"type": "string"},
                        "dependencies": {
                            "type": "array",
                            "items": {"type": "integer"},
                        },
                    },
                    "required": ["description"],
                    "anyOf": [
                        {"required": ["name"]},
                        {"required": ["title"]},
                    ],
                },
            },
        },
        "required": ["task_name", "context", "subtasks"],
    },
)
def create_task(task_name: str, context: str, subtasks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Create a markdown task file with structured subtasks and dependency metadata.

    Args:
        task_name: Human-readable task title.
        context: Goal and constraints for this task.
        subtasks: Ordered subtask list. Each item should include name/description,
            and may include priority/dependencies.

    Returns:
        Dict with success flag, filepath, todo_id, and subtask_count.
    """
    try:
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

**Acceptance Criteria**:
- Task completion criteria will be defined during execution
"""
        subtasks_section = "\n## Subtasks\n"
        for i, subtask in enumerate(normalized_subtasks, 1):
            deps = subtask.get("dependencies", [])
            deps_str = ", ".join([f"Task {d}" for d in deps])
            deps_line = f"- **Dependencies**: {deps_str}" if deps_str else "- **Dependencies**: None"
            subtasks_section += f"""
### Task {i}: {subtask['name']}
- **Status**: pending
- **Priority**: {subtask.get('priority', 'medium')}
{deps_line}
- **[ ]** {subtask['description']}
"""
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
            },
        )
        return {
            "success": True,
            "filepath": filepath,
            "todo_id": todo_id,
            "subtask_count": len(normalized_subtasks),
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
    """
    Update a subtask status while enforcing dependency constraints.

    Args:
        todo_id: Todo identifier or unique prefix.
        subtask_number: 1-based subtask number in the task file.
        status: Target status, one of pending/in-progress/completed.

    Returns:
        Dict with success flag and updated progress, or error details.
    """
    valid_statuses = ["pending", "in-progress", "completed"]
    if status not in valid_statuses:
        return {"success": False, "error": f"Invalid status '{status}'. Valid: {', '.join(valid_statuses)}"}

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
    name="list_tasks",
    description="List all task summaries in the todo directory.",
    stop_after_tool_call=False,
    requires_confirmation=False,
    cache_results=False,
)
def list_tasks() -> Dict[str, Any]:
    """
    List task summaries in the todo directory.

    Returns:
        Dict with success flag, task count, and summary list.
    """
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
    """
    Get the next executable pending subtask based on dependency satisfaction.

    Args:
        todo_id: Todo identifier or unique prefix.

    Returns:
        Dict with status=ready/all_completed/blocked and related payload.
    """
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
            },
        }

    all_done = all(t.get("status") == "completed" for t in task_data.get("subtasks", []))
    if all_done:
        return {"success": True, "status": "all_completed", "message": "All tasks completed!"}
    return {"success": True, "status": "blocked", "message": "No tasks ready (dependencies not met)"}


@tool(
    name="get_task_progress",
    description="Get progress with completed, ready, and blocked subtask breakdown.",
    stop_after_tool_call=False,
    requires_confirmation=False,
    cache_results=False,
)
def get_task_progress(todo_id: str) -> Dict[str, Any]:
    """
    Get progress summary including completed, ready, and blocked subtasks.

    Args:
        todo_id: Todo identifier or unique prefix.

    Returns:
        Dict with progress string and task breakdown lists.
    """
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
        "completed_tasks": [{"number": t["number"], "name": t["name"]} for t in task_data["subtasks"] if t["status"] == "completed"],
        "ready_tasks": [{"number": n, "name": nm} for n, nm in blocked_status["ready"]],
        "blocked_tasks": [{"number": n, "name": nm, "waiting_for": d} for n, nm, d in blocked_status["blocked"]],
    }


@tool(
    name="generate_task_report",
    description="Generate a formatted task report with progress bar and blocked summary.",
    stop_after_tool_call=False,
    requires_confirmation=False,
    cache_results=False,
)
def generate_task_report(todo_id: str) -> Dict[str, Any]:
    """
    Generate a formatted plain-text progress report for a task.

    Args:
        todo_id: Todo identifier or unique prefix.

    Returns:
        Dict with success flag and rendered report content.
    """
    task_data = _get_task_by_todo_id(todo_id)
    if not task_data:
        return {"success": False, "error": f"Todo not found: {todo_id}"}

    metadata = task_data.get("metadata", {})
    subtasks = task_data.get("subtasks", [])
    completed, total, percentage = _calculate_progress(subtasks)

    status_icons = {"completed": "✓", "in-progress": "→", "pending": "○"}
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
    for st in subtasks:
        icon = status_icons.get(st.get("status"), "?")
        deps = ", ".join(st.get("dependencies", [])) if st.get("dependencies") else "None"
        lines.append(f"Task {st['number']}: {st['name']} [{icon}] {st['status']}")
        lines.append(f"  Priority: {st.get('priority', 'N/A')}, Deps: {deps}")

    blocked = _calculate_blocked_status(subtasks)["blocked"]
    if blocked:
        lines.extend(["", "-" * 44, f"BLOCKED: {', '.join([b[0] for b in blocked])}", "These tasks are waiting on dependencies."])
    lines.append("=" * 44)
    return {"success": True, "report": "\n".join(lines)}


class TodoTools:
    @staticmethod
    def get_tools():
        return [
            create_task,
            update_task_status,
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
            "list_tasks",
            "get_next_task",
            "get_task_progress",
            "generate_task_report",
        ]


def load_todo_tools():
    """Compatibility shim for existing callers."""
    return TodoTools
