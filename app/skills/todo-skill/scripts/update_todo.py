#!/usr/bin/env python3
"""Update a todo task's status."""

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path


def get_todo_dir():
    """Get todo directory path."""
    return Path("todo")


def read_task(task_id):
    """Read a task file."""
    task_path = get_todo_dir() / f"{task_id}.md"
    if not task_path.exists():
        return None
    
    content = task_path.read_text(encoding='utf-8')
    
    # Parse frontmatter
    metadata = {}
    if content.startswith('---'):
        parts = content.split('---', 2)
        if len(parts) >= 3:
            frontmatter = parts[1].strip()
            for line in frontmatter.split('\n'):
                if ':' in line:
                    key, value = line.split(':', 1)
                    metadata[key.strip()] = value.strip()
    
    return {
        "path": task_path,
        "content": content,
        "metadata": metadata
    }


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


def write_index(tasks):
    """Write the INDEX.md file."""
    index_path = get_todo_dir() / "INDEX.md"
    
    content = """# Todo Index

> Last updated: {timestamp}

## Status Legend

- `pending`: Ready to start
- `in_progress`: Currently working
- `completed`: Finished
- `blocked`: Waiting for dependencies

## Tasks

| ID | Title | Status | Depends |
|----|-------|--------|---------|
{task_rows}
"""
    
    task_rows = []
    for task in tasks:
        depends_str = task.get('depends', '') or '-'
        task_rows.append(f"| {task['id']} | {task['title']} | {task['status']} | {depends_str} |")
    
    content = content.format(
        timestamp=datetime.now().isoformat(),
        task_rows='\n'.join(task_rows)
    )
    
    index_path.write_text(content, encoding='utf-8')


def check_dependencies(task_id, new_status):
    """Check if dependencies are satisfied for a task."""
    task = read_task(task_id)
    if not task:
        return False, "Task not found"
    
    depends_str = task["metadata"].get("depends", "[]")
    # Parse depends list
    depends_str = depends_str.strip('[]')
    if not depends_str:
        return True, None
    
    depends = [d.strip() for d in depends_str.split(',') if d.strip()]
    
    if not depends:
        return True, None
    
    # Check each dependency
    index_tasks = {t["id"]: t for t in read_index()}
    
    for dep_id in depends:
        if dep_id not in index_tasks:
            return False, f"Dependency '{dep_id}' not found"
        if index_tasks[dep_id]["status"] != "completed":
            return False, f"Dependency '{dep_id}' not completed (status: {index_tasks[dep_id]['status']})"
    
    return True, None


def update_blocked_tasks():
    """Update status of tasks that may have become unblocked."""
    index_tasks = read_index()
    updated = []
    
    for task in index_tasks:
        if task["status"] == "blocked":
            # Check if all dependencies are now complete
            depends_str = task.get("depends", "")
            if not depends_str or depends_str == '-':
                task["status"] = "pending"
                updated.append(task["id"])
                continue
            
            depends = [d.strip() for d in depends_str.split(',') if d.strip()]
            all_complete = all(
                t.get("status") == "completed"
                for t in index_tasks
                if t["id"] in depends
            )
            
            if all_complete:
                task["status"] = "pending"
                updated.append(task["id"])
    
    if updated:
        write_index(index_tasks)
    
    return updated


def update_task(task_id, new_status):
    """Update a task's status."""
    task = read_task(task_id)
    if not task:
        result = {"success": False, "error": f"Task '{task_id}' not found"}
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return result
    
    old_status = task["metadata"].get("status", "pending")
    
    # Check dependencies when starting a task
    if new_status in ["in_progress", "pending"]:
        can_proceed, error = check_dependencies(task_id, new_status)
        if not can_proceed:
            result = {
                "success": False,
                "error": f"Cannot update status: {error}",
                "task_id": task_id,
                "current_status": old_status
            }
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return result
    
    # Update task file
    content = task["content"]
    content = re.sub(
        f'status: {re.escape(old_status)}',
        f'status: {new_status}',
        content
    )
    
    # Add updated timestamp
    if "updated:" in content:
        content = re.sub(
            r'updated:.*',
            f'updated: {datetime.now().isoformat()}',
            content
        )
    else:
        # Add updated field after created
        content = re.sub(
            r'(created:.*\n)',
            f'\\1updated: {datetime.now().isoformat()}\n',
            content
        )
    
    task["path"].write_text(content, encoding='utf-8')
    
    # Update index
    index_tasks = read_index()
    for t in index_tasks:
        if t["id"] == task_id:
            t["status"] = new_status
    write_index(index_tasks)
    
    # Check for unblocked tasks if we completed this one
    unblocked = []
    if new_status == "completed":
        unblocked = update_blocked_tasks()
    
    result = {
        "success": True,
        "task": {
            "id": task_id,
            "title": task["metadata"].get("title", ""),
            "old_status": old_status,
            "new_status": new_status
        },
        "unblocked": unblocked if unblocked else None
    }
    
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return result


def main():
    parser = argparse.ArgumentParser(description="Update a todo task's status")
    parser.add_argument("task_id", help="Task ID to update")
    parser.add_argument("--status", required=True, 
                        choices=["pending", "in_progress", "completed", "blocked"],
                        help="New status")
    
    args = parser.parse_args()
    
    update_task(args.task_id, args.status)


if __name__ == "__main__":
    main()
