# InDepth Subtask 执行选择与基础状态更新参考

更新时间：2026-04-21

## 1. 目标

这份文档只聚焦三件事：
1. 当前实现如何判断“现在应该执行哪个 subtask”
2. 当前支持哪些 subtask 状态
3. 三种基础更新动作各自负责什么

## 2. 当前应该执行哪个 Subtask

### 2.1 工具层判断：`get_next_task`

当前真正负责“找下一个可执行 subtask”的入口是：
- `get_next_task(todo_id)`

内部规则很简单：
1. 先收集所有 `completed` subtasks
2. 按 todo 文件里的顺序从前往后扫描
3. 只看状态属于 `READY_SUBTASK_STATUSES` 的 subtasks
4. 当前 `READY_SUBTASK_STATUSES` 只有 `pending`
5. 若这个 `pending` subtask 的依赖都已完成，就返回它
6. 找到第一个满足条件的就停止

当前语义不是“找最优任务”，而是“按既有顺序找第一个依赖闭合的 pending subtask”。

### 2.2 `get_next_task` 的主要返回

1. `status="ready"`
   - 返回当前可执行 subtask
2. `status="all_completed"`
   - 表示所有 subtasks 都已进入终态
3. `status="blocked"`
   - 表示没有 ready subtask

## 3. 当前支持的状态

当前允许的 subtask 状态共有 9 个：
- `pending`
- `in-progress`
- `completed`
- `blocked`
- `failed`
- `partial`
- `awaiting_input`
- `timed_out`
- `abandoned`

### 3.1 Ready 状态

当前只有一个真正会被 `get_next_task` 直接选中的 ready 状态：
- `pending`

### 3.2 终态

当前 terminal 状态为：
- `completed`
- `abandoned`

这也意味着 progress 统计按这两个状态计数。

### 3.3 会让 todo 保持 active 的状态

这些状态会让整体 todo 继续保持 active/in-progress 语义：
- `in-progress`
- `blocked`
- `failed`
- `partial`
- `awaiting_input`
- `timed_out`

## 4. 三种基础更新动作

### 4.1 `update_task_status`

标准状态迁移入口，适合：
- `pending -> in-progress`
- `in-progress -> completed`
- 显式写成 `blocked/failed/partial/awaiting_input/timed_out/abandoned`

依赖检查当前会应用在：
- `in-progress`
- `completed`
- `partial`

### 4.2 `update_subtask`

补丁式字段更新入口，适合：
- 更新 `name/description`
- 更新 `owner`
- 更新 `acceptance_criteria`
- 调整 `priority/dependencies`

它也能改 `status`，但语义上更适合字段级补丁，而不是主状态迁移。

### 4.3 `reopen_subtask`

把已有 subtask 重新标记为 `in-progress`，并同步刷新 active todo context。

适合：
1. 已完成任务需要重开
2. 已失败/阻塞任务重新进入执行
3. 当前主线需要重新挂回已有 subtask

## 5. Runtime 上下文联动

当前会驱动 active todo context 的主要动作有：
- `plan_task`
- `update_task_status`
- `update_subtask`
- `reopen_subtask`
- `get_next_task`

当前不再通过 fallback/recovery 专用字段驱动执行上下文。

## 6. 相关代码

- `app/tool/todo_tool/todo_tool.py`
- `app/core/runtime/todo_runtime_lifecycle.py`
- `app/core/runtime/agent_runtime.py`
