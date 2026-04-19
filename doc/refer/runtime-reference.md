# InDepth Runtime 参考

更新时间：2026-04-19

## 1. 定位

`AgentRuntime`（[agent_runtime.py](/Users/yezibin/Project/InDepth/app/core/runtime/agent_runtime.py)）是当前系统的执行中枢。它不只是“调模型 + 调工具”，而是负责把一次用户输入组织成一个完整的运行周期：

1. 恢复当前 task 的上下文
2. 在首轮模型请求前强制执行 `prepare phase`
3. 依据 prepare 结果自动完成 todo create/update
4. 进入多步工具循环
5. 处理澄清暂停、失败恢复、评估、记忆收尾和观测落盘

如果只记一条主线，当前 Runtime 的整体流程是：

1. 载入 history、用户偏好和系统记忆
2. 恢复 active todo context
3. 执行 prepare phase，并补充基础现状扫描
4. 必要时自动调用 `plan_task`
5. 进入 executing phase，开始模型-工具循环
6. 根据 `finish_reason` 收敛为完成、等待输入或失败
7. 若存在未闭环 todo，则自动补 fallback / recovery
8. 统一进入 finalizing phase，完成 verification、memory、postmortem 和事件收尾

## 2. Runtime 的几层职责

可以把 Runtime 理解成五层连续职责：

1. 上下文装配
   - system prompt
   - history
   - user preference recall
   - system memory recall
   - active todo context

2. 前置规划
   - `prepare_task`
   - prepare result
   - prepare CLI summary
   - auto-apply `plan_task`

3. 执行循环
   - 调模型
   - 处理 `tool_calls`
   - 回写 tool messages
   - 维护 active todo / active subtask 绑定

4. 失败与暂停处理
   - clarification judge
   - awaiting user input
   - fallback record
   - recovery decision

5. 结束收尾
   - verification handoff
   - task judgement
   - postmortem
   - runtime/system/user preference memory finalize

## 3. 核心状态

Runtime 当前维护几组关键状态。

### 3.1 运行级状态

- `last_runtime_state`
  - `idle / running / awaiting_user_input / completed / failed`
- `last_stop_reason`
  - 记录本轮结束原因
- `last_task_id`
- `last_run_id`

### 3.2 Prepare 状态

- `_prepare_phase_completed`
  - 当前 run 是否已完成 prepare
- `_prepare_phase_result`
  - prepare 的结构化结果，供 guard、auto-apply 和提示词注入复用

### 3.3 Todo 执行上下文

`_active_todo_context` 由 [todo_runtime_lifecycle.py](/Users/yezibin/Project/InDepth/app/core/runtime/todo_runtime_lifecycle.py) 维护，当前最重要的字段有：

- `todo_id`
- `active_subtask_id`
- `active_subtask_number`
- `execution_phase`
  - `planning / executing / recovering / finalizing`
- `binding_required`
- `binding_state`
  - `bound / closed`
- `todo_bound_at`
- `active_retry_guidance`

### 3.4 最近恢复结果

- `_latest_todo_recovery`
  - 保存最近一次自动 recovery 的摘要，便于后续输出给用户和 handoff

## 4. 运行入口

Runtime 的入口方法是：

```python
def run(
    self,
    user_input: str,
    task_id: str = "runtime_task",
    run_id: str = "runtime_run",
    resume_from_waiting: bool = False,
) -> str:
```

其中：

- `task_id`
  - 代表当前任务容器
- `run_id`
  - 代表当前这次运行
- `resume_from_waiting`
  - 用户是否是在接续上一次“等待澄清”的 run

当前设计里，若上一次 run 因澄清进入 `awaiting_user_input`，后续用户回复会沿用同一个 `run_id` 恢复。

## 5. 完整执行流程

## 5.1 运行前恢复

在第一次模型请求前，Runtime 会先做这些事情：

1. 清空上轮残留的 `_latest_todo_recovery`
2. 重置 `_prepare_phase_completed` / `_prepare_phase_result`
3. 从 `memory_store` 读取最近消息
4. 用 `restore_active_todo_context_from_history(...)` 从历史工具执行恢复 todo 绑定
5. 组装基础消息：
   - system
   - history
   - current user input
6. 注入用户偏好 recall
7. 注入系统经验记忆 recall

到这一步为止，还没开始首轮模型请求。

## 5.2 Prepare Phase

prepare phase 是当前 Runtime 的硬前置步骤。

### 做什么

prepare phase 当前负责：

1. 判断本轮是否应使用 todo
2. 若已有 active todo，则读取其当前现状
3. 形成候选计划
4. 生成 prepare CLI summary
5. 必要时自动调用 `plan_task`

### 当前现状扫描

这是当前最新行为之一。

当 active todo 存在时，Runtime 会在 prepare 前调用 [todo_tool.py](/Users/yezibin/Project/InDepth/app/tool/todo_tool/todo_tool.py) 里的 `_build_current_state_scan(...)`，得到：

1. `progress`
2. `completed_subtasks`
3. `unfinished_subtasks`
4. `ready_subtasks`
5. `known_artifacts`
6. `summary`

这份扫描结果会通过两条路径进入 prepare：

1. rule fallback prepare
2. LLM prepare payload

因此现在的 prepare 不只是知道“有没有 active todo”，还知道“当前 todo 已做到哪里”。

### Prepare 的两条实现路径

当前有两条 prepare 路径：

1. LLM 路径
   - `_run_prepare_phase_llm`
   - 由 mini model 读取结构化输入后直接输出 JSON

2. 规则回退路径
   - `_run_prepare_phase_rule_fallback`
   - 调用隐藏工具 `prepare_task`

无论走哪条路径，prepare 的结果都会规范化成：

- `should_use_todo`
- `task_name`
- `context`
- `split_reason`
- `subtasks`
- `active_todo_id`
- `active_todo_summary`
- `current_state_scan`
- `current_state_summary`
- `notes`
- `recommended_plan_task_args`

### Prepare 的用户可见输出

prepare 完成后，Runtime 会向两个方向输出结果：

1. system-visible prepare message
   - 注入后续模型上下文
2. CLI 可见 `[Prepare]` 摘要
   - 打印给用户

当前 CLI 摘要通常包含：

1. 任务目标
2. todo 决策
3. 下一阶段
4. 拆分理由
5. 计划摘要
6. 当前现状（仅 active todo 存在时）
7. 计划明细

## 5.3 Prepare Auto Apply

若 prepare 结果已经形成成熟计划，Runtime 会在首轮模型请求前自动调用 `plan_task`。

当前策略是：

1. `should_use_todo=False`
   - 不自动落盘

2. `should_use_todo=True` 且无 active todo
   - `plan_task` 走 `create`

3. `should_use_todo=True` 且有 active todo
   - `plan_task` 走 `update`

这里不要求模型自己再决定 create/update，Runtime 会直接把 `active_todo_id` 带进去。

## 5.4 进入 Executing Phase

prepare 结束并且 auto-apply 完成后，Runtime：

1. 把 phase 切换为 `executing`
2. 刷新首条 system message，使其反映当前 phase
3. 若本轮是 `resume_from_waiting=True`
   - 发送 `user_clarification_received`
   - 发送 `run_resumed`
4. 否则发送 `task_started`

然后正式进入主循环。

## 5.5 主循环

主循环的每一轮大致是：

1. 构造 step seed messages
2. 列出当前工具 schema
3. 必要时执行 mid-run compaction
4. 统计 step 级 token 使用
5. 调用 `model_provider.generate(...)`
6. 解析 `finish_reason`
7. 根据 `finish_reason` 分流

## 6. finish_reason 分流

### 6.1 `tool_calls`

这是最常见的执行分支。

Runtime 会：

1. 调用 `handle_native_tool_calls(...)`
2. 逐个执行工具
3. 发出 `tool_called / tool_succeeded / tool_failed`
4. 把工具返回写回消息历史
5. 更新 `_active_todo_context`

这里最关键的是，todo 相关工具会不断刷新 active subtask 绑定。例如：

- `plan_task`
- `update_task_status`
- `update_subtask`
- `record_task_fallback`
- `reopen_subtask`
- `get_next_task`

### 6.2 `stop`

`stop` 不一定等于任务完成。

当前 Runtime 会先走 clarification judge：

1. 若模型回复像是在向用户索取缺失信息
   - 进入 `awaiting_user_input`
2. 否则
   - 视为正常收敛候选

### 6.3 `length`

表示模型被长度截断。

通常会被收敛成未正常完成的 stop reason，并进入后续恢复/收尾逻辑。

### 6.4 `content_filter`

表示内容被过滤。

同样会走未正常完成的出口。

### 6.5 其他 finish_reason

若有文本内容，Runtime 会尽量收敛成一个可解释的结果；
若既无有效文本也无工具，则会视作异常失败路径的一部分。

## 7. Tool Loop 与 Todo 绑定

当前 Runtime 的工具循环有一个重要附加职责：维护 todo 绑定现实。

### 7.1 binding warning

如果：

1. 当前已有 todo
2. `binding_required=True`
3. 但当前普通工具调用没有绑定 active subtask

Runtime 会发出 `todo_binding_missing_warning`。

这只是 warning，不会强阻断执行，但它是一个重要观测信号，说明当前执行正在脱离既有编排。

### 7.2 active todo context 更新

`update_active_todo_context(...)` 会根据工具执行结果维护绑定状态，例如：

1. `plan_task(create/update)` 后切到 planning
2. `update_task_status(..., in-progress)` 后切到 executing
3. `record_task_fallback` 后切到 recovering
4. `reopen_subtask` 后重新切回 executing
5. `completed/abandoned/pending` 会清空 active subtask 指针

## 8. Clarification 与恢复

## 8.1 Clarification Judge

clarification judge 的职责是区分：

1. 这是任务完成后的最终回答
2. 这是在向用户索取缺失信息

当前实现支持：

1. LLM judge
2. heuristic fallback

若命中 clarification：

1. Runtime state 进入 `awaiting_user_input`
2. 当前 run 挂起
3. 用户下次回复时，可以通过 `resume_from_waiting=True` 在同一个 run 恢复

## 8.2 失败出口

若 run 未正常完成且存在 active todo，Runtime 会进入自动恢复链路。

这部分主要由 [todo_runtime_lifecycle.py](/Users/yezibin/Project/InDepth/app/core/runtime/todo_runtime_lifecycle.py) 驱动。

主要顺序是：

1. 构造 runtime fallback record
2. 若当前失败无法归属具体 subtask，则识别为 orphan failure
3. 调用 `record_task_fallback`
4. 调用 `plan_task_recovery`
5. 若 recovery decision 允许自动推进，则补 follow-up subtasks 或原位恢复
6. 将 recovery 摘要挂到 `_latest_todo_recovery`

### 当前恢复策略特点

当前恢复策略有几个特点：

1. 优先围绕原 subtask 恢复
2. 只有必要时才派生 recovery subtasks
3. 失败出口会触发单次 `LLM recovery assessment`
4. 最终是否自动执行，还要经过 guardrails 落地

## 9. Finalizing Phase

无论是完成、澄清暂停还是失败，Runtime 最后都会进入 `finalizing phase`。

这里会统一处理：

1. verification handoff
2. `EvalOrchestrator.evaluate(...)`
3. `task_judged`
4. postmortem 生成
5. runtime memory finalize
6. system memory finalize
7. user preference capture
8. `_active_todo_context` 关闭或收束

### 9.1 Verification

verification 的目标是把“回答看起来完成”与“任务真完成”分开。

当前评估链主要由：

- `EvalOrchestrator`
- verifier 链
- 可选 LLM judge

共同决定最终 judgement。

### 9.2 Postmortem

每次运行结束后，系统会把关键事件、恢复信息和结果判断沉淀到 `observability-evals/`。

## 10. 关键模块映射

当前 Runtime 相关的核心模块如下：

- 主循环
  - [agent_runtime.py](/Users/yezibin/Project/InDepth/app/core/runtime/agent_runtime.py)

- todo 生命周期与恢复
  - [todo_runtime_lifecycle.py](/Users/yezibin/Project/InDepth/app/core/runtime/todo_runtime_lifecycle.py)

- clarification 判断
  - [clarification_policy.py](/Users/yezibin/Project/InDepth/app/core/runtime/clarification_policy.py)

- stop policy
  - [runtime_stop_policy.py](/Users/yezibin/Project/InDepth/app/core/runtime/runtime_stop_policy.py)

- finalization
  - [runtime_finalization.py](/Users/yezibin/Project/InDepth/app/core/runtime/runtime_finalization.py)

- compaction
  - [runtime_compaction_policy.py](/Users/yezibin/Project/InDepth/app/core/runtime/runtime_compaction_policy.py)

- tool execution
  - [tool_execution.py](/Users/yezibin/Project/InDepth/app/core/runtime/tool_execution.py)

- todo 工具
  - [todo_tool.py](/Users/yezibin/Project/InDepth/app/tool/todo_tool/todo_tool.py)

## 11. 当前 Runtime 的现实边界

理解当前实现时，有几个边界要明确：

1. prepare 现在已经有“基础现状扫描”，但还没有“自动重规划”
2. active todo 存在时，prepare 会更像“在现状上继续规划”，而不是重新从零设计
3. binding warning 是观测信号，不是强阻断
4. recovery 默认偏主动，但仍受 guardrails 约束
5. Runtime 只负责编排，不应该替代协议层定义任务边界

## 12. 一句话总结

当前 Runtime 的真实职责可以概括为：

它先在首轮请求前把“当前有什么、要怎么做、todo 要不要跟”准备好，再在执行中持续维护 active subtask 绑定，最后把暂停、失败、恢复、评估和记忆收尾闭成一个完整运行周期。
