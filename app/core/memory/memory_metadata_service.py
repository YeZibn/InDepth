import json
import re
from typing import Any, Callable, Dict

from app.config import load_runtime_model_config
from app.core.model.base import GenerationConfig, ModelProvider


# 这里放的是“记忆元数据能力”：
# - 记忆卡片 title / recall_hint 生成
# - 语义化 title 构造
# runtime 只负责在 run-start / run-end 这些时机调用它。


def generate_memory_card_metadata_llm(
    model_provider: ModelProvider,
    enabled: bool,
    build_memory_metadata_config: Callable[[], GenerationConfig],
    parse_json_dict: Callable[[str], Dict[str, Any]],
    preview: Callable[[str, int], str],
    mode: str,
    user_input: str,
    runtime_status: str,
    stop_reason: str,
    failure_brief: str,
    answer_brief: str,
    fallback_title: str,
    fallback_recall_hint: str,
    task_id: str = "",
    run_id: str = "",
) -> Dict[str, str]:
    if not enabled:
        return {}
    payload = {
        "task": "memory_card_metadata_generation",
        "instruction": (
            "Generate concise high-signal memory card metadata in Chinese. "
            "Return strict JSON only with fields: title, recall_hint. "
            "title should be stable and semantic, follow <问题对象/场景> + <关键动作/原则>, "
            "and no task_id/run_id/timestamp noise. "
            "recall_hint should follow: 问题; 适用条件; 建议动作; 风险提示."
        ),
        "mode": mode,
        "task_id": task_id,
        "run_id": run_id,
        "user_input": user_input,
        "runtime_status": runtime_status,
        "stop_reason": stop_reason,
        "failure_brief": failure_brief,
        "answer_brief": answer_brief,
        "fallback": {"title": fallback_title, "recall_hint": fallback_recall_hint},
        "constraints": {"title_max_len": 40, "recall_hint_max_len": 220},
        "output_schema": {"title": "string", "recall_hint": "string"},
    }
    try:
        output = model_provider.generate(
            messages=[
                {
                    "role": "system",
                    "content": "You generate memory metadata. Output JSON only.",
                },
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            tools=[],
            config=build_memory_metadata_config(),
        )
    except Exception:
        return {}
    parsed = parse_json_dict(str(getattr(output, "content", "") or ""))
    if not isinstance(parsed, dict):
        return {}
    title = preview(str(parsed.get("title", "") or "").strip(), 40)
    recall_hint = preview(str(parsed.get("recall_hint", "") or "").strip(), 220)
    if not title and not recall_hint:
        return {}
    return {"title": title, "recall_hint": recall_hint}


def build_memory_metadata_config() -> GenerationConfig:
    options: Dict[str, Any] = {}
    try:
        model_cfg = load_runtime_model_config()
        mini_id = str(getattr(model_cfg, "mini_model_id", "") or "").strip()
        if mini_id:
            options["model"] = mini_id
    except Exception:
        pass
    return GenerationConfig(
        temperature=0.1,
        max_tokens=400,
        provider_options=options,
    )


def build_semantic_memory_title(
    user_input: str,
    runtime_status: str,
    stop_reason: str,
    extract_title_topic: Callable[[str], str],
    preview: Callable[[str, int], str],
) -> str:
    topic = extract_title_topic(user_input=user_input)
    _ = stop_reason
    suffix = "复用策略" if runtime_status == "ok" else "排查与修复策略"
    raw = f"{topic}{suffix}"
    return preview(raw, 40)


def extract_title_topic(user_input: str, preview: Callable[[str, int], str]) -> str:
    text = (user_input or "").strip()
    if not text:
        return "任务执行"
    compact = re.sub(r"\s+", " ", text)
    return preview(compact, 40)
