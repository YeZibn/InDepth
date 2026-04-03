#!/usr/bin/env python3
"""
Todo Skill Utilities
Helper functions for task management
"""

import os
import re
import glob
from datetime import datetime
from typing import Dict, List, Optional, Tuple


def find_project_root() -> str:
    """
    Find the project root directory by looking for characteristic directories.
    
    Searches upward from the current script location for:
    1. Directory containing '.git' folder
    2. Directory containing 'app/skills' folder structure
    
    Returns:
        Absolute path to the project root directory
    """
    # Start from the directory containing this script
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Search upward until we find the project root markers
    while current_dir != os.path.dirname(current_dir):  # Stop at filesystem root
        # Check for .git directory (primary marker)
        if os.path.isdir(os.path.join(current_dir, '.git')):
            return current_dir
        
        # Check for app/skills directory structure (secondary marker)
        if os.path.isdir(os.path.join(current_dir, 'app', 'skills')):
            return current_dir
        
        # Move up one directory
        current_dir = os.path.dirname(current_dir)
    
    # Fallback: if no markers found, use the script's grandparent directory
    # (scripts/ -> todo-skill/ -> skills/ -> app/ -> project_root)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(os.path.dirname(os.path.dirname(script_dir)))


def get_project_root() -> str:
    """Get the cached project root directory"""
    # Use a function attribute to cache the result
    if not hasattr(get_project_root, '_cached'):
        get_project_root._cached = find_project_root()
    return get_project_root._cached


def get_todo_dir() -> str:
    """Get the todo directory path"""
    return os.path.join(get_project_root(), 'todo')


def ensure_todo_dir() -> None:
    """Ensure todo directory exists"""
    todo_dir = get_todo_dir()
    if not os.path.exists(todo_dir):
        os.makedirs(todo_dir)


def generate_task_id(task_name: str) -> str:
    """Generate a unique task ID based on timestamp and task name"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    # Sanitize task name for filename
    sanitized_name = re.sub(r'[^\w\s-]', '', task_name.lower())
    sanitized_name = re.sub(r'[\s]+', '_', sanitized_name)
    return f"{timestamp}_{sanitized_name}"


def parse_task_file(filepath: str) -> Dict:
    """Parse a task markdown file and return structured data"""
    if not os.path.exists(filepath):
        return {}
    
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Extract metadata
    metadata = {}
    # Match from ## Metadata to next ## section or end of file
    metadata_pattern = r'## Metadata\s*\n(.*?)(?=\n## |\Z)'
    metadata_match = re.search(metadata_pattern, content, re.DOTALL)
    
    if metadata_match:
        metadata_lines = metadata_match.group(1).strip().split('\n')
        for line in metadata_lines:
            line = line.strip()
            if line.startswith('- ') and ':' in line:
                # Remove leading "- " and extract key-value
                line = line[2:]
                key, value = line.split(':', 1)
                key = key.strip().replace('**', '').strip()
                value = value.strip()
                metadata[key] = value
    
    # Extract subtasks
    subtasks = []
    subtask_pattern = r'### Task (\d+): (.*?)\n(.*?)(?=\n### Task|\n## |\Z)'
    subtask_matches = re.finditer(subtask_pattern, content, re.DOTALL)
    
    for match in subtask_matches:
        task_num = match.group(1)
        task_name = match.group(2).strip()
        task_content = match.group(3).strip()
        
        # Extract status
        status_match = re.search(r'\*\*Status\*\*:\s*(\w+(?:-\w+)*)', task_content)
        status = status_match.group(1) if status_match else 'pending'
        
        # Extract priority
        priority_match = re.search(r'\*\*Priority\*\*:\s*(\w+)', task_content)
        priority = priority_match.group(1) if priority_match else 'medium'
        
        # Extract dependencies
        deps_match = re.search(r'\*\*Dependencies\*\*:\s*(.*?)\n', task_content)
        dependencies = []
        if deps_match:
            deps_str = deps_match.group(1)
            if deps_str.strip() and deps_str.strip().lower() != 'none':
                # Parse "Task 1, Task 2" format
                deps_list = re.findall(r'Task\s*(\d+)', deps_str)
                dependencies = deps_list
        
        # Extract checklist items
        checklist_items = re.findall(r'- \*\[(.)\]\* (.*)', task_content)
        
        subtasks.append({
            'number': task_num,
            'name': task_name,
            'status': status,
            'priority': priority,
            'dependencies': dependencies,
            'checklist': checklist_items
        })
    
    return {
        'metadata': metadata,
        'subtasks': subtasks,
        'filename': os.path.basename(filepath),
        'filepath': filepath
    }


def calculate_progress(subtasks: List[Dict]) -> Tuple[int, int, int]:
    """Calculate progress from subtasks"""
    total = len(subtasks)
    completed = sum(1 for t in subtasks if t['status'] == 'completed')
    percentage = int((completed / total * 100)) if total > 0 else 0
    return completed, total, percentage


def list_all_tasks() -> List[Dict]:
    """List all task files in the todo directory"""
    todo_dir = get_todo_dir()
    if not os.path.exists(todo_dir):
        return []
    
    tasks = []
    pattern = os.path.join(todo_dir, "*.md")
    
    for filepath in glob.glob(pattern):
        task_data = parse_task_file(filepath)
        if task_data:
            tasks.append(task_data)
    
    # Sort by creation time (newest first)
    tasks.sort(key=lambda x: x['metadata'].get('Created', ''), reverse=True)
    return tasks


def get_task_by_id(task_id: str) -> Optional[Dict]:
    """Get a task by its ID"""
    # Try exact match first
    filepath = os.path.join(get_todo_dir(), f"{task_id}.md")
    if os.path.exists(filepath):
        return parse_task_file(filepath)
    
    # Try partial match
    tasks = list_all_tasks()
    for task in tasks:
        if task_id in task['metadata'].get('ID', ''):
            return task
    
    return None


def get_next_task(subtasks: List[Dict]) -> Optional[Dict]:
    """Get the next task that can be executed (pending with all dependencies completed)"""
    # Build a set of completed task numbers
    completed_tasks = set()
    for task in subtasks:
        if task['status'] == 'completed':
            completed_tasks.add(task['number'])
    
    # Find first pending task with all dependencies satisfied
    for task in subtasks:
        if task['status'] == 'pending':
            deps_satisfied = all(dep in completed_tasks for dep in task['dependencies'])
            if deps_satisfied:
                return task
    
    return None


def calculate_blocked_status(subtasks: List[Dict]) -> Dict:
    """
    Calculate which subtasks are blocked and which are blocking others.
    
    Returns:
        Dict with:
        - blocked: List of (task_number, task_name, waiting_for) tuples
        - blocking: List of (task_number, task_name, blocks) tuples
        - ready: List of (task_number, task_name) tuples
    """
    completed_tasks = set()
    for task in subtasks:
        if task['status'] == 'completed':
            completed_tasks.add(task['number'])
    
    blocked = []
    blocking = []
    ready = []
    
    for task in subtasks:
        task_num = task['number']
        task_name = task['name']
        deps = task.get('dependencies', [])
        status = task['status']
        
        if status == 'pending':
            unmet_deps = [d for d in deps if d not in completed_tasks]
            
            if unmet_deps:
                blocked.append((task_num, task_name, unmet_deps))
            else:
                ready.append((task_num, task_name))
        
        if status != 'completed':
            blocks_tasks = []
            for other_task in subtasks:
                if task_num in other_task.get('dependencies', []):
                    blocks_tasks.append(other_task['number'])
            
            if blocks_tasks:
                blocking.append((task_num, task_name, blocks_tasks))
    
    return {
        'blocked': blocked,
        'blocking': blocking,
        'ready': ready
    }


def generate_dependencies_section(subtasks: List[Dict]) -> str:
    """
    Generate the ## Dependencies section content based on current subtask status.
    
    Args:
        subtasks: List of subtask dicts
    
    Returns:
        Formatted dependencies section string
    """
    status = calculate_blocked_status(subtasks)
    
    lines = ["## Dependencies"]
    
    if status['blocked']:
        lines.append("- **Blocked subtasks**:")
        for task_num, task_name, waiting_for in status['blocked']:
            waiting_str = ", ".join([f"Task {d}" for d in waiting_for])
            lines.append(f"  - Task {task_num} ({task_name}) - waiting for {waiting_str}")
    else:
        lines.append("- **Blocked subtasks**: None")
    
    if status['ready']:
        lines.append("- **Ready subtasks**:")
        for task_num, task_name in status['ready']:
            lines.append(f"  - Task {task_num} ({task_name})")
    else:
        lines.append("- **Ready subtasks**: None")
    
    if status['blocking']:
        lines.append("- **Blocking subtasks**:")
        for task_num, task_name, blocks in status['blocking']:
            blocks_str = ", ".join([f"Task {b}" for b in blocks])
            lines.append(f"  - Task {task_num} ({task_name}) - blocks {blocks_str}")
    else:
        lines.append("- **Blocking subtasks**: None")
    
    return "\n".join(lines)


def update_task_status(filepath: str, task_number: str, new_status: str) -> bool:
    """Update the status of a specific subtask in a task file"""
    if not os.path.exists(filepath):
        return False
    
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Find and update the specific subtask status
    # Pattern to match the subtask section
    subtask_pattern = rf'(### Task {task_number}:.*?\*\*Status\*\*:\s*)(\w+(?:-\w+)*)(.*?)(?=\n### Task|\n## |\Z)'
    
    def replace_status(match):
        return f"{match.group(1)}{new_status}{match.group(3)}"
    
    new_content = re.sub(subtask_pattern, replace_status, content, flags=re.DOTALL)
    
    if new_content == content:
        # Try alternative pattern for edge cases
        alt_pattern = rf'(### Task {re.escape(task_number)}:.*?)\*\*Status\*\*:\s*\w+(.*?)(?=\n### Task|\n## |\Z)'
        
        def replace_status_alt(match):
            return f"{match.group(1)}**Status**: {new_status}{match.group(2)}"
        
        new_content = re.sub(alt_pattern, replace_status_alt, content, flags=re.DOTALL)
    
    # Update the "Updated" timestamp
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    new_content = re.sub(
        r'(\*\*Updated\*\*:\s*)\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}',
        rf'\g<1>{now}',
        new_content
    )
    
    # Recalculate and update progress
    task_data = parse_task_file(filepath)
    if task_data and task_data['subtasks']:
        completed, total, percentage = calculate_progress(task_data['subtasks'])
        
        # Update progress in metadata (need to account for the new status)
        # Re-calculate with the new status
        for subtask in task_data['subtasks']:
            if subtask['number'] == task_number:
                subtask['status'] = new_status
        
        completed, total, percentage = calculate_progress(task_data['subtasks'])
        
        # Update progress line
        new_content = re.sub(
            r'(\*\*Progress\*\*:\s*)\d+/\d+\s*\(\d+%\)',
            rf'\g<1>{completed}/{total} ({percentage}%)',
            new_content
        )
        
        # Update overall status based on progress
        overall_status = 'completed' if percentage == 100 else ('in-progress' if percentage > 0 else 'pending')
        new_content = re.sub(
            r'(\*\*Status\*\*:\s*)(\w+(?:-\w+)*)',
            rf'\g<1>{overall_status}',
            new_content,
            count=1  # Only replace first occurrence (in metadata)
        )
        
        # Update Dependencies section
        new_deps_section = generate_dependencies_section(task_data['subtasks'])
        new_content = re.sub(
            r'## Dependencies\n.*?(?=\n## |\Z)',
            new_deps_section + '\n',
            new_content,
            flags=re.DOTALL
        )
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(new_content)
    
    return True


def update_checklist_item(filepath: str, task_number: str, item_index: int, checked: bool) -> bool:
    """Update the checked status of a checklist item within a subtask"""
    if not os.path.exists(filepath):
        return False
    
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Find the specific subtask
    subtask_pattern = rf'(### Task {task_number}:.*?)(?=\n### Task|\n## |\Z)'
    subtask_match = re.search(subtask_pattern, content, re.DOTALL)
    
    if not subtask_match:
        return False
    
    subtask_content = subtask_match.group(1)
    
    # Find and update the specific checklist item
    checklist_pattern = r'(- \*\[)(.)(\]\* .*)'
    items = list(re.finditer(checklist_pattern, subtask_content))
    
    if item_index >= len(items):
        return False
    
    item = items[item_index]
    new_mark = 'x' if checked else ' '
    new_subtask_content = subtask_content[:item.start()] + f"{item.group(1)}{new_mark}{item.group(3)}" + subtask_content[item.end():]
    
    # Replace in full content
    new_content = content[:subtask_match.start()] + new_subtask_content + content[subtask_match.end():]
    
    # Update timestamp
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    new_content = re.sub(
        r'(\*\*Updated\*\*:\s*)\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}',
        rf'\g<1>{now}',
        new_content
    )
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(new_content)
    
    return True


def delete_task(task_id: str) -> bool:
    """Delete a task file by ID"""
    filepath = os.path.join(get_todo_dir(), f"{task_id}.md")
    if os.path.exists(filepath):
        os.remove(filepath)
        return True
    return False


def search_tasks(query: str) -> List[Dict]:
    """Search tasks by name or content"""
    tasks = list_all_tasks()
    query_lower = query.lower()
    
    matching_tasks = []
    for task in tasks:
        # Search in metadata
        metadata = task.get('metadata', {})
        task_id = metadata.get('ID', '').lower()
        
        # Search in subtask names
        subtask_names = ' '.join(st.get('name', '').lower() for st in task.get('subtasks', []))
        
        if query_lower in task_id or query_lower in subtask_names:
            matching_tasks.append(task)
    
    return matching_tasks
