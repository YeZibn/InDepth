#!/usr/bin/env python3
"""Get the next executable task (pending or unblocked)."""

import json
import sys
from pathlib import Path


def get_todo_dir():
    """Get todo directory path."""
    return Path("todo")


def read_index():
    """Read the INDEX.md file."""
    index_path = get_todo_dir() / "INDEX.md"
    if not index_path.exists():
        return []
    
    content = index_path.read_text(encoding='utf-8')
    tasks = []
    in_table = False
    for line in content.split('\n'):
        if line.startswith('| ID |'):
            in_table = True
            continue
        if in_table and line.startswith('|'):
            parts = [p.strip() for p in line.split('|')]
            if len(parts) >= 5 and parts[1] and not parts[1].startswith('-'):
                tasks.append({
                    "id": parts[1],
                    "title": parts[2],
                    "status": parts[3],
                    "depends": parts[4] if parts[4] != '-' else ''
                })
        elif in_table and not line.startswith('|'):
            break
    
    return tasks


def get_next_task():
    """Get the next executable task."""
    tasks = read_index()
    
    # Build a lookup for status
    task_status = {t["id"]: t["status"] for t in tasks}
    
    # First priority: tasks in progress
    in_progress = [t for t in tasks if t["status"] == "in_progress"]
    if in_progress:
        result = {
            "success": True,
            "message": "Found task in progress",
            "task": in_progress[0],
            "recommendation": "Continue with this task before starting new ones"
        }
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return result
    
    # Second priority: pending tasks with no dependencies or completed dependencies
    pending = [t for t in tasks if t["status"] == "pending"]
    
    for task in pending:
        depends_str = task.get("depends", "")
        if not depends_str or depends_str == '-':
            result = {
                "success": True,
                "message": "Found pending task with no dependencies",
                "task": task,
                "recommendation": "This task can be started immediately"
            }
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return result
        
        # Check if all dependencies are completed
        depends = [d.strip() for d in depends_str.split(',') if d.strip()]
        all_complete = all(
            task_status.get(dep_id) == "completed"
            for dep_id in depends
        )
        
        if all_complete:
            result = {
                "success": True,
                "message": "Found pending task with all dependencies completed",
                "task": task,
                "dependencies": depends,
                "recommendation": "All dependencies satisfied, task is ready"
            }
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return result
    
    # No executable tasks found
    blocked_tasks = [t for t in tasks if t["status"] == "blocked"]
    
    if blocked_tasks:
        result = {
            "success": False,
            "message": "No executable tasks found",
            "blocked_tasks": blocked_tasks,
            "recommendation": "Complete blocking tasks first"
        }
    else:
        result = {
            "success": False,
            "message": "No pending tasks found",
            "all_tasks": tasks,
            "recommendation": "All tasks completed or create new tasks"
        }
    
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return result


def main():
    get_next_task()


if __name__ == "__main__":
    main()
