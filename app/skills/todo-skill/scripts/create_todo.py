#!/usr/bin/env python3
"""Create a new todo task with optional dependencies."""

import argparse
import json
import os
import re
import sys
import uuid
from datetime import datetime
from pathlib import Path


def get_todo_dir():
    """Get todo directory path."""
    return Path("todo")


def generate_task_id(title):
    """Generate a task ID from title."""
    # Try to create a slug from title
    # First try ASCII only
    slug = re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')
    
    # If slug is empty (non-ASCII title), use timestamp
    if not slug or slug == '-':
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        slug = f"task-{timestamp}"
    else:
        # Add short random suffix for uniqueness
        slug = f"{slug}-{uuid.uuid4().hex[:6]}"
    
    return slug


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
            # Skip separator lines like |----|----|
            if len(parts) >= 5 and parts[1] and not parts[1].startswith('-') and parts[1] != 'ID':
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
    index_path.parent.mkdir(exist_ok=True)
    
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


def create_task(title, description="", depends=None, priority="medium"):
    """Create a new task."""
    todo_dir = get_todo_dir()
    todo_dir.mkdir(exist_ok=True)
    
    task_id = generate_task_id(title)
    task_path = todo_dir / f"{task_id}.md"
    
    # Determine initial status
    if depends:
        status = "blocked"
        depends_list = [d.strip() for d in depends.split(',')]
    else:
        status = "pending"
        depends_list = []
    
    # Create task file
    content = f"""---
id: {task_id}
title: {title}
status: {status}
priority: {priority}
created: {datetime.now().isoformat()}
depends: [{', '.join(depends_list)}]
---

# {title}

{description}

## Notes

<!-- Add notes here -->

## Checklist

- [ ] Task item 1
- [ ] Task item 2
"""
    
    task_path.write_text(content, encoding='utf-8')
    
    # Update index
    existing_tasks = read_index()
    existing_tasks.append({
        "id": task_id,
        "title": title,
        "status": status,
        "depends": ', '.join(depends_list) if depends_list else ''
    })
    write_index(existing_tasks)
    
    result = {
        "success": True,
        "task": {
            "id": task_id,
            "title": title,
            "status": status,
            "priority": priority,
            "depends": depends_list
        },
        "file": str(task_path)
    }
    
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return result


def main():
    parser = argparse.ArgumentParser(description="Create a new todo task")
    parser.add_argument("--title", required=True, help="Task title")
    parser.add_argument("--description", default="", help="Task description")
    parser.add_argument("--depends", default="", help="Comma-separated dependency IDs")
    parser.add_argument("--priority", default="medium", choices=["low", "medium", "high"])
    
    args = parser.parse_args()
    
    create_task(
        title=args.title,
        description=args.description,
        depends=args.depends if args.depends else None,
        priority=args.priority
    )


if __name__ == "__main__":
    main()
