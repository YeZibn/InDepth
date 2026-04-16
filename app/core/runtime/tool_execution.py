import json
from typing import Any, Callable, Dict, List

from app.core.memory.base import MemoryStore
from app.core.tools.registry import ToolRegistry


def handle_native_tool_calls(
    tool_calls: List[Dict[str, Any]],
    messages: List[Dict[str, Any]],
    task_id: str,
    run_id: str,
    tool_registry: ToolRegistry,
    memory_store: MemoryStore | None,
    enrich_capture_memory_tool_args: Callable[[str, Dict[str, Any], str, str], Dict[str, Any]],
    emit_event: Callable[..., Dict[str, Any]],
    trace: Callable[[str], None],
    preview_json: Callable[[Any, int], str],
) -> Dict[str, Any]:
    failures: List[Dict[str, str]] = []
    executions: List[Dict[str, Any]] = []
    for call in tool_calls:
        call_id = str(call.get("id", ""))
        fn = call.get("function", {}) if isinstance(call, dict) else {}
        tool_name = str(fn.get("name", "")).strip()
        raw_args = fn.get("arguments", "{}")
        try:
            tool_args = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
            if not isinstance(tool_args, dict):
                tool_args = {}
        except Exception:
            tool_args = {}
        tool_args = enrich_capture_memory_tool_args(
            tool_name=tool_name,
            tool_args=tool_args,
            task_id=task_id,
            run_id=run_id,
        )
        emit_event(
            task_id=task_id,
            run_id=run_id,
            actor="main",
            role="general",
            event_type="tool_called",
            payload={"tool": tool_name, "args": tool_args},
        )
        result = tool_registry.invoke(tool_name, tool_args)
        tool_payload = result.get("result") if result.get("success") else result.get("result", {})
        trace(
            f"[tool] name={tool_name} args={preview_json(tool_args, 200)} "
            f"success={result.get('success')} result={preview_json(result, 200)}"
        )
        event_type = "tool_succeeded" if result.get("success") else "tool_failed"
        if not result.get("success"):
            failures.append(
                {
                    "tool": tool_name,
                    "error": str(result.get("error", "")).strip(),
                }
            )
        emit_event(
            task_id=task_id,
            run_id=run_id,
            actor="main",
            role="general",
            event_type=event_type,
            status="ok" if result.get("success") else "error",
            payload={"tool": tool_name, "error": str(result.get("error", "")) if not result.get("success") else ""},
        )
        messages.append(
            {
                "role": "tool",
                "tool_call_id": call_id,
                "content": json.dumps(result, ensure_ascii=False),
            }
        )
        if memory_store:
            memory_store.append_message(
                task_id,
                "tool",
                json.dumps(result, ensure_ascii=False),
                tool_call_id=call_id,
            )
        executions.append(
            {
                "tool": tool_name,
                "args": tool_args,
                "success": bool(result.get("success")),
                "error": str(result.get("error", "")),
                "payload": tool_payload if isinstance(tool_payload, dict) else {},
            }
        )
    return {"failures": failures, "executions": executions}


def enrich_capture_memory_tool_args(
    tool_name: str,
    tool_args: Dict[str, Any],
    task_id: str,
    run_id: str,
    enable_memory_card_metadata_llm: bool,
    extract_title_topic: Callable[[str], str],
    preview: Callable[[str, int], str],
    generate_memory_card_metadata_llm: Callable[..., Dict[str, str]],
) -> Dict[str, Any]:
    if tool_name != "capture_runtime_memory_candidate":
        return tool_args
    if not enable_memory_card_metadata_llm:
        return tool_args
    if not isinstance(tool_args, dict):
        return {}
    title = str(tool_args.get("title", "") or "").strip()
    observation = str(tool_args.get("observation", "") or "").strip()
    proposed_action = str(tool_args.get("proposed_action", "") or "").strip()
    if not any([title, observation, proposed_action]):
        return tool_args
    fallback_title = title or extract_title_topic(observation)
    fallback_recall_hint = preview(
        observation or proposed_action or title,
        200,
    )
    generated = generate_memory_card_metadata_llm(
        mode="capture",
        user_input=observation or title,
        runtime_status="runtime_capture",
        stop_reason="tool_capture",
        failure_brief="",
        answer_brief=proposed_action,
        fallback_title=fallback_title,
        fallback_recall_hint=fallback_recall_hint,
        task_id=task_id,
        run_id=run_id,
    )
    out = dict(tool_args)
    new_title = str(generated.get("title", "") or "").strip()
    new_recall_hint = str(generated.get("recall_hint", "") or "").strip()
    if new_title:
        out["title"] = new_title
    if new_recall_hint:
        out["recall_hint"] = new_recall_hint
    return out
