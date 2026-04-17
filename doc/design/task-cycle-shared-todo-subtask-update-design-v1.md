# InDepth Task 周期共享 Todo 与 Subtask 增量更新设计稿 V1

更新时间：2026-04-17  
状态：Draft

## 1. 背景

当前 Todo 编排已经具备较完整的任务拆分、状态流转、失败兜底与恢复能力，但在“一个 task 周期里 todo 应该如何被复用”这件事上，仍然存在两类不够稳定的实践：

1. 同一 task 周期内可能重复创建多个 todo，导致上下文分散。
2. subtask 一旦创建后更偏向静态记录，缺少清晰的“局部更新”语义。

这会带来几个实际问题：
1. 进度被拆散到多个 todo 文件里，主线不清晰。
2. 同一个 task 周期中的计划调整难以沉淀为结构化变更。
3. Runtime、Agent 和恢复链路更难稳定复用同一份执行上下文。

因此，本稿提出一个更收敛的原则：
1. 一个 task 周期共用一个 todo。
2. 允许对 todo 中单个 subtask 做增量更新，而不是频繁整体重写。

## 2. 目标

1. 明确“task 周期”与“todo 实体”的一对一关系。
2. 定义 subtask 可被增量更新的边界、时机与数据规则。
3. 降低重复建 todo 带来的上下文碎片化。
4. 为后续 Runtime 绑定、失败恢复、审计回放提供稳定事实源。
5. 明确 subtask 失败后的默认恢复原则，减少恢复链路对主线的污染。

## 3. 非目标

1. 本稿不重新设计 todo 的完整状态机。
2. 本稿不引入新的前端交互形态。
3. 本稿不要求本轮立即完成所有工具接口改造。

## 4. 核心设计

### 4.1 一个 Task 周期共用一个 Todo

定义：
1. 一个 task 周期，从任务开始到任务完成、放弃或显式结束，默认只对应一个 `todo_id`。
2. 该 `todo_id` 作为该周期内规划、执行、恢复、审计的统一载体。
3. Runtime 应将该 `todo_id` 绑定为当前 task 的 `active_todo_id`，并在本次 task 周期内持续复用。

设计判断：
1. todo 应被视为 task 周期的“共享执行面板”，而不是某一步动作的临时清单。
2. task 周期内出现的新信息，优先更新已有 todo，而不是新建 todo。

带来的收益：
1. 进度连续，可直接观察任务主线演进。
2. 减少 Agent 在多个 todo 之间切换上下文的成本。
3. 恢复链路可以稳定挂靠到同一 `todo_id`。
4. 最终报告与 postmortem 更容易回放完整过程。

### 4.2 Todo 与本次 Task 的绑定规则

为避免同一 task 周期内 todo 漂移，本稿进一步要求：
1. 一个 todo 对应本次 task。
2. 一个 task 在任意时刻只应有一个 `active_todo_id`。
3. 一旦本次 task 已创建 todo，后续 todo 相关操作默认都应落到该 `active_todo_id` 上。

建议 Runtime 维护最小绑定上下文：
1. `active_todo_id`
2. `task_scope_status`
3. `todo_bound_at`

字段含义：
1. `active_todo_id`：当前 task 周期绑定的唯一 todo。
2. `task_scope_status`：当前 task 是否仍处于进行中，用于决定是否允许继续复用。
3. `todo_bound_at`：绑定发生时间，便于审计与问题排查。

绑定规则：
1. 首次 `create_task` 成功后，立即写入 `active_todo_id`。
2. 在 task 周期结束前，默认禁止再次创建新的 todo 并替换绑定。
3. 若后续只是补充计划、推进状态、追加恢复动作，应复用当前 `active_todo_id`。
4. 只有在“当前 task 已结束”或“显式开启新 task 周期”时，才允许创建并绑定新的 todo。

设计判断：
1. 这里的“静态保存”应限定在本次 task 的 runtime 上下文内，而不是跨 task 的全局静态变量。
2. 这样既能保证本次 task 的执行连续性，也能避免下一次 task 误复用上一次 todo。

### 4.3 允许对单个 Subtask 做增量更新

subtask 不应被视为一次性静态声明，而应允许在 task 周期内按需演化。

允许更新的典型场景：
1. 原描述过于粗糙，需要补充分工或验收口径。
2. 任务被进一步拆细，需要补充依赖或说明。
3. 执行中发现优先级需要调整。
4. 任务状态发生变化，如 `pending -> in-progress -> completed`。
5. 失败后需要补充 `fallback_record`、阻塞原因或下一步动作。

设计原则：
1. 更新应优先落在单个 subtask 维度。
2. 更新应尽量是“字段级”而不是“整段重写”。
3. 更新后的 subtask 仍应保留稳定身份，避免因为改名而丢失关联。

### 4.4 Subtask 失败后默认原地恢复

本稿进一步定义 subtask 失败后的默认处理原则：
1. subtask 失败后，默认围绕原 subtask 继续恢复。
2. follow-up subtask 不是失败后的默认动作，而是恢复升级动作。
3. 只有当恢复过程已经构成独立工作单元时，才允许派生新的 recovery subtask。

设计判断：
1. `subtask` 是 task 主线中的长期对象，应持续代表原始目标。
2. 一次失败只表示“这次推进没有成功”，不应默认把主线切换到新 subtask。
3. 恢复动作首先服务于“让原 subtask 继续完成”，而不是立即扩张 todo 结构。

这样做的目的：
1. 保持 todo 主线稳定。
2. 降低失败后 todo 快速膨胀的风险。
3. 让用户和 Runtime 都能更清楚地回答“原 subtask 现在到底进行到哪里”。

### 4.5 Failure、Status 与 Recovery 的职责边界

当前最容易混乱的，是把失败事实、subtask 状态和恢复动作混在一起。本稿建议显式区分三层语义：

1. `subtask`
   长期工作单元，表示“要完成什么”。

2. `fallback_record`
   最近一次未完成或失败尝试的结构化事实，表示“刚刚发生了什么问题”。

3. `recovery_decision`
   下一步恢复策略，表示“接下来准备怎么做”。

设计要求：
1. 不应把 `fallback_record` 直接等同于 subtask 本身。
2. `failed/partial/awaiting_input/timed_out` 更接近一次推进结果，而不应天然被理解为 subtask 生命周期终态。
3. 恢复规划应优先回答“能否原地恢复”，其次才是“是否需要派生新 subtask”。

## 5. 数据模型建议

### 5.1 Subtask 需要稳定标识

当前很多逻辑仍以 `subtask_number` 作为定位手段，但如果未来允许更灵活的编辑，仅依赖顺序编号会有几个问题：
1. 重排后容易产生歧义。
2. 文案变更后不利于追踪历史。
3. 并发更新时更容易发生误覆盖。

因此建议在保留 `subtask_number` 的同时，为每个 subtask 增加稳定标识：
1. `subtask_id`：todo 内稳定唯一，不因标题改动而变化。
2. `subtask_number`：面向展示与人工阅读，可继续保留。

建议关系：
1. `subtask_id` 作为内部更新锚点。
2. `subtask_number` 作为排序视图与工具兼容层。

### 5.2 建议允许更新的字段

建议开放以下字段的增量更新：
1. `title` / `name`
2. `description`
3. `status`
4. `priority`
5. `dependencies`
6. `acceptance_criteria`
7. `split_rationale`
8. `owner`
9. `kind`
10. `fallback_record`
11. `notes`

更新约束：
1. `subtask_id` 创建后不可修改。
2. 已完成的 subtask 默认允许补充说明，但不应随意改回未开始状态，除非显式重开。
3. 若更新会破坏依赖闭环，系统应拒绝或要求显式确认。

### 5.3 Task 级 Todo 绑定字段

除 subtask 字段外，建议 Runtime 或 Todo 上下文显式保存以下 task 级绑定信息：
1. `active_todo_id`
2. `bound_task_id` 或等价 task runtime 标识
3. `binding_state`

建议约束：
1. `binding_state` 至少区分 `unbound`、`bound`、`closed`。
2. 当 `binding_state=bound` 时，普通流程默认不可再次调用 `create_task` 创建新 todo。
3. 若确需切换，必须先结束当前 task 周期，或显式触发“新周期切换”语义。

### 5.4 Failure 与 Recovery 字段建议

为支持“默认原地恢复”的设计，建议在现有模型上明确以下语义：

1. `fallback_record`
   记录最近一次失败/未完成尝试的事实，不负责替代整个 subtask。

2. `recovery_decision`
   应至少包含一个关键判断：
   - `can_resume_in_place`
   - `needs_derived_recovery_subtask`

3. 若派生 recovery subtask，建议显式挂回原 subtask：
   - `origin_subtask_id`
   - 或兼容层字段 `origin_subtask_number`

建议解释：
1. `can_resume_in_place=true` 表示下一步仍应继续围绕原 subtask 推进。
2. `needs_derived_recovery_subtask=true` 表示恢复动作已独立到需要单独编排。
3. 派生 subtask 若没有来源锚点，todo 很容易退化成恢复碎片堆。

### 5.5 Failure Taxonomy 建议

为减少当前失败分类“偏 runtime、弱 subtask 语义”的问题，建议把失败信息拆成两层：

1. `failure_state`
   表示这次推进的结果形态。

2. `reason_code`
   表示导致该结果的主要原因。

建议的 `failure_state`：
1. `failed`
2. `blocked`
3. `partial`
4. `awaiting_input`
5. `timed_out`

建议的 `reason_code`：
1. `dependency_unmet`
   依赖未满足，当前 subtask 不能推进。

2. `missing_context`
   缺少上下文、材料、约束或必要背景，系统无法安全继续。

3. `waiting_user_input`
   必须等待用户补充信息或做决策。

4. `tool_invocation_error`
   工具参数、调用方式或执行路径不正确。

5. `execution_environment_error`
   环境、权限、外部系统或资源状态导致执行失败。

6. `validation_failed`
   已产生结果，但未通过验收或验证。

7. `budget_exhausted`
   因步数、时间或预算耗尽而未完成。

8. `partial_progress`
   已有部分有效产出，但尚未闭环。

9. `orphan_subtask_unbound`
   Runtime 已进入 todo 流，但失败发生时未绑定到具体 subtask。

设计说明：
1. `failure_state` 负责表达“当前停在什么结果形态”。
2. `reason_code` 负责表达“为什么会停在这里”。
3. `orphan_subtask_unbound` 属于 runtime 级兜底，不应被视为正常 subtask failure。

## 6. 接口语义建议

### 6.1 区分“新增”“更新”“整体替换”

建议把 todo 相关写操作明确分成三类：

1. `append_followup_subtasks`
   用于追加新的 subtask，不修改既有 subtask。
   在恢复链路中，它应被视为升级动作，而不是默认动作。

2. `update_subtask`
   用于按 `todo_id + subtask_id` 或兼容的 `todo_id + subtask_number` 更新单个 subtask 的部分字段。

3. `replace_todo_structure`
   用于极少数需要整体重构计划的场景，应视为高风险操作。

这样做的原因：
1. 避免所有修改都退化成“重写整个 todo”。
2. 降低并发编辑时误覆盖其他 subtask 的概率。
3. 让审计日志更容易表达“这次只改了哪个 subtask 的哪些字段”。

同时建议补一条 task 级约束：
1. 若当前已存在 `active_todo_id`，则 `create_task` 默认应被拒绝，或仅在显式新周期参数下允许执行。

### 6.2 更新操作应采用 Patch 语义

`update_subtask` 建议采用 patch 而非 replace 语义：
1. 仅传入需要变更的字段。
2. 未提供的字段保持不变。
3. 对数组字段需要明确策略，如 `replace`、`append`、`remove`。

推荐最小接口语义：
1. `todo_id`
2. `subtask_id` 或 `subtask_number`
3. `fields_to_update`
4. `update_reason`（可选，但建议记录）

### 6.3 恢复决策应先判断是否可原地恢复

针对失败后的恢复规划，建议将判断顺序收紧为：

1. 先判断是否可以原地恢复原 subtask。
2. 只有原地恢复不合适时，才判断是否派生 recovery subtask。
3. `append_followup_subtasks` 不应作为 recovery planner 的默认输出。

推荐恢复决策最小语义：
1. `todo_id`
2. `subtask_id` 或 `subtask_number`
3. `can_resume_in_place`
4. `needs_derived_recovery_subtask`
5. `primary_action`
6. `rationale`

设计要求：
1. 如果恢复动作的目标仍然是“完成原 subtask”，则优先原地恢复。
2. 如果恢复动作已变成独立工作目标，才允许派生新的 recovery subtask。

### 6.4 Failure 判断应以规则为主，LLM 为辅

失败分类与恢复分叉不建议完全交给 LLM，而应采用“规则优先，LLM 兜底”的模式。

建议的判断顺序：
1. 先判断结构性条件：
   - 是否已绑定 `active_todo_id`
   - 是否已绑定 active subtask
   - 是否达到 retry budget
   - 是否存在必需输入缺失

2. 再判断 subtask 语义事实：
   - 是否缺依赖
   - 是否缺上下文
   - 是否已有部分产出
   - 是否验证失败

3. 再判断执行失败事实：
   - 是否工具调用失败
   - 是否环境失败
   - 是否预算耗尽
   - 是否 runtime 被截断

4. 只有规则无法充分分辨时，才允许 LLM 参与：
   - 补充 `reason_detail`
   - 生成恢复建议文案
   - 在模糊场景下辅助判断恢复路径

设计要求：
1. `failure_state` 与 `reason_code` 的主判定应是 deterministic 的。
2. `can_resume_in_place` 与 `needs_derived_recovery_subtask` 的控制位也应优先走规则判断。
3. LLM 更适合作为 planner，而不是唯一裁判。

## 7. 生命周期规则

### 7.1 何时复用已有 Todo

满足以下条件时，应复用当前 task 周期的已有 todo：
1. 主目标未变。
2. 当前工作仍属于既有交付范围。
3. 只是补充步骤、修正计划或推进执行状态。
4. 当前 task 的 `active_todo_id` 仍处于绑定中。

典型例子：
1. 代码实现后补测。
2. 修复验证失败。
3. 补充遗漏的分析步骤。
4. 基于失败现场生成恢复动作。

### 7.2 何时才应该新建 Todo

只有在以下场景才建议新建 todo：
1. 用户目标已经切换到新的主任务。
2. 原 task 周期已经明确结束。
3. 新工作与原 todo 的上下文边界明显不同，继续混用会损害可读性。
4. Runtime 已显式解除旧的 `active_todo_id` 绑定，准备进入新的 task 周期。

换句话说，“发现原 subtask 设计得不好”不应成为新建 todo 的理由，优先选择更新已有 subtask 或追加 follow-up subtasks。

### 7.3 何时允许派生 Recovery Subtask

subtask 失败后，只有满足以下任一条件时，才建议派生 recovery subtask：
1. 恢复动作本身已经是独立目标，例如根因分析、补充前置依赖、等待外部确认。
2. 恢复过程会长时间偏离原 subtask，继续塞在原 subtask 内会损害语义清晰度。
3. 恢复链路需要拆成多个可协作步骤，例如 diagnose / repair / verify。
4. 原 subtask 需要保持稳定语义，不适合承载大量补救细节。

反过来说，以下情况应优先原地恢复，而不是派生：
1. 小范围重试。
2. 修复后重试。
3. 等待输入后继续执行原目标。
4. 对原 subtask 做收敛性的补充说明或局部修正。

### 7.4 Failure 判断链路建议

为了让失败分类更贴近 subtask 恢复语义，建议将判断链路从“runtime 停止原因驱动”调整为“subtask 推进事实驱动”：

1. 先看 subtask 语义事实。
2. 再看执行失败事实。
3. 最后才参考 runtime stop reason。

当前不建议直接用 runtime stop reason 作为主分类轴，原因是：
1. 它更适合说明“本次运行怎么停了”。
2. 但未必能准确说明“这个 subtask 为什么没能继续完成”。

例如：
1. `max_steps_reached` 更适合作为 `budget_exhausted` 的辅助信号，而不是唯一证据。
2. `model_failed` 不应一律压成粗粒度的 `tool_error`，还应区分调用问题和环境问题。
3. `length/content_filter` 更适合作为执行异常信号，而不是天然归入宽泛的“不可验证”。

因此，建议 Runtime 输出候选失败信号，而由 todo/recovery 层完成贴近 subtask 语义的归类。

## 8. 审计与并发考虑

### 8.1 审计要求

每次 subtask 更新建议记录最小变更事件：
1. 更新目标：`todo_id`、`subtask_id`
2. 更新前后的字段差异
3. 更新时间
4. 更新来源：主 Agent、SubAgent、Runtime、恢复逻辑
5. 更新原因

这样可以支持：
1. 回放 subtask 是如何逐步演化的。
2. 判断某次失败是否源于错误更新。
3. 在最终报告中区分“原计划”与“执行中修正”。

对于失败恢复，还建议额外记录：
1. 是否尝试原地恢复。
2. 是否升级为派生 recovery subtask。
3. 若已派生，派生 subtask 与原 subtask 的关联关系。
4. `failure_state` 与 `reason_code` 的最终判定来源，是规则还是 LLM 辅助。

### 8.2 并发安全

若多个执行单元可能更新同一个 todo，应优先避免整份文件覆盖。

最低要求：
1. 更新单元尽量收敛到单个 subtask。
2. 通过稳定 `subtask_id` 定位。
3. 若写入前发现目标 subtask 已被其他流程更新，应进行冲突检测或重读。

## 9. 兼容策略

为降低改造成本，建议分阶段推进：

### 9.1 V1 兼容策略

1. 继续允许通过 `subtask_number` 更新。
2. 对外先补充“共享 todo + 单 subtask 更新”的规则说明。
3. 工具层先支持最小 patch 语义，不强制一次性引入完整变更历史。

### 9.2 后续演进

1. 引入 `subtask_id`。
2. 引入结构化更新事件日志。
3. 对高风险整体重写操作增加额外保护。
4. 让 Runtime 更明确地区分“复用当前 todo”与“新建 todo”。
5. 让 recovery planner 从“默认 append follow-up”转向“默认原地恢复，必要时派生”。
6. 将当前偏 runtime 的失败分类，收敛为偏 subtask 语义的 failure taxonomy。

## 10. 收益与风险

### 10.1 收益

1. todo 从“静态计划单”提升为 task 周期内的动态事实源。
2. 执行上下文更稳定，降低信息碎片化。
3. subtask 更贴近真实执行过程，恢复与补救链路更自然。
4. 为后续自动化编排和审计追踪打下更好的基础。
5. 失败后主线更稳定，todo 不容易退化成恢复碎片堆。

### 10.2 风险

1. 如果没有稳定 `subtask_id`，局部更新仍可能受到编号漂移影响。
2. 如果 patch 语义不清楚，数组字段更新容易产生歧义。
3. 如果缺少冲突检测，并发更新仍可能相互覆盖。

## 11. 结论

本稿建议将 todo 明确定位为“单个 task 周期的共享执行面板”，并允许 subtask 在该周期中持续增量演化。

核心原则收敛为三条：
1. 一个 task 周期默认共用一个 todo。
2. subtask 应允许细粒度更新，且更新优先按稳定标识进行。
3. subtask 失败后默认原地恢复，必要时才派生 recovery subtask。

这套规则能够在不推翻现有 todo 体系的前提下，显著提升执行连续性、恢复闭环能力和审计可读性，适合作为后续工具与 Runtime 改造的统一设计前提。
