---
name: todo-skill
description: "Task management with dependency tracking. Use when: (1) Breaking down complex multi-step tasks, (2) Tracking progress across steps, (3) Managing task dependencies and blocked states, (4) Creating structured workflow plans. Automatically manages todo/ directory with markdown files and INDEX.md for tracking."
---

# Todo Management Skill

Manage tasks with dependency tracking using markdown files in `todo/` directory.

## When to Use

- Complex tasks requiring 3+ steps
- Multi-stage development work
- Tasks with dependencies between steps
- Need to track progress and blocked states

## Directory Structure

```
todo/
├── INDEX.md           # Task index with status overview
└── {task-id}.md       # Individual task files
```

## Task Workflow

### 1. Create Tasks

Use `scripts/create_todo.py` to create tasks:

```bash
python scripts/create_todo.py --title "Task title" --description "Details" --depends "dep-task-id"
```

Parameters:
- `--title`: Task title (required)
- `--description`: Task details (optional)
- `--depends`: Comma-separated list of dependency task IDs (optional)
- `--priority`: low/medium/high (default: medium)

Creates:
- `todo/{task-id}.md` with task details
- Updates `todo/INDEX.md` with new task entry

### 2. Check Dependencies

Use `scripts/get_next.py` to find executable tasks:

```bash
python scripts/get_next.py
```

Returns tasks that:
- Have no dependencies, OR
- All dependencies are completed

### 3. Update Status

Use `scripts/update_todo.py` to change task status:

```bash
python scripts/update_todo.py {task-id} --status {status}
```

Status values:
- `pending`: Not started, waiting
- `in_progress`: Currently working
- `completed`: Finished successfully
- `blocked`: Dependencies not met (auto-set by system)

### 4. List All Tasks

Use `scripts/list_todos.py` to view all tasks:

```bash
python scripts/list_todos.py [--status {status}] [--all]
```

## Task File Format

See `assets/template.md` for the standard format.

Each task file contains:
- YAML frontmatter with metadata
- Markdown body with description and notes

## Dependency Rules

1. **Blocked tasks**: Tasks with incomplete dependencies are marked `blocked`
2. **Auto-unblock**: When a dependency completes, blocked tasks become `pending`
3. **Circular detection**: Cannot create circular dependencies
4. **Cascade completion**: Completing a task may unblock multiple downstream tasks

## Integration

All scripts return JSON output for easy integration with other systems:

```json
{
  "success": true,
  "task": {
    "id": "task-001",
    "title": "Example task",
    "status": "pending",
    "depends": ["task-000"]
  }
}
```

## Best Practices

1. Create all tasks upfront for complex workflows
2. Check dependencies before starting work
3. Update status immediately when state changes
4. Use descriptive task IDs (e.g., `fix-login-bug`, `add-user-api`)
