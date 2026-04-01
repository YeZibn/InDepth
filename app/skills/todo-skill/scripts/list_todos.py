#!/usr/bin/env python3
"""List all todo tasks."""

import argparse
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
            # Skip separator lines and header-like lines
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


def list_tasks(status=None, show_all=False):
    """List all tasks, optionally filtered by status."""
    tasks = read_index()
    
    if status:
        tasks = [t for t in tasks if t["status"] == status]
    
    if not show_all and not status:
        # Default: show pending, in_progress, and blocked
        tasks = [t for t in tasks if t["status"] in ["pending", "in_progress", "blocked"]]
    
    result = {
        "success": True,
        "count": len(tasks),
        "tasks": tasks
    }
    
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return result


def main():
    parser = argparse.ArgumentParser(description="List todo tasks")
    parser.add_argument("--status", choices=["pending", "in_progress", "completed", "blocked"],
                        help="Filter by status")
    parser.add_argument("--all", action="store_true", help="Show all tasks including completed")
    
    args = parser.parse_args()
    
    list_tasks(status=args.status, show_all=args.all)


if __name__ == "__main__":
    main()
