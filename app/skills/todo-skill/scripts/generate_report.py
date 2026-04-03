#!/usr/bin/env python3
"""
Generate progress report for a task
"""

import sys
import os

# Add scripts directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from utils import get_task_by_id, calculate_progress


def generate_report(task_id: str) -> str:
    """Generate a formatted progress report"""
    task_data = get_task_by_id(task_id)
    
    if not task_data:
        return f"Task not found: {task_id}"
    
    metadata = task_data['metadata']
    subtasks = task_data['subtasks']
    
    completed, total, percentage = calculate_progress(subtasks)
    
    report = f"""
========================================
TASK PROGRESS REPORT
========================================
Task ID: {metadata.get('ID', 'N/A')}
Task Name: {task_id.replace('_', ' ').title()}
Status: {metadata.get('Status', 'N/A')}
Priority: {metadata.get('Priority', 'N/A')}
Created: {metadata.get('Created', 'N/A')}
Updated: {metadata.get('Updated', 'N/A')}

PROGRESS: {completed}/{total} ({percentage}%)
{'█' * (percentage // 10)}{'░' * (10 - percentage // 10)} {percentage}%

----------------------------------------
SUBTASKS:
----------------------------------------
"""
    
    for task in subtasks:
        status_icon = {
            'completed': '✓',
            'in-progress': '→',
            'pending': '○'
        }.get(task['status'], '?')
        
        deps_str = ", ".join(task['dependencies']) if task['dependencies'] else "None"
        
        report += f"""
Task {task['number']}: {task['name']}
  Status: [{status_icon}] {task['status']}
  Priority: {task.get('priority', 'N/A')}
  Dependencies: {deps_str}
  Checklist: {len(task['checklist'])} items
"""
    
    # Check for blocked tasks
    blocked_tasks = []
    for task in subtasks:
        if task['status'] == 'pending' and task['dependencies']:
            blocked_tasks.append(task['number'])
    
    if blocked_tasks:
        report += f"""
----------------------------------------
BLOCKED TASKS: {', '.join(blocked_tasks)}
These tasks are waiting on dependencies.
----------------------------------------
"""
    
    report += "\n========================================\n"
    
    return report


def main():
    if len(sys.argv) != 2:
        print("Usage: generate_report.py <task_id>")
        sys.exit(1)
    
    task_id = sys.argv[1]
    report = generate_report(task_id)
    print(report)


if __name__ == "__main__":
    main()
