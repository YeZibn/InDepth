from typing import Any, Iterable, List

from app.core.tools.registry import ToolRegistry, ToolSpec


def register_tool_functions(registry: ToolRegistry, functions: Iterable[Any]) -> None:
    for fn in functions:
        name = getattr(fn, "name", "")
        if not name:
            continue
        handler = getattr(fn, "entrypoint", None)
        if handler is None:
            continue
        registry.register(
            ToolSpec(
                name=name,
                description=getattr(fn, "description", "") or "",
                handler=handler,
                parameters=getattr(fn, "parameters", None),
                hidden=bool(getattr(fn, "hidden", False)),
            )
        )


def build_default_registry() -> ToolRegistry:
    from app.tool.bash_tool import execute_bash_command
    from app.tool.get_current_time_tool import get_current_time
    from app.tool.read_file_tool import read_file
    from app.tool.memory_query_tool import get_memory_card_by_id
    from app.tool.runtime_memory_harvest_tool import capture_runtime_memory_candidate
    from app.tool.write_file_tool import write_file
    from app.tool.search_tool.search_guard import get_guarded_search_tools
    from app.tool.sub_agent_tool.sub_agent_tool import get_sub_agent_tools
    from app.tool.todo_tool.todo_tool import load_todo_tools

    todo_tools = load_todo_tools().get_tools()
    all_tools: List[Any] = [
        execute_bash_command,
        get_current_time,
        read_file,
        write_file,
        capture_runtime_memory_candidate,
        get_memory_card_by_id,
    ]
    all_tools += get_guarded_search_tools()
    all_tools += get_sub_agent_tools()
    all_tools += todo_tools

    registry = ToolRegistry()
    register_tool_functions(registry, all_tools)
    return registry
