import os
from agno.tools import tool
from typing import Any, Callable, Dict

def logger_hook(function_name: str, function_call: Callable, arguments: Dict[str, Any]):
    """Hook function that wraps the tool execution"""
    print(f"About to call {function_name} with arguments: {arguments}")
    result = function_call(**arguments)
    print(f"Function call completed with result: {result[:100]}..." if len(str(result)) > 100 else f"Function call completed with result: {result}")
    return result

@tool(
    name="read_file",                # Custom name for the tool
    description="Read the content of a file",  # Custom description
    stop_after_tool_call=False,                      # Return the result immediately after the tool call and stop the agent
    tool_hooks=[logger_hook],                       # Hook to run before and after execution
    requires_confirmation=False,                     # Requires user confirmation before execution
    cache_results=False,                            # Disable caching of results
)
def read_file(file_path: str) -> str:
    """
    Read the content of a file.

    Args:
        file_path: The path to the file to read

    Returns:
        str: The content of the file
    """
    try:
        # Check if file exists
        if not os.path.exists(file_path):
            return f"Error: File '{file_path}' does not exist"
        
        # Check if it's a file
        if not os.path.isfile(file_path):
            return f"Error: '{file_path}' is not a file"
        
        # Read file content
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        return content
    except Exception as e:
        return f"Error reading file: {str(e)}"
