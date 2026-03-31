from agno.agent import Agent, RunOutput
from agno.models.dashscope import DashScope
from dotenv import load_dotenv
import os
from agno.utils.pprint import pprint_run_response
from agno.skills import Skills
from agno.db.sqlite import SqliteDb
from agno.compression.manager import CompressionManager
from agno.models.openai import OpenAIResponses



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
    
def load_indepth_content() -> str:
    """加载 InDepth.md 行为准则"""
    indepth_path = os.path.join(os.path.dirname(__file__), "../../InDepth.md")
    try:
        with open(indepth_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        print(f"⚠️ 读取 InDepth.md 失败: {e}")
        return ""


# ======================
# 自定义 Agent 类（完整封装）
# ======================
class BaseAgent:
    """自定义智能体基类，可扩展工具、记忆、工作流"""

    def __init__(self, name:str, description:str, instructions:str="", tools:list=None, skills:Skills=None, load_memory_knowledge:bool=True):
        # 先设置属性
        self.name = name
        self.description = description
        self.tools = tools
        self.skills = skills
        self.db = SqliteDb(db_file="db/history.db")

        # 合并指令：InDepth.md + 用户提供的 instructions
        if load_memory_knowledge:
            indepth_content = load_indepth_content()
            self.instructions = indepth_content + "\n\n" + instructions
        else:
            self.instructions = instructions

        self.compression_manager = CompressionManager(
            model=DashScope(
                id="qwen3.5-flash",
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
            instructions=self.instructions,
            markdown=True,
            tools=self.tools,
            skills=self.skills,
            db=self.db,
            add_history_to_context=True,
            compress_tool_results=True,
            compression_manager=self.compression_manager
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
