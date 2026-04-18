# InDepth Prepare 前置规划阶段设计稿 V1

更新时间：2026-04-18  
状态：Implemented

## 1. 背景

原始问题并不在于 `subtasks` 是否必填，而在于阶段职责混乱：

1. Agent 很容易把 `plan_task` 理解成“现在就要把计划设计完整”。
2. 当任务还是开放性的、上下文尚未读完时，模型会过早承诺 `subtasks`。
3. 这会把“思考如何做”和“把已成型计划登记到 todo”混在一起。

典型后果是：

1. 首轮调用容易因参数不完整而报错。
2. Agent 更容易在尚未掌握材料前过度拆分。
3. 后续不得不频繁修改 todo，增加计划漂移。

因此，本稿引入一个显式的 `prepare` 阶段：先形成候选计划，再进入 Todo 落盘阶段。

## 2. 目标

1. 把“前置规划”和“Todo 落盘”拆成两个清晰阶段。
2. 让 Agent 不再把 `plan_task` 误解为现场设计计划的场所。
3. 让 `prepare` 能感知当前是否已有 active todo。
4. 明确 create / update 的分流：
   - 无 active todo 时走 `plan_task`
   - 有 active todo 时走 `update_task`
5. 让 Runtime 在长文写作、开放性调研、复杂执行任务上更稳定。

## 3. 非目标

1. `prepare_task` 不直接修改 todo。
2. 本稿不重做 todo markdown schema。
3. 本稿不引入复杂多轮 planning state machine。
4. 本稿不让模型自行决定是否先执行 prepare。

## 4. 核心判断

### 4.1 Prepare 要看到 todo，但不应修改 todo

`prepare` 必须知道当前是否已有 active todo，否则无法判断这是：

1. 新任务，适合 `create-ready`
2. 续做任务，适合 `update-ready`
3. 轻量任务，适合 `skip`

但 `prepare` 不应真正执行 create / update，因为：

1. 它属于思考层，不属于入库层。
2. 真实的 todo 状态需要由 Runtime 在最新上下文里落盘。
3. create 路径和 update 路径的参数结构已经不同，不应再混成一个“边想边落盘”的动作。

一句话概括：

1. `prepare` 要“看见” todo。
2. 真正改 todo 的是 `plan_task` 或 `update_task`。

## 5. 分层设计

新的职责分层如下：

1. `prepare_task`
   - 读取上下文
   - 感知当前 active todo 状态
   - 形成候选执行计划
   - 不落盘、不改 todo

2. `plan_task`
   - 只负责 create 路径
   - 接收完整计划包
   - 做严格 envelope 校验
   - 创建新的 todo 并完成首次落盘

3. `update_task`
   - 只负责 update 路径
   - 接收结构化 `operations`
   - 对既有 todo 执行增量修改

4. `execute`
   - 根据 active subtask 推进执行
   - 使用 `update_task_status/update_subtask/reopen_subtask/...`

对应心智模型：

1. `prepare_task` = 想清楚怎么做
2. `plan_task/update_task` = 把已成型计划登记到 todo
3. `execute` = 真的开始做

## 6. Prepare 阶段设计

### 6.1 工具

新增隐藏工具：

1. `prepare_task`

### 6.2 输入

`prepare_task` 当前接收：

1. `task_name`
2. `context`
3. `active_todo_id`
4. `active_todo_exists`
5. `active_todo_summary`
6. `active_subtask_number`
7. `active_subtask_status`
8. `execution_intent`

### 6.3 输出

`prepare_task` 当前输出的核心字段：

1. `should_use_todo`
2. `plan_ready`
3. `recommended_mode`
4. `task_name`
5. `context`
6. `split_reason`
7. `subtasks`
8. `planning_confidence`
9. `notes`
10. `recommended_plan_task_args`
11. `update_plan`
12. `recommended_update_task_args`

### 6.4 三种结果语义

`prepare_task` 支持三种结果：

1. `skip`
   - 任务太小，不值得建 todo
   - 直接普通执行

2. `create-ready`
   - 当前没有 active todo
   - 已形成成熟计划
   - 可交给 `plan_task`

3. `update-ready`
   - 当前已有 active todo
   - 已形成增量计划
   - 可交给 `update_task`

注意：

1. 这里的 `create-ready/update-ready` 是 prepare 的输出语义。
2. 并不代表 `prepare_task` 真正执行了 create / update。

## 7. Runtime 链路设计

当前 Runtime 执行流改为：

1. 接收用户任务
2. 恢复当前 todo 上下文
3. 强制调用 `prepare_task`
4. 根据 `prepare_task` 输出分流：
   - `skip` -> 直接普通执行
   - `create-ready` -> 自动内部调用 `plan_task`
   - `update-ready` -> 自动内部调用 `update_task`
5. 绑定 active todo / active subtask
6. 进入执行与恢复阶段

### 7.1 Prepare 必须在首轮模型请求前执行

`prepare` 不是提示词约定，而是 Runtime 硬顺序：

1. `AgentRuntime.run()` 在第一次 `model_request` 之前先执行 `prepare_task`
2. `prepare_task` 结果写入：
   - runtime 内部状态
   - 模型可见的 system context
3. 首轮模型请求只能发生在 prepare 完成之后

### 7.2 Prepare 结果是 runtime facts

`prepare_task` 的输出会保存为 Runtime 状态：

1. `prepare_phase_completed`
2. `prepare_phase_result`

其作用是：

1. 供首轮模型请求读取
2. 供 planning guard 使用
3. 供 history restore / recovery 复用

### 7.3 Planning Tool Guard

为了把“prepare 必跑”从编排约束提升为运行时约束，当前对以下工具增加 guard：

1. `plan_task`
2. `create_task`
3. `update_task`

规则：

1. 若 `prepare_phase_completed=false`
2. 则 Runtime 拒绝这些工具调用
3. 并返回明确错误，提示先执行 `prepare_task`

### 7.4 自动落盘

当前已落地的自动化策略：

1. `create-ready` 时，Runtime 自动内部执行一次 `plan_task`
2. `update-ready` 时，Runtime 自动内部执行一次 `update_task`
3. 内部自动执行结果会同时写入：
   - 当前 `messages`
   - `memory_store`

这样可以保证：

1. create / update 的分流不再依赖模型现场判断
2. 恢复历史时能看到 prepare 触发的内部工具执行
3. 首轮模型拿到的是已经完成预处理后的上下文

## 8. 与现有设计的兼容性

1. 与 todo recovery 机制兼容
   - 一旦 todo 已落盘，后续恢复链路仍绑定到真实 subtask

2. 与共享 todo 设计兼容
   - `prepare_task` 显式读取 active todo，避免同一 task 周期重复 create

3. 与 create / update 解耦兼容
   - create 继续走 `plan_task`
   - update 明确走 `update_task`

## 9. 错误与边界处理

### 9.1 `prepare_task` 产出为空

若 `prepare_task` 输出：

1. `should_use_todo=true`
2. 但 `plan_ready=false`

则 Runtime 不应直接进入落盘工具，而应继续收集上下文或降级为普通执行。

### 9.2 `prepare_task` 建议 create，但实际存在 active todo

当前实现不鼓励把这类偏差交给 `plan_task` 二次裁决，而是应优先修正 prepare 输入或上下文恢复逻辑。

### 9.3 `prepare_task` 建议 update，但 active todo 已失效

当前实现默认以 `update_task` 为执行工具：

1. 若 active todo 不可用，应返回显式错误
2. 后续可再决定是否增加回退到 create 的策略

## 10. 当前已落地内容

1. 新增 `prepare_task`
2. Runtime 在 task 起始阶段先调用 `prepare_task`
3. `prepare_task` 读取 active todo 上下文并返回候选计划
4. 无 active todo 时，由 Runtime 自动调用 `plan_task`
5. 有 active todo 时，由 Runtime 自动调用 `update_task`
6. Runtime 保存 prepare 状态，并对 planning 类工具增加 guard

## 11. 验收口径

至少覆盖以下场景：

1. 无 active todo 时，`prepare_task` 输出 `create-ready`，随后 `plan_task` 正常 create
2. 有 active todo 时，`prepare_task` 输出 `update-ready`，随后 `update_task` 正常 update
3. `prepare_task` 能感知 active todo，并避免错误重复 create
4. `prepare_task` 不直接修改 todo
5. Runtime 在首轮模型请求前完成 prepare 与自动落盘
6. Agent 不再因为 `plan_task` 而过早现场设计 subtasks

## 12. 一句话总结

本稿的核心不是让 `plan_task` 更宽松，而是让 Runtime 的阶段边界更清晰：

1. `prepare_task` 负责先想清楚
2. `plan_task/update_task` 负责再登记进去
3. `prepare` 看得到 todo
4. 只有真正的落盘工具才改得动 todo
