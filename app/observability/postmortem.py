import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from .metrics import aggregate_task_metrics
from .store import EventStore, _find_project_root
from .trace import build_trace


def _default_postmortem_dir() -> str:
    root = _find_project_root()
    path = os.path.join(root, "work", "observability-postmortems")
    os.makedirs(path, exist_ok=True)
    return path


def _format_trace(trace_rows: List[Dict[str, Any]], max_rows: int = 40) -> str:
    lines = []
    for row in trace_rows[:max_rows]:
        lines.append(
            f"{row['step']}. [{row['timestamp']}] {row['event_type']} "
            f"(actor={row['actor']}, role={row['role']}, status={row['status']})"
        )
    if len(trace_rows) > max_rows:
        lines.append(f"... ({len(trace_rows) - max_rows} more events omitted)")
    return "\n".join(lines)


def generate_postmortem(
    task_id: str,
    run_id: Optional[str] = None,
    events: Optional[List[Dict[str, Any]]] = None,
    store: Optional[EventStore] = None,
    output_dir: Optional[str] = None,
) -> Dict[str, Any]:
    event_store = store or EventStore()
    rows = events if events is not None else event_store.query(task_id=task_id, run_id=run_id)
    if not rows:
        return {"success": False, "error": f"No events found for task_id={task_id}"}

    metrics = aggregate_task_metrics(rows)
    trace_rows = build_trace(rows)

    failed = [e for e in rows if e.get("status") == "error"]
    top_failures = failed[:5]

    lines = [
        f"# Postmortem: {task_id}",
        "",
        "## 1. 执行摘要",
        f"- 事件总数: {metrics['event_count']}",
        f"- 总耗时(秒): {metrics['duration_seconds']}",
        f"- 成功事件数: {metrics['success_count']}",
        f"- 失败事件数: {metrics['failure_count']}",
        "",
        "## 2. 工具与子代理指标",
        f"- 工具调用次数: {metrics['tool_called_count']}",
        f"- 工具失败次数: {metrics['tool_failed_count']}",
        f"- 子代理启动次数: {metrics['subagent_started_count']}",
        f"- 子代理失败次数: {metrics['subagent_failed_count']}",
        "",
        "## 3. 关键时间线",
        _format_trace(trace_rows),
        "",
        "## 4. 失败与修复线索",
    ]

    if not top_failures:
        lines.append("- 本次未记录到 error 级事件。")
    else:
        for idx, e in enumerate(top_failures, 1):
            lines.append(
                f"{idx}. {e.get('event_type')} | actor={e.get('actor')} | role={e.get('role')} | payload={e.get('payload', {})}"
            )

    lines.extend(
        [
            "",
            "## 5. 改进建议（Top 3）",
            "1. 对失败率最高的 event_type 添加参数自检与自动重试。",
            "2. 将高频失败路径前置门禁（输入校验/依赖检查/预算检查）。",
            "3. 为关键链路增加更细粒度埋点，缩短问题定位时间。",
            "",
        ]
    )

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = output_dir or _default_postmortem_dir()
    out_path = os.path.join(out_dir, f"postmortem_{task_id}_{ts}.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return {
        "success": True,
        "task_id": task_id,
        "output_path": out_path,
        "metrics": metrics,
    }

