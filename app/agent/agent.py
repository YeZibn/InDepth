from agno.agent import Agent
from agno.models.siliconflow import Siliconflow
from typing import Iterator
from agno.agent import Agent, RunOutputEvent, RunEvent
from typing import Iterator
from dotenv import load_dotenv
import os

# 加载环境变量
load_dotenv()

# ======================
# 模型配置（固定工具函数）
# ======================
def get_model():
    """获取 Siliconflow 模型实例"""
    return Siliconflow(
        id=os.getenv("LLM_MODEL_ID"),
        api_key=os.getenv("LLM_API_KEY"),
        base_url=os.getenv("LLM_BASE_URL"),
    )

# ======================
# 自定义 Agent 类（完整封装）
# ======================
class BaseAgent:
    """自定义智能体基类，可扩展工具、记忆、工作流"""
    
    def __init__(self, name:str, description:str, instructions:str):
        # 先设置属性
        self.name = name
        self.description = description
        self.instructions = instructions
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
            stream=True,
            stream_events=True
        )

    def chat(self, message: str):
        """与智能体对话（核心方法）"""
        stream: Iterator[RunOutputEvent] = self.agent.run(message, stream=True, stream_events=True)
        for chunk in stream:
            if chunk.event == RunEvent.run_content:
                if chunk.content:
                    print(chunk.content, end="", flush=True)
            elif chunk.event == RunEvent.tool_call_started:
                print(f"Tool call started: {chunk.tool.tool_name}")
            elif chunk.event == RunEvent.reasoning_step:
                print(f"Reasoning step: {chunk.reasoning_content}")

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
