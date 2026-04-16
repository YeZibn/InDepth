from typing import Any, Callable, Dict, List

from app.config import RuntimeUserPreferenceConfig, load_runtime_model_config
from app.core.memory.user_preference_store import UserPreferenceStore
from app.core.model.base import GenerationConfig, ModelProvider


USER_PREFERENCE_EXTRACT_SYSTEM_PROMPT = """你是用户偏好抽取器，只能输出 JSON。
目标：从用户输入中提取“明确表达”的偏好，不要猜测。

输出格式：
{
  "updates": [
    {
      "key": "job_role|domain_expertise|interest_topics|language_preference|response_style|tooling_stack|goal_long_term",
      "value": "string 或 string数组",
      "confidence": 0.0,
      "explicit": true,
      "action": "upsert|delete|ignore",
      "evidence_span": "原文证据片段"
    }
  ]
}

规则：
1) 仅输出白名单 key，未知 key 不输出。
2) 只有用户明确表达时 explicit=true。
3) 不输出解释文本，只输出 JSON。
"""

USER_PREFERENCE_EXTRACT_USER_PROMPT_TEMPLATE = """请基于以下用户输入提取偏好更新：

用户输入：
{user_input}
"""


def inject_user_preference_recall(
    task_id: str,
    run_id: str,
    user_input: str,
    messages: List[Dict[str, Any]],
    store: UserPreferenceStore | None,
    cfg: RuntimeUserPreferenceConfig,
    emit_event: Callable[..., Dict[str, Any]],
) -> List[Dict[str, Any]]:
    if not cfg.enabled or store is None:
        return messages
    try:
        block = store.render_recall_block(
            user_input=user_input,
            top_k=cfg.recall_top_k,
            always_include_keys=list(cfg.always_include_keys),
            max_chars=cfg.max_inject_chars,
        )
    except Exception as e:
        emit_event(
            task_id=task_id,
            run_id=run_id,
            actor="main",
            role="general",
            event_type="user_preference_recall_failed",
            status="error",
            payload={"error": str(e)},
        )
        return messages
    if not block:
        emit_event(
            task_id=task_id,
            run_id=run_id,
            actor="main",
            role="general",
            event_type="user_preference_recall_succeeded",
            payload={"injected": False, "items": 0},
        )
        return messages
    out: List[Dict[str, Any]] = []
    inserted = False
    for msg in messages:
        if not inserted and str(msg.get("role", "")) == "user":
            out.append({"role": "system", "content": block})
            inserted = True
        out.append(msg)
    if not inserted:
        out.append({"role": "system", "content": block})
    emit_event(
        task_id=task_id,
        run_id=run_id,
        actor="main",
        role="general",
        event_type="user_preference_recall_succeeded",
        payload={"injected": True, "chars": len(block)},
    )
    return out


def capture_user_preferences(
    task_id: str,
    run_id: str,
    user_input: str,
    store: UserPreferenceStore | None,
    cfg: RuntimeUserPreferenceConfig,
    model_provider: ModelProvider,
    parse_json_dict: Callable[[str], Dict[str, Any]],
    preview: Callable[[str, int], str],
    emit_event: Callable[..., Dict[str, Any]],
) -> None:
    if not cfg.enabled or store is None:
        return
    try:
        raw_updates = extract_user_preferences_llm(
            task_id=task_id,
            run_id=run_id,
            user_input=user_input,
            cfg=cfg,
            model_provider=model_provider,
            parse_json_dict=parse_json_dict,
            emit_event=emit_event,
        )
        changed_keys, skipped = apply_user_preference_updates(
            updates=raw_updates,
            store=store,
            cfg=cfg,
            preview=preview,
        )
        emit_event(
            task_id=task_id,
            run_id=run_id,
            actor="main",
            role="general",
            event_type="user_preference_capture_succeeded",
            payload={
                "updated_keys": changed_keys,
                "updated_count": len(changed_keys),
                "skipped_count": len(skipped),
                "skipped_reasons": skipped[:8],
            },
        )
    except Exception as e:
        emit_event(
            task_id=task_id,
            run_id=run_id,
            actor="main",
            role="general",
            event_type="user_preference_capture_failed",
            status="error",
            payload={"error": str(e)},
        )


def extract_user_preferences_llm(
    task_id: str,
    run_id: str,
    user_input: str,
    cfg: RuntimeUserPreferenceConfig,
    model_provider: ModelProvider,
    parse_json_dict: Callable[[str], Dict[str, Any]],
    emit_event: Callable[..., Dict[str, Any]],
) -> List[Dict[str, Any]]:
    if not cfg.enable_llm_extract:
        return []
    emit_event(
        task_id=task_id,
        run_id=run_id,
        actor="main",
        role="general",
        event_type="user_preference_extract_started",
    )
    try:
        result = model_provider.generate(
            messages=[
                {"role": "system", "content": USER_PREFERENCE_EXTRACT_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": USER_PREFERENCE_EXTRACT_USER_PROMPT_TEMPLATE.format(user_input=user_input),
                },
            ],
            tools=[],
            config=build_user_preference_extract_config(),
        )
        parsed = parse_json_dict(result.content)
        updates = parsed.get("updates", []) if isinstance(parsed, dict) else []
        if not isinstance(updates, list):
            updates = []
        emit_event(
            task_id=task_id,
            run_id=run_id,
            actor="main",
            role="general",
            event_type="user_preference_extract_succeeded",
            payload={"candidate_count": len(updates)},
        )
        return [x for x in updates if isinstance(x, dict)]
    except Exception as e:
        emit_event(
            task_id=task_id,
            run_id=run_id,
            actor="main",
            role="general",
            event_type="user_preference_extract_failed",
            status="error",
            payload={"error": str(e)},
        )
        raise


def normalize_preference_value(value: Any) -> Any:
    if isinstance(value, list):
        items: List[str] = []
        for part in value:
            text = str(part or "").strip()
            if text and text not in items:
                items.append(text)
        return items[:10]
    return str(value or "").strip()


def is_sensitive_preference_value(value: Any) -> bool:
    text = str(value or "")
    if not text:
        return False
    digits = "".join([c for c in text if c.isdigit()])
    if len(digits) >= 11:
        return True
    lowered = text.lower()
    sensitive_tokens = ["身份证", "银行卡", "信用卡", "住址", "手机号", "password", "passwd"]
    return any(token in lowered for token in sensitive_tokens)


def value_changed(old_value: Any, new_value: Any) -> bool:
    if isinstance(old_value, list) or isinstance(new_value, list):
        old_list = old_value if isinstance(old_value, list) else [str(old_value or "").strip()]
        new_list = new_value if isinstance(new_value, list) else [str(new_value or "").strip()]
        old_norm = [str(x).strip() for x in old_list if str(x).strip()]
        new_norm = [str(x).strip() for x in new_list if str(x).strip()]
        return old_norm != new_norm
    return str(old_value or "").strip() != str(new_value or "").strip()


def apply_user_preference_updates(
    updates: List[Dict[str, Any]],
    store: UserPreferenceStore | None,
    cfg: RuntimeUserPreferenceConfig,
    preview: Callable[[str, int], str],
) -> tuple[List[str], List[str]]:
    if store is None:
        return [], ["store_unavailable"]
    allowed_keys = {
        "job_role",
        "domain_expertise",
        "interest_topics",
        "language_preference",
        "response_style",
        "tooling_stack",
        "goal_long_term",
    }
    existing = store.list_preferences()
    changed: List[str] = []
    skipped: List[str] = []

    for row in updates:
        key = str(row.get("key", "") or "").strip()
        action = str(row.get("action", "ignore") or "ignore").strip().lower()
        explicit = bool(row.get("explicit", False))
        evidence = str(row.get("evidence_span", "") or "").strip()
        try:
            confidence = float(row.get("confidence", 0.0) or 0.0)
        except Exception:
            confidence = 0.0

        if key not in allowed_keys:
            skipped.append(f"{key or 'unknown'}:key_not_allowed")
            continue
        if action not in {"upsert", "delete", "ignore"}:
            skipped.append(f"{key}:action_invalid")
            continue
        if action == "ignore":
            skipped.append(f"{key}:ignored")
            continue
        if not explicit:
            skipped.append(f"{key}:not_explicit")
            continue
        # 第一层门槛：只有“明确表达 + 置信度达标”的偏好，才允许自动写入。
        if confidence < cfg.auto_write_min_confidence:
            skipped.append(f"{key}:low_confidence")
            continue

        if action == "delete":
            store.delete_preference(key)
            changed.append(key)
            continue

        new_value = normalize_preference_value(row.get("value", ""))
        if (isinstance(new_value, list) and not new_value) or (not isinstance(new_value, list) and not new_value):
            skipped.append(f"{key}:empty_value")
            continue
        if is_sensitive_preference_value(new_value):
            skipped.append(f"{key}:sensitive_blocked")
            continue
        old_rec = existing.get(key, {}) if isinstance(existing.get(key), dict) else {}
        old_value = old_rec.get("value", "")
        has_existing = bool(str(old_value).strip()) or (isinstance(old_value, list) and bool(old_value))
        # 第二层门槛：如果要覆盖已有偏好，要求更高置信度，避免轻易把稳定偏好写坏。
        if has_existing and value_changed(old_value, new_value) and confidence < cfg.conflict_min_confidence:
            skipped.append(f"{key}:conflict_low_confidence")
            continue
        store.upsert_preference(
            key=key,
            value=new_value,
            source="llm_extract_v1",
            confidence=confidence,
            note=f"evidence={preview(evidence, max_len=120)}" if evidence else "",
        )
        changed.append(key)

    return changed, skipped


def build_user_preference_extract_config() -> GenerationConfig:
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
        max_tokens=700,
        provider_options=options,
    )
