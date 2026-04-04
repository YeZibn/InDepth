from agno.agent import Agent
from agno.models.dashscope import DashScope
from dotenv import load_dotenv
import os
from agno.skills import Skills,LocalSkills
from agno.db.sqlite import SqliteDb
from agno.compression.manager import CompressionManager

from app.tool.bash_tool import execute_bash_command
from app.tool.get_current_time_tool import get_current_time
from app.tool.write_file_tool import write_file
from app.tool.read_file_tool import read_file
from app.tool.search_tool.ddg_search_tool import ddg_search
from app.tool.search_tool.url_search_tool import url_search



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
class SubAgent:
    """自定义智能体基类，可扩展工具、记忆、工作流"""

    def __init__(self, name:str, description:str, task:str):
        # 先设置属性
        self.name = name
        self.description = description
        self.db = SqliteDb(db_file="db/history.db")
        self.task = task

        self.compression_manager = CompressionManager(
            model=DashScope(
                id=os.getenv("LLM_MODEL_MINI_ID"),
                api_key=os.getenv("LLM_API_KEY"),
                base_url=os.getenv("LLM_BASE_URL"),
                enable_thinking=True
            ),  # Use a faster model for compression
            compress_tool_results_limit=5,  # Compress after 2 tool calls (default: 3)
            compress_tool_call_instructions="请精简工具调用结果，保留关键数据、结果和参数，删除冗余描述，保持逻辑完整，不丢失核心信息，用最简洁的语言概括。",
        )

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
            instructions=f"""你是一个子智能体（subagent），负责协助主智能体完成任务。
                                请严格遵守以下要求：
                                1. 只专注处理指定任务，不扩展无关内容。
                                2. 输出简洁、结构化，避免多余解释。
                                3. 如无法完成，明确说明原因，不编造信息。

                                你的专属任务：
                                {self.task}
                                """,
            markdown=True,
            tools= [execute_bash_command,get_current_time,read_file,write_file,ddg_search,url_search],
            skills= Skills(loaders=[LocalSkills("app/skills/memory-knowledge-skill")]),
            db=self.db,
            add_history_to_context=True,
            compress_tool_results=True,
            compression_manager=self.compression_manager
        )

    def chat(self, message: str):

        self.agent.print_response(message, streaming=True)

if __name__ == "__main__":
    agent = SubAgent(name="sub_agent", description="子智能体", task="助手")
    agent.chat("你好啊，你是谁")
