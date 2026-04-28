# S13 StepResult 与 Unified Runtime Memory 最小正式结构（T6-T7）

更新时间：2026-04-28  
状态：Draft

## 1. 目标

本设计稿用于收口 `S13-T6 ~ S13-T7`：

1. `StepResult` 的最小正式结构
2. unified `runtime memory` 与其中 `reflexion` entry 的最小正式结构

## 2. 正式结论摘要

当前正式结论如下：

1. `StepResult` 与 unified `runtime memory` 是两个独立对象
2. `StepResult` 主要服务 `Solver`
3. unified `runtime memory` 主要服务后续 `Solver`、`Re-plan`、`PreparePhase` 与 `Finalize`
4. 当前阶段所有主要阶段都读取全量 `runtime memory`
5. 当前不引入分阶段 `memory view`

## 3. StepResult 的正式位置

`StepResult` 是 `Actor -> Solver` 的最小运行时结构化交接对象。

它不是：

1. 额外的 step 总结层
2. 一次新的长文本生成
3. `Reflexion` 的替代物

它应当尽量从当前 step 的已有执行产物中收口，而不是额外增加一次重生成。

## 4. StepResult 的最小字段

当前 `StepResult` 的最小字段收敛为：

1. `result_refs`
2. `status_signal`
3. `reason`
4. `patch`

### 4.1 result_refs

1. 表示本轮新增、且可被后续阶段消费的结果引用集合
2. 当前不再拆分 `artifacts / evidence`
3. 继续沿用统一引用思路

### 4.2 status_signal

1. 是给 `Solver` 的局部推进信号
2. 当前最小枚举为：
   - `progressed`
   - `ready_for_completion`
   - `blocked`
   - `failed`

### 4.3 reason

1. 当前只在 `status_signal != progressed` 时要求必填
2. 供 `Solver / Reflexion / Re-plan` 消费

### 4.4 patch

1. 直接挂正式 `TaskGraphPatch`
2. 该字段应来自 tool 的结构化返回结果
3. 不再由 `Solver` 二次拼装 patch

## 5. Unified Runtime Memory 的正式位置

当前 `runtime memory` 采用统一记录流。

这意味着：

1. `context` 与 `reflexion` 不拆分存储区
2. 所有运行期记忆统一以 entry 形式写入
3. 设计目标是让时间线语义更自然，并能明确知道何时、因何发生反思

## 6. Unified Memory Entry 的最小字段

统一 memory entry 的最小字段包括：

1. `entry_id`
2. `entry_type`
3. `content`
4. `role`
5. `run_id`
6. `step_id`
7. `node_id`
8. `created_at`
9. `related_result_refs`
10. `tool_name`
11. `tool_call_id`

其中：

1. `entry_type` 当前区分：
   - `context`
   - `reflexion`
2. `tool_name / tool_call_id` 为可选字段
3. 该结构借鉴旧版 InDepth runtime memory 中的：
   - `role`
   - `tool_call_id`
   - `run_id`
   - `step_id`
   - `created_at`
4. 同时补入 v2 所需的 `node_id`

## 7. Reflexion Entry 的附加字段

当 `entry_type = reflexion` 时，附加字段最小收敛为：

1. `trigger`
2. `reason`
3. `next_try_hint`
4. `replan_signal`

其中：

1. `trigger` 当前最小集合为：
   - `completion_failed`
   - `blocked`
   - `failed`
2. `replan_signal` 当前最小语义为：
   - `none`
   - `suggested`

## 8. 与各阶段的接口关系

当前正式接口关系如下：

1. `Solver` 直接消费 `StepResult`
2. `Reflexion` 触发后向 unified `runtime memory` 追加 `entry_type = reflexion` 的 entry
3. `PreparePhase / ExecutePhase / Re-plan / Finalize` 当前都读取全量 `runtime memory`
4. `Re-plan` 判定与 `PreparePhase` 重规划都基于统一 memory 上下文
5. 若后续出现上下文膨胀、阶段噪声或性能问题，再单独引入分阶段 `memory view`

当前实现补充说明：

1. execute 链正在从“直接输出 `TaskGraphPatch`”迁移到“统一输出 `StepResult`”
2. 当前 orchestrator 已开始接入 `StepResult`
3. 但当前仍处于过渡态，实际只消费 `StepResult.patch`
4. `result_refs / status_signal / reason` 的更完整执行语义仍留待后续模块继续落地

## 9. 当前未展开部分

本模块当前明确不进入：

1. `result_refs` 的正式字段细节
2. `content` 字段与结构化附加字段之间的最小书写规则
3. 统一 `runtime memory` 的持久化模型与 API contract
4. 分阶段 `memory view` 的裁剪策略
