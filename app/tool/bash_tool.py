import subprocess
from agno.tools import tool
from typing import Any, Callable, Dict

def logger_hook(function_name: str, function_call: Callable, arguments: Dict[str, Any]):
    """Hook function that wraps the tool execution"""
    print(f"About to call {function_name} with arguments: {arguments}")
    result = function_call(**arguments)
    print(f"Function call completed with result: {result}")
    return result

@tool(
    name="bash",                # Custom name for the tool
    description="Execute bash commands and return the output",  # Custom description
    stop_after_tool_call=False,                      # Return the result immediately after the tool call and stop the agent
    tool_hooks=[logger_hook],                       # Hook to run before and after execution
    requires_confirmation=True,                     # Requires user confirmation before execution
    cache_results=False,                            # Disable caching of results
)
def execute_bash_command(command: str) -> str:
    """
    Execute a bash command and return the output.

    Args:
        command: The bash command to execute

    Returns:
        str: The output of the command
    """
    try:
        # Execute the command and capture output
        result = subprocess.run(
            command, 
            shell=True, 
            capture_output=True, 
            text=True, 
            timeout=30  # Set a timeout to prevent hanging
        )
        
        # Combine stdout and stderr
        output = result.stdout
        if result.stderr:
            output += f"\nSTDERR: {result.stderr}"
        
        # Include return code
        output += f"\nReturn code: {result.returncode}"
        
        return output
    except Exception as e:
        return f"Error executing command: {str(e)}"
