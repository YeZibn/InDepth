# InDepth Runtime Todo 绑定与失败兜底闭环设计稿 V1

更新时间：2026-04-16  
状态：Draft（基于当前实现整理，待落地）

## 1. 背景

当前 InDepth 在 Todo 编排与失败兜底上已经不是空白状态，而是进入了“模型已建立、闭环未完全收紧”的阶段。

已有进展：
1. Todo 域已统一使用 `todo_id`
2. Todo 工具已支持多种未完成状态
3. Runtime 已能在失败出口自动写入最小 `fallback_record`
4. Runtime 已能根据失败上下文自动规划最小恢复动作，并在部分场景下追加 follow-up subtasks

当前主要缺口：
1. Runtime 还没有把“当前 step 必须属于某个 subtask”真正做成强约束
2. 自动恢复依赖 `active todo context`，一旦失败发生时没有绑定 `subtask_number`，恢复链路会直接跳过
3. 失败兜底设计稿中的部分字段、动作语义与升级规则，尚未与工具层实现完全对齐

因此，本设计稿的重点不是重新发明失败兜底模型，而是把“当前已实现内容、剩余缺口、建议闭环路径”整理清楚。

## 2. 目标

1. 明确当前 Runtime + Todo + Fallback 已实现到哪一层
2. 明确失败兜底与 subtask 绑定之间的依赖关系
3. 定义一套从“软约束”走向“运行时闭环”的收紧方案
4. 为下一批工程改动提供优先级排序

## 3. 非目标

1. 本稿不替代 `task-incomplete-fallback-design-v1.md`
2. 本稿不在本轮定义新的 UI 交互
3. 本稿不要求一次性把所有恢复动作都做成强自动化

## 4. 当前实现盘点

### 4.1 Todo 状态机

当前 `todo_tool` 已真实支持以下 subtask 状态：
1. `pending`
2. `in-progress`
3. `completed`
4. `blocked`
5. `failed`
6. `partial`
7. `awaiting_input`
8. `timed_out`
9. `abandoned`

当前实现说明：
1. `update_task_status(todo_id, subtask_number, status)` 已支持上述状态
2. 对 `in-progress/completed/partial` 已有依赖检查
3. `completed` 时会清空 subtask 的 `fallback_record`

这意味着失败兜底所依赖的状态底座已经存在。

### 4.2 Fallback Record 最小实现

当前工具层已支持最小 `fallback_record` 模型，核心字段包括：
1. `state`
2. `reason_code`
3. `reason_detail`
4. `impact_scope`
5. `retryable`
6. `required_input`
7. `suggested_next_action`
8. `evidence`
9. `owner`
10. `retry_count`
11. `retry_budget_remaining`

当前实现状态：
1. `record_task_fallback` 已可写入上述结构
2. `fallback_record.state` 会反向驱动 subtask 状态
3. `todo_tool` 已能把失败事实保存在 subtask 上，而不是只停留在日志或最终口头说明里

### 4.3 Recovery Decision 最小实现

当前系统已经存在最小恢复决策链路：
1. Runtime 进入未完成出口
2. 自动构造最小 `fallback_record`
3. 调用 `record_task_fallback`
4. 调用 `plan_task_recovery`
5. 若决策为低风险自动动作，则调用 `append_followup_subtasks`

这说明当前系统已经具备“失败后不只是停下来，而是主动生成恢复动作草案”的能力。

### 4.4 Runtime 已实现的自动恢复触发

当前 Runtime 已在以下场景触发自动恢复：
1. `awaiting_user_input`
2. `tool_failed_before_stop`
3. `model_failed`
4. `length`
5. `content_filter`
6. `max_steps_reached`
7. 其他统一归入未成功完成的出口

这些出口会被转换成最小 `fallback_record`，并透传到后续交付与验证链路。

## 5. 当前缺口

### 5.1 Active Subtask 绑定仍是软约束

协议层已经明确要求：
1. 每一步执行前必须明确当前正在执行的 todo 子任务
2. 若当前动作不属于任何已登记子任务，必须先补充子任务再执行

但 Runtime 当前实际只做了“上下文跟踪”，还没有做“执行前校验”。

当前表现为：
1. `create_task` 后 Runtime 只记住 `todo_id`
2. `update_task_status/get_next_task/record_task_fallback` 后，Runtime 才可能拿到 `subtask_number`
3. 如果模型在绑定 `subtask_number` 前就执行大量动作，系统不会立即报错

这意味着：
1. 编排协议已经很硬
2. Runtime 约束还不够硬

### 5.2 自动恢复依赖 Active Todo Context

当前自动恢复的前提条件是：
1. Runtime 必须有 `todo_id`
2. Runtime 必须有 `subtask_number`

若失败发生时两者不完整，当前逻辑会直接跳过自动恢复。

这会导致一个关键问题：
1. 失败兜底模型本身已经存在
2. 但最需要它的场景之一，恰恰可能因为上下文未绑定而无法进入恢复链路

### 5.3 设计稿与实现语义尚未完全对齐

当前仍存在几类不完全对齐：
1. 文档中的抽象恢复动作，与代码中的具体动作命名尚未完全统一
2. `fallback_record` 的可选字段只落地了一部分
3. `recovery_decision` 已有最小版本，但离设计稿中的完整输出模型还有差距
4. `degrade/abandon` 的升级边界还未成为强规则

## 6. 总体设计

### 6.1 设计判断

失败兜底部分本身已经具备较强设计基础，下一步不应重写模型，而应补“运行时绑定 + 恢复闭环”。

换句话说，真正需要收紧的不是：
1. 再增加更多失败状态
2. 再写一套更复杂的恢复术语

而是：
1. 失败发生时，系统能否稳定知道“当前失败属于哪个 subtask”
2. 知道后，系统能否稳定把失败写回 Todo 并生成下一步动作

### 6.2 新增 Runtime 执行上下文模型

建议 Runtime 在当前 `_active_todo_context` 基础上，升级为更明确的执行上下文：

1. `todo_id`
2. `active_subtask_number`
3. `execution_phase`
4. `binding_required`

字段说明：
1. `todo_id`：当前 todo 主任务标识
2. `active_subtask_number`：当前正在推进的 subtask
3. `execution_phase`：`planning | executing | recovering | finalizing`
4. `binding_required`：当前 step 是否必须绑定到某个 subtask

设计目的：
1. 不再只用“是否有 todo”来判断约束
2. 把“计划阶段”和“执行阶段”区分开
3. 避免 `create_task` 刚结束就因为尚未选择 active subtask 而被系统误伤

### 6.3 Runtime Guard 分层策略

建议 Runtime Guard 分三档：

1. `off`
   不做运行时检查，仅保留协议提示。

2. `warn`
   若已进入需要绑定的阶段，但当前 step 没有 active subtask：
   - 记录观测事件
   - 向模型提供修正信号
   - 不立即阻断整个流程

3. `enforce`
   若 `binding_required=true` 且没有 active subtask：
   - 禁止继续执行普通业务工具
   - 只允许进入补救性工具链路

补救性工具示例：
1. `get_next_task`
2. `update_task_status`
3. `append_followup_subtasks`
4. `record_task_fallback`
5. `plan_task_recovery`

### 6.4 Orphan Failure 设计

建议新增一种 Runtime 级失败分类：`orphan_failure`

定义：
1. 任务已进入 todo 执行流
2. Runtime 已存在 `todo_id`
3. 当前失败发生时没有可确认的 `active_subtask_number`

设计目标：
1. 不让失败兜底因为“上下文不完整”而静默跳过
2. 把这类问题显式暴露为编排缺陷，而不是悄悄丢掉恢复能力

建议处理：
1. 记录专门事件
2. 在 `warn` 模式下要求模型先补绑定
3. 在 `enforce` 模式下只允许补救性工具
4. 若仍无法绑定，则将该失败显式写入最终交付与 postmortem

## 7. 与失败兜底设计稿的关系

本稿不替代原有失败兜底设计，而是把它推进到“实现闭环”层。

两份设计稿分工建议如下：

`task-incomplete-fallback-design-v1.md`
1. 负责定义未完成模型
2. 负责定义恢复动作与恢复决策模型
3. 负责定义交付层如何表达未完成项

`runtime-todo-fallback-closure-design-v1.md`
1. 负责定义 Runtime 如何稳定绑定 active subtask
2. 负责定义 Runtime Guard 的检查与升级策略
3. 负责定义何时会因为缺少 subtask 绑定而进入 `orphan_failure`
4. 负责定义如何保证失败兜底链路不被上下文缺口绕过

## 8. 已实现 / 部分实现 / 未实现

### 8.1 已实现

1. Todo 多状态状态机
2. `fallback_record` 最小模型
3. Runtime 自动 fallback 写回
4. Runtime 自动 recovery planning
5. follow-up subtasks 追加能力
6. 恢复摘要向交付链路外溢

### 8.2 部分实现

1. `reason_code` 仍未形成完整稳定枚举
2. `fallback_record` 可选字段未完全落地
3. `recovery_decision` 尚未达到完整设计稿输出
4. 恢复动作命名仍需文档与代码统一
5. 交付层已能展示恢复摘要，但未完全结构化展示未完成项

### 8.3 未实现

1. Runtime step 级 subtask binding guard
2. `orphan_failure` 显式分类与处理
3. `degrade/abandon` 的统一升级边界
4. 状态写回与证据写回的一体化接口
5. “连续自动恢复未缩小问题范围” 的升级判定

## 9. 分阶段落地建议

### Phase 1：文档与语义对齐

1. 统一恢复动作命名
2. 明确 `orphan_failure` 的定义与出口
3. 明确 Runtime Guard 三档策略
4. 明确 `degrade/abandon` 默认不自动执行

### Phase 2：Runtime 最小收紧

1. 扩展 `_active_todo_context`
2. 增加 `execution_phase`
3. 在 step 入口增加 binding guard
4. 增加 `warn` 模式观测事件

### Phase 3：失败闭环收口

1. 为 orphan failure 建立明确 fallback 路径
2. 让失败兜底不再因为缺失 `subtask_number` 而静默失效
3. 让状态写回与失败证据更紧密联动

### Phase 4：恢复质量升级

1. 补齐 `fallback_record` 可选字段
2. 补齐 `recovery_decision` 完整字段
3. 增加恢复成功率、升级率、止损率观测
4. 在最终交付中结构化展示未完成项

## 10. 结论

当前 InDepth 在 Todo 与失败兜底上已经具备较完整的模型基础：
1. Todo 状态机已扩展
2. Fallback record 已存在
3. Runtime 自动恢复链路已存在

真正尚未闭环的核心问题不是“没有失败兜底设计”，而是：
1. Runtime 还不能稳定保证每个执行 step 都挂在某个 subtask 上
2. 自动恢复仍然可能因为缺失 active subtask 而失效

因此，下一阶段设计重点应从“继续扩展失败术语”转向“收紧 Runtime 执行约束”，让 Todo 编排、失败写回、恢复决策、交付说明形成真正闭环。
