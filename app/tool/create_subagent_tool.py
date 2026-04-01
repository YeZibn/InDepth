import uuid
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from agno.agent import Agent
from agno.models.dashscope import DashScope
from dotenv import load_dotenv
import os

load_dotenv()


class SubAgent:
    """轻量级子 Agent，用于执行简单单任务"""

    def __init__(self, task: str, context: dict = None, forbidden: list = None):
        self.id = str(uuid.uuid4())[:8]
        self.task = task
        self.context = context or {}
        self.forbidden = forbidden or []
        self.created_at = datetime.now()
        self.result = None

    def build_instructions(self) -> str:
        """构建 SubAgent 的指令"""
        instructions = [
            f"## 任务",
            f"{self.task}",
            "",
            f"## 约束",
            "- 只完成一个任务，完成后立即返回结果",
            "- 不要创建子 Agent 或使用 todo-skill",
            "- 使用最简洁的方式完成任务",
            "",
        ]

        if self.context:
            instructions.append("## 上下文")
            for key, value in self.context.items():
                instructions.append(f"- **{key}**: {value}")
            instructions.append("")

        if self.forbidden:
            instructions.append("## 禁止行为")
            for item in self.forbidden:
                instructions.append(f"- ~~{item}~~")
            instructions.append("")

        instructions.append("完成后，用最简洁的方式返回结果。")

        return "\n".join(instructions)

    def run(self) -> dict:
        """执行 SubAgent 任务"""
        agent = Agent(
            name=f"subagent_{self.id}",
            description=f"执行子任务: {self.task[:50]}...",
            instructions=self.build_instructions(),
            model=DashScope(
                id=os.getenv("LLM_MODEL_ID"),
                api_key=os.getenv("LLM_API_KEY"),
                base_url=os.getenv("LLM_BASE_URL"),
                enable_thinking=True
            ),
            markdown=True,
        )

        try:
            response = agent.run(self.task)
            self.result = {
                "success": True,
                "subagent_id": self.id,
                "task": self.task,
                "result": response.content if hasattr(response, 'content') else str(response),
                "duration": (datetime.now() - self.created_at).total_seconds()
            }
        except Exception as e:
            self.result = {
                "success": False,
                "subagent_id": self.id,
                "task": self.task,
                "error": str(e),
                "duration": (datetime.now() - self.created_at).total_seconds()
            }

        return self.result


class SubAgentRunner:
    """SubAgent 管理器，支持单任务和并行任务"""

    @staticmethod
    def run(task: str, context: dict = None, forbidden: list = None) -> dict:
        """运行单个 SubAgent"""
        subagent = SubAgent(task=task, context=context, forbidden=forbidden)
        return subagent.run()

    @staticmethod
    def run_parallel(tasks: list, context: dict = None, forbidden: list = None) -> list:
        """
        并行运行多个 SubAgent

        Args:
            tasks: 任务描述列表
            context: 共享上下文
            forbidden: 禁止行为列表

        Returns:
            list: 各 SubAgent 的执行结果
        """
        def run_single(task):
            subagent = SubAgent(task=task, context=context, forbidden=forbidden)
            return subagent.run()

        with ThreadPoolExecutor(max_workers=len(tasks)) as executor:
            results = list(executor.map(run_single, tasks))

        return results

    @staticmethod
    def aggregate_results(results: list) -> str:
        """聚合多个 SubAgent 的结果"""
        if not results:
            return "无结果"

        output = ["## SubAgent 执行结果\n"]
        for i, r in enumerate(results, 1):
            status = "✅" if r.get("success") else "❌"
            output.append(f"### {status} Task {i}: {r.get('subagent_id')}")
            output.append(f"**任务**: {r.get('task', '')[:80]}...")
            if r.get("success"):
                output.append(f"**结果**: {r.get('result', '')}")
            else:
                output.append(f"**错误**: {r.get('error', '')}")
            output.append(f"**耗时**: {r.get('duration', 0):.2f}s")
            output.append("")

        return "\n".join(output)
