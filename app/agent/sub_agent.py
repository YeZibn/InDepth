import os
import uuid
from typing import Any, Dict, List

from dotenv import load_dotenv

from app.config import load_runtime_compression_config
from app.core.memory import SQLiteMemoryStore, build_context_compressor
from app.core.model import GenerationConfig
from app.core.model.http_chat_provider import HttpChatModelProvider
from app.core.runtime.agent_runtime import AgentRuntime
from app.core.runtime.task_token_store import TaskTokenStore
from app.core.skills import build_skills_manager
from app.core.tools.adapters import register_tool_functions
from app.core.tools.registry import ToolRegistry
from app.tool.bash_tool import execute_bash_command
from app.tool.get_current_time_tool import get_current_time
from app.tool.read_file_tool import read_file
from app.tool.search_tool.search_guard import get_guarded_search_tools
from app.tool.memory_query_tool import get_memory_card_by_id, search_memory_cards
from app.tool.write_file_tool import write_file


load_dotenv()


def load_sub_agent_role_prompt_template(role: str) -> str:
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
        return (
            "你是一个子智能体（subagent）。\n"
            "你的角色是：{role}\n"
            "你的专属任务：\n{task}\n"
            "{extra_instructions}"
        )


class SubAgent:
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
        temperature: float | None = 0.2,
        top_p: float | None = None,
        presence_penalty: float | None = None,
        frequency_penalty: float | None = None,
        stop: list[str] | str | None = None,
        seed: int | None = None,
        n: int | None = None,
        max_tokens: int | None = None,
        enable_thinking: bool | None = None,
        model_options: dict | None = None,
    ):
        self.name = name
        self.description = description
        self.role = self._normalize_role(role)
        self.task = task
        self.generated_instructions = (generated_instructions or "").strip()

        system_prompt_template = load_sub_agent_role_prompt_template(self.role)
        extra = (
            f"\n\n主Agent额外指令（必须遵守）：\n{self.generated_instructions}"
            if self.generated_instructions
            else ""
        )
        final_prompt = system_prompt_template.format(
            role=self.role,
            task=self.task,
            extra_instructions=extra,
        )
        self.skills_manager = build_skills_manager(["app/skills/memory-knowledge-skill"], validate=False)
        skill_prompt = self.skills_manager.get_system_prompt_snippet()
        # Aggregate runtime memory by sub-agent role.
        memory_file = f"db/runtime_memory_subagent_{self.role}.db"
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
        model_provider = HttpChatModelProvider(default_config=generation_config)
        compressor = build_context_compressor(
            kind=compression_config.compressor_kind,
            model_provider=model_provider,
            llm_max_tokens=compression_config.compressor_llm_max_tokens,
        )
        task_token_store = TaskTokenStore()

        self.runtime = AgentRuntime(
            model_provider=model_provider,
            tool_registry=self._build_registry(),
            system_prompt=final_prompt,
            max_steps=25,
            memory_store=SQLiteMemoryStore(
                db_file=memory_file,
                keep_recent=compression_config.keep_recent_turns,
                consistency_guard=compression_config.consistency_guard,
                context_window_tokens=compression_config.compression_trigger_window_tokens,
                target_keep_ratio_midrun=compression_config.target_keep_ratio_midrun,
                target_keep_ratio_finalize=compression_config.target_keep_ratio_finalize,
                min_keep_turns=compression_config.min_keep_turns,
                compressor=compressor,
                event_summarizer_kind=compression_config.event_summarizer_kind,
                event_summarizer_max_tokens=compression_config.event_summarizer_max_tokens,
                event_summarizer_model_provider=model_provider,
                task_token_store=task_token_store,
            ),
            skill_prompt=skill_prompt,
            generation_config=generation_config,
            compression_config=compression_config,
            task_token_store=task_token_store,
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

    def _build_tools(self) -> List[Any]:
        role_tools: Dict[str, List[Any]] = {
            self.ROLE_GENERAL: [execute_bash_command, get_current_time, read_file, write_file] + get_guarded_search_tools(),
            self.ROLE_RESEARCHER: [get_current_time, read_file, search_memory_cards, get_memory_card_by_id] + get_guarded_search_tools(),
            self.ROLE_BUILDER: [execute_bash_command, get_current_time, read_file, write_file],
            self.ROLE_REVIEWER: [get_current_time, read_file, search_memory_cards, get_memory_card_by_id],
            self.ROLE_VERIFIER: [execute_bash_command, get_current_time, read_file, search_memory_cards, get_memory_card_by_id],
        }
        return role_tools.get(self.role, role_tools[self.ROLE_GENERAL])

    def _build_registry(self) -> ToolRegistry:
        registry = ToolRegistry()
        all_tools = self._build_tools() + self.skills_manager.get_tools()
        register_tool_functions(registry, all_tools)
        return registry

    def chat(self, message: str) -> str:
        run_id = f"{self.name}_{uuid.uuid4().hex[:8]}"
        task_id = f"subagent_{self.role}_{self.name}"
        return self.runtime.run(user_input=message, task_id=task_id, run_id=run_id)


if __name__ == "__main__":
    agent = SubAgent(name="sub_agent", description="子智能体", task="助手")
    print(agent.chat("你好啊，你是谁"))
