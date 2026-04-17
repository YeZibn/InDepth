# InDepth 状态型 Tool 强校验与 Todo 绑定恢复设计稿 V1

更新时间：2026-04-17  
状态：Draft

## 1. 背景

当前 Runtime 已经为 Todo 编排建立了较明确的协议：
1. 一个 task 周期原则上共用一个 todo。
2. `create_task` 是进入 todo 周期的显式起点。
3. 一旦已有 active todo，后续动作应优先复用该 todo，而不是重新创建。

但在真实运行中，仍然暴露出两类关键缺口：
1. 状态型 tool 的参数完整性仍然过度依赖模型自觉，尤其是 `create_task`。
2. todo 绑定上下文主要保存在单次 run 的内存态中，新 run 启动后默认丢失。

这两类缺口叠加时，会形成一条典型故障链：
1. 上一轮已经创建并推进了 todo。
2. 新 run 启动时没有恢复 active todo context。
3. 模型误以为当前尚未进入 todo 周期，再次调用 `create_task`。
4. 新调用又可能缺少 `subtasks` 等必填参数。
5. 最终出现“重复建 todo + 参数校验失败”的双重问题。

因此，本稿不把“参数完整性”和“todo 绑定恢复”拆成两个孤立修复点，而把它们视为同一条状态链路上的两个护栏。

## 2. 目标

1. 提升 `create_task` 等状态型 tool 的参数完整性约束强度。
2. 让 tool 失败反馈不再停留在泛化的 `validation failed`，而是给出更强、更可恢复的提示。
3. 让 Runtime 在新 run 启动时能够恢复同一 `task_id` 的最近有效 todo 绑定。
4. 将“一个 task 周期共用一个 todo”从文档约定收紧为运行时事实。
5. 为后续扩展到 `append_followup_subtasks`、`update_task_status` 等状态型 tool 提供统一模式。

## 3. 非目标

1. 本稿不重做 todo markdown 文件 schema。
2. 本稿不重写完整的任务规划策略。
3. 本稿不在本轮改变 UI 交互。
4. 本稿不要求一次性把所有状态型 tool 都纳入强校验，只先收紧最关键路径。

## 4. 问题拆解

### 4.1 参数完整性问题

以 `create_task` 为例，当前风险点包括：
1. 模型可能漏传 `subtasks`。
2. 模型可能传入空数组，但语义上仍不足以创建 tracked todo。
3. 模型可能本意是“继续已有 todo”，却错误调用了 `create_task`。

当前仅依赖 schema 校验会带来两个不足：
1. 错误信息过于泛化，难以把模型拉回正确轨道。
2. 无法表达“这个错误不只是缺字段，还意味着你可能走错了状态路径”。

### 4.2 Todo 绑定问题

当前 duplicate guard 依赖 `_active_todo_context`：
1. 当同一 run 内已绑定 active todo，再次 `create_task` 会被拒绝。
2. 但新 run 开始时 `_active_todo_context` 会重新初始化。

这意味着：
1. 保护只在单次 run 内有效。
2. 跨 run 场景下，即便历史里已经创建过 todo，Runtime 仍可能把自己当成“未绑定”。

### 4.3 两类问题的耦合

如果只修参数完整性，不修 todo 绑定恢复：
1. 系统会少报错，但仍会继续误判为“应该重新 create_task”。

如果只修 todo 绑定恢复，不修参数完整性：
1. 重复建 todo 的概率会下降，但模型在真正需要创建 todo 时仍可能因为缺参而脆弱失败。

因此两者必须一起收紧。

## 5. 核心设计

### 5.1 状态型 Tool 分层护栏

本稿建议为状态型 tool 增加两层护栏：
1. 参数护栏：校验“调用是否合法”。
2. 状态护栏：校验“此时此刻该不该调用这个 tool”。

对应到 `create_task`：
1. 参数护栏负责检查 `task_name/context/split_reason/subtasks`。
2. 状态护栏负责检查当前是否已有 active todo，是否真的需要新周期。

### 5.2 `create_task` 的更强前置校验

在真正执行 tool 之前，Runtime 应先做前置判断：
1. `task_name` 必须存在且非空。
2. `context` 必须存在且非空。
3. `split_reason` 必须存在且非空。
4. `subtasks` 必须存在。
5. `subtasks` 必须是非空数组。

若不满足，不应直接把调用交给底层 tool，而应返回更强的结构化错误：
1. 明确指出缺失字段。
2. 明确指出 `create_task` 需要完整 envelope。
3. 明确指出“如果你是在继续已有 todo，请不要调用 create_task”。

设计判断：
1. 这里的目标不是帮模型自动猜完整 subtasks。
2. 对 `create_task` 这种状态型入口工具，宁可强拒绝，也不要无依据补齐关键结构。

### 5.3 更强的 tool 反馈文案

对于 `create_task` 的参数错误，反馈应比普通 validation error 更重：
1. 不只说“参数校验失败”。
2. 还要提示“这是 tracked todo 的入口工具，缺少 subtasks 不能继续”。
3. 还要提示“若本意是继续已有 todo，应改走复用路径”。

示例语义：
1. `create_task requires task_name, context, split_reason, and a non-empty subtasks array`
2. `This tool creates a tracked todo and cannot proceed with an incomplete task envelope`
3. `If you mean to continue existing work, reuse or extend the current todo instead of calling create_task again`

### 5.4 新 run 启动时恢复 Todo 绑定

Runtime 在新 run 启动时，不应把空白内存态直接视为真实状态，而应先尝试从历史恢复：
1. 读取同一 `task_id` 的最近消息。
2. 从 assistant 历史中的 `tool_calls` 与 tool 历史返回中重建执行序列。
3. 将最近有效的 `create_task/update_task_status/update_subtask/...` 重放到 `_active_todo_context`。

恢复产物至少包括：
1. `todo_id`
2. `active_subtask_id`
3. `active_subtask_number`
4. `execution_phase`
5. `binding_required`
6. `binding_state`
7. `todo_bound_at`

设计判断：
1. 这里恢复的是“运行时绑定事实”，不是重新解析整个 todo 文件。
2. 优先使用当前 task 的历史消息，是因为这些消息已经包含模型实际调用过的工具链。

### 5.5 Duplicate Guard 的跨 run 生效

恢复完 `_active_todo_context` 后，现有 duplicate guard 才真正具备跨 run 意义：
1. 若恢复出 `todo_id` 且 `binding_state=bound`，再次 `create_task` 默认拒绝。
2. 只有显式 `force_new_cycle=true` 时才允许切新周期。

### 5.6 复用优先级

当已有 todo 且用户目标仍属于同一任务链时，优先级应为：
1. 复用已有 todo。
2. 必要时更新 subtask。
3. 必要时追加 `follow_up_subtasks`。
4. 最后才是显式新周期 `create_task(force_new_cycle=true)`。

换句话说：
1. “信息变多了”不是新建 todo 的理由。
2. “要写下一阶段内容”默认也不是新建 todo 的理由。
3. 只有目标切换或显式新周期，才进入新 todo。

## 6. 最小落地方案

本轮建议先落地以下最小集合：

1. Runtime 增加 `restore_active_todo_context_from_history(history)`。
2. `run()` 启动时先恢复 todo 绑定，再进入模型主循环。
3. `create_task` 在 Runtime 层增加 `build_create_task_arg_error(...)` 前置拦截。
4. `ToolRegistry.invoke()` 对 `create_task` 的 schema 失败返回更强错误文案。
5. 补一条跨 run 回归测试：上一轮已创建 todo，下一轮再次 `create_task` 应被拒绝。

## 7. 后续增强

后续可继续扩展到：
1. `append_followup_subtasks` 的 envelope 校验。
2. `update_task_status` 的状态迁移前置判断。
3. 状态型 tool 的统一错误分类，例如：
   - `arg_incomplete`
   - `state_conflict`
   - `todo_reuse_expected`
   - `new_cycle_requires_confirmation`
4. 在 postmortem 中单独标记“参数错误”和“绑定恢复命中情况”。

## 8. 风险与权衡

### 8.1 风险

1. 恢复历史消息时，如果历史被强压缩，可能拿不到完整 tool 链。
2. 更强的 `create_task` 拒绝可能让部分原本“勉强可继续”的调用提前失败。

### 8.2 权衡

1. 对状态型入口工具，提前失败优于错误建 todo。
2. 即便历史恢复不完整，恢复失败也只是退回当前行为，不会比现状更差。

## 9. 验收建议

至少覆盖以下用例：
1. `create_task` 缺少 `subtasks` 时，返回强错误提示。
2. `create_task` 传空 `subtasks` 时，返回强错误提示。
3. 同一 `task_id` 的第二次 run 能恢复上一次的 todo 绑定。
4. 已恢复出 active todo 后，再次 `create_task` 会被拒绝。
5. 显式 `force_new_cycle=true` 时，仍允许新建 todo。
