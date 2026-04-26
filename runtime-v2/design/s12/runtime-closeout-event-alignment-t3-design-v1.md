# S12-T3 Runtime / Closeout 事件对齐（V1）

更新时间：2026-04-22  
状态：Draft  
对应任务：`S12-T3`

## 1. 目标

本任务用于把当前已经收敛的 `step`、`handoff`、final verification、`RunOutcome` 闭环正式映射到 v2 事件模型中。

目标是：

1. 让事件模型跟上当前主链路设计
2. 明确哪些动作应成为正式事件
3. 明确 verification fail 回灌 `execute` 时的事件表达

## 2. 正式结论

本任务最终结论如下：

1. 事件模型应围绕 `step -> handoff -> final verification -> outcome` 建立闭环
2. `verification` 只保留 final verification 相关事件
3. verification fail 回到 `execute` 必须有显式事件
4. `handoff` 生成必须有显式事件
5. `StepResult` 的应用结果应有 node / graph 侧事件表达

## 3. 需要新增或强调的主干事件

基于当前设计，第一版建议正式保留以下事件组。

## 3.1 Step Events

建议保留：

1. `step_started`
2. `step_completed`
3. `step_failed`

作用：

1. 标记一次 `active_node` 单步推进的边界
2. 为 `StepResult` 的应用提供事件锚点

## 3.2 Node / Graph Apply Events

建议保留：

1. `node_patch_applied`
2. `node_status_changed`
3. `active_node_switched`
4. `followup_nodes_appended`
5. `node_abandoned`

作用：

1. 记录 `StepResult` 被 orchestrator 正式执行后的结果
2. 明确 graph 增量扩展与 node 状态迁移

## 3.3 Handoff Events

建议保留：

1. `handoff_built`
2. `handoff_attached_to_outcome`

作用：

1. 明确统一 `handoff` 的生成时机
2. 明确 `handoff` 如何进入 `RunOutcome`

## 3.4 Final Verification Events

建议保留：

1. `final_verification_started`
2. `final_verification_passed`
3. `final_verification_failed`

作用：

1. 明确 verification 只发生在 final 前
2. 与旧的中途 verification 语义做切割

## 3.5 Finalize Return Events

建议保留：

1. `finalize_return_prepared`
2. `execute_returned_from_finalize`

作用：

1. 标记 verification fail 的返工输入已写入
2. 标记当前 run 从 `finalize` 回到 `execute`

## 3.6 Outcome Events

建议保留：

1. `run_outcome_built`
2. `final_answer_committed`

作用：

1. 标记 `RunOutcome` 已正式生成
2. 标记最终 answer 已写入正式结果

## 4. 与当前 phase 设计的对齐

当前 phase 已收缩为：

1. `prepare`
2. `execute`
3. `finalize`

因此事件模型也应同步收缩：

1. 不再以中途 `verification phase` 作为主干事件域前提
2. verification 事件统一挂在 `finalize` 过程中
3. `phase_started / phase_completed` 仍保留，但 phase 集合只围绕 3 个正式 phase

## 5. 与 StepResult 的对齐

`StepResult` 当前包含：

1. `node_patch`
2. `node_decision`
3. `runtime_control`
4. `followup_nodes`

因此事件层不应只记录“step 跑过了”，还应记录“结果已被执行”。

推荐最小映射如下：

1. `node_patch` -> `node_patch_applied`
2. `switch` -> `active_node_switched`
3. `abandon` -> `node_abandoned`
4. `followup_nodes` -> `followup_nodes_appended`
5. node 状态变化 -> `node_status_changed`

## 6. Verification Fail 的事件表达

本任务明确规定：

1. verification fail 不经过 `external_signal_state`
2. 它通过 `finalize_return_input` 回灌 `execute`
3. 因此事件层应明确记录这次回灌

推荐顺序如下：

1. `final_verification_failed`
2. `finalize_return_prepared`
3. `phase_completed(finalize)`
4. `phase_started(execute)`
5. `execute_returned_from_finalize`

## 7. Payload 最小建议

这些新增事件的 `payload` 第一版建议保持摘要化。

示例：

### `active_node_switched`

1. `from_node_id`
2. `to_node_id`
3. `reason`

### `followup_nodes_appended`

1. `count`
2. `node_ids`
3. `source_node_id`

### `handoff_built`

1. `handoff_id`
2. `graph_id`
3. `final_node_ids`

### `finalize_return_prepared`

1. `issue_count`
2. `summary`

## 8. 与旧事件定义的关系

本任务不是推翻 `S12-T2`，而是对其做当前版本补强。

需要保留：

1. `phase_started`
2. `phase_completed`
3. `tool_called`
4. `tool_succeeded`
5. `tool_failed`

需要按当前设计重解释：

1. `verification_started`
2. `verification_passed`
3. `verification_failed`

建议在实现层改为更明确的 final 语义命名：

1. `final_verification_started`
2. `final_verification_passed`
3. `final_verification_failed`

## 9. 对其他任务的直接输入

`S12-T3` 直接服务：

1. `S11-T3` 统一 handoff
2. `S11-T4` finalize / verification / outcome 闭环
3. `S3-T5` step / orchestrator 契约
4. `S4-T4` 极简 RunContext 结构

同时它直接依赖：

1. `S12-T2` 正式事件模型
2. `S3-T5` StepResult 结构
3. `S11-T4` finalize 回灌 execute 规则

## 10. 本任务结论摘要

可以压缩成 5 句话：

1. 事件模型要显式覆盖 `step -> handoff -> final verification -> outcome`
2. verification 事件只保留 final verification 语义
3. verification fail 回到 `execute` 必须有显式事件
4. `StepResult` 的执行结果要在 node / graph 事件中落出来
5. 统一 `handoff` 的生成与挂接也应成为正式事件
