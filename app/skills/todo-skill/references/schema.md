# Todo Data Schema

## Task File Structure

Location: `todo/{task-id}.md`

```markdown
---
id: {task-id}
title: Task Title
status: pending | in_progress | completed | blocked
priority: low | medium | high
created: 2024-01-15T10:30:00
updated: 2024-01-15T14:20:00
depends: [dependency-id-1, dependency-id-2]
---

# Task Title

Description of the task...

## Notes

Additional notes and context.

## Checklist

- [ ] Sub-task 1
- [ ] Sub-task 2
- [x] Completed sub-task
```

## INDEX.md Structure

Location: `todo/INDEX.md`

```markdown
# Todo Index

> Last updated: 2024-01-15T14:20:00

## Status Legend

- `pending`: Ready to start
- `in_progress`: Currently working
- `completed`: Finished
- `blocked`: Waiting for dependencies

## Tasks

| ID | Title | Status | Depends |
|----|-------|--------|---------|
| task-001 | First task | completed | - |
| task-002 | Second task | in_progress | task-001 |
| task-003 | Third task | blocked | task-002 |
```

## Status Flow

```
pending ──► in_progress ──► completed
    │            │
    ▼            ▼
blocked ◄───────┘
    │
    ▼ (when deps complete)
pending
```

## Status Transitions

| From | To | Condition |
|------|-----|-----------|
| pending | in_progress | Dependencies satisfied |
| pending | blocked | Dependencies not satisfied |
| blocked | pending | All dependencies completed |
| in_progress | completed | Task finished |
| in_progress | pending | Paused/reverted |

## Dependency Rules

1. **No circular dependencies**: A task cannot depend on itself directly or indirectly
2. **Cascade check**: When marking complete, check all blocked tasks for unblocking
3. **Validation**: Before starting, verify all dependencies are `completed`
4. **Auto-update**: System automatically updates blocked → pending when deps complete
