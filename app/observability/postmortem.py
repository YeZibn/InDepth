import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from .metrics import aggregate_task_metrics
from .store import EventStore, _find_project_root
from .trace import build_trace


def _sanitize_segment(value: str, fallback: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return fallback
    sanitized = re.sub(r"[^A-Za-z0-9._-]+", "_", raw).strip("._")
    return sanitized or fallback


def _default_postmortem_dir(task_id: str, run_id: Optional[str] = None) -> str:
    root = _find_project_root()
    base = os.path.join(root, "observability-evals")
    task_seg = _sanitize_segment(task_id, "task")
    run_seg = _sanitize_segment(run_id or "", "run") if run_id else ""
    folder = f"{task_seg}__{run_seg}" if run_seg else task_seg
    path = os.path.join(base, folder)
    os.makedirs(path, exist_ok=True)
    return path


def _to_local_display(ts: Any) -> str:
    if not isinstance(ts, str) or not ts.strip():
        return "invalid-timestamp"
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.astimezone().isoformat()
    except Exception:
        return ts


def _format_trace(trace_rows: List[Dict[str, Any]], max_rows: int = 40) -> str:
    lines = []
    for row in trace_rows[:max_rows]:
        lines.append(
            f"{row['step']}. [{_to_local_display(row.get('timestamp'))}] {row['event_type']} "
            f"(actor={row['actor']}, role={row['role']}, status={row['status']})"
        )
    if len(trace_rows) > max_rows:
        lines.append(f"... ({len(trace_rows) - max_rows} more events omitted)")
    return "\n".join(lines)


def _find_latest_judgement(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    judged = [x for x in rows if x.get("event_type") == "task_judged"]
    if not judged:
        return {}
    judged_sorted = sorted(judged, key=lambda x: str(x.get("timestamp", "")))
    payload = judged_sorted[-1].get("payload", {})
    return payload if isinstance(payload, dict) else {}


def _summarize_failure_payload(event_type: str, payload: Dict[str, Any]) -> str:
    if not isinstance(payload, dict):
        return "{}"
    if event_type == "tool_failed":
        return f"tool={payload.get('tool', 'unknown')}"
    if event_type == "model_failed":
        return f"error={str(payload.get('error', ''))[:180]}"
    if event_type in {"verification_failed", "task_judged", "task_finished"}:
        return (
            f"final_status={payload.get('final_status')} "
            f"failure_type={payload.get('failure_type')} "
            f"verified_success={payload.get('verified_success')}"
        )
    compact = {k: payload.get(k) for k in list(payload.keys())[:3]}
    return str(compact)


def _format_judgement_block(judgement: Dict[str, Any]) -> List[str]:
    if not judgement:
        return ["- 本次未生成 task_judged 评估结果。"]
    lines = [
        f"- 自报成功: {judgement.get('self_reported_success')}",
        f"- 验证成功: {judgement.get('verified_success')}",
        f"- 最终判定: {judgement.get('final_status')}",
        f"- 失败类型: {judgement.get('failure_type')}",
        f"- 过度宣称(overclaim): {judgement.get('overclaim')}",
        f"- 置信度: {judgement.get('confidence')}",
    ]
    breakdown = judgement.get("verifier_breakdown", [])
    if isinstance(breakdown, list) and breakdown:
        lines.append("- 分项评估:")
        for idx, item in enumerate(breakdown, 1):
            if not isinstance(item, dict):
                continue
            lines.append(
                f"  {idx}. {item.get('verifier_name')} | passed={item.get('passed')} | "
                f"hard={item.get('hard')} | score={item.get('score')} | reason={item.get('reason')}"
            )
    return lines


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
    judgement = _find_latest_judgement(rows)

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
        "## 3. 评估结论",
        *_format_judgement_block(judgement),
        "",
        "## 4. 关键时间线",
        _format_trace(trace_rows),
        "",
        "## 5. 失败与修复线索",
    ]

    if not top_failures:
        lines.append("- 本次未记录到 error 级事件。")
    else:
        for idx, e in enumerate(top_failures, 1):
            payload = e.get("payload", {}) if isinstance(e.get("payload", {}), dict) else {}
            lines.append(
                f"{idx}. [{e.get('event_type')}] actor={e.get('actor')} role={e.get('role')} "
                f"summary={_summarize_failure_payload(str(e.get('event_type', '')), payload)}"
            )

    lines.extend(
        [
            "",
            "## 6. 改进建议（Top 3）",
            "1. 对失败率最高的 event_type 添加参数自检与自动重试。",
            "2. 将高频失败路径前置门禁（输入校验/依赖检查/预算检查）。",
            "3. 为关键链路增加更细粒度埋点，缩短问题定位时间。",
            "",
        ]
    )

    ts = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    out_dir = output_dir or _default_postmortem_dir(task_id=task_id, run_id=run_id)
    out_path = os.path.join(out_dir, f"postmortem_{ts}.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return {
        "success": True,
        "task_id": task_id,
        "output_path": out_path,
        "metrics": metrics,
    }
