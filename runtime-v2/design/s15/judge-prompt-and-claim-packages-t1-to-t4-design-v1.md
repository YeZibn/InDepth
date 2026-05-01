# S15 Judge 型 Prompt 与结构化主张包（T1-T4）

更新时间：2026-05-02  
状态：Draft

## 1. 目标

本设计稿用于收口模块 24 当前已经讨论完成的 `T1 ~ T4`：

1. judge 型 prompt 的总体边界
2. `CompletionClaim` 的正式字段结构
3. `CompletionEvaluator` 的 prompt contract
4. `Handoff` 与 `RuntimeVerifier` 的 prompt contract

## 2. 正式结论摘要

当前正式结论如下：

1. `Actor` 负责生成 `CompletionClaim`
2. `CompletionEvaluator` 只审 `CompletionClaim`
3. `Finalize generator` 负责生成 `Handoff`
4. `RuntimeVerifier` 只审 `Handoff`
5. judge 型组件不再直接读取：
   - `runtime_memory_text`
   - `capability_text`
6. judge 型组件只返回判断结果，不直接产出动作

## 3. 模块 24 任务 01：judge 型 prompt 的总体边界

当前正式确认：

1. `Actor` 负责生成 `CompletionClaim`
2. `CompletionEvaluator` 只审 `CompletionClaim`
3. `Finalize generator` 负责生成 `Handoff`
4. `RuntimeVerifier` 只审 `Handoff`
5. `CompletionEvaluator` 不再直接读取 node 外围运行时上下文，所需最小 node 目标信息直接进入 `CompletionClaim`
6. `RuntimeVerifier` 不再直接读取额外上下文，只基于 `Handoff` 做判断
7. 两个 judge 型组件都不再直接读取：
   - `runtime_memory_text`
   - `capability_text`
8. 两个 judge 型组件都不负责：
   - 执行动作
   - 修改 graph
   - 重规划决策
9. 两个 judge 型组件都只返回 judge 结果，不直接产出动作

当前模块 24 的总体架构正式拆为两类 prompt：

1. 主链上下文型 prompt：
   - `Prepare`
   - `Execute / Actor`
   - `Node Reflexion`
   - `Run Reflexion`
   - `Finalize generator`
2. judge 型 prompt：
   - `CompletionEvaluator`
   - `RuntimeVerifier`

## 4. 模块 24 任务 02：`CompletionClaim` 的正式字段结构

当前 `CompletionClaim` 第一版正式字段结构如下：

1. `node_id`
2. `node_name`
3. `node_kind`
4. `node_description`
5. `completion_summary`
6. `completion_evidence`
7. `completion_notes`
8. `completion_reason`

当前正式边界如下：

1. `CompletionClaim` 是 actor 在准备完成当前 node 时，交给 `CompletionEvaluator` 的结构化完成主张包
2. `CompletionEvaluator` 只审 `CompletionClaim`，不再额外读取外围运行时上下文
3. `node_id / node_name / node_kind / node_description` 负责提供 node 目标锚点
4. `completion_summary / completion_evidence / completion_notes / completion_reason` 负责表达完成主张内容
5. `completion_evidence` 第一版固定为 `list[str]`
6. `completion_notes` 第一版保留
7. `node_kind` 第一版保留

当前明确不放入 `CompletionClaim` 的内容包括：

1. `user_input`
2. `goal`
3. `runtime_memory_text`
4. `capability_text`
5. `dependency_summaries`
6. `step history`
7. `request_replan`

## 5. 模块 24 任务 03：`CompletionEvaluator` 的 prompt contract

当前 `CompletionEvaluator` 第一版正式结论如下：

1. `CompletionEvaluator` 是 judge 型组件，只负责判断 `CompletionClaim` 是否足以支持当前 node completed
2. `CompletionEvaluator` 不负责：
   - 执行动作
   - 调度决策
   - 重规划决策
   - 生成下一步提示
3. `CompletionEvaluator` prompt 输出字段第一版固定为：
   - `result_status`
   - `summary`
   - `issues`
4. `result_status` 第一版只保留：
   - `pass`
   - `fail`
5. `summary` 第一版保留，为当前判断结果提供稳定摘要
6. `issues` 第一版保留，类型固定为 `list[str]`
7. 第一版明确不输出：
   - `action`
   - `next_attempt_hint`
   - `replan_hint`
   - `confidence`
   - `thought`

对应的 phase prompt 语义正式收口为：

1. 当前链路是 `completion evaluator`
2. 输入是一个 `CompletionClaim`
3. 任务是判断该 claim 是否足以证明当前 node 完成
4. 只能返回 judge 结果
5. 必须返回 JSON only

## 6. 模块 24 任务 04：`Handoff` 与 `RuntimeVerifier` 的 prompt contract

当前 `Handoff` 第一版继续保持当前 4 个字段：

1. `user_input`
2. `goal`
3. `graph_summary`
4. `final_output`

当前 `RuntimeVerifier` 第一版正式结论如下：

1. `RuntimeVerifier` 只审 `Handoff`
2. `RuntimeVerifier` 不再额外读取其他上下文
3. `RuntimeVerifier` 输出字段第一版固定为：
   - `result_status`
   - `summary`
   - `issues`
4. `result_status` 第一版只保留：
   - `pass`
   - `fail`
5. `issues` 第一版固定为 `list[str]`
6. `RuntimeVerifier` 不直接输出动作

对应的 phase prompt 语义正式收口为：

1. 当前链路是 `runtime verifier`
2. 输入是一个最终 `Handoff`
3. 任务是判断这个 `Handoff` 是否足以满足用户目标
4. 不补做工作，也不提出动作决策
5. 必须返回 JSON only

## 7. 当前仍未展开的内容

当前第一版仍未展开：

1. `CompletionClaim` 的最终代码模型与 actor 侧产出位置
2. judge 型 prompt 在统一 prompt 模块中的最终代码落点
3. `CompletionEvaluator / RuntimeVerifier` 接入统一 assembler 后的实际接线细节
