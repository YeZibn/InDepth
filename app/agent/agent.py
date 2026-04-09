import os
import uuid
from typing import Any, Iterable, Optional

from dotenv import load_dotenv

from app.core.memory import SQLiteMemoryStore
from app.core.model import GenerationConfig
from app.core.model.http_chat_provider import HttpChatModelProvider
from app.core.runtime.agent_runtime import AgentRuntime
from app.core.skills import SkillLoader
from app.core.tools.adapters import register_tool_functions
from app.core.tools.registry import ToolRegistry


load_dotenv()


def load_indepth_content() -> str:
    indepth_path = os.path.join(os.path.dirname(__file__), "../../InDepth.md")
    try:
        with open(indepth_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        print(f"⚠️ 读取 InDepth.md 失败: {e}")
        return ""


class BaseAgent:
    """自研运行时版本的基础 Agent（兼容原构造参数）。"""

    def __init__(
        self,
        name: str,
        description: str,
        instructions: str = "",
        tools: Optional[Iterable[Any]] = None,
        skills: Any = None,
        load_memory_knowledge: bool = True,
        temperature: float | None = 0.2,
        top_p: float | None = None,
        presence_penalty: float | None = None,
        frequency_penalty: float | None = None,
        stop: list[str] | str | None = None,
        seed: int | None = None,
        n: int | None = None,
        max_tokens: int | None = None,
        enable_thinking: bool | None = None,
        model_options: Optional[dict] = None,
        enable_llm_judge: bool = True,
    ):
        self.name = name
        self.description = description
        self.skills = skills
        self.tools = list(tools) if tools else []
        self.skill_paths = self._extract_skill_paths(skills)
        self.skill_prompt = SkillLoader().build_skill_prompt(self.skill_paths)

        if load_memory_knowledge:
            self.instructions = load_indepth_content() + "\n\n" + instructions
        else:
            self.instructions = instructions

        generation_config = GenerationConfig(
            temperature=temperature,
            top_p=top_p,
            presence_penalty=presence_penalty,
            frequency_penalty=frequency_penalty,
            stop=stop,
            seed=seed,
            n=n,
            max_tokens=max_tokens,
            enable_thinking=enable_thinking,
            provider_options=model_options or {},
        )
        memory_file = f"db/runtime_memory_{self.name}.db"
        self.runtime = AgentRuntime(
            model_provider=HttpChatModelProvider(default_config=generation_config),
            tool_registry=self._build_registry(),
            system_prompt=self.instructions,
            max_steps=100,
            memory_store=SQLiteMemoryStore(db_file=memory_file),
            skill_prompt=self.skill_prompt,
            generation_config=generation_config,
            enable_llm_judge=enable_llm_judge,
        )

    def _build_registry(self) -> ToolRegistry:
        registry = ToolRegistry()
        register_tool_functions(registry, self.tools)
        return registry

    def chat(self, message: str) -> str:
        run_id = f"{self.name}_{uuid.uuid4().hex[:8]}"
        task_id = f"{self.name}_task"
        answer = self.runtime.run(user_input=message, task_id=task_id, run_id=run_id)
        print(answer)
        return answer

    def _extract_skill_paths(self, skills: Any) -> list[str]:
        if skills is None:
            return []
        if isinstance(skills, str):
            return [skills]
        if isinstance(skills, (list, tuple)):
            return [str(s) for s in skills if str(s).strip()]
        return []


if __name__ == "__main__":
    agent = BaseAgent(
        name="base_agent",
        description="基础智能体",
        instructions="你是一个专业、友好、知识渊博的 AI 助手，擅长回答各种问题。",
    )

    print("欢迎使用 LeadAgent！输入 'exit' 退出程序。\n")
    while True:
        user_input = input("请输入: ").strip()
        if user_input.lower() in ["exit", "quit", "q"]:
            print("再见！")
            break
        if not user_input:
            continue
        print("\nAgent: ", end="")
        agent.chat(user_input)
        print()
