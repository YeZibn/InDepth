# Task File Format

## Storage

- Directory: `{project-root}/todo/`
- File name: `{YYYYMMDD_HHMMSS}_{sanitized_task_name}.md`

## Minimal Structure

```markdown
# Task: <Task Name>

## Metadata
- **Todo ID**: <todo-id>
- **Status**: pending | in-progress | completed
- **Priority**: high | medium | low
- **Created**: YYYY-MM-DD HH:MM:SS
- **Updated**: YYYY-MM-DD HH:MM:SS
- **Progress**: X/Y (Z%)

## Context
**Goal**: <goal>

**Acceptance Criteria**:
- <criterion>

## Subtasks
### Task 1: <name>
- **Status**: pending | in-progress | completed
- **Priority**: high | medium | low
- **Dependencies**: None | Task N, Task M
- **[ ]** <description>

## Dependencies
- **Blocked subtasks**: ...
- **Ready subtasks**: ...
- **Blocking subtasks**: ...

## Notes
<free text>
```
