# InDepth Runtime 参考

更新时间：2026-04-21

## 1. 定位

`AgentRuntime` 是当前系统的执行中枢，负责把一次用户输入组织成完整运行周期：
1. 恢复 task 上下文与 active todo context
2. 在首轮模型请求前强制执行 `prepare phase`
3. 依据 prepare 结果自动完成 todo create/update
4. 进入 executing phase 的模型-工具循环
5. 在 finalizing phase 完成 handoff、评估、记忆与 postmortem 收尾

当前 Runtime 主线已经简化为“正常执行 + handoff”，不再维护独立 recovery planner/fallback 主链。

## 2. 运行阶段

### 2.1 Preparing

prepare 是硬前置阶段，负责：
1. 判断本轮是否启用 todo
2. 若已有 active todo，则补充 `current_state_scan` 与 `current_state_summary`
3. 生成候选计划
4. 输出 CLI `[Prepare]` 摘要
5. 必要时自动调用 `plan_task`

当 `resume_from_waiting=True` 且存在 active todo 时，prepare 会先把旧计划中未完成的 subtasks 标记为 `abandoned`，然后继续追加新计划。

### 2.2 Executing

executing 阶段负责：
1. 组装 system prompt、history、user input
2. 调模型并解析 `finish_reason`
3. 处理 `tool_calls`
4. 回写 tool messages
5. 同步 active todo / active subtask 绑定

当前 system prompt 只注入阶段提示，不再拼接 retry/recovery 提示。

### 2.3 Finalizing

finalizing 阶段统一做：
1. 产出 final answer
2. 产出 structured verification handoff
3. 调用 verifier / eval orchestrator
4. 写 postmortem
5. 沉淀 task memory / system memory / user preference

当前 handoff schema 已不包含 `recovery` 字段。

## 3. 关键状态

### 3.1 运行级状态

- `last_runtime_state`
  - `idle / running / awaiting_user_input / completed / failed`
- `last_stop_reason`
- `last_task_id`
- `last_run_id`

### 3.2 Prepare 状态

- `_prepare_phase_completed`
- `_prepare_phase_result`

### 3.3 Todo 执行上下文

`_active_todo_context` 当前最重要的字段有：
- `todo_id`
- `active_subtask_id`
- `active_subtask_number`
- `execution_phase`
  - `planning / executing / finalizing`
- `binding_required`
- `binding_state`
  - `bound / closed`
- `todo_bound_at`

## 4. Prepare 输入事实

当前 prepare 使用的核心输入包括：
1. `user_input`
2. `active_todo_exists`
3. `active_todo_id`
4. `active_todo_full_text`
5. `current_state_scan`
6. `current_state_summary`
7. `active_subtask_number`
8. `execution_phase`
9. `resume_from_waiting`

## 5. Todo 绑定更新

Runtime 通过 `todo_runtime_lifecycle.py` 同步 active todo context。

当前会驱动上下文变化的主要动作：
- `plan_task`
- `update_task_status`
- `update_subtask`
- `reopen_subtask`
- `get_next_task`

当前没有专门的 recovery/fallback 生命周期分支。

## 6. Finalization 输出

finalizing handoff 的关键字段目前包括：
- `goal`
- `task_summary`
- `final_status`
- `constraints`
- `expected_artifacts`
- `key_evidence`
- `claimed_done_items`
- `key_tool_results`
- `known_gaps`
- `risks`
- `memory_seed`
- `self_confidence`
- `soft_score_threshold`
- `rubric`

## 7. 相关代码

- `app/core/runtime/agent_runtime.py`
- `app/core/runtime/runtime_finalization.py`
- `app/core/runtime/todo_runtime_lifecycle.py`
- `app/tool/todo_tool/todo_tool.py`
