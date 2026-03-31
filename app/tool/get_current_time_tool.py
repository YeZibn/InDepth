from datetime import datetime
from agno.tools import tool
from typing import Any, Callable, Dict

def logger_hook(function_name: str, function_call: Callable, arguments: Dict[str, Any]):
    """Hook function that wraps the tool execution"""
    print(f"About to call {function_name} with arguments: {arguments}")
    result = function_call(**arguments)
    print(f"Function call completed with result: {result}")
    return result

@tool(
    name="get_current_time",                # Custom name for the tool
    description="Get the current date and time",  # Custom description
    stop_after_tool_call=True,                      # Return the result immediately after the tool call and stop the agent
    tool_hooks=[logger_hook],                       # Hook to run before and after execution
    requires_confirmation=False,                     # Doesn't require user confirmation
    cache_results=False,                            # Disable caching of results
)
def get_current_time(format: str = "%Y-%m-%d %H:%M:%S") -> str:
    """
    Get the current date and time.

    Args:
        format: The format of the date and time string (default: "%Y-%m-%d %H:%M:%S")
               Common formats:
               - "%Y-%m-%d %H:%M:%S" -> "2026-03-29 14:30:00"
               - "%Y-%m-%d" -> "2026-03-29"
               - "%H:%M:%S" -> "14:30:00"
               - "%Y年%m月%d日 %H时%M分%S秒" -> "2026年03月29日 14时30分00秒"

    Returns:
        str: The current date and time in the specified format
    """
    try:
        now = datetime.now()
        return now.strftime(format)
    except Exception as e:
        return f"Error getting current time: {str(e)}"
