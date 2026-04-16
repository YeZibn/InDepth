import json
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
    path = os.path.join(base, task_seg)
    if run_id:
        run_seg = _sanitize_segment(run_id, "run")
        # When run_id equals task_id (common in todo flows), keep outputs at
        # task root to avoid redundant nested folders.
        if run_seg != task_seg:
            path = os.path.join(path, run_seg)
    os.makedirs(path, exist_ok=True)
    return path


def _task_root_dir(task_id: str) -> str:
    root = _find_project_root()
    base = os.path.join(root, "observability-evals")
    task_seg = _sanitize_segment(task_id, "task")
    path = os.path.join(base, task_seg)
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


def _find_latest_judgement_with_run(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    judged = [x for x in rows if x.get("event_type") == "task_judged"]
    if not judged:
        return {}
    latest = sorted(judged, key=lambda x: str(x.get("timestamp", "")))[-1]
    payload = latest.get("payload", {})
    if not isinstance(payload, dict):
        payload = {}
    return {
        "run_id": str(latest.get("run_id", "")).strip(),
        "timestamp": str(latest.get("timestamp", "")).strip(),
        "payload": payload,
    }


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


def _format_delivery_block(judgement: Dict[str, Any]) -> List[str]:
    if not judgement:
        return ["- 无可用交付信息（缺少 task_judged 结果）。"]
    handoff = judgement.get("verification_handoff", {})
    if not isinstance(handoff, dict):
        handoff = {}
    source = str(judgement.get("verification_handoff_source", "") or "").strip() or "unknown"
    lines = [f"- handoff 来源: {source}"]
    goal = str(handoff.get("goal", "") or "").strip()
    if goal:
        lines.append(f"- 任务目标: {goal}")

    claimed = handoff.get("claimed_done_items", [])
    if isinstance(claimed, list) and claimed:
        lines.append("- 交付完成项:")
        for idx, item in enumerate(claimed[:12], 1):
            text = str(item or "").strip()
            if text:
                lines.append(f"  {idx}. {text}")
    else:
        lines.append("- 交付完成项: (none)")

    artifacts = handoff.get("expected_artifacts", [])
    if isinstance(artifacts, list) and artifacts:
        lines.append("- 交付产物:")
        for idx, item in enumerate(artifacts[:20], 1):
            if not isinstance(item, dict):
                continue
            path = str(item.get("path", "") or "").strip()
            if not path:
                continue
            must_exist = bool(item.get("must_exist", True))
            non_empty = bool(item.get("non_empty", False))
            contains = str(item.get("contains", "") or "").strip()
            desc = f"path={path}; must_exist={must_exist}; non_empty={non_empty}"
            if contains:
                desc += f"; contains={contains}"
            lines.append(f"  {idx}. {desc}")
    else:
        lines.append("- 交付产物: (none)")

    gaps = handoff.get("known_gaps", [])
    if isinstance(gaps, list) and gaps:
        lines.append("- 已知缺口:")
        for idx, item in enumerate(gaps[:12], 1):
            text = str(item or "").strip()
            if text:
                lines.append(f"  {idx}. {text}")
    else:
        lines.append("- 已知缺口: (none)")
    recovery = handoff.get("recovery", {})
    if isinstance(recovery, dict) and recovery:
        lines.append("- 恢复信息:")
        todo_id = str(recovery.get("todo_id", "") or "").strip()
        subtask_number = recovery.get("subtask_number")
        if todo_id:
            lines.append(f"  - todo_id={todo_id}")
        if subtask_number not in (None, ""):
            lines.append(f"  - subtask_number={subtask_number}")
        fallback = recovery.get("fallback_record", {})
        if isinstance(fallback, dict) and fallback:
            state = str(fallback.get("state", "") or "").strip()
            reason = str(fallback.get("reason_code", "") or "").strip()
            detail = str(fallback.get("reason_detail", "") or "").strip()
            if state or reason or detail:
                lines.append(f"  - fallback={state or 'unknown'} / {reason or 'n/a'} / {detail or 'n/a'}")
        decision = recovery.get("recovery_decision", {})
        if isinstance(decision, dict) and decision:
            action = str(decision.get("primary_action", "") or "").strip()
            level = str(decision.get("decision_level", "") or "").strip()
            rationale = str(decision.get("rationale", "") or "").strip()
            if action or level:
                lines.append(f"  - decision={action or 'n/a'} / level={level or 'n/a'}")
            if rationale:
                lines.append(f"  - rationale={rationale}")
    return lines


def _write_json(path: str, payload: Dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, sort_keys=True)


def _write_run_events(path: str, rows: List[Dict[str, Any]]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _write_judgement_history(path: str, rows: List[Dict[str, Any]]) -> None:
    judged_rows = [
        x
        for x in sorted(rows, key=lambda r: str(r.get("timestamp", "")))
        if x.get("event_type") == "task_judged"
    ]
    with open(path, "w", encoding="utf-8") as f:
        for row in judged_rows:
            payload = row.get("payload", {})
            if not isinstance(payload, dict):
                payload = {}
            item = {
                "event_id": str(row.get("event_id", "")).strip(),
                "task_id": str(row.get("task_id", "")).strip(),
                "run_id": str(row.get("run_id", "")).strip(),
                "timestamp": str(row.get("timestamp", "")).strip(),
                "status": str(row.get("status", "")).strip(),
                "judgement": payload,
            }
            f.write(json.dumps(item, ensure_ascii=False) + "\n")


def _build_task_summary(task_id: str, rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    runs: Dict[str, Dict[str, Any]] = {}
    sorted_rows = sorted(rows, key=lambda x: str(x.get("timestamp", "")))
    for row in sorted_rows:
        run_id = str(row.get("run_id", "")).strip() or "run"
        rec = runs.get(run_id)
        if rec is None:
            rec = {
                "run_id": run_id,
                "event_count": 0,
                "first_event_at": "",
                "last_event_at": "",
                "last_event_type": "",
                "last_status": "",
                "runtime_state": "",
                "has_final_judgement": False,
                "verification_skipped": False,
            }
            runs[run_id] = rec
        rec["event_count"] += 1
        ts = str(row.get("timestamp", "")).strip()
        if ts and not rec["first_event_at"]:
            rec["first_event_at"] = ts
        if ts:
            rec["last_event_at"] = ts
        rec["last_event_type"] = str(row.get("event_type", "")).strip()
        rec["last_status"] = str(row.get("status", "")).strip()
        payload = row.get("payload", {})
        if isinstance(payload, dict):
            state = str(payload.get("runtime_state", "")).strip()
            if state:
                rec["runtime_state"] = state
        if rec["last_event_type"] == "task_judged":
            rec["has_final_judgement"] = True
        if rec["last_event_type"] == "verification_skipped":
            rec["verification_skipped"] = True

    ordered_runs = sorted(runs.values(), key=lambda x: (x.get("first_event_at", ""), x.get("run_id", "")))
    latest_judgement = _find_latest_judgement_with_run(rows)
    return {
        "task_id": task_id,
        "updated_at": datetime.now().astimezone().isoformat(),
        "run_count": len(ordered_runs),
        "final_run_id": latest_judgement.get("run_id", ""),
        "runs": ordered_runs,
    }


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
        "## 4. 交付内容",
        *_format_delivery_block(judgement),
        "",
        "## 5. 关键时间线",
        _format_trace(trace_rows),
        "",
        "## 6. 失败与修复线索",
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
            "## 7. 改进建议（Top 3）",
            "1. 对失败率最高的 event_type 添加参数自检与自动重试。",
            "2. 将高频失败路径前置门禁（输入校验/依赖检查/预算检查）。",
            "3. 为关键链路增加更细粒度埋点，缩短问题定位时间。",
            "",
        ]
    )

    out_dir = output_dir or _default_postmortem_dir(task_id=task_id, run_id=run_id)
    out_path = os.path.join(out_dir, "postmortem.md")

    # Keep a single canonical postmortem file per task/run folder.
    # Clean up legacy timestamped snapshots when rewriting.
    try:
        for name in os.listdir(out_dir):
            if not name.startswith("postmortem_") or not name.endswith(".md"):
                continue
            legacy_path = os.path.join(out_dir, name)
            if os.path.isfile(legacy_path):
                os.remove(legacy_path)
    except Exception:
        pass

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    try:
        _write_run_events(os.path.join(out_dir, "events.jsonl"), rows)
    except Exception:
        pass

    try:
        run_judgement = _find_latest_judgement(rows)
        if run_judgement:
            _write_json(
                os.path.join(out_dir, "judgement.json"),
                {
                    "task_id": task_id,
                    "run_id": run_id or "",
                    "updated_at": datetime.now().astimezone().isoformat(),
                    "judgement": run_judgement,
                },
            )
    except Exception:
        pass

    try:
        task_root = _task_root_dir(task_id)
        all_task_rows = event_store.query(task_id=task_id)
        if not all_task_rows:
            all_task_rows = rows
        summary = _build_task_summary(task_id=task_id, rows=all_task_rows)
        _write_json(os.path.join(task_root, "task_summary.json"), summary)

        latest = _find_latest_judgement_with_run(all_task_rows)
        payload = latest.get("payload", {})
        if isinstance(payload, dict) and payload:
            _write_json(
                os.path.join(task_root, "task_judgement.json"),
                {
                    "task_id": task_id,
                    "final_run_id": latest.get("run_id", ""),
                    "judged_at": latest.get("timestamp", ""),
                    "judgement": payload,
                },
            )
        _write_judgement_history(
            os.path.join(task_root, "task_judgement_history.jsonl"),
            all_task_rows,
        )
    except Exception:
        pass

    return {
        "success": True,
        "task_id": task_id,
        "output_path": out_path,
        "metrics": metrics,
    }
