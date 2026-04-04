# Todo Workflow

## Decision Rule

Use todo workflow when work is complex:
- 3+ concrete steps
- Cross-file/component changes
- Over 30 minutes
- Non-trivial dependency ordering

## Recommended Execution Loop

1. Create task with explicit subtasks and dependency graph.
2. Ask for next executable subtask.
3. Execute one subtask.
4. Update subtask status.
5. Re-check progress and blockers.
6. Repeat until all subtasks are completed.

## Status Rules

- `pending`: not started
- `in-progress`: actively working
- `completed`: done and verified

Dependency rule:
- A subtask cannot move to `in-progress` or `completed` until all dependencies are completed.

## Progress Rule

`Progress = completed_subtasks / total_subtasks`

Overall task status is derived from progress:
- `pending`: 0%
- `in-progress`: 1% to 99%
- `completed`: 100%
