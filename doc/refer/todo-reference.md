# InDepth Todo 编排参考

更新时间：2026-04-16

## 1. 目标

Todo 编排层负责把复杂任务拆成可执行、可验证、可审计的最小动作单元，并为主 Agent / SubAgent 协作、失败恢复、以及最终交付提供统一状态面。

这份文档重点回答五个问题：
- 什么情况下必须创建 todo？
- subtask 应该如何设计，粒度多大才合适？
- 当前 todo 工具真实支持哪些状态和数据结构？
- 任务未完成时，fallback 与 recovery 现在是如何实现的？
- Runtime 如何自动接入这条恢复链路？

相关代码：
- `InDepth.md`
- `app/tool/todo_tool/todo_tool.py`
- `app/core/runtime/agent_runtime.py`
- `app/core/runtime/tool_execution.py`
- `app/core/runtime/verification_handoff.py`
- `doc/refer/tools-reference.md`

## 2. 设计定位

Todo 不是简单的待办清单，而是运行时编排层的事实源。

它承担四类职责：
- 规划职责：把复杂目标拆成有依赖关系的 subtask。
- 执行职责：给主 Agent 一个明确的“当前正在做什么”。
- 恢复职责：在任务未完成时记录失败现场并生成下一步动作。
- 审计职责：把状态变化、依赖阻塞、恢复决策和进度沉淀为可回放记录。

在 InDepth 协议里，主 Agent 不能绕开 todo 直接做清单外动作；执行必须围绕 subtask 展开。

## 3. 何时必须创建 Todo

满足以下任一条件即必须创建 todo：
- 至少 3 个可识别步骤。
- 涉及跨文件或跨组件修改。
- 预计执行超过 5 分钟。
- 存在依赖关系或并行机会。

调用 `create_task` 时必须提供：
- `task_name`：主任务标题，必须体现“动作 + 对象”。
- `context`：范围、边界、交付物、验收口径、时间基准。
- `split_reason`：为什么需要拆分。
- `subtasks`：结构化子任务数组。

返回值中的 `todo_id` 是 todo 域唯一标识，后续状态更新、失败记录、恢复规划和报告生成都必须复用它。

## 4. 当前 Todo 数据模型

### 4.1 顶层结构

`create_task` 会生成 `todo/<timestamp>_<sanitized_name>.md` 文件，主体结构包含：
- `Metadata`
- `Context`
- `Subtasks`
- `Dependencies`
- `Notes`

顶层元数据包括：
- `Todo ID`
- `Status`
- `Priority`
- `Created`
- `Updated`
- `Progress`

### 4.2 Subtask 结构

当前实现中，每个 subtask 会落为：
- `Task <n>: <name>`
- `Status`
- `Priority`
- `Dependencies`
- `Kind`（可选）
- `Owner`（可选）
- `Split Rationale`
- `Acceptance Criteria`（可选）
- `Fallback Record`（可选）
- 复选描述项

`create_task` / `append_followup_subtasks` 支持的核心字段包括：
- `name` / `title`
- `description`
- `priority`
- `dependencies`
- `split_rationale`
- `kind`
- `owner`
- `acceptance_criteria`
- `fallback_record`

### 4.3 依赖派生信息

`todo_tool` 会根据依赖关系额外生成一段依赖摘要：
- `Blocked subtasks`
- `Ready subtasks`
- `Blocking subtasks`

这段内容不是独立输入，而是由 subtask 的状态和依赖列表推导出来的。

## 5. Subtask 设计准则

### 5.1 粒度要求

一个好的 subtask 应满足：
- 单一动作：只做一件可描述、可验收的事。
- 单一责任：不要把“实现 + 测试 + 汇总”混成一步。
- 可验证：完成后能用产物、命令结果或结构化结论证明。
- 可流转：能够自然进入状态流转，而不是长期停留在模糊的“处理中”。

推荐粒度是 5 到 30 分钟可完成。

### 5.2 推荐写法

推荐使用“动词 + 对象 + 产出”：
- 读取错误日志并定位构建失败根因
- 基于诊断结果修复验证失败的实现
- 重新分派 researcher 并产出缩小范围后的证据摘要

### 5.3 完成判据

每个 subtask 至少应绑定一种完成判据：
- 产物路径
- 命令结果
- 结构化结论

如果完成后无法明确回答“什么算做完”，这个 subtask 往往拆得还不够好。

## 6. 当前代码实现状态机

### 6.1 Subtask 状态

当前 `todo_tool` 已真实支持以下状态：
- `pending`
- `in-progress`
- `completed`
- `blocked`
- `failed`
- `partial`
- `awaiting_input`
- `timed_out`
- `abandoned`

与旧版本不同，当前实现已经不再是三态。

### 6.2 状态含义

1. `pending`
   尚未开始，且没有被显式标记为未完成态。

2. `in-progress`
   当前正在执行。

3. `completed`
   满足完成判据。

4. `blocked`
   当前不能继续执行，通常是依赖未满足或外部条件不满足。

5. `failed`
   已执行，但结果失败、工具失败或输出不符合要求。

6. `partial`
   已有部分有效产出，但尚未完整闭环。

7. `awaiting_input`
   等待用户或外部系统补充输入。

8. `timed_out`
   达到预算上限、重试上限或步数上限。

9. `abandoned`
   明确止损，不再继续投入。

### 6.3 依赖推进规则

当前工具仍然会对 `in-progress`、`completed`、`partial` 做依赖检查：
- 若依赖未满足，不允许直接推进。

`get_next_task_item()` 只会返回依赖满足的 `pending` 任务作为下一个 ready subtask。

## 7. Fallback 记录

### 7.1 作用

任务未完成时，当前实现不会只停留在自然语言说明，而是支持将失败事实结构化写入 `Fallback Record`。

对应工具：
- `record_task_fallback(todo_id, subtask_number, ...)`

### 7.2 最小字段

当前实现支持的核心字段包括：
- `state`
- `reason_code`
- `reason_detail`
- `impact_scope`
- `retryable`
- `required_input`
- `suggested_next_action`
- `evidence`
- `owner`
- `retry_count`
- `retry_budget_remaining`

### 7.3 典型 `reason_code`

当前设计与实现对齐的原因码包括：
- `dependency_unmet`
- `tool_error`
- `validation_failed`
- `missing_context`
- `waiting_user_input`
- `budget_exhausted`
- `subagent_empty_result`
- `subagent_execution_error`
- `output_not_verifiable`

## 8. Recovery 决策

### 8.1 恢复决策器

当前已落地一个规则版恢复决策器：
- `plan_task_recovery(todo_id, subtask_number, ...)`

它会基于当前 subtask 的 `fallback_record` 生成 `recovery_decision`。

### 8.2 输出结构

当前恢复决策输出包含：
- `primary_action`
- `recommended_actions`
- `decision_level`
- `rationale`
- `preserve_artifacts`
- `next_subtasks`
- `resume_condition`
- `escalation_reason`
- `stop_auto_recovery`
- `suggested_owner`

### 8.3 当前动作集

规则版恢复决策器当前使用的动作包括：
- `retry`
- `retry_with_fix`
- `split`
- `fallback_path`
- `execution_handoff`
- `decision_handoff`
- `pause`
- `degrade`
- `abandon`

### 8.4 当前分级

恢复动作会被标记为：
- `auto`
- `agent_decide`
- `user_confirm`

当前 runtime 只会自动推进：
- `decision_level=auto`
- 且 `stop_auto_recovery=false`
的恢复决策。

## 9. Follow-up Subtasks

### 9.1 作用

当前实现支持把恢复动作进一步落成新的 subtask，而不是只停留在建议层。

对应工具：
- `append_followup_subtasks(todo_id, follow_up_subtasks)`

### 9.2 当前支持的 kind

follow-up subtask 的 `kind` 当前支持：
- `diagnose`
- `repair`
- `retry`
- `verify`
- `handoff`
- `resume`
- `report`

### 9.3 推荐模板

当前规则版恢复链路最常见的 follow-up 模式是：

1. `diagnose`
   先定位根因。

2. `repair` / `retry`
   再执行修复或重试。

3. `verify`
   最后做聚焦验证。

## 10. Runtime 自动接入

这是当前实现与早期设计最大的变化之一。

### 10.1 当前 runtime 做了什么

`AgentRuntime` 现在会跟踪活跃的 todo 上下文：
- `todo_id`
- `active_subtask_number`
- `execution_phase`
- `binding_required`

上下文来源于工具执行结果，例如：
- `create_task`
- `update_task_status`
- `record_task_fallback`
- `get_next_task`

当前语义：
- `create_task` 成功后，runtime 会记录 `todo_id`，并进入 `planning` 阶段
- `update_task_status(..., status="in-progress")` 后，runtime 会把该 subtask 视为当前 active subtask，并进入 `executing`
- `record_task_fallback(...)` 后，runtime 会把该 subtask 视为恢复中的 subtask，并进入 `recovering`
- `get_next_task` 返回 ready subtask 后，runtime 会记录候选 active subtask，但此时仍属于“待激活”状态，阶段仍偏向 `planning`

这意味着 runtime 已经不只是“记住最近的 todo_id”，而是开始区分：
- 当前是否已经进入 todo 执行流
- 当前是否已经绑定具体 subtask
- 当前是在规划、执行，还是恢复阶段

### 10.2 自动触发点

当 runtime 进入以下未完成出口时，会自动触发恢复链路：
- `failed`
- `awaiting_user_input`
- `max_steps_reached`
- `tool_failed_before_stop`
- 其他运行失败分支

### 10.3 自动恢复顺序

当前自动顺序为：

1. `record_task_fallback`
2. `plan_task_recovery`
3. 若恢复决策为低风险自动动作，则 `append_followup_subtasks`

这意味着：
- 失败记录不再只靠 agent 自觉
- 即便 agent 没主动做恢复登记，runtime 也会在失败出口补上

### 10.4 当前新增的绑定告警与 orphan failure

当前 runtime 还没有把“每个 step 都必须绑定 subtask”升级为强拦截，但已经新增了一层 `warn` 级 guard：

- 当 todo 已创建
- 且 runtime 认为当前动作应属于某个 subtask
- 但模型仍直接调用普通业务工具

runtime 会记录 `todo_binding_missing_warning` 观测事件。

当前被视为“补救性/编排性”的工具包括：
- `create_task`
- `list_tasks`
- `get_next_task`
- `get_task_progress`
- `generate_task_report`
- `update_task_status`
- `record_task_fallback`
- `plan_task_recovery`
- `append_followup_subtasks`

除这些工具外，其他工具默认会被视为“需要 active subtask 绑定的普通执行工具”。

#### 10.4.1 orphan failure

当前 runtime 还新增了一个重要异常分支：`orphan failure`

含义：
- 已经创建了 todo
- 但失败发生时还没有 active subtask
- 导致失败无法归属到具体 subtask

当前处理方式：
- runtime 不再静默跳过恢复链路
- 会生成一份最小恢复摘要
- `reason_code = orphan_subtask_unbound`
- `primary_action = decision_handoff`
- `decision_level = agent_decide`

这种情况下：
- 当前 todo 文件里的 subtask 不会被自动改写成 `failed`
- 但最终交付与恢复摘要会明确说明：当前失败来自“todo 已存在，但执行未绑定到具体 subtask”

## 11. 恢复信息如何外溢

当前恢复信息会进一步进入以下位置：

1. `verification_handoff.recovery`
   包含：
   - `todo_id`
   - `subtask_number`（若存在 active subtask）
   - `fallback_record`
   - `recovery_decision`

2. `task_judged.payload.verification_handoff`

3. postmortem 的“交付内容”区块

4. 最终用户回复中的简短“恢复摘要”

这意味着恢复信息已经不是 todo 内部私有信息，而是贯穿了：
- 编排
- 评估
- 观测
- 用户可见输出

## 12. 当前实现与设计稿关系

### 12.1 已实现部分

当前已经实现：
- richer subtask states
- `fallback_record`
- 规则版 `recovery_decision`
- follow-up subtask 追加
- runtime 自动接入恢复链路
- recovery 信息进入 handoff / postmortem / user-facing summary

### 12.2 仍未完全收口的部分

当前仍然是“最小规则版恢复系统”，还没有：
- 更高级的策略评分器
- 严格的关键路径推断
- 强制所有复杂任务必须先建 todo 的 runtime gate
- 恢复效果 metrics（成功率、升级率、止损率）

## 13. 一句话结论

当前 Todo 的核心已经不只是“列任务”，而是把复杂执行过程压缩成一组可验证、可恢复、可继续推进的 subtask；而 runtime 已经开始在失败出口自动补齐 fallback 与 recovery 链路，保证恢复机制不再只靠 agent 自觉遵守。
