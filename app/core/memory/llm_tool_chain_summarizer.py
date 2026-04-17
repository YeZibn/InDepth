import json
import re
from typing import Any, Dict, List, Optional

from app.config import load_runtime_model_config
from app.core.model.base import GenerationConfig, ModelProvider


def build_tool_chain_replace_config(max_tokens: int) -> GenerationConfig:
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
        max_tokens=max(int(max_tokens), 120),
        provider_options=options,
    )


def summarize_tool_chain_payload(
    payload: Dict[str, Any],
    model_provider: Optional[ModelProvider],
    kind: str,
    max_tokens: int,
) -> Dict[str, Any]:
    kind_norm = str(kind or "auto").strip().lower()
    if kind_norm == "rule":
        return _fallback_result(reason="", requested="rule")
    if model_provider is None:
        return _fallback_result(reason="missing_model_provider", requested=kind_norm or "auto")
    if kind_norm == "auto" and model_provider.__class__.__name__ == "MockModelProvider":
        return _fallback_result(reason="mock_provider_auto_rule", requested="auto")

    try:
        messages = _build_messages(payload)
        config = build_tool_chain_replace_config(max_tokens=max_tokens)
        output = model_provider.generate(messages=messages, tools=[], config=config)
        parsed = _parse_json_object(str(output.content or ""))
        summary = str(parsed.get("summary", "") or "").strip()
        key_results = _normalize_string_list(parsed.get("key_results"), limit=3, item_limit=180)
        failures = _normalize_string_list(parsed.get("failures"), limit=3, item_limit=160)
        if not summary:
            raise ValueError("empty_summary")
        model_name = str((config.provider_options or {}).get("model", "") or "").strip()
        return {
            "summary": _clean_line(summary, 220),
            "key_results": key_results,
            "failures": failures,
            "meta": {
                "tool_chain_summary_requested": "llm",
                "tool_chain_summary_applied": "llm",
                "tool_chain_summary_fallback_used": False,
                "tool_chain_summary_fallback_reason": "",
                "tool_chain_summary_model": model_name or "default",
            },
        }
    except Exception as e:
        return _fallback_result(
            reason=f"llm_error:{str(e).strip()[:120]}",
            requested="llm" if kind_norm == "llm" else "auto",
        )


def _build_messages(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    user_payload = {
        "task": "Summarize this compressed runtime tool chain for future context injection.",
        "output_schema": {
            "summary": "One concise sentence about what the tool chain did and what happened.",
            "key_results": ["Up to 3 high-signal results."],
            "failures": ["Up to 3 concrete failure snippets, empty when none."],
        },
        "rules": [
            "Return a single JSON object only.",
            "Do not invent files, ids, tools, outputs, or conclusions not present in the input.",
            "Prefer execution outcomes over restating tool names.",
            "Keep summary concise and useful for the next runtime step.",
            "If there are no failures, return an empty failures array.",
        ],
        "tool_chain": payload,
    }
    return [
        {
            "role": "system",
            "content": (
                "You summarize runtime tool chains for compact memory replacement. "
                "Return only valid JSON matching the requested schema."
            ),
        },
        {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
    ]


def _parse_json_object(text: str) -> Dict[str, Any]:
    raw = str(text or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end >= start:
        raw = raw[start : end + 1]
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("invalid_json_object")
    return parsed


def _normalize_string_list(value: Any, limit: int, item_limit: int) -> List[str]:
    out: List[str] = []
    for item in value or []:
        text = _clean_line(str(item or "").strip(), item_limit)
        if text:
            out.append(text)
        if len(out) >= limit:
            break
    return out


def _clean_line(text: str, limit: int) -> str:
    flat = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(flat) <= limit:
        return flat
    return flat[:limit] + "..."


def _fallback_result(reason: str, requested: str) -> Dict[str, Any]:
    return {
        "summary": "",
        "key_results": [],
        "failures": [],
        "meta": {
            "tool_chain_summary_requested": requested or "auto",
            "tool_chain_summary_applied": "rule",
            "tool_chain_summary_fallback_used": True,
            "tool_chain_summary_fallback_reason": reason,
            "tool_chain_summary_model": "",
        },
    }
