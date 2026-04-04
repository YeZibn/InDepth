# Todo Tool Examples

## Register Tools In Agent

```python
from app.tool.todo_tool.todo_tool import TodoTools

tools = TodoTools.get_tools()
```

## Create Task (Local Debug)

```python
from app.tool.todo_tool.todo_tool import create_task

result = create_task.entrypoint(
    task_name="Implement Auth System",
    context="Implement login/register with JWT",
    subtasks=[
        {"name": "Design schema", "description": "Define user/auth schema", "priority": "high", "dependencies": []},
        {"name": "Implement login API", "description": "POST /auth/login", "priority": "high", "dependencies": ["1"]},
        {"name": "Implement register API", "description": "POST /auth/register", "priority": "high", "dependencies": ["1"]},
    ],
)
```

## Drive Execution (Local Debug)

```python
from app.tool.todo_tool.todo_tool import get_next_task_item, update_task_status

task_id = "20260404_120000_implement_auth_system"
next_item = get_next_task_item.entrypoint(task_id=task_id)

# after execution:
update_task_status.entrypoint(task_id=task_id, subtask_number=1, status="completed")
```

## Track Progress

```python
from app.tool.todo_tool.todo_tool import get_task_progress, generate_task_report

progress = get_task_progress.entrypoint(task_id="20260404_120000_implement_auth_system")
report = generate_task_report.entrypoint(task_id="20260404_120000_implement_auth_system")
```

## List Tasks

```python
from app.tool.todo_tool.todo_tool import list_tasks

all_tasks = list_tasks.entrypoint()
```
