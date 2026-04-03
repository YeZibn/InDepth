# Todo Skill Examples

## Example 1: Simple Task Decomposition

**User Request**: "Create a REST API for blog posts"

**Agent Actions:**

1. Assess complexity: 5+ steps, cross-file, 2-3 hours → Use Todo Skill
2. Create task file:

```python
from scripts.create_task import create_task

subtasks = [
    {
        "name": "Design API Schema",
        "description": "Define request/response schemas and create OpenAPI spec",
        "priority": "high",
        "dependencies": []
    },
    {
        "name": "Create Database Models",
        "description": "Create BlogPost model and run migrations",
        "priority": "high",
        "dependencies": ["1"]
    },
    {
        "name": "Implement GET Endpoints",
        "description": "GET /posts (list) and GET /posts/{id} (single)",
        "priority": "medium",
        "dependencies": ["2"]
    },
    {
        "name": "Implement POST/PUT Endpoints",
        "description": "POST /posts (create) and PUT /posts/{id} (update)",
        "priority": "medium",
        "dependencies": ["2"]
    },
    {
        "name": "Implement DELETE Endpoint",
        "description": "DELETE /posts/{id} with auth check",
        "priority": "low",
        "dependencies": ["2"]
    }
]

filepath = create_task("Create Blog API", "Implement REST API for blog post management", subtasks)
print(f"Task created: {filepath}")
```

**Generated Task File** (`20240402_110000_create_blog_api.md`):
```markdown
# Task: Create Blog API

## Metadata
- **ID**: 20240402_110000_create_blog_api
- **Status**: pending
- **Priority**: high
- **Created**: 2024-04-02 11:00:00
- **Updated**: 2024-04-02 11:00:00
- **Progress**: 0/5 (0%)

## Context
**Goal**: Implement REST API for blog post management

**Acceptance Criteria**: 
- CRUD operations for blog posts
- Proper error handling
- Input validation
- Authentication on write operations

## Subtasks

### Task 1: Design API Schema
- **Status**: pending
- **Priority**: high
- **Dependencies**: None
- **[ ]** Define request/response schemas and create OpenAPI spec

### Task 2: Create Database Models
- **Status**: pending
- **Priority**: high
- **Dependencies**: Task 1
- **[ ]** Create BlogPost model and run migrations

### Task 3: Implement GET Endpoints
- **Status**: pending
- **Priority**: medium
- **Dependencies**: Task 2
- **[ ]** GET /posts (list) and GET /posts/{id} (single)

### Task 4: Implement POST/PUT Endpoints
- **Status**: pending
- **Priority**: medium
- **Dependencies**: Task 2
- **[ ]** POST /posts (create) and PUT /posts/{id} (update)

### Task 5: Implement DELETE Endpoint
- **Status**: pending
- **Priority**: low
- **Dependencies**: Task 2
- **[ ]** DELETE /posts/{id} with auth check

## Dependencies
- **Blocked by**: None
- **Blocking**: None

## Notes
Task created automatically. Update as needed during execution.
```

3. Execute tasks:
```bash
# Get next task
$ python scripts/get_next_task.py 20240402_110000_create_blog_api
{
  "number": "1",
  "name": "Design API Schema",
  "status": "pending",
  "dependencies": []
}

# After completing Task 1, update status
$ python scripts/update_task_status.py 20240402_110000_create_blog_api 1 completed
✓ Subtask 1 status updated to: completed
  Overall progress: 1/5 (20%)

# Get next task (now Task 2 is ready)
$ python scripts/get_next_task.py 20240402_110000_create_blog_api
{
  "number": "2",
  "name": "Create Database Models",
  "status": "pending",
  "dependencies": ["1"]
}

# Generate progress report
$ python scripts/generate_report.py 20240402_110000_create_blog_api
========================================
TASK PROGRESS REPORT
========================================
Task ID: 20240402_110000_create_blog_api
Task Name: Create Blog Api
Status: in-progress
Priority: high
Created: 2024-04-02 11:00:00
Updated: 2024-04-02 11:30:00

PROGRESS: 1/5 (20%)
██░░░░░░░░ 20%

----------------------------------------
SUBTASKS:
----------------------------------------

Task 1: Design API Schema
  Status: [✓] completed
  Priority: high
  Dependencies: None
  Checklist: 0 items

Task 2: Create Database Models
  Status: [○] pending
  Priority: high
  Dependencies: 1
  Checklist: 0 items

Task 3: Implement GET Endpoints
  Status: [○] pending
  Priority: medium
  Dependencies: 2
  Checklist: 0 items

Task 4: Implement POST/PUT Endpoints
  Status: [○] pending
  Priority: medium
  Dependencies: 2
  Checklist: 0 items

Task 5: Implement DELETE Endpoint
  Status: [○] pending
  Priority: low
  Dependencies: 2
  Checklist: 0 items

----------------------------------------
BLOCKED TASKS: 2, 3, 4, 5
These tasks are waiting on dependencies.
----------------------------------------

========================================
```

---

## Example 2: Complex Multi-File Task with Dependencies

**User Request**: "Refactor authentication system to use JWT tokens"

**Agent Actions:**

1. Assess complexity: 8+ steps, cross-file, security-critical → Use Todo Skill
2. Create task with complex dependencies:

```python
from scripts.create_task import create_task

subtasks = [
    {
        "name": "Research JWT libraries",
        "description": "Evaluate PyJWT vs authlib vs python-jose",
        "priority": "high",
        "dependencies": []
    },
    {
        "name": "Design token schema",
        "description": "Define access token and refresh token structure",
        "priority": "high",
        "dependencies": ["1"]
    },
    {
        "name": "Install JWT dependencies",
        "description": "Add PyJWT to requirements and install",
        "priority": "high",
        "dependencies": ["1"]
    },
    {
        "name": "Create JWT utilities",
        "description": "Token generation, validation, refresh functions",
        "priority": "high",
        "dependencies": ["2", "3"]
    },
    {
        "name": "Update login endpoint",
        "description": "Replace session-based auth with JWT tokens",
        "priority": "high",
        "dependencies": ["4"]
    },
    {
        "name": "Create auth middleware",
        "description": "JWT verification middleware for protected routes",
        "priority": "high",
        "dependencies": ["4"]
    },
    {
        "name": "Update frontend auth",
        "description": "Store and send JWT tokens from frontend",
        "priority": "medium",
        "dependencies": ["5", "6"]
    },
    {
        "name": "Write tests",
        "description": "Unit and integration tests for auth flow",
        "priority": "medium",
        "dependencies": ["5", "6"]
    }
]

filepath = create_task("Refactor Auth to JWT", "Migrate from session-based to JWT token authentication", subtasks)
```

**Dependency Graph:**
```
Task 1: Research
    ↓
Task 2: Design Schema ←──┐
    ↓                    │
Task 3: Install Deps ────┤
    ↓                    │
Task 4: JWT Utils ←──────┘
    ↓
    ├──→ Task 5: Login Endpoint ──┐
    │                             ├──→ Task 7: Frontend Auth
    └──→ Task 6: Auth Middleware ─┤
                                  ├──→ Task 8: Tests
```

**Execution Flow:**
```bash
# Tasks 1 can start immediately
$ python scripts/get_next_task.py 20240402_143000_refactor_auth_to_jwt
{ "number": "1", ... }

# After Task 1 completes, Tasks 2 and 3 can run in parallel
$ python scripts/update_task_status.py 20240402_143000_refactor_auth_to_jwt 1 completed

$ python scripts/get_next_task.py 20240402_143000_refactor_auth_to_jwt
{ "number": "2", ... }

# Mark Task 2 in-progress while working on it
$ python scripts/update_task_status.py 20240402_143000_refactor_auth_to_jwt 2 in-progress

# Complete Task 2
$ python scripts/update_task_status.py 20240402_143000_refactor_auth_to_jwt 2 completed

# Task 4 requires both 2 and 3, so only start when both complete
```

---

## Example 3: Bug Fix with Multiple Checklist Items

**User Request**: "Fix the login bug where users can't log in with special characters in password"

**Task File with Checklist:**
```markdown
# Task: Fix Login Special Characters Bug

## Metadata
- **ID**: 20240402_150000_fix_login_special_chars
- **Status**: in-progress
- **Priority**: high
- **Created**: 2024-04-02 15:00:00
- **Updated**: 2024-04-02 15:30:00
- **Progress**: 0/3 (0%)

## Context
**Goal**: Fix login failure when passwords contain special characters

**Acceptance Criteria**: 
- Users can log in with passwords containing !@#$%^&*()_+-=[]{}|;':\",./<>?
- Password hashing works correctly with Unicode characters
- Existing users with simple passwords still work

## Subtasks

### Task 1: Reproduce the bug
- **Status**: completed
- **Priority**: high
- **Dependencies**: None
- **[x]** Create test account with special character password
- **[x]** Attempt login and confirm failure
- **[x]** Check error logs for root cause

### Task 2: Fix password validation
- **Status**: in-progress
- **Priority**: high
- **Dependencies**: Task 1
- **[ ]** Update password validation regex
- **[ ]** Fix encoding issues in auth controller
- **[ ]** Test with various special characters

### Task 3: Regression testing
- **Status**: pending
- **Priority**: medium
- **Dependencies**: Task 2
- **[ ]** Test with simple passwords (regression)
- **[ ]** Test with Unicode passwords
- **[ ]** Test with very long passwords
- **[ ]** Run full auth test suite

## Dependencies
- **Blocked by**: None
- **Blocking**: None

## Notes
Bug reported in issue #234. Root cause appears to be improper URL encoding of password in POST body.
```

---

## Example 4: Listing and Searching Tasks

**List all tasks:**
```bash
$ python scripts/list_tasks.py

Found 3 task(s):

================================================================================

Task: 20240402_150000_fix_login_special_chars
  Status: in-progress
  Priority: high
  Progress: 1/3 (33%)
  File: 20240402_150000_fix_login_special_chars.md

Task: 20240402_143000_refactor_auth_to_jwt
  Status: pending
  Priority: high
  Progress: 0/8 (0%)
  File: 20240402_143000_refactor_auth_to_jwt.md

Task: 20240402_110000_create_blog_api
  Status: completed
  Priority: high
  Progress: 5/5 (100%)
  File: 20240402_110000_create_blog_api.md
--------------------------------------------------------------------------------
```

**Using Python API to search:**
```python
from scripts.utils import search_tasks, list_all_tasks

# Search for auth-related tasks
auth_tasks = search_tasks("auth")
for task in auth_tasks:
    print(f"{task['metadata']['ID']}: {task['metadata']['Status']}")

# Get all in-progress tasks
all_tasks = list_all_tasks()
in_progress = [t for t in all_tasks if t['metadata'].get('Status') == 'in-progress']
print(f"Active tasks: {len(in_progress)}")
```

---

## Example 5: Programmatic Task Management

**Create task and immediately start working:**
```python
import sys
sys.path.insert(0, '/root/github/InDepth/app/skills/todo-skill/scripts')

from create_task import create_task
from utils import get_task_by_id, get_next_task, update_task_status

# Create task
subtasks = [
    {"name": "Analyze requirements", "description": "Review PRD", "priority": "high", "dependencies": []},
    {"name": "Design solution", "description": "Create tech design", "priority": "high", "dependencies": ["1"]},
    {"name": "Implement", "description": "Write code", "priority": "high", "dependencies": ["2"]},
]

filepath = create_task("New Feature", "Implement new feature", subtasks)
task_id = filepath.split('/')[-1].replace('.md', '')

# Get first task and mark in-progress
task_data = get_task_by_id(task_id)
next_task = get_next_task(task_data['subtasks'])

if next_task:
    print(f"Starting: Task {next_task['number']} - {next_task['name']}")
    update_task_status(task_data['filepath'], next_task['number'], 'in-progress')
```

---

## Best Practice Patterns

### Pattern 1: Sequential Dependencies
Use when each step must complete before next starts:
```python
[
    {"name": "Step 1", "dependencies": []},
    {"name": "Step 2", "dependencies": ["1"]},
    {"name": "Step 3", "dependencies": ["2"]},
]
```

### Pattern 2: Parallel Branches
Use when multiple workstreams can proceed independently:
```python
[
    {"name": "Setup", "dependencies": []},
    {"name": "Backend work", "dependencies": ["1"]},
    {"name": "Frontend work", "dependencies": ["1"]},  # Parallel with backend
    {"name": "Integration", "dependencies": ["2", "3"]},  # Needs both
]
```

### Pattern 3: Fan-out / Fan-in
Use when one task enables many, which then converge:
```python
[
    {"name": "Design API", "dependencies": []},
    {"name": "Endpoint A", "dependencies": ["1"]},
    {"name": "Endpoint B", "dependencies": ["1"]},
    {"name": "Endpoint C", "dependencies": ["1"]},
    {"name": "Documentation", "dependencies": ["2", "3", "4"]},
]
```
