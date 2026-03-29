from agno.agent import Agent, RunOutput
from agno.models.dashscope import DashScope
from agno.agent import Agent
from dotenv import load_dotenv
import os
from agno.utils.pprint import pprint_run_response

# 加载环境变量
load_dotenv()

# ======================
# 模型配置（固定工具函数）
# ======================
def get_model():
    """获取 Dashscope 模型实例"""
    return DashScope(
        id=os.getenv("LLM_MODEL_ID"),
        api_key=os.getenv("LLM_API_KEY"),
        base_url=os.getenv("LLM_BASE_URL"),
        enable_thinking=True
    )

# ======================
# 自定义 Agent 类（完整封装）
# ======================
class BaseAgent:
    """自定义智能体基类，可扩展工具、记忆、工作流"""
    
    def __init__(self, name:str, description:str, instructions:str, tools:list=None):
        # 先设置属性
        self.name = name
        self.description = description
        self.instructions = instructions
        self.tools = tools
        # 初始化模型
        self.model = get_model()
        # 初始化 agent 实例
        self.agent = self._create_agent()

    def _create_agent(self):
        """创建并配置 Agno Agent"""
        return Agent(
            model=self.model,
            name=self.name,
            description=self.description,
            instructions=self.instructions,
            markdown=True,
            tools=self.tools
        )

    def chat(self, message: str):

        # Print the response in markdown format
        self.agent.print_response(message, streaming=True)

        # run_response: Iterator[RunOutputEvent] = self.agent.run(message, stream=True)
        # for chunk in run_response:
        #     print(chunk)

# ======================
# 实例化 & 使用示例
# ======================
if __name__ == "__main__":
    # 创建智能体
    agent = BaseAgent(
        name="base_agent", 
        description="基础智能体", 
        instructions="你是一个专业、友好、知识渊博的 AI 助手，擅长回答各种问题。"
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
        agent.chat(user_input)
        print("\n")
