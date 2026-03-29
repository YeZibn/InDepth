from app.tool.search.baidu_search_tool import baidu_search
from app.agent.agent import BaseAgent
from app.tool.search.url_search_tool import url_search



# ======================
# 实例化 & 使用示例
# ======================
if __name__ == "__main__":
    # 创建智能体
    search_agent = BaseAgent(
        name="search_agent", 
        description="搜索智能体", 
        instructions="你是一个专业、友好、知识渊博的 AI 助手，擅长回答各种问题。",
        tools=[baidu_search,url_search]
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