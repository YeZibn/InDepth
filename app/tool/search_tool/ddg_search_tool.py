from ddgs import DDGS
from agno.tools import tool
from typing import Any, Callable, Dict


def logger_hook(function_name: str, function_call: Callable, arguments: Dict[str, Any]):
    print(f"About to call {function_name} with arguments: {arguments}")
    result = function_call(**arguments)
    print(f"Function call completed with result: {result[:100]}..." if len(str(result)) > 100 else f"Function call completed with result: {result}")
    return result


@tool(
    name="ddg_search",
    description="Search DuckDuckGo for information. Call this when you need to search for current events, technical documentation, or any information. After receiving results, organize directly into a clear answer and stop calling tools. Do not search the same query twice.",
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
    try:
        results = []
        with DDGS() as ddgs:
            for i, r in enumerate(ddgs.text(query, max_results=num_results), 1):
                title = r.get('title', 'No title')
                body = r.get('body', 'No description')
                href = r.get('href', 'No link')
                results.append(f"{i}. {title}\n   {body}\n   Link: {href}")

        if not results:
            return "No results found"

        return "\n\n".join(results)
    except Exception as e:
        return f"Error searching DuckDuckGo: {str(e)}"
