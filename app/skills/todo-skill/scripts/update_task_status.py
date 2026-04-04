#!/usr/bin/env python3
"""
Update task status
"""

import sys
import os

# Add scripts directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from utils import update_task_status, get_task_by_id


def main():
    if len(sys.argv) != 4:
        print("Usage: update_task_status.py <task_id> <subtask_number> <status>")
        print("  task_id: The task ID (e.g., 20240402_103045_implement_auth)")
        print("  subtask_number: The subtask number (e.g., 1, 2, 3)")
        print("  status: pending | in-progress | completed")
        print()
        print("Example:")
        print("  python update_task_status.py 20240402_103045_implement_auth 1 completed")
        sys.exit(1)
    
    task_id = sys.argv[1]
    subtask_number = sys.argv[2]
    status = sys.argv[3]
    
    # Validate status
    valid_statuses = ['pending', 'in-progress', 'completed']
    if status not in valid_statuses:
        print(f"Error: Invalid status '{status}'")
        print(f"Valid statuses: {', '.join(valid_statuses)}")
        sys.exit(1)
    
    # Get task filepath
    task_data = get_task_by_id(task_id)
    if not task_data:
        print(f"Error: Task not found: {task_id}")
        sys.exit(1)
    
    filepath = task_data['filepath']
    
    if update_task_status(filepath, subtask_number, status):
        print(f"✓ Subtask {subtask_number} status updated to: {status}")

        from utils import calculate_progress, parse_task_file
        updated_task = parse_task_file(filepath)
        completed, total, percentage = calculate_progress(updated_task['subtasks'])

        print(f"  Overall progress: {completed}/{total} ({percentage}%)")
    else:
        print(f"✗ Failed to update subtask {subtask_number}")
        sys.exit(1)


if __name__ == "__main__":
    main()
