# Task File Format

## File Structure

Each task is stored as a Markdown file in `/root/github/InDepth/todo/{task-id}.md`

## File Naming

- **Pattern**: `{timestamp}_{task-name}.md`
- **Example**: `20240402_103045_implement_auth.md`
- **Location**: `/root/github/InDepth/todo/`

## Markdown Format

```markdown
# Task: {Task Name}

## Metadata
- **ID**: {task-id}
- **Status**: pending | in-progress | completed
- **Priority**: high | medium | low
- **Created**: {YYYY-MM-DD HH:MM:SS}
- **Updated**: {YYYY-MM-DD HH:MM:SS}
- **Progress**: {X/Y} ({percentage}%)

## Context
**Goal**: {任务目标}

**Acceptance Criteria**: 
- {完成标准1}
- {完成标准2}

## Subtasks
### Task 1: {子任务名称}
- **Status**: pending | in-progress | completed
- **Priority**: high | medium | low
- **Dependencies**: Task {N}, Task {M} (如果需要前置任务)
- **[ ]** {子任务描述}

### Task 2: {子任务名称}
- **Status**: pending | in-progress | completed
- **Priority**: high | medium | low
- **Dependencies**: Task {N}
- **[ ]** {子任务描述}

## Dependencies
- **Blocked by**: Task {N} (未完成时阻塞当前任务)
- **Blocking**: Task {M} (当前任务未完成时阻塞的任务)

## Notes
{任何额外的备注信息}
```

## Status Values

- `pending`: 任务待办
- `in-progress`: 任务进行中
- `completed`: 任务已完成

## Priority Values

- `high`: 高优先级，需要优先处理
- `medium`: 中等优先级
- `low`: 低优先级

## Progress Tracking

Progress is calculated as:
```
Progress = (Completed Subtasks / Total Subtasks) * 100%
```

Example:
```
Progress: 3/10 (30%)
```

## Dependency Notation

Dependencies are tracked in two ways:

1. **Within Subtasks**: Each subtask lists its dependencies
2. **At Task Level**: Overall blocking relationships

Example:
```markdown
### Task 3: Implement API Endpoint
- **Status**: pending
- **Dependencies**: Task 1, Task 2
```

This means Task 3 cannot start until Task 1 and Task 2 are completed.
