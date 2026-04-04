#!/usr/bin/env python3
"""
Todo Skill Tools - Agno Tool wrappers for task management
"""

import sys
import os
from typing import List, Dict, Optional, Any
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from utils import (
    get_todo_dir, ensure_todo_dir, generate_task_id,
    parse_task_file, list_all_tasks, get_task_by_id,
    get_next_task, calculate_progress, update_task_status as utils_update_task_status,
    calculate_blocked_status
)
from agno.tools import tool


@tool(
    name="create_task",
    description="Create a new task with structured subtasks. Use this when you need to track complex tasks with multiple steps, dependencies, and progress monitoring. Creates a markdown task file in the todo directory.",
    stop_after_tool_call=False,
    requires_confirmation=False,
    cache_results=False
)
def create_task(
    task_name: str,
    context: str,
    subtasks: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Create a new task with subtasks.

    Args:
        task_name: Name of the task (short, descriptive)
        context: Context and goal description (what needs to be accomplished)
        subtasks: List of subtask dictionaries, each with:
            - name: Subtask name (short)
            - description: Detailed description
            - priority: "high" | "medium" | "low"
            - dependencies: List of task numbers this depends on, e.g., ["1", "2"]

    Returns:
        Dict with:
            - success: bool
            - filepath: Path to created task file
            - task_id: Unique task ID
            - subtask_count: Number of subtasks
            - error: Error message if failed
    """
    try:
        ensure_todo_dir()
        task_id = generate_task_id(task_name)
        filepath = os.path.join(get_todo_dir(), f"{task_id}.md")
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        metadata = f"""# Task: {task_name}

## Metadata
- **ID**: {task_id}
- **Status**: pending
- **Priority**: high
- **Created**: {now}
- **Updated**: {now}
- **Progress**: 0/{len(subtasks)} (0%)
"""

        context_section = f"""
## Context
**Goal**: {context}

**Acceptance Criteria**:
- Task completion criteria will be defined during execution
"""

        subtasks_section = "\n## Subtasks\n"
        for i, subtask in enumerate(subtasks, 1):
            deps = subtask.get('dependencies', [])
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
- **Blocked by**: None
- **Blocking**: None
"""

        notes_section = """
## Notes
Task created automatically. Update as needed during execution.
"""

        content = metadata + context_section + subtasks_section + dependencies_section + notes_section

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)

        return {
            "success": True,
            "filepath": filepath,
            "task_id": task_id,
            "subtask_count": len(subtasks)
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


@tool(
    name="update_task_status",
    description="Update the status of a subtask within a task. Automatically recalculates overall progress and updates the task file.",
    stop_after_tool_call=False,
    requires_confirmation=False,
    cache_results=False
)
def update_task_status(
    task_id: str,
    subtask_number: int,
    status: str
) -> Dict[str, Any]:
    """
    Update the status of a subtask.

    Args:
        task_id: The task ID (e.g., "20240402_103045_implement_auth")
        subtask_number: Subtask number (1, 2, 3...)
        status: New status - "pending" | "in-progress" | "completed"

    Returns:
        Dict with:
            - success: bool
            - message: Status update message
            - progress: "X/Y (Z%)"
            - error: Error message if failed
    """
    valid_statuses = ['pending', 'in-progress', 'completed']
    if status not in valid_statuses:
        return {
            "success": False,
            "error": f"Invalid status '{status}'. Valid: {', '.join(valid_statuses)}"
        }

    task_data = get_task_by_id(task_id)
    if not task_data:
        return {
            "success": False,
            "error": f"Task not found: {task_id}"
        }

    filepath = task_data['filepath']

    if utils_update_task_status(filepath, str(subtask_number), status):
        from utils import parse_task_file
        updated_task = parse_task_file(filepath)
        completed, total, percentage = calculate_progress(updated_task['subtasks'])

        return {
            "success": True,
            "message": f"Subtask {subtask_number} updated to: {status}",
            "progress": f"{completed}/{total} ({percentage}%)"
        }
    else:
        return {
            "success": False,
            "error": f"Failed to update subtask {subtask_number}"
        }


@tool(
    name="list_tasks",
    description="List all tasks in the todo directory. Shows task ID, status, priority, and progress for each task.",
    stop_after_tool_call=False,
    requires_confirmation=False,
    cache_results=False
)
def list_tasks() -> Dict[str, Any]:
    """
    List all tasks.

    Returns:
        Dict with:
            - success: bool
            - tasks: List of task summaries
            - count: Number of tasks
            - error: Error message if failed
    """
    try:
        tasks = list_all_tasks()

        if not tasks:
            return {
                "success": True,
                "tasks": [],
                "count": 0,
                "message": "No tasks found"
            }

        task_summaries = []
        for task in tasks:
            metadata = task['metadata']
            task_summaries.append({
                "id": metadata.get('ID', 'N/A'),
                "status": metadata.get('Status', 'N/A'),
                "priority": metadata.get('Priority', 'N/A'),
                "progress": metadata.get('Progress', 'N/A'),
                "file": task['filename']
            })

        return {
            "success": True,
            "tasks": task_summaries,
            "count": len(task_summaries)
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


@tool(
    name="get_next_task",
    description="Get the next subtask that can be executed based on dependency order. Returns a pending task only when all its dependencies are completed.",
    stop_after_tool_call=False,
    requires_confirmation=False,
    cache_results=False
)
def get_next_task_item(task_id: str) -> Dict[str, Any]:
    """
    Get the next executable subtask.

    Args:
        task_id: The task ID to check

    Returns:
        Dict with:
            - success: bool
            - next_task: Next task details or None
            - status: "ready" | "all_completed" | "blocked" | "not_found"
            - error: Error message if failed
    """
    task_data = get_task_by_id(task_id)

    if not task_data:
        return {
            "success": False,
            "status": "not_found",
            "error": f"Task not found: {task_id}"
        }

    next_t = get_next_task(task_data['subtasks'])

    if next_t:
        return {
            "success": True,
            "status": "ready",
            "next_task": {
                "number": next_t['number'],
                "name": next_t['name'],
                "description": next_t.get('description', ''),
                "priority": next_t.get('priority', 'medium'),
                "dependencies": next_t.get('dependencies', [])
            }
        }

    all_completed = all(t['status'] == 'completed' for t in task_data['subtasks'])
    if all_completed:
        return {
            "success": True,
            "status": "all_completed",
            "message": "All tasks completed!"
        }

    return {
        "success": True,
        "status": "blocked",
        "message": "No tasks ready (dependencies not met)"
    }


@tool(
    name="get_task_progress",
    description="Get detailed progress information for a task including blocked and ready subtasks.",
    stop_after_tool_call=False,
    requires_confirmation=False,
    cache_results=False
)
def get_task_progress(task_id: str) -> Dict[str, Any]:
    """
    Get detailed task progress.

    Args:
        task_id: The task ID

    Returns:
        Dict with:
            - success: bool
            - task_id: Task ID
            - progress: "X/Y (Z%)"
            - blocked_tasks: List of blocked tasks
            - ready_tasks: List of ready tasks
            - completed_tasks: List of completed tasks
            - error: Error message if failed
    """
    task_data = get_task_by_id(task_id)

    if not task_data:
        return {
            "success": False,
            "error": f"Task not found: {task_id}"
        }

    completed, total, percentage = calculate_progress(task_data['subtasks'])
    blocked_status = calculate_blocked_status(task_data['subtasks'])

    return {
        "success": True,
        "task_id": task_id,
        "progress": f"{completed}/{total} ({percentage}%)",
        "completed_tasks": [
            {"number": t['number'], "name": t['name']}
            for t in task_data['subtasks'] if t['status'] == 'completed'
        ],
        "ready_tasks": [
            {"number": num, "name": name}
            for num, name in blocked_status['ready']
        ],
        "blocked_tasks": [
            {"number": num, "name": name, "waiting_for": deps}
            for num, name, deps in blocked_status['blocked']
        ]
    }


@tool(
    name="generate_task_report",
    description="Generate a formatted progress report for a task with visual progress bar.",
    stop_after_tool_call=False,
    requires_confirmation=False,
    cache_results=False
)
def generate_task_report(task_id: str) -> Dict[str, Any]:
    """
    Generate a formatted progress report.

    Args:
        task_id: The task ID

    Returns:
        Dict with:
            - success: bool
            - report: Formatted report string
            - error: Error message if failed
    """
    task_data = get_task_by_id(task_id)

    if not task_data:
        return {
            "success": False,
            "error": f"Task not found: {task_id}"
        }

    metadata = task_data['metadata']
    subtasks = task_data['subtasks']
    completed, total, percentage = calculate_progress(subtasks)

    status_icons = {
        'completed': '✓',
        'in-progress': '→',
        'pending': '○'
    }

    report_lines = [
        "=" * 44,
        "TASK PROGRESS REPORT",
        "=" * 44,
        f"Task ID: {metadata.get('ID', 'N/A')}",
        f"Status: {metadata.get('Status', 'N/A')}",
        f"Priority: {metadata.get('Priority', 'N/A')}",
        f"Created: {metadata.get('Created', 'N/A')}",
        "",
        f"PROGRESS: {completed}/{total} ({percentage}%)",
        f"{'█' * (percentage // 10)}{'░' * (10 - percentage // 10)} {percentage}%",
        "",
        "-" * 44,
        "SUBTASKS:",
        "-" * 44,
    ]

    for task in subtasks:
        icon = status_icons.get(task['status'], '?')
        deps_str = ", ".join(task['dependencies']) if task['dependencies'] else "None"
        report_lines.append(
            f"Task {task['number']}: {task['name']} [{icon}] {task['status']}"
        )
        report_lines.append(f"  Priority: {task.get('priority', 'N/A')}, Deps: {deps_str}")

    blocked_status = calculate_blocked_status(subtasks)
    if blocked_status['blocked']:
        blocked_nums = [t[0] for t in blocked_status['blocked']]
        report_lines.extend([
            "",
            "-" * 44,
            f"BLOCKED: {', '.join(blocked_nums)}",
            "These tasks are waiting on dependencies.",
        ])

    report_lines.append("=" * 44)

    return {
        "success": True,
        "report": "\n".join(report_lines)
    }


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
