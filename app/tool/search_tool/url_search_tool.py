from app.core.tools import tool
from typing import Any, Callable, Dict

def logger_hook(function_name: str, function_call: Callable, arguments: Dict[str, Any]):
    """Hook function that wraps the tool execution"""
    print(f"About to call {function_name} with arguments: {arguments}")
    result = function_call(**arguments)
    print(f"Function call completed with result: {result[:100]}..." if len(str(result)) > 100 else f"Function call completed with result: {result}")
    return result

@tool(
    name="url_search",                # Custom name for the tool
    description="DEPRECATED: direct URL fetch is disabled. Use search guard tools instead: init_search_guard -> guarded_url_search.",  # Custom description
    stop_after_tool_call=False,                      # Return the result immediately after the tool call and stop the agent
    tool_hooks=[logger_hook],                       # Hook to run before and after execution
    requires_confirmation=False,                     # Doesn't require user confirmation
    cache_results=False,                            # Enable caching of results
    cache_ttl=3600                                  # Cache TTL in seconds (1 hour)
)
def url_search(url: str, max_length: int = 2000) -> str:
    """
    Fetch content from a URL and return it.

    Args:
        url: The URL to fetch
        max_length: Maximum length of the returned content (default: 2000)

    Returns:
        str: The content of the URL
    """
    return (
        "Error: direct url_search is disabled by policy. "
        "Use search guard flow: "
        "init_search_guard -> guarded_url_search -> update_search_progress -> get_search_guard_status."
    )
