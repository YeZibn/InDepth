#!/usr/bin/env python3
"""
Create a new task file with intelligent subtask parsing
"""

import sys
import os
import json
import re
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from utils import ensure_todo_dir, generate_task_id, get_todo_dir


def create_task(task_name: str, context: str, subtasks: list) -> str:
    """
    Create a new task file
    
    Args:
        task_name: Name of the task
        context: Context and goal description
        subtasks: List of subtask dicts with keys:
            - name: Subtask name
            - description: Subtask description
            - priority: high/medium/low
            - dependencies: List of task numbers this depends on (e.g., ["1", "2"])
    
    Returns:
        Path to created task file
    """
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
        deps_str = ", ".join([f"Task {d}" for d in subtask.get('dependencies', [])])
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
    
    return filepath


def parse_subtasks_arg(arg):
    """
    Parse subtasks from JSON array format.

    Args:
        arg: JSON string representing a list of subtasks

    Returns:
        List of subtask dictionaries

    Raises:
        ValueError: If JSON format is invalid
    """
    arg = arg.strip()

    if not (arg.startswith('[') and arg.endswith(']')):
        raise ValueError("Subtasks must be a JSON array format: '[{...}, {...}]'")

    try:
        subtasks = json.loads(arg)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON format: {e}")

    if not isinstance(subtasks, list):
        raise ValueError("JSON subtasks must be an array")

    for i, subtask in enumerate(subtasks):
        if not isinstance(subtask, dict):
            raise ValueError(f"Subtask {i+1} must be a dictionary, got {type(subtask).__name__}")
        if 'name' not in subtask or 'description' not in subtask:
            raise ValueError(f"Subtask {i+1} must have 'name' and 'description' fields")
        subtask.setdefault('priority', 'medium')
        subtask.setdefault('dependencies', [])

    return subtasks


def parse_args_from_list(args_list):
    """
    Parse arguments from a list for agent framework calls.

    Args:
        args_list: JSON string or Python list containing:
            - args_list[0]: task_name
            - args_list[1]: context
            - args_list[2]: subtasks JSON array (optional)

    Returns:
        Tuple of (task_name, context, subtask_args)
    """
    if isinstance(args_list, str):
        args_list = json.loads(args_list)

    if not isinstance(args_list, list):
        raise ValueError(f"args must be a list or JSON string, got {type(args_list)}")

    if len(args_list) < 2:
        raise ValueError("At least task_name and context are required")

    task_name = args_list[0]
    context = args_list[1]
    subtask_args = args_list[2:] if len(args_list) > 2 else []

    return task_name, context, subtask_args


def main_from_args_list(args_list):
    """
    Main entry point for agent framework calls.
    Accepts args as a list or JSON string.
    
    Args:
        args_list: List of arguments or JSON string
    
    Returns:
        Dict with task creation results
    """
    try:
        task_name, context, subtask_args = parse_args_from_list(args_list)

        if not subtask_args:
            subtasks = [
                {"name": "Initial Setup", "description": "Setup and preparation", "priority": "high", "dependencies": []},
                {"name": "Implementation", "description": "Main implementation work", "priority": "high", "dependencies": []},
                {"name": "Testing", "description": "Test and validate", "priority": "medium", "dependencies": []},
                {"name": "Documentation", "description": "Update documentation", "priority": "low", "dependencies": []}
            ]
        else:
            subtasks = parse_subtasks_arg(subtask_args[0])

        filepath = create_task(task_name, context, subtasks)
        
        return {
            "success": True,
            "filepath": filepath,
            "task_id": os.path.basename(filepath).replace('.md', ''),
            "subtask_count": len(subtasks)
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: create_task.py <task_name> <context> [subtasks_json]")
        print("\nSubtask format (JSON array):")
        print('  \'[{"name":"Task1","description":"...","priority":"high","dependencies":[]}]\'')
        print("\nExample:")
        print('  create_task.py "My Task" "Task context" \'[{"name":"Step 1","description":"Do something","priority":"high","dependencies":[]}]\'')
        sys.exit(1)

    task_name = sys.argv[1]
    context = sys.argv[2]
    subtask_args = sys.argv[3:] if len(sys.argv) > 3 else []

    if not subtask_args:
        subtasks = [
            {"name": "Initial Setup", "description": "Setup and preparation", "priority": "high", "dependencies": []},
            {"name": "Implementation", "description": "Main implementation work", "priority": "high", "dependencies": []},
            {"name": "Testing", "description": "Test and validate", "priority": "medium", "dependencies": []},
            {"name": "Documentation", "description": "Update documentation", "priority": "low", "dependencies": []}
        ]
    else:
        try:
            subtasks = parse_subtasks_arg(subtask_args[0])
        except ValueError as e:
            print(f"Error: {e}")
            sys.exit(1)

    filepath = create_task(task_name, context, subtasks)
    print(f"✅ Task created: {filepath}")
    print(f"📋 Task ID: {os.path.basename(filepath).replace('.md', '')}")
    print(f"📊 Subtasks: {len(subtasks)}")
