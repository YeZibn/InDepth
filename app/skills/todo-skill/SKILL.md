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

```python
# Create a new task with subtasks
from scripts.create_task import create_task

subtasks = [
    {
        "name": "Design database schema",
        "description": "Define tables and relationships",
        "priority": "high",
        "dependencies": []
    },
    {
        "name": "Implement API endpoints",
        "description": "Create REST endpoints",
        "priority": "high",
        "dependencies": ["1"]
    }
]

filepath = create_task("Build User System", "Create user management system", subtasks)
```

### For Agent Framework Calls

When calling from agent frameworks that pass arguments as JSON strings:

```python
from scripts.create_task import main_from_args_list

# Agent framework may pass args as JSON string
args_json = '["Task Name", "Context", \'[{"name":"Step1","description":"...","priority":"high","dependencies":[]}]\']'

result = main_from_args_list(args_json)
# Returns: {"success": True, "filepath": "...", "task_id": "...", "subtask_count": 1}

# Or as Python list
args_list = ["Task Name", "Context", "Step1,Step2,Step3"]
result = main_from_args_list(args_list)
```

**Supported formats:**
1. JSON string (for agent framework compatibility)
2. Python list
3. Comma-separated subtasks (auto-split)
4. JSON array of subtask objects

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

## Core Capabilities

### 1. Task Creation

Create structured task files with metadata, context, and subtasks.

**Location:** `/root/github/InDepth/todo/{task-id}.md`

**File Format:**
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

### 2. Task Listing

List all tasks and their current status.

```bash
python scripts/list_tasks.py
```

**Output:**
```
Found 3 task(s):

================================================================================

Task: 20240402_103045_implement_auth
  Status: in-progress
  Priority: high
  Progress: 2/5 (40%)
  File: 20240402_103045_implement_auth.md
```

### 3. Status Updates

Update subtask status and automatically recalculate progress.

```bash
python scripts/update_task_status.py <task_id> <subtask_number> <status>
```

**Example:**
```bash
python scripts/update_task_status.py 20240402_103045_implement_auth 1 completed
```

**Valid Status Values:**
- `pending` - Task not started
- `in-progress` - Task being worked on
- `completed` - Task finished

### 4. Get Next Task

Identify which subtask should be executed next based on dependencies.

```bash
python scripts/get_next_task.py <task_id>
```

**Logic:**
- Returns first pending task with all dependencies completed
- Returns "All tasks completed!" if done
- Returns "No tasks ready" if dependencies not met

### 5. Progress Reports

Generate formatted progress reports with visual progress bars.

```bash
python scripts/generate_report.py <task_id>
```

**Output:**
```
========================================
TASK PROGRESS REPORT
========================================
Task ID: 20240402_103045_implement_auth
Status: in-progress
Progress: 2/5 (40%)
████░░░░░░ 40%

SUBTASKS:
----------------------------------------
Task 1: Design schema [✓] completed
Task 2: Create models [→] in-progress
Task 3: Build API [○] pending
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

## Resources

### scripts/
Executable Python scripts for task operations:
- `create_task.py` - Create new task files
- `list_tasks.py` - List all tasks
- `update_task_status.py` - Update subtask status
- `get_next_task.py` - Get next executable task
- `generate_report.py` - Generate progress reports
- `utils.py` - Shared utility functions

### references/
Documentation for detailed reference:
- `task_format.md` - Complete file format specification
- `workflow.md` - Detailed workflow guide
- `examples.md` - Real-world usage examples

### assets/templates/
- `task_template.md` - Template for new task files

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
   subtasks = [
       {"name": "Design auth schema", "description": "...", "priority": "high", "dependencies": []},
       {"name": "Create user model", "description": "...", "priority": "high", "dependencies": ["1"]},
       {"name": "Implement login API", "description": "...", "priority": "high", "dependencies": ["2"]},
       {"name": "Implement register API", "description": "...", "priority": "high", "dependencies": ["2"]},
       {"name": "Add auth middleware", "description": "...", "priority": "medium", "dependencies": ["3"]},
       {"name": "Write tests", "description": "...", "priority": "medium", "dependencies": ["3", "4"]}
   ]
   create_task("Implement Auth System", "Complete user authentication", subtasks)
   ```

3. **Execute Tasks**
   - Run `get_next_task.py` to identify next task
   - Execute subtask
   - Update status with `update_task_status.py`
   - Repeat until complete

4. **Monitor Progress**
   - Run `generate_report.py` periodically
   - Check for blocked tasks
   - Adjust priorities as needed
