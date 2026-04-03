#!/usr/bin/env python3
"""
List all tasks
"""

import sys
import os

# Add scripts directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from utils import list_all_tasks


def main():
    tasks = list_all_tasks()
    
    if not tasks:
        print("No tasks found.")
        return
    
    print(f"\nFound {len(tasks)} task(s):\n")
    print("=" * 80)
    
    for task in tasks:
        metadata = task['metadata']
        task_id = metadata.get('ID', 'N/A')
        status = metadata.get('Status', 'N/A')
        priority = metadata.get('Priority', 'N/A')
        progress = metadata.get('Progress', 'N/A')
        
        print(f"\nTask: {task_id}")
        print(f"  Status: {status}")
        print(f"  Priority: {priority}")
        print(f"  Progress: {progress}")
        print(f"  File: {task['filename']}")
        print("-" * 80)


if __name__ == "__main__":
    main()
