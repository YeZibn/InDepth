from app.core.memory import SQLiteMemoryStore
from app.core.model import GenerationConfig
from app.core.model.http_chat_provider import HttpChatModelProvider
from app.core.runtime.agent_runtime import AgentRuntime
from app.core.skills import SkillLoader
from app.core.tools.adapters import build_default_registry


def create_runtime(
    system_prompt: str = "",
    max_steps: int = 50,
    skill_paths: list[str] | None = None,
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
    enable_llm_judge: bool = True,
) -> AgentRuntime:
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
    model_provider = HttpChatModelProvider(default_config=generation_config)
    tool_registry = build_default_registry()
    skill_prompt = SkillLoader().build_skill_prompt(skill_paths or [])
    return AgentRuntime(
        model_provider=model_provider,
        tool_registry=tool_registry,
        system_prompt=system_prompt,
        max_steps=max_steps,
        memory_store=SQLiteMemoryStore(db_file="db/runtime_memory_cli.db"),
        skill_prompt=skill_prompt,
        generation_config=generation_config,
        enable_llm_judge=enable_llm_judge,
    )
