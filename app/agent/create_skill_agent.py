import os

from dotenv import load_dotenv

from app.agent.agent import BaseAgent
from app.tool.bash_tool import execute_bash_command
from app.tool.read_file_tool import read_file
from app.tool.write_file_tool import write_file


load_dotenv()


def get_indepth_content() -> str:
    indepth_path = os.path.join(os.path.dirname(__file__), "../../InDepth.md")
    try:
        with open(indepth_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        print(f"⚠️ 读取 InDepth.md 失败: {e}")
        return ""


class CreateSkillAgent:
    """专门用于创建和打包 Skill 的 Agent。"""

    def __init__(self):
        instructions = get_indepth_content() + "\n\n" + """你是一个 Skill 创建专家。

当你收到创建 Skill 的请求时：
1. 理解需求并确认触发场景。
2. 使用 `app/skills/skill-creator` 的流程与脚本。
3. 先初始化目录，再编辑文件，最后打包。
4. 输出最终 skill 产物路径和使用说明。
"""
        self.agent = BaseAgent(
            name="skill_creator",
            description="Skill 创建专家，擅长设计、构建和打包 Agent Skills",
            instructions=instructions,
            tools=[execute_bash_command, read_file, write_file],
            load_default_tools=False,
            skills=None,
            load_memory_knowledge=False,
        )

    def chat(self, message: str):
        return self.agent.chat(message)


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
