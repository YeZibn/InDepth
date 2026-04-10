# Observability Center (MVP)

该目录实现本地 Agent 的“观测与复盘中心”最小闭环：

1. 事件采集：`events.py`
2. 事件存储：`store.py`（JSONL + SQLite system memory events）
3. 指标聚合：`metrics.py`
4. 执行链路：`trace.py`
5. 复盘报告：`postmortem.py`

## 目录

- `schema.py`：事件结构与事件类型
- `events.py`：统一 `emit_event(...)` 接口
- `store.py`：事件落盘与查询
- `store.py::SystemMemoryEventStore`：`memory_triggered/retrieved/decision_made` 落库
- `metrics.py`：任务级指标聚合
- `trace.py`：时间线构建
- `postmortem.py`：生成 `observability-evals/<task_id>__<run_id>/postmortem_*.md`
- `data/events.jsonl`：默认事件存储文件（运行后自动生成）
- `db/runtime_memory_main_agent.db`：主 Agent 运行时记忆（按类型聚合）
- `db/runtime_memory_subagent_<role>.db`：SubAgent 运行时记忆（按角色聚合）
- `db/system_memory.db`：系统记忆事件 SQLite（运行后自动生成）
- `db/system_memory.db::memory_card`：结构化经验卡（由 `SystemMemoryStore` 维护）

## System Memory 接入点（阶段二）

- 运行中由 `memory-knowledge-skill` 触发候选记忆事件（`capture_runtime_memory_candidate`）
- 任务结束由 Runtime 框架触发强制沉淀事件

## 快速示例

```python
from app.observability.events import emit_event
from app.observability.postmortem import generate_postmortem

task_id = "demo_task_001"
run_id = "run_001"

emit_event(task_id, run_id, actor="main", role="general", event_type="task_started")
emit_event(task_id, run_id, actor="main", role="general", event_type="tool_called", payload={"tool": "create_task"})
emit_event(task_id, run_id, actor="main", role="general", event_type="tool_succeeded", payload={"tool": "create_task"})
emit_event(task_id, run_id, actor="main", role="general", event_type="task_finished")

result = generate_postmortem(task_id=task_id, run_id=run_id)
print(result["output_path"])
```
