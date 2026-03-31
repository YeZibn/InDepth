import requests
from bs4 import BeautifulSoup
from agno.tools import tool
from typing import Any, Callable, Dict

def logger_hook(function_name: str, function_call: Callable, arguments: Dict[str, Any]):
    """Hook function that wraps the tool execution"""
    print(f"About to call {function_name} with arguments: {arguments}")
    result = function_call(**arguments)
    print(f"Function call completed with result: {result[:100]}..." if len(str(result)) > 100 else f"Function call completed with result: {result}")
    return result

@tool(
    name="baidu_search",                # Custom name for the tool
    description="When you need to search for information, call the Baidu search tool only once.After receiving the search results, organize the content directly into a clear answer and stop calling tools immediately.Do not search repeatedly for the same query, and do not ask for supplementary confirmation.Return concise and accurate results without redundant explanations.",  # Custom description
    stop_after_tool_call=False,                      # Return the result immediately after the tool call and stop the agent
    tool_hooks=[logger_hook],                       # Hook to run before and after execution
    requires_confirmation=False,                     # Doesn't require user confirmation
    cache_results=False,                            # Enable caching of results
    cache_ttl=3600                                  # Cache TTL in seconds (1 hour)
)
def baidu_search(query: str, num_results: int = 5) -> str:
    """
    Search on Baidu and return the top results.

    Args:
        query: The search query
        num_results: Number of results to return (default: 5)

    Returns:
        str: The search results in text format
    """
    try:
        # Baidu search URL
        url = "https://www.baidu.com/s"
        params = {
            "wd": query,
            "rn": num_results
        }
        
        # Headers to mimic a browser
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        
        # Send request
        response = requests.get(url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
        
        # Parse HTML
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Extract results
        results = []
        # Baidu search results are in div with class 'result'
        search_results = soup.find_all('div', class_='result')
        
        for i, result in enumerate(search_results[:num_results], 1):
            # Extract title
            title_elem = result.find('h3', class_='t')
            if title_elem:
                title = title_elem.get_text(strip=True)
                # Extract link
                link_elem = title_elem.find('a')
                link = link_elem['href'] if link_elem else 'No link'
                
                results.append(f"{i}. {title}\n   Link: {link}")
        
        if not results:
            return "No results found"
        
        return "\n\n".join(results)
    except Exception as e:
        return f"Error searching Baidu: {str(e)}"


