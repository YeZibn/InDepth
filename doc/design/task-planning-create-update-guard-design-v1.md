# InDepth 任务规划单入口与内部 Create/Update 执行设计稿 V1

更新时间：2026-04-17  
状态：Draft

## 1. 背景

当前 Todo 编排已经具备：
1. `create_task` 创建 todo
2. `update_task_status / update_subtask / reopen_subtask / append_followup_subtasks` 等细粒度更新能力
3. Runtime 对 active todo 的绑定与恢复能力

但真实使用中仍然存在三类问题：
1. 模型仍可能绕过规划，直接调用 `create_task/update_task`。
2. 当已有 active todo 时，模型仍可能误走 create 路径。
3. 多个入口并列存在时，提示词、状态判断和参数校验容易重复且分叉。

因此，本稿进一步收口：
1. `plan_task` 成为唯一对外 Todo 主入口。
2. `create/update` 从对模型暴露的 tool 列表中移除。
3. `plan_task` 在内部完成状态判断，并调用内部 create/update 方法执行。

## 2. 目标

1. 把 `plan_task` 做成真正的总入口。
2. 把 create/update 的状态判断彻底收敛到 plan 阶段。
3. 保留 create/update 的内部能力，但不再让模型直接调用。
4. 保证参数校验仍然严格，尤其是 update 路径。
5. 让提示词只围绕 `plan_task` 展开，减少误导。

## 3. 非目标

1. 本稿不重做 todo markdown 文件 schema。
2. 本稿不引入自由 patch 或 JSON patch 机制。
3. 本稿不在本轮实现所有高风险结构变更操作。

## 4. 核心设计

### 4.1 单入口链路

新的执行链路为：
1. 模型调用 `plan_task`
2. `plan_task` 完成：
   - 严格 envelope 校验
   - active todo 状态判断
   - mode=create/update 裁决
3. `plan_task` 内部调用：
   - `_create_todo_from_plan(...)`
   - 或 `_update_todo_from_plan(...)`
4. 将最终执行结果作为 `plan_task` 的结果返回

### 4.2 `plan_task` 的职责

`plan_task` 的职责包括：
1. 验证任务计划是否完整。
2. 归一化 `task_name/context/split_reason/subtasks`。
3. 读取当前 active todo 状态。
4. 输出严格结构化任务包。
5. 判定 `mode=create/update`。
6. 触发内部执行。

因此，`plan_task` 不再只是“规划器”，而是：
1. strict envelope validator
2. mode selector
3. internal create/update dispatcher

### 4.3 内部 Create/Update 方法

对模型不暴露，但在能力层保留：
1. `_create_todo_from_plan(...)`
2. `_update_todo_from_plan(...)`

它们的职责是：
1. `create` 只负责从已校验的计划结果创建新 todo。
2. `update` 只负责把已校验的 update 计划应用到现有 todo。

这些方法不再承担：
1. 自行判断当前该 create 还是 update
2. 解释用户意图
3. 作为模型自由调用入口

### 4.4 `plan_task` 的模式判断

规则：
1. 若当前没有 active todo，则 `mode=create`
2. 若当前已有 active todo，则 `mode=update`

`plan_task` 结果至少包含：
1. `mode`
2. `active_todo_id`
3. `task_plan`
4. `execution_result`
5. `subtask_count`

### 4.5 Update 仍然参照 Create 模板

update 路径中涉及“新增 subtasks”时，应继续复用 create 风格模板：
1. `name/title`
2. `description`
3. `dependencies`
4. `priority`
5. `acceptance_criteria`
6. 其他统一字段

### 4.6 Update 的最小 operation 集合

第一版建议只支持：
1. `update_subtask`
2. `append_subtasks`
3. `reopen_subtask`

这组操作足以覆盖大多数“继续推进已有 todo”的场景。

## 5. 严格参数校验原则

### 5.1 `plan_task`

必须提供：
1. `task_name`
2. `context`
3. `split_reason`
4. `subtasks`

且：
1. `subtasks` 必须是非空数组
2. 每个 subtask 必须符合 create 风格模板
3. `plan_task` 输出必须包含明确的 `mode=create/update`

### 5.2 内部 create

必须消费已校验的 `mode=create` 计划结果。

不允许：
1. 重新做状态判断
2. 在已有 active todo 时继续 create

### 5.3 内部 update

必须消费已校验的 `mode=update` 计划结果。

且：
1. 必须有 `todo_id`
2. 必须有严格 `operations`
3. 每个 `operation` 必须声明 `type`
4. 涉及 subtask 时，必须指定 `subtask_id` 或 `subtask_number`

## 6. 状态规则

### 6.1 active todo 存在时

默认规则：
1. `plan_task` 必须输出并执行 `mode=update`
2. 不再允许模型直接走 create tool

### 6.2 active todo 不存在时

默认规则：
1. `plan_task` 必须输出并执行 `mode=create`
2. 不再允许模型直接走 update tool

## 7. 提示词与错误文案规范

### 7.1 不应出现的表达

以下表达容易误导：
1. “先按协议补齐 todo”
2. “先补齐 create_task 再继续”
3. “先创建 todo 再说”

### 7.2 推荐表达

提示词应围绕：
1. 先 `plan_task`
2. 由 `plan_task` 内部判断并执行 create/update
3. 不要求模型自行选择 create 还是 update

### 7.3 提示词原则

状态型 tool 的提示词应满足：
1. 不预设一定要创建新 todo
2. 不把参数修复和状态裁决混在一起
3. 把模式判断统一留给 `plan_task`

## 8. 最小落地方案

本轮建议落地：
1. 保留 `plan_task` 作为唯一对外 Todo 主入口
2. `plan_task` 输出 `mode=create/update`
3. `plan_task` 内部直接执行 create/update
4. 从对外 tool 列表中移除 `create_task/update_task`
5. 保留已有细粒度 tool 作为内部能力层

## 9. 验收建议

至少覆盖：
1. 无 active todo 时，`plan_task` 输出并执行 `mode=create`
2. 有 active todo 时，`plan_task` 输出并执行 `mode=update`
3. 新增 subtasks 仍复用 create 风格模板
4. update 路径对不完整 operation 严格拒绝
