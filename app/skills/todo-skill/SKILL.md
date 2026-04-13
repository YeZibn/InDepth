---
name: todo-skill
description: "Manage complex engineering work by decomposing tasks into structured subtasks with dependencies and progress tracking. Use this skill when work has at least 3 steps, spans multiple files/components, takes over 30 minutes, or requires explicit execution order and status reporting."
---

# Todo Skill

## Overview

Use this skill to manage complex tasks in `{project-root}/todo/*.md` through the unified todo tool.

Use when:
- Work has 3 or more meaningful steps
- Work spans multiple files/components
- Estimated duration is over 30 minutes
- Subtasks depend on each other
- Ongoing progress reporting is required

## Quick Start

Import from the unified tool module:

```python
from app.tool.todo_tool.todo_tool import TodoTools

# Register these tools in your agent:
tools = TodoTools.get_tools()
```

For local debugging (outside agent runtime), call tool entrypoints:

```python
from app.tool.todo_tool.todo_tool import create_task

result = create_task.entrypoint(
    task_name="Implement Auth System",
    context="Implement login/register with JWT",
    subtasks=[
        {"name": "Design schema", "description": "Define schema", "priority": "high", "dependencies": []}
    ],
)
```

## Available Tools

| Tool | Purpose |
|------|---------|
| `create_task` | Create task file with subtasks and dependencies |
| `update_task_status` | Update subtask status (`pending`, `in-progress`, `completed`) |
| `list_tasks` | List task summaries |
| `get_next_task_item` | Get next executable subtask |
| `get_task_progress` | Get completed/ready/blocked breakdown |
| `generate_task_report` | Generate formatted progress report |

## Behavior Guarantees

- `update_task_status` enforces dependency order:
  - A subtask cannot move to `in-progress` or `completed` if unmet dependencies exist.
- Progress and overall task status are recalculated after status updates.
- Dependencies section is regenerated on status updates.

## Workflow

1. Assess complexity.
2. Create a task with explicit subtasks and dependencies.
3. Use `get_next_task_item` to pick executable work.
4. Mark status transitions as you execute.
5. Use `get_task_progress` or `generate_task_report` to monitor execution.

## Task File Location and Shape

- Location: `{project-root}/todo/{todo-id}.md`
- ID pattern: `{YYYYMMDD_HHMMSS}_{sanitized_task_name}`
- Progress pattern: `X/Y (Z%)`

See references for details:
- [workflow.md](references/workflow.md)
- [task_format.md](references/task_format.md)
- [examples.md](references/examples.md)
- [task_template.md](references/task_template.md)

## Resources

`todo-skill` follows the current unified skill layout:

1. `SKILL.md` - Skill definition and usage guidance
2. `references/` - Workflow docs, examples, and reusable templates

Current reference files:
- `workflow.md` - Execution loop and status transition rules
- `task_format.md` - Canonical todo markdown file structure
- `examples.md` - End-to-end usage examples
- `task_template.md` - Reusable markdown task skeleton
