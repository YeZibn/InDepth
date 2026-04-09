from app.tool.bash_tool import execute_bash_command
from app.tool.search_tool.search_guard import get_guarded_search_tools
from app.agent.agent import BaseAgent
from app.tool.get_current_time_tool import get_current_time
from app.tool.read_file_tool import read_file
from app.tool.write_file_tool import write_file
from app.tool.sub_agent_tool.sub_agent_tool import get_sub_agent_tools
from app.tool.todo_tool.todo_tool import load_todo_tools

TodoTools = load_todo_tools()



# ======================
# 实例化 & 使用示例
# ======================
if __name__ == "__main__":

    # 创建智能体
    search_agent = BaseAgent(
        name="main_agent", 
        description="主智能体", 
        instructions="你是一个主智能体，可以帮助用户完成任务，包括搜索、任务分配、子智能体调用等。",
        tools=[execute_bash_command, get_current_time, read_file, write_file] + get_guarded_search_tools() + get_sub_agent_tools() + TodoTools.get_tools(),
        skills=None,
        load_memory_knowledge=True
    )

    
    print("欢迎使用 LeadAgent！输入 'exit' 退出程序。\n")
    
    # 循环对话
    while True:
        user_input = input("请输入: ").strip()
        
        if user_input.lower() in ["exit", "quit", "q"]:
            print("再见！")
            break
        
        if not user_input:
            continue
        
        print("\nAgent: ", end="")
        search_agent.chat(user_input)
        print("\n")
