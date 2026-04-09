from app.core.tools import tool
from typing import Any, Callable, Dict


def logger_hook(function_name: str, function_call: Callable, arguments: Dict[str, Any]):
    print(f"About to call {function_name} with arguments: {arguments}")
    result = function_call(**arguments)
    print(f"Function call completed with result: {result[:100]}..." if len(str(result)) > 100 else f"Function call completed with result: {result}")
    return result


@tool(
    name="ddg_search",
    description="DEPRECATED: direct search is disabled. Use search guard tools instead: init_search_guard -> guarded_ddg_search.",
    stop_after_tool_call=False,
    tool_hooks=[logger_hook],
    requires_confirmation=False,
    cache_results=False
)
def ddg_search(query: str, num_results: int = 5) -> str:
    """
    Search using DuckDuckGo and return results.

    Args:
        query: The search query
        num_results: Number of results to return (default: 5)

    Returns:
        str: Search results in text format
    """
    return (
        "Error: direct ddg_search is disabled by policy. "
        "Use search guard flow: "
        "init_search_guard -> guarded_ddg_search -> update_search_progress -> get_search_guard_status."
    )
