from agno.agent import Agent
from agno.models.dashscope import DashScope
from dotenv import load_dotenv
import os
from typing import Dict, List
from agno.skills import Skills,LocalSkills
from agno.db.sqlite import SqliteDb
from agno.compression.manager import CompressionManager

from app.tool.bash_tool import execute_bash_command
from app.tool.get_current_time_tool import get_current_time
from app.tool.write_file_tool import write_file
from app.tool.read_file_tool import read_file
from app.tool.search_tool.search_guard import get_guarded_search_tools



# 加载环境变量
load_dotenv()

# ======================
# 模型配置（固定工具函数）
# ======================
def get_model():
    """获取 Dashscope 模型实例"""
    return DashScope(
        id=os.getenv("CODEX_MODEL_ID"),
        api_key=os.getenv("CODEX_API_KEY"),
        base_url=os.getenv("CODEX_BASE_URL"),
        enable_thinking=True
    )


def load_sub_agent_role_prompt_template(role: str) -> str:
    """按角色加载 SubAgent 系统提示词模板"""
    prompt_path = os.path.join(
        os.path.dirname(__file__),
        "prompts",
        "sub_agent_roles",
        f"{role}.md",
    )
    try:
        with open(prompt_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        # 兜底，避免模板文件缺失导致系统不可用
        return (
            "你是一个子智能体（subagent）。\n"
            "你的角色是：{role}\n"
            "你的专属任务：\n{task}\n"
            "{extra_instructions}"
        )

# ======================
# 自定义 Agent 类（完整封装）
# ======================
class SubAgent:
    """自定义智能体基类，可扩展工具、记忆、工作流"""

    ROLE_GENERAL = "general"
    ROLE_RESEARCHER = "researcher"
    ROLE_BUILDER = "builder"
    ROLE_REVIEWER = "reviewer"
    ROLE_VERIFIER = "verifier"

    def __init__(
        self,
        name: str,
        description: str,
        task: str,
        role: str = ROLE_GENERAL,
        generated_instructions: str = "",
    ):
        # 先设置属性
        self.name = name
        self.description = description
        self.role = self._normalize_role(role)
        self.db = SqliteDb(db_file=self._get_db_file_by_role())
        self.task = task
        self.generated_instructions = (generated_instructions or "").strip()

        self.compression_manager = CompressionManager(
            model=DashScope(
                id=os.getenv("CODEX_MODEL_MINI_ID"),
                api_key=os.getenv("CODEX_API_KEY"),
                base_url=os.getenv("CODEX_BASE_URL"),
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
        extra_instructions = (
            f"\n\n主Agent额外指令（必须遵守）：\n{self.generated_instructions}"
            if self.generated_instructions
            else ""
        )
        system_prompt_template = load_sub_agent_role_prompt_template(self.role)
        final_instructions = system_prompt_template.format(
            role=self.role,
            task=self.task,
            extra_instructions=extra_instructions,
        )
        return Agent(
            model=self.model,
            name=self.name,
            description=self.description,
            instructions=final_instructions,
            markdown=True,
            tools=self._build_tools(),
            skills= Skills(loaders=[LocalSkills("app/skills/memory-knowledge-skill")]),
            db=self.db,
            add_history_to_context=True,
            compress_tool_results=True,
            compression_manager=self.compression_manager
        )

    def _normalize_role(self, role: str) -> str:
        role_norm = (role or "").strip().lower()
        allowed = {
            self.ROLE_GENERAL,
            self.ROLE_RESEARCHER,
            self.ROLE_BUILDER,
            self.ROLE_REVIEWER,
            self.ROLE_VERIFIER,
        }
        return role_norm if role_norm in allowed else self.ROLE_GENERAL

    def _get_db_file_by_role(self) -> str:
        role_to_db = {
            self.ROLE_GENERAL: "db/history_subagent_general.db",
            self.ROLE_RESEARCHER: "db/history_subagent_researcher.db",
            self.ROLE_BUILDER: "db/history_subagent_builder.db",
            self.ROLE_REVIEWER: "db/history_subagent_reviewer.db",
            self.ROLE_VERIFIER: "db/history_subagent_verifier.db",
        }
        return role_to_db[self.role]

    def _build_tools(self) -> List:
        role_tools: Dict[str, List] = {
            self.ROLE_GENERAL: [execute_bash_command, get_current_time, read_file, write_file] + get_guarded_search_tools(),
            self.ROLE_RESEARCHER: [get_current_time, read_file] + get_guarded_search_tools(),
            self.ROLE_BUILDER: [execute_bash_command, get_current_time, read_file, write_file],
            self.ROLE_REVIEWER: [get_current_time, read_file],
            self.ROLE_VERIFIER: [execute_bash_command, get_current_time, read_file],
        }
        return role_tools.get(self.role, role_tools[self.ROLE_GENERAL])

    def chat(self, message: str) -> str:
        """执行子任务并返回文本结果，供主 Agent 汇总。"""
        run_output = self.agent.run(message, stream=False)
        try:
            return run_output.get_content_as_string()
        except Exception:
            content = getattr(run_output, "content", None)
            return "" if content is None else str(content)

if __name__ == "__main__":
    agent = SubAgent(name="sub_agent", description="子智能体", task="助手")
    print(agent.chat("你好啊，你是谁"))
