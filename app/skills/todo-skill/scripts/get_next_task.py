#!/usr/bin/env python3
"""
Get the next task that can be executed
"""

import sys
import os
import json

# Add scripts directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from utils import get_task_by_id, get_next_task


def main():
    if len(sys.argv) != 2:
        print("Usage: get_next_task.py <task_id>")
        sys.exit(1)
    
    task_id = sys.argv[1]
    task_data = get_task_by_id(task_id)
    
    if not task_data:
        print(f"Task not found: {task_id}")
        sys.exit(1)
    
    next_task = get_next_task(task_data['subtasks'])
    
    if next_task:
        print(json.dumps(next_task, indent=2))
    else:
        # Check if all tasks are completed
        all_completed = all(t['status'] == 'completed' for t in task_data['subtasks'])
        if all_completed:
            print("All tasks completed!")
        else:
            print("No tasks ready to execute (dependencies not met)")


if __name__ == "__main__":
    main()
