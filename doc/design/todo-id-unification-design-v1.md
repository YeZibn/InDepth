# InDepth Todo ID Unification V1 设计稿

更新时间：2026-04-13  
状态：V1 已实现

## 1. 背景

当前系统里存在两套“task”语义：
1. Runtime 会话任务：`task_id`（如 `runtime_cli_task_xxx`）
2. Todo 任务实体：原先也命名为 `task_id`（如 `20260413_xxx`）

两者在观测与目录层面容易混淆，尤其当 Todo 事件也写入 `task_id/run_id` 字段时，排障与审计成本升高。

## 2. 目标

1. Todo 领域统一使用 `todo_id` 命名，避免与 Runtime `task_id` 语义冲突。
2. Todo 观测链路保持“单 todo 单 run”一致性，确保事件与复盘落在同一目录。
3. 对历史 Todo 文件保持读取兼容，避免一次性迁移成本。

## 3. 方案概述

### 3.1 Todo 工具接口统一为 `todo_id`

对外参数改造：
1. `update_task_status(todo_id, subtask_number, status)`
2. `get_next_task_item(todo_id)`
3. `get_task_progress(todo_id)`
4. `generate_task_report(todo_id)`

返回字段改造：
1. `create_task` 返回 `todo_id`（不再返回 `task_id`）
2. `list_tasks` 返回 `todo_id`（移除通用 `id` 字段）

### 3.2 文件元数据统一为 `Todo ID`

新建 Todo 文件写入：
1. `- **Todo ID**: <todo_id>`

读取兼容策略：
1. 优先读取 `Todo ID`
2. 若不存在，则回退读取旧字段 `ID`

### 3.3 观测 ID 规范

由于观测底层 schema 固定字段为 `task_id/run_id`，V1 采用“值域隔离”：
1. Todo 观测上报时，统一写入 `task_id = run_id = todo-id:<todo_id>`
2. 通过前缀 `todo-id:` 与 Runtime `task_id` 彻底隔离

目录落盘策略：
1. 当 `run_id == task_id` 时，复盘直接写到任务根目录，避免重复嵌套
2. 因而 Todo 观测文件集中在：`observability-evals/todo-id:<todo_id>/`

## 4. 变更清单

代码：
1. `app/tool/todo_tool/todo_tool.py`
2. `app/observability/postmortem.py`

测试：
1. `tests/test_todo_observability_id.py`
2. `tests/test_postmortem_output_layout.py`

文档/技能：
1. `doc/refer/tools-reference.md`
2. `app/skills/todo-skill/*`（历史实现；已于后续版本移除）

## 5. 兼容性与影响

### 5.1 兼容性

1. 旧 Todo 文件仍可被读取（`ID` 回退兼容）
2. 观测系统无需修改 schema（仍使用 `task_id/run_id` 字段）

### 5.2 影响

1. 调用 Todo 工具的代码需改用 `todo_id` 参数名
2. 依赖 `create_task` 返回 `task_id` 的调用方需同步调整
3. `list_tasks` 若读取 `id` 字段需切换为 `todo_id`

## 6. 验证

已通过的最小回归：
1. `tests/test_todo_observability_id.py`
2. `tests/test_postmortem_output_layout.py`

验证点：
1. Todo 观测 ID 前缀化正确
2. `task_id == run_id` 时复盘目录扁平化正确

## 7. 风险与后续

风险：
1. 外部调用方若未同步参数名，可能出现工具调用失败

后续建议：
1. 在 Runtime/system prompt 中明确 Todo 工具参数为 `todo_id`
2. 增加一条集成测试，覆盖 `create_task -> update_task_status -> postmortem` 全链路
