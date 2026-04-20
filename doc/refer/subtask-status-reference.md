# InDepth Subtask 执行选择与基础状态更新参考

更新时间：2026-04-20

## 1. 目标

这份文档只聚焦两件事：
- 当前实现如何判断“现在应该执行哪个 subtask”
- 当前已经落地的三种基础更新动作是什么，以及它们各自的边界

如果你只想先抓主结论，可以先记住：
1. 判断“下一个该做谁”，主入口是 `get_next_task`
2. 它只会挑选“第一个依赖已满足的 `pending` subtask”
3. 当前已经有三种基础更新动作：`update_task_status`、`update_subtask`、`reopen_subtask`
4. 其中真正负责标准状态迁移的是 `update_task_status`
5. `update_subtask` 更像补丁工具，虽然也能改 `status`，但约束更弱

相关代码：
- `app/tool/todo_tool/todo_tool.py`
- `app/core/runtime/todo_runtime_lifecycle.py`
- `app/core/runtime/agent_runtime.py`
- `tests/test_todo_recovery_flow.py`
- `tests/test_runtime_todo_recovery_integration.py`

## 2. 当前应该执行哪个 Subtask

这部分要分两层理解：
- Todo 工具层如何判断“下一个可执行 subtask”
- Runtime 如何记住“当前已经绑定到哪个 active subtask”

### 2.1 工具层判断：`get_next_task`

当前真正负责“找下一个该执行的 subtask”的工具是：
- `get_next_task(todo_id)`

它内部调用的是：
- `_get_next_task(subtasks)`

实际规则非常简单，也非常保守：
1. 先收集所有 `completed` subtask，形成 `completed_tasks`
2. 按 todo 文件中的 subtask 顺序从前往后扫描
3. 只看状态属于 `READY_SUBTASK_STATUSES` 的 subtask
4. 当前 `READY_SUBTASK_STATUSES` 只有 `pending`
5. 若该 `pending` subtask 的所有依赖都已经在 `completed_tasks` 里，就返回它
6. 找到第一个满足条件的就停止，不会继续找“更优候选”

也就是说，当前语义不是：
- “找最重要的任务”
- “找优先级最高的任务”
- “找最像当前上下文的任务”

而是：
- “按既有顺序，找第一个依赖闭合的 `pending` subtask”

### 2.2 `get_next_task` 的返回结果

`get_next_task` 有三种主要返回：

1. `status="ready"`
   表示找到了当前可执行 subtask，并返回：
   - `number`
   - `subtask_id`
   - `name`
   - `description`
   - `priority`
   - `dependencies`
   - `owner`
   - `kind`

2. `status="all_completed"`
   表示所有 subtask 都已进入终态：
   - `completed`
   - `abandoned`

补充：
- 当前 progress 也按终态口径统计
- 也就是 `completed + abandoned` 都计入进度分子

3. `status="blocked"`
   表示没有任何 ready subtask
   常见原因：
   - 依赖还没满足
   - 有 unfinished subtask 卡在 `blocked/failed/partial/awaiting_input/timed_out`

### 2.3 Runtime 里的“当前 active subtask”

除了“下一个可执行 subtask”，Runtime 还会维护一个执行中的绑定上下文：
- `todo_id`
- `active_subtask_id`
- `active_subtask_number`
- `execution_phase`

这个绑定不是靠 `_get_next_task()` 自动长期维护的，而是靠后续工具调用不断更新。

当前会更新 active subtask 的主要动作有：
- `get_next_task`
- `update_task_status`
- `update_subtask`
- `reopen_subtask`
- `record_task_fallback`

其中最常见的链路是：
1. `get_next_task` 选出当前应执行的 pending subtask
2. Runtime 把它写进 active todo context，但阶段仍是 `planning`
3. 真正开始执行时，再调用 `update_task_status(..., "in-progress")`
4. 这时执行阶段才切到 `executing`

这说明当前实现里：
- “选中下一个 subtask”
- 和“正式进入执行”
- 是两个动作，不是一个动作

## 3. 三种基础更新动作

当前更适合把 subtask 基础更新理解成三类：
- 标准状态迁移：`update_task_status`
- 补丁式字段更新：`update_subtask`
- 恢复执行：`reopen_subtask`

## 4. `update_task_status`：标准状态迁移入口

### 4.1 作用

`update_task_status(todo_id, subtask_number, status)` 是当前最标准的 subtask 状态更新入口。

它适合做的事是：
- `pending -> in-progress`
- `in-progress -> completed`
- `in-progress -> failed/blocked/partial/awaiting_input/timed_out`
- 显式写成 `abandoned`

### 4.2 当前支持的状态

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

#### Ready 状态

当前只有一个真正的“可直接被 `get_next_task` 选中”的 ready 状态：
- `pending`

实现来源：
- `READY_SUBTASK_STATUSES = {"pending"}`

这意味着：
- `blocked/failed/partial/awaiting_input/timed_out` 虽然都不是终态
- 但它们不会被当作“下一个可直接执行的常规任务”
- 它们会进入 blocked/incomplete 视图，等待恢复动作处理

#### 终态

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

当前 progress 统计也与这组终态保持一致：
- `completed` 计入 progress
- `abandoned` 也计入 progress

#### 会让 Todo 整体保持 active 的状态

当前会让整体 todo 元数据保持 active/in-progress 语义的状态有：
- `in-progress`
- `blocked`
- `failed`
- `partial`
- `awaiting_input`
- `timed_out`

实现来源：
- `ACTIVE_TODO_STATUSES`

### 4.3 依赖检查

当前 `_update_task_status()` 会对以下目标状态做依赖检查：
- `in-progress`
- `completed`
- `partial`

如果目标 subtask 仍有未完成依赖，会直接拒绝更新。

这意味着：
- 不能在依赖没满足时把任务标成 `in-progress`
- 不能在依赖没满足时把任务标成 `completed`
- 连 `partial` 也要求依赖已满足

### 4.4 对 Runtime 上下文的影响

`update_task_status` 成功后，Runtime 会同步更新 active todo context。

若状态为：
- `in-progress`

则：
- `active_subtask_number` 绑定到当前项
- `execution_phase = "executing"`

若状态为：
- `blocked`
- `failed`
- `partial`
- `awaiting_input`
- `timed_out`

则：
- active subtask 仍指向当前项
- `execution_phase = "recovering"`

若状态为：
- `completed`
- `abandoned`
- `pending`

则：
- active subtask 指针会被清空
- `execution_phase = "planning"`

### 4.5 一个实现细节

当状态更新为：
- `completed`

当前实现会自动清空该 subtask 的：
- `fallback_record`

也就是说，`completed` 被视为真正闭环，而不是“带着旧失败现场完成”。

## 5. `update_subtask`：补丁式字段更新入口

### 5.1 作用

`update_subtask(...)` 的定位不是“标准状态迁移”，而是：
- 不重写整个 todo
- 只 patch 某个 subtask 的部分字段

它可以更新的字段包括：
- `name/title`
- `description`
- `status`
- `priority`
- `dependencies`
- `acceptance_criteria`
- `split_rationale`
- `owner`
- `kind`
- `origin_subtask_id`
- `origin_subtask_number`
- `fallback_record`

### 5.2 一个很关键的边界

虽然 `update_subtask` 也允许直接改 `status`，但它和 `update_task_status` 不一样：
- `update_task_status` 会走标准状态更新逻辑
- `update_subtask` 是字段 patch

当前实现里，`update_subtask` 在修改 `status` 时：
- 会做状态合法性校验
- 但不会复用 `_update_task_status()` 的依赖检查逻辑

这意味着：
- 如果只是正常推进 subtask 生命周期，优先用 `update_task_status`
- `update_subtask` 更适合修补结构字段，或在非常明确知道后果时做局部 patch

### 5.3 对 Runtime 上下文的影响

`update_subtask` 执行成功后，Runtime 也会更新 active todo context。

当前行为是：
- 把这个 subtask 记为当前 active subtask
- 但 `execution_phase` 基本沿用旧值，不主动切换为 `executing/recovering`

所以它更像：
- “把当前关注点绑到这个 subtask 上”

而不是：
- “显式宣告它已经进入标准执行状态迁移”

## 6. `reopen_subtask`：恢复执行入口

### 6.1 作用

`reopen_subtask(todo_id, subtask_id|subtask_number, reason)` 的作用是：
- 找到一个已有 subtask
- 把它重新标记为 `in-progress`

适合场景：
- 失败后恢复
- 阻塞解除后恢复
- 部分完成后继续补做
- 超时后收缩范围再继续

### 6.2 查找目标的方式

它支持两种定位方式：
- `subtask_id`
- `subtask_number`

匹配顺序是：
1. 如果提供了 `subtask_id`，先按 `subtask_id` 找
2. 找不到再按 `subtask_number` 找

### 6.3 为什么它是独立动作

`reopen_subtask` 本质上还是调用 `_update_task_status(..., "in-progress")`。

所以它的价值不在于“多一种状态”，而在于：
- 把“恢复执行”表达成单独语义
- 不需要调用方自己拼“先找目标，再手动写 in-progress”

### 6.4 对 Runtime 上下文的影响

成功后：
- 当前 subtask 会重新成为 active subtask
- `execution_phase = "executing"`
- 已保存的 `active_retry_guidance` 会保留

这也是恢复链路里从 `recovering` 回到 `executing` 的标准入口。

## 7. 每个状态的真实语义

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

## 8. 状态和 Fallback Record 的分工

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

## 9. Runtime 自动状态推导规则

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

## 10. 状态变更对 active todo 上下文的影响

当前 Runtime 不只写 markdown 文件，还会同步维护 `_active_todo_context`。这里最重要的是三个字段：
- `active_subtask_number`
- `active_subtask_id`
- `execution_phase`

### 10.1 `update_task_status` 的联动规则

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

### 10.2 `record_task_fallback` 的联动规则

写 fallback 后：
- `execution_phase = "recovering"`
- active subtask 会绑定到当前失败 subtask
- `active_retry_guidance` 会从 fallback 中抽取并保留

### 10.3 `reopen_subtask` 的联动规则

当调用 `reopen_subtask(...)` 成功后：
- subtask 会被重新置为 `in-progress`
- `execution_phase` 会回到 `executing`
- 原有 `active_retry_guidance` 会被保留

### 10.4 `get_next_task` 的联动规则

`get_next_task(...)` 选中 ready subtask 后：
- 会把它绑定为新的 active subtask
- 但 `execution_phase` 仍保留为 `planning`

这意味着：
- “被选中为下一项”
- 和“已经显式开始执行”
- 在当前实现里是两个不同动作

## 11. 工具层对状态迁移的硬约束

### 11.1 依赖检查

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

### 11.2 `completed` 会清空 fallback

这是一个很重要的实现细节：
- 当状态改成 `completed`
- 当前 subtask 的 `fallback_record` 会被自动清空

含义是：
- 历史失败信息不再作为当前未完成现场保留
- 该 subtask 已被视为闭环

### 11.3 `reopen_subtask` 的适用对象

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

## 12. Dependencies 视图里怎么显示这些状态

`_calculate_blocked_status()` 当前会把两类 subtask 放进 blocked 视图：

### 12.1 依赖未满足的 `pending`

如果 subtask 是 `pending`，但依赖未完成：
- 会出现在 `Blocked subtasks`
- 原因展示为缺失依赖的 `Task N`

### 12.2 已进入恢复态的 unfinished 状态

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

## 13. 推荐的状态使用口径

为了让文档、工具和 runtime 语义一致，当前推荐口径如下。

### 13.1 正常执行主线

推荐主线：
1. 新建时为 `pending`
2. 开始做时改成 `in-progress`
3. 完成后改成 `completed`

### 13.2 执行失败但仍可继续

优先区分失败类型：
- 缺依赖：`blocked`
- 缺用户输入：`awaiting_input`
- 已有部分产出：`partial`
- 预算耗尽：`timed_out`
- 普通执行失败：`failed`

不要把所有异常都粗暴写成 `failed`，否则恢复链路的信息密度会下降。

### 13.3 明确放弃

只有在下面场景再用 `abandoned`：
- 旧计划整体失效
- 本轮收到新约束，需要先关闭旧未完成 subtasks
- 恢复决策明确要求终止原路线

### 13.4 是否应该派生新的 recovery subtask

当前推荐顺序是：
1. 先保住原 subtask 主线
2. 先写 fallback 和状态
3. 让 `plan_task_recovery` 判断能否原地恢复
4. 只有 `needs_derived_recovery_subtask=true` 时，才追加 follow-up subtasks

## 14. 一张速查表

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

## 15. 代码定位

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
