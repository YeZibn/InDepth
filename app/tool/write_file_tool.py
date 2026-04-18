import os
from app.core.tools import tool
from typing import Any, Callable, Dict

def logger_hook(function_name: str, function_call: Callable, arguments: Dict[str, Any]):
    """Hook function that wraps the tool execution"""
    print(f"About to call {function_name} with arguments: {arguments}")
    result = function_call(**arguments)
    print(f"Function call completed with result: {result}")
    return result

@tool(
    name="write_file",                # Custom name for the tool
    description="Write content to a file. Supports overwrite or append modes.",  # Custom description
    stop_after_tool_call=False,                      # Return the result immediately after the tool call and stop the agent
    tool_hooks=[logger_hook],                       # Hook to run before and after execution
    requires_confirmation=False,                     # Requires user confirmation before execution
    cache_results=False,                            # Disable caching of results
)
def write_file(file_path: str, content: str, overwrite: bool = False, append: bool = False) -> str:
    """
    Write content to a file.

    Args:
        file_path: The path to the file to write
        content: The content to write to the file
        overwrite: Whether to overwrite the file if it already exists
        append: Whether to append content to the file if it already exists

    Returns:
        str: Success message or error
    """
    try:
        if overwrite and append:
            return "Error: overwrite and append cannot both be True."

        file_exists = os.path.exists(file_path)

        # Check if file exists and neither overwrite nor append is enabled
        if file_exists and not overwrite and not append:
            return f"Error: File '{file_path}' already exists. Use overwrite=True to overwrite it."

        # Create directory if it doesn't exist
        directory = os.path.dirname(file_path)
        if directory and not os.path.exists(directory):
            os.makedirs(directory, exist_ok=True)

        mode = "a" if append else "w"
        with open(file_path, mode, encoding='utf-8') as f:
            f.write(content)

        if append:
            return f"Successfully appended to file: {file_path}"
        return f"Successfully wrote to file: {file_path}"
    except Exception as e:
        return f"Error writing file: {str(e)}"
