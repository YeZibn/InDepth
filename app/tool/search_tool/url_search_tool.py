import httpx
from agno.tools import tool
from typing import Any, Callable, Dict

def logger_hook(function_name: str, function_call: Callable, arguments: Dict[str, Any]):
    """Hook function that wraps the tool execution"""
    print(f"About to call {function_name} with arguments: {arguments}")
    result = function_call(**arguments)
    print(f"Function call completed with result: {result[:100]}..." if len(str(result)) > 100 else f"Function call completed with result: {result}")
    return result

@tool(
    name="url_search",                # Custom name for the tool
    description="Fetch content from a URL",  # Custom description
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
    try:
        # Headers to mimic a browser
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        
        # Send request
        with httpx.Client(timeout=10) as client:
            response = client.get(url, headers=headers)
            response.raise_for_status()
            
            # Get content
            content = response.text
            
            # Truncate if too long
            if len(content) > max_length:
                content = content[:max_length] + "\n... (truncated)"
            
            return content
    except Exception as e:
        return f"Error fetching URL: {str(e)}"
