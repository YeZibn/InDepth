# InDepth Observability 参考

更新时间：2026-04-21

## 1. 目标

观测层提供三件事：
1. 过程可追溯：事件时间线
2. 结果可审计：`task_judged` + postmortem
3. 记忆链路可量化：memory event SQLite

当前观测主线围绕正常执行、todo 绑定、评估与收尾展开，不再把 recovery 作为独立观测子系统。

相关代码：
- `app/observability/schema.py`
- `app/observability/events.py`
- `app/observability/store.py`
- `app/observability/metrics.py`
- `app/observability/trace.py`
- `app/observability/postmortem.py`

## 2. 当前重要事件

### 2.1 任务级

- `task_started`
- `task_finished`
- `task_judged`
- `task_updated`
- `run_resumed`

### 2.2 模型与工具

- `model_request_started`
- `model_reasoning`
- `model_failed`
- `tool_called`
- `tool_succeeded`
- `tool_failed`

### 2.3 Todo

- `status_updated`
- `subtask_updated`
- `subtask_reopened`
- `followup_subtasks_appended`
- `todo_binding_missing_warning`

### 2.4 评估与收尾

- `verification_started`
- `verification_passed`
- `verification_failed`
- `verification_skipped`

### 2.5 其他

- Search Guard 相关事件
- memory 相关事件
- user preference 相关事件
- context compression 相关事件

## 3. 事件落点

### 3.1 JSONL

- 路径：`app/observability/data/events.jsonl`
- 所有事件都写入 JSONL
- append-only 模式

### 3.2 SQLite

仅 memory 事件会额外写入 `db/system_memory.db`。

## 4. postmortem 生成

postmortem 会在两个关键节点生成：
1. `task_finished`：生成初版 postmortem
2. `task_judged`：覆盖写最终版 postmortem

当前 postmortem 主要读取：
- 事件时间线
- verification handoff
- judgement 结果
- task/todo 相关快照

当前不再渲染 `handoff.recovery`。

## 5. 未知事件处理

若传入未知 `event_type`：
1. 会归一化为 `unknown_event_type`
2. 在 payload 里补 `_original_event_type`

这只应用于真正未建模的新事件，不应用来承载已知主链。

## 6. 相关代码

- `app/observability/schema.py`
- `app/observability/postmortem.py`
- `tests/test_observability_event_whitelist.py`
