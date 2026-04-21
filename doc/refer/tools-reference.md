# InDepth Tools 参考

更新时间：2026-04-21

## 1. 模块范围

工具体系负责把原子能力封装为 Agent 可调用函数，是 Runtime 推进行为、同步 todo 上下文和沉淀执行证据的桥梁。

当前工具层主要承担三类职责：
1. 提供原子执行能力，例如读写文件、bash、时间、todo、search、memory
2. 作为 Runtime 状态机输入，驱动 active todo context 与 subtask 状态流转
3. 作为 observability 事件来源，沉淀过程证据

当前已经不再把 fallback/recovery 作为工具层主链。

## 2. 工具框架分层

相关代码：
- `app/core/tools/decorator.py`
- `app/core/tools/registry.py`
- `app/core/tools/validator.py`
- `app/core/tools/adapters.py`
- `app/tool/*`

调用流程：
1. 模型返回 `tool_calls`
2. Runtime 发出 `tool_called`
3. `ToolRegistry.invoke(name, args)` 做查找、校验、执行
4. Runtime 发出 `tool_succeeded` 或 `tool_failed`
5. 结果回写为 `role="tool"` 消息

## 3. 默认工具分类

### 3.1 基础执行

- `bash`
- `read_file`
- `write_file`
- `get_current_time`

### 3.2 Search Guard

- `init_search_guard`
- `guarded_ddg_search`
- `update_search_progress`
- `build_search_conclusion`
- `get_search_guard_status`
- `request_search_budget_override`

### 3.3 SubAgent

- `create_sub_agent`
- `run_sub_agent`
- `run_sub_agents_parallel`
- `list_sub_agents`
- `get_sub_agent_info`
- `destroy_sub_agent`
- `destroy_all_sub_agents`

### 3.4 Todo

当前公开的 todo 工具为：
- `prepare_task`
- `plan_task`
- `update_task_status`
- `reopen_subtask`
- `update_subtask`
- `append_followup_subtasks`
- `list_tasks`
- `get_next_task`
- `get_task_progress`
- `generate_task_report`

### 3.5 Memory

- `search_memory_cards`
- `get_memory_card_by_id`

## 4. Todo 工具的当前职责

### 4.1 `prepare_task`

规则回退型 prepare 工具，用于：
1. 形成最小可执行计划
2. 判断是否应启用 todo
3. 在 active todo 存在时补充现状摘要

### 4.2 `plan_task`

当前唯一的对外 todo 落盘入口：
1. 校验结构化计划
2. 根据 `active_todo_id` 决定 create/update
3. 内部调用 `_create_todo_from_plan(...)` 或 `_update_todo_from_plan(...)`

### 4.3 `update_task_status`

标准状态迁移入口，负责：
- `pending -> in-progress`
- `in-progress -> completed`
- 显式写成 `blocked/failed/partial/awaiting_input/timed_out/abandoned`

### 4.4 `update_subtask`

补丁式字段更新入口，适合：
- 更新 `description`
- 更新 `owner`
- 更新 `acceptance_criteria`
- 调整依赖或优先级

### 4.5 `reopen_subtask`

把已有 subtask 重新拉回执行主线，并将其置为 `in-progress`。

### 4.6 `append_followup_subtasks`

向现有 todo 追加后续 subtasks。

它仍然可用于正常后续编排。

## 5. Runtime 与工具的关系

当前 Runtime 会把以下工具视为 todo 绑定相关工具：
- `plan_task`
- `update_task_status`
- `update_subtask`
- `reopen_subtask`
- `append_followup_subtasks`
- `get_next_task`
- `get_task_progress`
- `generate_task_report`

当 todo 已经建立、但普通执行工具调用尚未绑定 active subtask 时，Runtime 会发出 `todo_binding_missing_warning`。

## 6. 相关代码

- `app/core/tools/*`
- `app/tool/todo_tool/todo_tool.py`
- `app/core/runtime/agent_runtime.py`
- `app/core/runtime/todo_runtime_lifecycle.py`
