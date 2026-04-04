import sys
import os
from importlib import util

def load_todo_tools():
    """Dynamically load TodoTools from todo-skill directory"""
    current_file = os.path.abspath(__file__)

    search_tool_dir = os.path.dirname(current_file)
    tool_dir = os.path.dirname(search_tool_dir)
    app_dir = os.path.dirname(tool_dir)
    skills_dir = os.path.join(app_dir, 'skills')
    todo_skill_path = os.path.join(skills_dir, 'todo-skill', 'scripts')

    print(f"✓ Paths resolved correctly:")
    print(f"  - todo_skill_path: {todo_skill_path}")
    print(f"  - exists: {os.path.exists(todo_skill_path)}")

    utils_path = os.path.join(todo_skill_path, "utils.py")
    tools_path = os.path.join(todo_skill_path, "tools.py")
    print(f"  - utils.py exists: {os.path.exists(utils_path)}")
    print(f"  - tools.py exists: {os.path.exists(tools_path)}")

    if not os.path.exists(tools_path):
        return None

    utils_spec = util.spec_from_file_location("todo_utils", utils_path)
    utils_module = util.module_from_spec(utils_spec)
    sys.modules["utils"] = utils_module
    utils_spec.loader.exec_module(utils_module)

    tools_spec = util.spec_from_file_location("todo_tools", tools_path)
    tools_module = util.module_from_spec(tools_spec)
    sys.modules["scripts.tools"] = tools_module

    try:
        tools_spec.loader.exec_module(tools_module)
    except ModuleNotFoundError as e:
        print(f"✗ Import error (expected in dev environment): {e}")
        print("  This will work in Agent environment with agno installed.")
        return None

    return tools_module.TodoTools


