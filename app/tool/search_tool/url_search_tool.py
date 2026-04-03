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
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
        }
        
        # Send request with redirect following
        with httpx.Client(
            timeout=15,
            follow_redirects=True,
            max_redirects=5
        ) as client:
            response = client.get(url, headers=headers)
            
            # Handle different status codes
            if response.status_code == 200:
                # Get content
                content = response.text
                
                # Truncate if too long
                if len(content) > max_length:
                    content = content[:max_length] + "\n... (truncated)"
                
                return content
            elif response.status_code in [301, 302, 303, 307, 308]:
                # Redirect but httpx should have followed it
                return f"Error: Redirect loop detected for URL: {url}"
            elif response.status_code == 404:
                return f"Error: Page not found (404) for URL: {url}"
            elif response.status_code == 403:
                return f"Error: Access forbidden (403) for URL: {url}. The site may block automated requests."
            elif response.status_code >= 500:
                return f"Error: Server error ({response.status_code}) for URL: {url}"
            else:
                return f"Error: HTTP {response.status_code} for URL: {url}"
                
    except httpx.TimeoutException:
        return f"Error: Request timeout for URL: {url}"
    except httpx.TooManyRedirects:
        return f"Error: Too many redirects for URL: {url}"
    except httpx.RequestError as e:
        return f"Error: Request failed for URL {url}: {str(e)}"
    except Exception as e:
        return f"Error fetching URL: {str(e)}"
