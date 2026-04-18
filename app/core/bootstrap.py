from app.config import load_runtime_compression_config
from app.core.memory import SQLiteMemoryStore, build_context_compressor
from app.core.model import GenerationConfig
from app.core.model.http_chat_provider import HttpChatModelProvider
from app.core.runtime.agent_runtime import AgentRuntime
from app.core.skills import build_skills_manager
from app.core.tools.adapters import build_default_registry, register_tool_functions


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
    compression_config = load_runtime_compression_config()
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
    compressor = build_context_compressor(
        kind=compression_config.compressor_kind,
        model_provider=model_provider,
        llm_max_tokens=compression_config.compressor_llm_max_tokens,
    )
    tool_registry = build_default_registry()
    skills_manager = build_skills_manager(skill_paths or [], validate=False)
    skill_prompt = skills_manager.get_system_prompt_snippet()
    if skills_manager.get_skill_names():
        register_tool_functions(tool_registry, skills_manager.get_tools())
    return AgentRuntime(
        model_provider=model_provider,
        tool_registry=tool_registry,
        system_prompt=system_prompt,
        max_steps=max_steps,
        memory_store=SQLiteMemoryStore(
            db_file="db/runtime_memory_cli.db",
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
        ),
        skill_prompt=skill_prompt,
        generation_config=generation_config,
        enable_llm_judge=enable_llm_judge,
        compression_config=compression_config,
    )
