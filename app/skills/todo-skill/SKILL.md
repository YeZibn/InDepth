---
name: todo-skill
description: "Manages complex tasks by decomposing them into trackable subtasks with dependencies. Invoke when task is complex (≥3 steps, cross-file, >30 minutes) or requires progress tracking and dependency management."
---

# Todo Skill

## Overview

The Todo Skill enables systematic task management for complex software engineering work. It helps break down large tasks into manageable subtasks, track progress, manage dependencies, and maintain visibility on project status.

**When to use this skill:**
- Task requires 3 or more steps
- Work spans multiple files or components
- Estimated time exceeds 30 minutes
- Dependencies exist between subtasks
- Progress tracking is needed

## Quick Start

### For Agent Framework (Recommended)

Import and use the tools directly:

```python
from app.skills.todo_skill.scripts.tools import (
    create_task,
    update_task_status,
    list_tasks,
    get_next_task_item,
    get_task_progress,
    generate_task_report
)

# Create a task
result = create_task(
    task_name="Build User System",
    context="Create user management system with authentication",
    subtasks=[
        {"name": "Design schema", "description": "Define user table", "priority": "high", "dependencies": []},
        {"name": "Implement API", "description": "Create endpoints", "priority": "high", "dependencies": ["1"]},
    ]
)

# Update progress
update_task_status(task_id=result["task_id"], subtask_number=1, status="completed")

# List all tasks
all_tasks = list_tasks()

# Get next task
next_task = get_next_task_item(task_id="20260403_xxx_xxx")

# Generate report
report = generate_task_report(task_id="20260403_xxx_xxx")
```

## Workflow Decision Tree

```
Start
  ↓
Is task complex? (≥3 steps, cross-file, >30 min)
  ├─ Yes → Use Todo Skill
  │          ↓
  │          Create Task File
  │          ↓
  │          Decompose into Subtasks
  │          ↓
  │          Define Dependencies
  │          ↓
  │          Execute & Track Progress
  └─ No → Execute Directly
```

## Available Tools

| Tool | Description |
|------|-------------|
| `create_task` | Create a new task with structured subtasks |
| `update_task_status` | Update subtask status and progress |
| `list_tasks` | List all tasks with status and progress |
| `get_next_task_item` | Get next executable subtask based on dependencies |
| `get_task_progress` | Get detailed progress including blocked/ready tasks |
| `generate_task_report` | Generate formatted report with visual progress bar |

### Tool Details

#### create_task
```
Create a new task with subtasks.
- task_name: Name of the task (short, descriptive)
- context: Context and goal description
- subtasks: List of {name, description, priority, dependencies}
Returns: {success, filepath, task_id, subtask_count}
```

#### update_task_status
```
Update subtask status.
- task_id: Task ID (e.g., "20240402_103045_implement_auth")
- subtask_number: 1, 2, 3...
- status: "pending" | "in-progress" | "completed"
Returns: {success, message, progress}
```

#### list_tasks
```
List all tasks.
Returns: {success, tasks: [{id, status, priority, progress, file}], count}
```

#### get_next_task_item
```
Get next executable subtask.
- task_id: Task ID to check
Returns: {success, status: "ready"|"all_completed"|"blocked", next_task}
```

#### get_task_progress
```
Get detailed task progress.
- task_id: Task ID
Returns: {success, progress, completed_tasks, ready_tasks, blocked_tasks}
```

#### generate_task_report
```
Generate formatted progress report.
- task_id: Task ID
Returns: {success, report: "formatted string with progress bar"}
```

## Task File Format

Tasks are stored as Markdown files in `{project-root}/todo/{task-id}.md`

```markdown
# Task: {Task Name}

## Metadata
- **ID**: {timestamp}_{task_name}
- **Status**: pending | in-progress | completed
- **Priority**: high | medium | low
- **Created**: YYYY-MM-DD HH:MM:SS
- **Updated**: YYYY-MM-DD HH:MM:SS
- **Progress**: X/Y (Z%)

## Context
**Goal**: {Task objective}

**Acceptance Criteria**:
- {Criterion 1}
- {Criterion 2}

## Subtasks
### Task 1: {Name}
- **Status**: pending
- **Priority**: high
- **Dependencies**: None
- **[ ]** {Description}

## Dependencies
- **Blocked by**: Task N
- **Blocking**: Task M

## Notes
{Additional information}
```

## Best Practices

### Task Granularity

| Scope | Description | Time Estimate |
|-------|-------------|---------------|
| Subtask | 1-2 files or focused operation | 15-30 minutes |
| Task | Cohesive feature or milestone | 2-4 hours |
| Project | Multiple related tasks | Days/Weeks |

### Dependency Management

1. **Explicit Dependencies**: Always declare dependencies explicitly
2. **Avoid Cycles**: Task A → B → A creates deadlock
3. **Minimize Chains**: Prefer parallel work where possible

**Good:**
```
Task 1: Setup database
Task 2: Create models (depends on 1)
Task 3: Build API (depends on 2)
Task 4: Write tests (depends on 2)  # Parallel with 3
```

### Status Workflow

```
pending → in-progress → completed
   ↑___________↓
   (can revert if needed)
```

Update status immediately after:
- Starting work (pending → in-progress)
- Completing work (in-progress → completed)
- Discovering blockers (in-progress → pending)

## Example Usage

**Scenario:** User asks to "Implement a complete user authentication system"

**Agent Actions:**

1. **Assess Complexity**
   - Multiple steps: design, models, APIs, middleware, tests
   - Cross-file work: database, backend, frontend
   - Time estimate: 3-4 hours
   - → Use Todo Skill

2. **Create Task**
   ```python
   result = create_task(
       task_name="Implement Auth System",
       context="Complete user authentication with login/register",
       subtasks=[
           {"name": "Design auth schema", "description": "Define user table and auth flows", "priority": "high", "dependencies": []},
           {"name": "Create user model", "description": "Create User model with auth methods", "priority": "high", "dependencies": ["1"]},
           {"name": "Implement login API", "description": "POST /auth/login endpoint", "priority": "high", "dependencies": ["2"]},
           {"name": "Implement register API", "description": "POST /auth/register endpoint", "priority": "high", "dependencies": ["2"]},
           {"name": "Add auth middleware", "description": "JWT verification middleware", "priority": "medium", "dependencies": ["3"]},
           {"name": "Write tests", "description": "Unit tests for auth", "priority": "medium", "dependencies": ["3", "4"]}
       ]
   )
   task_id = result["task_id"]
   ```

3. **Execute Tasks**
   - Call `get_next_task_item(task_id)` to identify next task
   - Execute subtask
   - Call `update_task_status(task_id, subtask_number, "completed")`
   - Repeat until complete

4. **Monitor Progress**
   - Call `generate_task_report(task_id)` periodically
   - Check for blocked tasks via `get_task_progress(task_id)`
   - Adjust priorities as needed
