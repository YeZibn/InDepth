import json
import re
from typing import Any, Callable, Dict, List

from app.config import load_runtime_model_config
from app.core.model.base import GenerationConfig, ModelProvider


# 这里放的是“记忆召回能力”本身：
# - 如何构造 recall query
# - 如何渲染 recall block
# - 如何做 rerank
# runtime 只负责决定何时触发这些能力，不负责实现细节。


def build_recall_query(user_input: str) -> str:
    base = f"{user_input}".lower()
    tokens = re.findall(r"[a-z0-9_\-\u4e00-\u9fff]+", base)
    stop = {
        "the",
        "a",
        "an",
        "and",
        "or",
        "to",
        "for",
        "of",
        "in",
        "on",
        "with",
        "请",
        "帮我",
        "一下",
        "麻烦",
        "需要",
        "现在",
        "这个",
        "那个",
        "进行",
        "完成",
    }
    out: List[str] = []
    for token in tokens:
        val = token.strip()
        if not val or len(val) <= 1:
            continue
        if val in stop:
            continue
        if val not in out:
            out.append(val)
        if len(out) >= 12:
            break
    return " ".join(out)


def render_memory_recall_block(cards: List[Dict[str, Any]], preview: Callable[[str, int], str]) -> str:
    if not cards:
        return ""
    lines: List[str] = ["系统记忆召回（轻注入：memory_id + recall_hint，最多5条）"]
    for idx, card in enumerate(cards, 1):
        memory_id = str(card.get("id", "") or "").strip()
        recall_hint = str(card.get("recall_hint", "") or "").strip()
        if not recall_hint:
            scenario = card.get("scenario", {}) if isinstance(card.get("scenario", {}), dict) else {}
            recall_hint = str(scenario.get("trigger_hint", "") or "").strip()
        if not memory_id:
            continue
        lines.append(f"{idx}. memory_id={memory_id}")
        if recall_hint:
            lines.append(f"   - recall_hint={preview(recall_hint, 200)}")
    return "\n".join(lines).strip()


def rerank_memory_candidates_llm(
    model_provider: ModelProvider,
    user_input: str,
    candidates: List[Dict[str, Any]],
    start_recall_candidate_pool: int,
    start_recall_top_k: int,
    build_memory_reranker_config: Callable[[], GenerationConfig],
    parse_json_dict: Callable[[str], Dict[str, Any]],
) -> List[Dict[str, Any]]:
    if not candidates:
        return []
    entries = []
    for card in candidates[:start_recall_candidate_pool]:
        cid = str(card.get("id", "")).strip()
        title = str(card.get("title", "")).strip()
        if not cid or not title:
            continue
        entries.append({"id": cid, "title": title})
    if not entries:
        return []

    prompt = {
        "task": "memory_recall_rerank",
        "instruction": (
            "Given user_input and memory card titles, return the most relevant cards. "
            "Match by semantic relevance only. Return strict JSON."
        ),
        "user_input": user_input,
        "top_k": start_recall_top_k,
        "candidates": entries,
        "output_schema": {"selected": [{"id": "memory_id", "score": "0~1 float", "reason": "short reason"}]},
    }
    try:
        output = model_provider.generate(
            messages=[
                {"role": "system", "content": "You are a precise memory recall ranker. Output JSON only."},
                {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
            ],
            tools=[],
            config=build_memory_reranker_config(),
        )
    except Exception:
        return []
    text = str(getattr(output, "content", "") or "").strip()
    parsed = parse_json_dict(text)
    if not isinstance(parsed, dict):
        return []
    selected = parsed.get("selected", [])
    if not isinstance(selected, list):
        return []
    out: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for item in selected:
        if not isinstance(item, dict):
            continue
        mid = str(item.get("id", "")).strip()
        if not mid or mid in seen:
            continue
        try:
            score = float(item.get("score", 0.0) or 0.0)
        except Exception:
            score = 0.0
        out.append(
            {
                "id": mid,
                "score": max(0.0, min(score, 1.0)),
                "reason": str(item.get("reason", "") or "").strip(),
            }
        )
        seen.add(mid)
        if len(out) >= start_recall_top_k:
            break
    out.sort(key=lambda x: x.get("score", 0.0), reverse=True)
    return out


def build_memory_reranker_config() -> GenerationConfig:
    options: Dict[str, Any] = {}
    try:
        model_cfg = load_runtime_model_config()
        mini_id = str(getattr(model_cfg, "mini_model_id", "") or "").strip()
        if mini_id:
            options["model"] = mini_id
    except Exception:
        pass
    return GenerationConfig(
        temperature=0.0,
        max_tokens=800,
        provider_options=options,
    )
