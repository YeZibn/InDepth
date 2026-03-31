from agno.agent import Agent
from agno.models.dashscope import DashScope
from agno.skills import Skills
from dotenv import load_dotenv
import os
from agno.skills import LocalSkills
from app.tool.bash_tool import execute_bash_command



load_dotenv()


def get_indepth_content() -> str:
    """加载 InDepth.md 行为准则"""
    indepth_path = os.path.join(os.path.dirname(__file__), "../../InDepth.md")
    try:
        with open(indepth_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        print(f"⚠️ 读取 InDepth.md 失败: {e}")
        return ""


class CreateSkillAgent:
    """专门用于创建和打包 Skill 的 Agent"""

    def __init__(self):
        self.agent = Agent(
            name="skill_creator",
            description="Skill 创建专家，擅长设计、构建和打包 Agent Skills",
            instructions=get_indepth_content() + "\n\n" + """你是一个 Skill 创建专家。

当你收到创建 Skill 的请求时：

1. **理解需求**
   - 用户想创建什么 Skill？
   - 主要功能是什么？
   - 触发场景有哪些？

2. **使用 skill-creator 框架**
   - 遵循 skill-creator 的 6 步流程
   - 设计合理的目录结构
   - 编写简洁有效的 SKILL.md

3. **创建流程**
   a. 先运行 init_skill.py 初始化目录
   b. 编辑 SKILL.md 和资源文件
   c. 运行 package_skill.py 打包

4. **交付**
   - 告知用户生成的 .skill 文件位置
   - 说明如何使用这个 Skill

开始之前，请先阅读 skill-creator 的完整指南。""",
            model=DashScope(
                id=os.getenv("LLM_MODEL_ID"),
                api_key=os.getenv("LLM_API_KEY"),
                base_url=os.getenv("LLM_BASE_URL"),
                enable_thinking=True
            ),
            skills=Skills(loaders=[LocalSkills("app/skills")]),
            tools=[execute_bash_command],
        )

    def chat(self, message: str):
        """与 Skill 创建 Agent 对话"""
        self.agent.print_response(message, streaming=True)


if __name__ == "__main__":
    agent = CreateSkillAgent()

    print("=" * 50)
    print("Skill Creator Agent")
    print("=" * 50)
    print("我可以帮你创建、构建和打包 Skill")
    print("输入 'exit' 退出\n")

    while True:
        user_input = input("你: ").strip()

        if user_input.lower() in ["exit", "quit", "q"]:
            print("再见！")
            break

        if not user_input:
            continue

        agent.chat(user_input)
        print()
