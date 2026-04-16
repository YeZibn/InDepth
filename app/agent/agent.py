import os
import re
import uuid
from datetime import datetime
from typing import Any, Iterable, Optional

from dotenv import load_dotenv

from app.config import load_runtime_compression_config
from app.core.memory import SQLiteMemoryStore
from app.core.model import GenerationConfig
from app.core.model.http_chat_provider import HttpChatModelProvider
from app.core.runtime.agent_runtime import AgentRuntime
from app.core.skills import build_skills_manager
from app.core.tools.adapters import build_default_registry, register_tool_functions
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
        load_default_tools: bool = True,
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
        self.load_default_tools = bool(load_default_tools)
        self.skill_paths = self._extract_skill_paths(skills)
        self.skills_manager = build_skills_manager(self.skill_paths, validate=False)
        self.skill_prompt = self.skills_manager.get_system_prompt_snippet()

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
        compression_config = load_runtime_compression_config()
        # Aggregate runtime memory by agent type to avoid per-name DB fragmentation.
        memory_file = "db/runtime_memory_main_agent.db"
        self.runtime = AgentRuntime(
            model_provider=HttpChatModelProvider(default_config=generation_config),
            tool_registry=self._build_registry(),
            system_prompt=self.instructions,
            max_steps=100,
            memory_store=SQLiteMemoryStore(
                db_file=memory_file,
                keep_recent=compression_config.keep_recent_turns,
                consistency_guard=compression_config.consistency_guard,
                context_window_tokens=compression_config.context_window_tokens,
                target_keep_ratio_midrun=compression_config.target_keep_ratio_midrun,
                target_keep_ratio_finalize=compression_config.target_keep_ratio_finalize,
                min_keep_messages=compression_config.min_keep_messages,
            ),
            skill_prompt=self.skill_prompt,
            generation_config=generation_config,
            enable_llm_judge=enable_llm_judge,
            compression_config=compression_config,
        )
        self._active_run_id: Optional[str] = None
        self._awaiting_user_input = False
        self._task_id = self._generate_task_id()

    def _build_registry(self) -> ToolRegistry:
        registry = build_default_registry() if self.load_default_tools else ToolRegistry()
        all_tools = list(self.tools)
        if self.skills_manager.get_skill_names():
            all_tools.extend(self.skills_manager.get_tools())
        register_tool_functions(registry, all_tools)
        return registry

    def chat(self, message: str) -> str:
        task_id = self._task_id
        resume_from_waiting = self._awaiting_user_input and bool(self._active_run_id)
        run_id = self._active_run_id or f"{self.name}_{uuid.uuid4().hex[:8]}"
        answer = self.runtime.run(
            user_input=message,
            task_id=task_id,
            run_id=run_id,
            resume_from_waiting=resume_from_waiting,
        )
        runtime_state = str(getattr(self.runtime, "last_runtime_state", "")).strip()
        if runtime_state == "awaiting_user_input":
            self._awaiting_user_input = True
            self._active_run_id = run_id
        else:
            self._awaiting_user_input = False
            self._active_run_id = None
        print(self._format_cli_answer(answer=answer, runtime_state=runtime_state))
        return answer

    def _format_cli_answer(self, answer: str, runtime_state: str) -> str:
        text = str(answer or "")
        if runtime_state != "awaiting_user_input":
            return text
        parts = [
            "[需要澄清]",
            text,
            "请直接回复补充信息，我会在当前任务中继续。",
        ]
        return "\n".join([p for p in parts if p])

    @property
    def is_awaiting_user_input(self) -> bool:
        return bool(self._awaiting_user_input)

    def _generate_task_id(self, label: str = "") -> str:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        suffix = ""
        if label.strip():
            sanitized = re.sub(r"[^a-zA-Z0-9_-]+", "_", label).strip("_")
            if sanitized:
                suffix = f"_{sanitized[:32]}"
        return f"{self.name}_task_{timestamp}{suffix}"

    def start_new_task(self, label: str = "") -> str:
        self._task_id = self._generate_task_id(label=label)
        self._awaiting_user_input = False
        self._active_run_id = None
        return self._task_id

    @property
    def current_task_id(self) -> str:
        return self._task_id

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
