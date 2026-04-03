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
from utils import ensure_todo_dir, generate_task_id


def parse_subtask_name(description):
    """Extract a concise name from a description"""
    words = description.split()
    if len(words) <= 6:
        return description
    return ' '.join(words[:6]) + '...'


def smart_split_description(text):
    """
    Intelligently split a comma-separated description into multiple subtasks.
    Handles various formats:
    - "Task1,Task2,Task3"
    - "Task1, Task2, Task3"
    - "Task1 description, Task2 description, Task3 description"
    """
    if ',' not in text:
        return [text]
    
    items = [item.strip() for item in text.split(',')]
    items = [item for item in items if item]
    
    return items


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
    filepath = f"/root/github/InDepth/todo/{task_id}.md"
    
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
    Parse subtasks argument intelligently.
    Supports:
    1. JSON array: '[{"name":"...","description":"..."}]'
    2. Comma-separated: 'Task1,Task2,Task3'
    3. Multiple args: 'Task1' 'Task2' 'Task3'
    """
    arg = arg.strip()
    
    if arg.startswith('[') and arg.endswith(']'):
        try:
            subtasks = json.loads(arg)
            if not isinstance(subtasks, list):
                print("Error: JSON subtasks must be an array")
                sys.exit(1)
            
            for i, subtask in enumerate(subtasks):
                if not isinstance(subtask, dict):
                    print(f"Error: Subtask {i+1} must be a dictionary")
                    sys.exit(1)
                if 'name' not in subtask or 'description' not in subtask:
                    print(f"Error: Subtask {i+1} must have 'name' and 'description' fields")
                    sys.exit(1)
                subtask.setdefault('priority', 'medium')
                subtask.setdefault('dependencies', [])
            
            return subtasks
        except json.JSONDecodeError as e:
            print(f"Error: Invalid JSON format: {e}")
            sys.exit(1)
    
    items = smart_split_description(arg)
    
    subtasks = []
    for i, item in enumerate(items, 1):
        subtasks.append({
            "name": parse_subtask_name(item),
            "description": item,
            "priority": "medium",
            "dependencies": []
        })
    
    if len(items) > 1:
        print(f"ℹ️  Detected comma-separated format, created {len(items)} subtasks")
    
    return subtasks


def parse_args_from_list(args_list):
    """
    Parse arguments from a list, handling both JSON strings and Python objects.
    This function is designed to work with agent framework calls that may pass
    args as JSON strings or Python lists.
    
    Args:
        args_list: Can be:
            - A Python list of arguments
            - A JSON string representing a list
            - A single string (treated as one-element list)
    
    Returns:
        Tuple of (task_name, context, subtasks)
    """
    if isinstance(args_list, str):
        try:
            args_list = json.loads(args_list)
        except json.JSONDecodeError:
            args_list = [args_list]
    
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
        elif len(subtask_args) == 1:
            subtasks = parse_subtasks_arg(subtask_args[0])
        else:
            subtasks = []
            for i, arg in enumerate(subtask_args, 1):
                items = smart_split_description(arg)
                for item in items:
                    subtasks.append({
                        "name": parse_subtask_name(item),
                        "description": item,
                        "priority": "medium",
                        "dependencies": []
                    })
        
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
        print("Usage: create_task.py <task_name> <context> [subtasks]")
        print("\nSubtask formats:")
        print("  1. JSON array (recommended):")
        print('     \'[{"name":"Task1","description":"...","priority":"high","dependencies":[]}]\'')
        print("\n  2. Comma-separated (auto-split):")
        print('     "Design schema,Implement API,Write tests"')
        print("\n  3. Multiple arguments:")
        print('     "Design schema" "Implement API" "Write tests"')
        print("\n  4. No subtasks (use defaults):")
        print('     (omit the subtasks argument)')
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
    elif len(subtask_args) == 1:
        subtasks = parse_subtasks_arg(subtask_args[0])
    else:
        subtasks = []
        for i, arg in enumerate(subtask_args, 1):
            items = smart_split_description(arg)
            for item in items:
                subtasks.append({
                    "name": parse_subtask_name(item),
                    "description": item,
                    "priority": "medium",
                    "dependencies": []
                })
    
    filepath = create_task(task_name, context, subtasks)
    print(f"✅ Task created: {filepath}")
    print(f"📋 Task ID: {os.path.basename(filepath).replace('.md', '')}")
    print(f"📊 Subtasks: {len(subtasks)}")
