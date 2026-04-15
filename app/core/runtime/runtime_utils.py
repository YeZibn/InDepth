import json
import re
from typing import Any, Dict, List


def parse_json_dict(text: str) -> Dict[str, Any]:
    raw = (text or "").strip()
    if not raw:
        return {}
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        pass
    match = re.search(r"\{[\s\S]*\}", raw)
    if not match:
        return {}
    try:
        data = json.loads(match.group(0))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def preview(text: str, max_len: int = 120) -> str:
    value = (text or "").replace("\n", " ").strip()
    if len(value) <= max_len:
        return value
    return value[:max_len] + "..."


def preview_json(obj: Any, max_len: int = 200) -> str:
    try:
        text = json.dumps(obj, ensure_ascii=False)
    except Exception:
        text = str(obj)
    return preview(text, max_len=max_len)


def estimate_context_tokens(messages: List[Dict[str, Any]]) -> int:
    # Hybrid estimator: CJK chars ~= 1 token, latin words ~= 1 token, plus JSON overhead.
    tokens = 0
    for msg in messages:
        content = str(msg.get("content", "") or "")
        cjk_count = len(re.findall(r"[\u4e00-\u9fff]", content))
        latin_words = len(re.findall(r"[A-Za-z0-9_]+", content))
        punctuation = len(re.findall(r"[^\w\s]", content))
        tokens += cjk_count + latin_words + max(punctuation // 2, 0) + 8  # per-message envelope
        if msg.get("tool_calls"):
            try:
                tokens += len(json.dumps(msg.get("tool_calls"), ensure_ascii=False)) // 4
            except Exception:
                tokens += 20
    return max(tokens, 1)


def estimate_context_usage(estimated_tokens: int, context_window_tokens: int) -> float:
    window = max(int(context_window_tokens), 1024)
    return min(estimated_tokens / window, 1.0)


def is_clarification_request(content: str) -> bool:
    text = (content or "").strip()
    if not text:
        return False
    lowered = text.lower()
    clarification_hints = [
        "请确认",
        "请补充",
        "请提供",
        "请明确",
        "你是指",
        "是否",
        "能否",
        "which",
        "what exactly",
        "can you clarify",
        "please clarify",
        "need more details",
    ]
    if any(hint in lowered for hint in clarification_hints):
        return True
    if "？" in text or "?" in text:
        complete_hints = ["已完成", "完成了", "done", "completed", "success", "成功"]
        if not any(hint in lowered for hint in complete_hints):
            return True
    return False


def extract_missing_info_hints(content: str) -> List[str]:
    text = (content or "").strip()
    if not text:
        return []
    fields = [
        ("时间", ["时间", "日期", "截止", "deadline", "when"]),
        ("范围", ["范围", "边界", "scope"]),
        ("目标", ["目标", "预期", "goal", "outcome"]),
        ("环境", ["环境", "分支", "workspace", "repo"]),
        ("验收标准", ["验收", "标准", "acceptance", "criteria"]),
    ]
    lowered = text.lower()
    hits: List[str] = []
    for label, hints in fields:
        if any(h in lowered for h in hints):
            hits.append(label)
    return hits


def extract_finish_reason_and_message(raw: Dict[str, Any]) -> tuple[str, Dict[str, Any]]:
    if not isinstance(raw, dict):
        return "", {}
    choices = raw.get("choices", [])
    if not isinstance(choices, list) or not choices:
        return "", {}
    choice0 = choices[0] if isinstance(choices[0], dict) else {}
    finish_reason = str(choice0.get("finish_reason", "") or "").strip()
    message = choice0.get("message", {})
    if not isinstance(message, dict):
        message = {}
    return finish_reason, message


def slug(value: str) -> str:
    text = (value or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text or "na"
