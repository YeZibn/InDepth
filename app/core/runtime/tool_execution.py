import json
from typing import Any, Callable, Dict, List

from app.core.memory.base import MemoryStore
from app.core.tools.registry import ToolRegistry


def handle_native_tool_calls(
    tool_calls: List[Dict[str, Any]],
    messages: List[Dict[str, Any]],
    task_id: str,
    run_id: str,
    step_id: str,
    tool_registry: ToolRegistry,
    memory_store: MemoryStore | None,
    enrich_runtime_tool_args: Callable[[str, Dict[str, Any], str, str, str], Dict[str, Any]],
    emit_event: Callable[..., Dict[str, Any]],
    trace: Callable[[str], None],
    preview_json: Callable[[Any, int], str],
) -> Dict[str, Any]:
    failures: List[Dict[str, str]] = []
    executions: List[Dict[str, Any]] = []
    appended_messages: List[Dict[str, Any]] = []
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
        tool_args = enrich_runtime_tool_args(
            tool_name=tool_name,
            tool_args=tool_args,
            task_id=task_id,
            run_id=run_id,
            step_id=step_id,
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
        tool_message = {
            "role": "tool",
            "tool_call_id": call_id,
            "content": json.dumps(result, ensure_ascii=False),
        }
        messages.append(tool_message)
        appended_messages.append(dict(tool_message))
        if memory_store:
            memory_store.append_message(
                task_id,
                "tool",
                json.dumps(result, ensure_ascii=False),
                tool_call_id=call_id,
                run_id=run_id,
                step_id=step_id,
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
    return {"failures": failures, "executions": executions, "appended_messages": appended_messages}


def enrich_runtime_tool_args(
    tool_name: str,
    tool_args: Dict[str, Any],
    task_id: str,
    run_id: str,
    step_id: str,
    enable_memory_card_metadata_llm: bool,
    memory_store_db_file: str,
    extract_title_topic: Callable[[str], str],
    preview: Callable[[str, int], str],
    generate_memory_card_metadata_llm: Callable[..., Dict[str, str]],
) -> Dict[str, Any]:
    if tool_name == "history_recall":
        out = dict(tool_args) if isinstance(tool_args, dict) else {}
        if not str(out.get("task_id", "") or "").strip():
            out["task_id"] = task_id
        if not str(out.get("run_id", "") or "").strip():
            out["run_id"] = run_id
        if not str(out.get("db_file", "") or "").strip() and memory_store_db_file:
            out["db_file"] = memory_store_db_file
        return out
    return tool_args
