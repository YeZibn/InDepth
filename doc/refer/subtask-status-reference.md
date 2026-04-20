# InDepth Subtask 状态控制参考

更新时间：2026-04-20

## 1. 目标

这份文档专门整理当前 InDepth 里 `subtask` 的状态控制规则，重点回答：
- 当前实现到底支持哪些 subtask 状态
- 这些状态分别表示什么
- Runtime / Todo 工具会在什么时机写入这些状态
- 状态变化会如何影响 active subtask 绑定与执行阶段
- 恢复场景下，状态、fallback、recovery 之间如何分工

如果你只想先抓主结论，可以先记住：
1. `fallback_record` 记录的是“最近一次失败/未完成事实”
2. `status` 记录的是“subtask 当前生命周期位置”
3. Runtime 自动恢复时，会先写 fallback，再单独推导状态
4. `append_followup_subtasks` 不是默认动作，优先围绕原 subtask 恢复

相关代码：
- `app/tool/todo_tool/todo_tool.py`
- `app/core/runtime/todo_runtime_lifecycle.py`
- `app/core/runtime/agent_runtime.py`
- `tests/test_todo_recovery_flow.py`
- `tests/test_runtime_todo_recovery_integration.py`

## 2. 当前支持的状态

当前 `todo_tool` 允许的 subtask 状态一共有 9 个：

- `pending`
- `in-progress`
- `completed`
- `blocked`
- `failed`
- `partial`
- `awaiting_input`
- `timed_out`
- `abandoned`

实现来源：
- `VALID_SUBTASK_STATUSES`：`app/tool/todo_tool/todo_tool.py`

其中几个重要分组如下。

### 2.1 Ready 状态

当前只有一个真正的“可直接被 `get_next_task` 选中”的 ready 状态：
- `pending`

实现来源：
- `READY_SUBTASK_STATUSES = {"pending"}`

这意味着：
- `blocked/failed/partial/awaiting_input/timed_out` 虽然都不是终态
- 但它们不会被当作“下一个可直接执行的常规任务”
- 它们会进入 blocked/incomplete 视图，等待恢复动作处理

### 2.2 终态

当前只有两个 terminal 状态：
- `completed`
- `abandoned`

实现来源：
- `TERMINAL_SUBTASK_STATUSES = {"completed", "abandoned"}`

这意味着：
- `failed` 不是终态
- `partial` 不是终态
- `awaiting_input` 不是终态
- `timed_out` 不是终态

系统语义是：这些状态表示“当前主线未顺利完成，但仍可能继续恢复或重开”。

### 2.3 会让 Todo 整体保持 active 的状态

当前会让整体 todo 元数据保持 active/in-progress 语义的状态有：
- `in-progress`
- `blocked`
- `failed`
- `partial`
- `awaiting_input`
- `timed_out`

实现来源：
- `ACTIVE_TODO_STATUSES`

## 3. 每个状态的真实语义

### 3.1 `pending`

表示 subtask 已存在，但尚未开始执行。

适用场景：
- 新创建的计划项默认就是 `pending`
- 旧 subtask 被关闭后，其他未启动 subtask 仍保留为 `pending`

注意：
- `pending` 是当前唯一 ready 状态
- 只有依赖已满足的 `pending` 才会被 `get_next_task` 选中

### 3.2 `in-progress`

表示当前 subtask 已被显式激活，进入执行主线。

常见进入方式：
- `update_task_status(..., status="in-progress")`
- `reopen_subtask(...)`

Runtime 联动：
- 会把当前 todo 上下文切到 `execution_phase="executing"`
- 会绑定 `active_subtask_number/active_subtask_id`

### 3.3 `completed`

表示该 subtask 已完成，并且当前实现会清空它的 `fallback_record`。

实现细节：
- `_update_task_status()` 中，状态写成 `completed` 时会把 `fallback_record` 置空

Runtime 联动：
- 当前 active 指针会被清空
- 上下文执行阶段回到 `planning`
- 如果全部 subtask 都完成，`binding_state` 会变成 `closed`

### 3.4 `blocked`

表示当前 subtask 暂时不能继续推进，通常是依赖未满足或外部条件未到位。

典型来源：
- Runtime 从 fallback 推导时，若 `failure_state == "blocked"` 或 `reason_code == "dependency_unmet"`，会写成 `blocked`
- 也可以人工显式调用 `update_task_status(..., "blocked")`

注意：
- `blocked` 不等于结束
- 它会出现在依赖视图的 `Blocked subtasks`
- 通常需要 `resolve_dependency` 一类恢复动作

### 3.5 `failed`

表示本次推进失败，但仍认为该 subtask 还应围绕原主线继续恢复。

典型来源：
- 普通工具失败
- 执行环境问题
- 模型调用失败后未进入更具体的 `awaiting_input/blocked/timed_out/partial`

注意：
- `failed` 不是终态
- 它更接近“当前执行尝试失败”
- 后续可以 `reopen_subtask(...)` 拉回 `in-progress`

### 3.6 `partial`

表示已经形成部分有效产出，但尚未完成闭环。

典型来源：
- Runtime 推导时 `failure_state == "partial"` 或 `reason_code == "partial_progress"`

常见语义：
- 结果需要保留
- 后续可能继续补完
- 恢复决策里可能结合 `partial_artifacts` 做保留或降级交付判断

### 3.7 `awaiting_input`

表示当前 subtask 已经不能靠系统单独继续，必须等待用户补充输入。

典型来源：
- Runtime 结束态是 `awaiting_user_input`
- 或 fallback 的 `reason_code == "waiting_user_input"`

注意：
- 这是“等人回复”，不是“执行失败重试”
- 后续恢复前，Runtime 可能先把旧未完成 subtasks 标成 `abandoned`，再在同一 todo 下追加新计划

### 3.8 `timed_out`

表示当前 subtask 不是逻辑错误，而是预算、步数或时限耗尽。

典型来源：
- `stop_reason == "max_steps_reached"`
- Runtime 会生成 `failure_state="timed_out"`、`reason_code="budget_exhausted"`

常见后续动作：
- `split`
- `degrade`
- `abandon`
- 或在收缩范围后重开执行

### 3.9 `abandoned`

表示该 subtask 被显式放弃，不再沿原计划继续推进。

典型来源：
- 人工调用 `update_task_status(..., "abandoned")`
- Runtime 从 `awaiting_input` 恢复新一轮计划前，先把旧计划中未完成 subtasks 标成 `abandoned`

注意：
- `abandoned` 是终态
- 它和 `completed` 一样会让 active subtask 指针被清空

## 4. 状态和 Fallback Record 的分工

这是当前实现里最容易混淆但也最关键的部分。

### 4.1 `fallback_record` 负责什么

`fallback_record` 负责记录一次失败或未完成推进的结构化事实，例如：
- `failure_state`
- `reason_code`
- `reason_detail`
- `retryable`
- `required_input`
- `retry_guidance`
- `partial_artifacts`
- `failure_interpretation`

它回答的是：
- 这次为什么没做完
- 现场证据是什么
- 下次恢复应该注意什么

### 4.2 `status` 负责什么

`status` 负责记录 subtask 当前在生命周期里的位置，例如：
- 还没开始
- 正在做
- 暂时阻塞
- 部分完成
- 等待输入
- 明确放弃

它回答的是：
- 这个 subtask 现在处于什么控制状态

### 4.3 当前主链顺序

Runtime 自动恢复时，当前顺序是：
1. 先构造 runtime fallback record
2. 调 `record_task_fallback(...)`
3. 调 `plan_task_recovery(...)`
4. 合并解释后的 fallback 信息
5. 再次写回 `record_task_fallback(...)`
6. 用 `derive_subtask_status_from_failure(...)` 单独推导 subtask 状态
7. 调 `update_task_status(...)`
8. 只有必要时才 `append_followup_subtasks(...)`

这条顺序说明：
- fallback 不直接覆盖 subtask 状态
- 状态是后推导、后写入的

## 5. Runtime 自动状态推导规则

当前 `derive_subtask_status_from_failure()` 的真实映射如下：

### 5.1 等待用户输入

若满足任一条件：
- `failure_state == "awaiting_input"`
- `reason_code == "waiting_user_input"`

则写入：
- `awaiting_input`

### 5.2 超时/预算耗尽

若：
- `failure_state == "timed_out"`

则写入：
- `timed_out`

### 5.3 部分完成

若满足任一条件：
- `failure_state == "partial"`
- `reason_code == "partial_progress"`

则写入：
- `partial`

### 5.4 依赖阻塞

若满足任一条件：
- `failure_state == "blocked"`
- `reason_code == "dependency_unmet"`

则写入：
- `blocked`

### 5.5 一般失败

若：
- `failure_state == "failed"`
- 且 `retryable == true`

则写入：
- `failed`

### 5.6 其他情况

否则：
- 返回 `failure_state` 本身

这意味着如果未来 fallback 层引入新的状态字面值，而工具层也接受，它可能会原样透传为 subtask 状态；但在当前实现里，推荐还是落在既有 9 个状态集合内。

## 6. 状态变更对 active todo 上下文的影响

当前 Runtime 不只写 markdown 文件，还会同步维护 `_active_todo_context`。这里最重要的是三个字段：
- `active_subtask_number`
- `active_subtask_id`
- `execution_phase`

### 6.1 `update_task_status` 的联动规则

当调用 `update_task_status` 时：

若状态为：
- `in-progress`

则：
- `execution_phase = "executing"`
- active subtask 绑定到当前项

若状态为：
- `blocked`
- `failed`
- `partial`
- `awaiting_input`
- `timed_out`

则：
- `execution_phase = "recovering"`
- active subtask 仍然绑定在当前项上

若状态为：
- `completed`
- `abandoned`
- `pending`

则：
- active subtask 指针会被清空
- `execution_phase = "planning"`

补充：
- 若 payload 里出现 `all_completed=true`，`binding_state` 会被置为 `closed`

### 6.2 `record_task_fallback` 的联动规则

写 fallback 后：
- `execution_phase = "recovering"`
- active subtask 会绑定到当前失败 subtask
- `active_retry_guidance` 会从 fallback 中抽取并保留

### 6.3 `reopen_subtask` 的联动规则

当调用 `reopen_subtask(...)` 成功后：
- subtask 会被重新置为 `in-progress`
- `execution_phase` 会回到 `executing`
- 原有 `active_retry_guidance` 会被保留

### 6.4 `get_next_task` 的联动规则

`get_next_task(...)` 选中 ready subtask 后：
- 会把它绑定为新的 active subtask
- 但 `execution_phase` 仍保留为 `planning`

这意味着：
- “被选中为下一项”
- 和“已经显式开始执行”
- 在当前实现里是两个不同动作

## 7. 工具层对状态迁移的硬约束

### 7.1 依赖检查

当前 `_update_task_status()` 会对以下目标状态做依赖检查：
- `in-progress`
- `completed`
- `partial`

若依赖未完成，会拒绝写入，报错类似：
- `Subtask X is blocked by Task Y`

这说明当前系统的保守策略是：
- 不能把仍被依赖卡住的 subtask 直接标成开始执行
- 也不能在依赖没满足时直接标成完成
- 连 `partial` 也要求依赖已满足

### 7.2 `completed` 会清空 fallback

这是一个很重要的实现细节：
- 当状态改成 `completed`
- 当前 subtask 的 `fallback_record` 会被自动清空

含义是：
- 历史失败信息不再作为当前未完成现场保留
- 该 subtask 已被视为闭环

### 7.3 `reopen_subtask` 的适用对象

工具描述里明确允许重开这些状态的 subtask：
- `failed`
- `blocked`
- `partial`
- `timed_out`
- `completed`

成功后统一回到：
- `in-progress`

虽然描述里没有把 `awaiting_input` 和 `abandoned` 明写进说明文本，但从整体流程语义看：
- `awaiting_input` 更常见做法是收到新输入后走新一轮 prepare/update
- `abandoned` 通常不建议直接重开，而是基于新计划追加或重建更清晰

## 8. Dependencies 视图里怎么显示这些状态

`_calculate_blocked_status()` 当前会把两类 subtask 放进 blocked 视图：

### 8.1 依赖未满足的 `pending`

如果 subtask 是 `pending`，但依赖未完成：
- 会出现在 `Blocked subtasks`
- 原因展示为缺失依赖的 `Task N`

### 8.2 已进入恢复态的 unfinished 状态

以下状态会直接进入 `Blocked subtasks`：
- `blocked`
- `failed`
- `partial`
- `awaiting_input`
- `timed_out`

展示原因优先取：
- `fallback_record.reason_code`

取不到时才回退为：
- 状态名本身

这意味着 dependencies 区域不只表达“拓扑依赖阻塞”，也承担了“恢复阻塞面板”的角色。

## 9. 推荐的状态使用口径

为了让文档、工具和 runtime 语义一致，当前推荐口径如下。

### 9.1 正常执行主线

推荐主线：
1. 新建时为 `pending`
2. 开始做时改成 `in-progress`
3. 完成后改成 `completed`

### 9.2 执行失败但仍可继续

优先区分失败类型：
- 缺依赖：`blocked`
- 缺用户输入：`awaiting_input`
- 已有部分产出：`partial`
- 预算耗尽：`timed_out`
- 普通执行失败：`failed`

不要把所有异常都粗暴写成 `failed`，否则恢复链路的信息密度会下降。

### 9.3 明确放弃

只有在下面场景再用 `abandoned`：
- 旧计划整体失效
- 本轮收到新约束，需要先关闭旧未完成 subtasks
- 恢复决策明确要求终止原路线

### 9.4 是否应该派生新的 recovery subtask

当前推荐顺序是：
1. 先保住原 subtask 主线
2. 先写 fallback 和状态
3. 让 `plan_task_recovery` 判断能否原地恢复
4. 只有 `needs_derived_recovery_subtask=true` 时，才追加 follow-up subtasks

## 10. 一张速查表

| 状态 | 是否终态 | 是否 ready | 常见进入原因 | 常见后续动作 |
| --- | --- | --- | --- | --- |
| `pending` | 否 | 是 | 新建计划、尚未开始 | `get_next_task` / `update_task_status(in-progress)` |
| `in-progress` | 否 | 否 | 当前主线执行中 | `completed` / 写 fallback 后进入恢复态 |
| `completed` | 是 | 否 | 已完成闭环 | 清空 fallback，推进下一个 subtask |
| `blocked` | 否 | 否 | 依赖未满足 | `resolve_dependency` / `reopen_subtask` |
| `failed` | 否 | 否 | 普通执行失败 | `retry` / `retry_with_fix` / `reopen_subtask` |
| `partial` | 否 | 否 | 已有部分产出 | 保留产物、补做、必要时降级交付 |
| `awaiting_input` | 否 | 否 | 等用户补充信息 | 等用户回复，再重规划或恢复 |
| `timed_out` | 否 | 否 | 步数/预算耗尽 | `split` / 收缩范围 / `reopen_subtask` |
| `abandoned` | 是 | 否 | 明确放弃原路线 | 不再继续该 subtask |

## 11. 代码定位

想继续往下追实现时，优先看这些位置：

- 状态集合与依赖检查：
  `app/tool/todo_tool/todo_tool.py`
- fallback -> status 映射：
  `app/core/runtime/todo_runtime_lifecycle.py`
- active todo 上下文更新：
  `app/core/runtime/todo_runtime_lifecycle.py`
- prepare 阶段对旧 subtask 批量 `abandoned`：
  `app/core/runtime/agent_runtime.py`
- 行为回归样例：
  `tests/test_todo_recovery_flow.py`
  `tests/test_runtime_todo_recovery_integration.py`
