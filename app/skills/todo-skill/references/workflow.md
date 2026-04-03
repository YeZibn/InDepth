# Todo Skill Workflow

## When to Use This Skill

Use the todo-skill when:
1. **Complex task detected** (≥3 steps, cross-file, >30 minutes)
2. **Need task decomposition** (break down into subtasks)
3. **Track progress** (monitor completion status)
4. **Manage dependencies** (handle task relationships)

## Workflow Decision Tree

```
Start
  ↓
Is task complex? (≥3 steps, dependencies, cross-file)
  ├─ Yes → Create Todo Project
  │          ↓
  │          Decompose into subtasks
  │          ↓
  │          Define dependencies
  │          ↓
  │          Save to /root/github/InDepth/todo/{task-id}.md
  │          ↓
  │          Execute tasks sequentially
  │          ↓
  │          Update status after each completion
  │          ↓
  │          Generate progress report
  └─ No → Execute directly
```

## Step-by-Step Process

### 1. Task Assessment
Before creating a todo project, assess:
- Number of steps required
- File modifications needed
- Time estimate
- Dependencies between steps

### 2. Project Creation
Create task file with:
- Unique ID (timestamp-based)
- Metadata (status, priority, timestamps)
- Context (goal, acceptance criteria)
- Subtasks with dependencies
- Progress tracking

### 3. Task Execution
Execute subtasks in order:
- Check dependencies first
- Update status to "in-progress"
- Complete the task
- Update status to "completed"
- Update parent task progress

### 4. Progress Monitoring
After each task:
- Update progress percentage
- Check for blocked tasks
- Generate status report if needed

## Best Practices

1. **Granularity**: Each subtask should be 1-2 files or 15-30 minutes of work
2. **Dependencies**: Explicitly list all dependencies
3. **Status Updates**: Update immediately after task completion
4. **Progress Tracking**: Calculate and update progress after each subtask
5. **File Naming**: Use timestamp prefix for chronological ordering

## Example Flow

**User Request**: "Implement user authentication system"

**Agent Actions**:
1. Assess complexity (≥5 steps, cross-file) → Use todo-skill
2. Create task file: `20240402_103045_implement_auth.md`
3. Decompose into subtasks:
   - Task 1: Design database schema
   - Task 2: Create user model
   - Task 3: Implement registration API
   - Task 4: Implement login API
   - Task 5: Add authentication middleware
4. Define dependencies (Task 2 depends on Task 1, etc.)
5. Execute and track each task
6. Update progress after each completion
