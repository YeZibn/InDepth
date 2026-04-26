# S11-T5 Result Status 与证据要求（V1）

更新时间：2026-04-22  
状态：Draft  
对应任务：`S11-T5`

## 1. 目标

本任务用于定义 `runtime-v2` 第一版中：

1. `pass / partial / fail` 的正式语义
2. `result_status` 的收敛来源
3. 各结果态的最低证据要求

## 2. 正式结论

本任务最终结论如下：

1. 第一版保留 `pass / partial / fail`
2. `partial` 允许作为最终可交付结果存在
3. `result_status` 由 final verification 与 finalize 共同收敛
4. 不同结果态必须满足不同最低证据要求
5. `completed` 仍不等于 `pass`

## 3. Result Status 正式集合

第一版 `result_status` 正式集合如下：

1. `pass`
2. `partial`
3. `fail`

## 4. 为什么保留 `partial`

本任务明确保留 `partial`，原因如下：

1. 某些 run 可以正常结束
2. 某些 run 也能形成可交付结果
3. 但最终仍存在明确未闭合项、范围收缩或未满足点

如果只保留 `pass / fail`，会把这类情况压扁。

## 5. `partial` 的交付语义

本任务明确规定：

1. `partial` 可以作为最终结果交付给用户
2. 但必须有明确缺口说明
3. 不允许把“未完成”伪装成 `pass`

也就是说：

1. `partial` 不是失败
2. `partial` 是“有限完成 + 明确说明”

## 6. `result_status` 的收敛来源

第一版建议采用共同收敛方式：

1. final verification 提供验证判断
2. finalize 结合最终状态做结果收口

也就是说：

1. verifier 不单独决定最终 `result_status`
2. finalize 也不脱离 verification 单独拍板
3. 两者共同决定 `pass / partial / fail`

## 7. 三种结果态的正式语义

## 7.1 `pass`

表示：

1. 最终结果满足 `goal`
2. final verification 通过
3. 关键证据足以支撑最终输出
4. graph 已达到可交付收敛

## 7.2 `partial`

表示：

1. run 正常收尾
2. 已形成可交付结果
3. 但存在明确未闭合项、范围收缩或未满足点
4. 这些缺口已被正式说明

## 7.3 `fail`

表示：

1. 最终未形成可交付结果
2. 或 final verification 不通过且无法继续收敛
3. 或 run 在最终结果层面失败

## 8. 最低证据要求

## 8.1 `pass` 的最低证据要求

第一版建议至少满足：

1. final verification `pass`
2. `handoff` 完整存在
3. `evidence_refs` 足以支撑最终输出
4. `final_node_ids` 能锚定最终结果的主要来源
5. 不存在关键未闭合 node

## 8.2 `partial` 的最低证据要求

第一版建议至少满足：

1. 已形成正式 `handoff`
2. 有可交付 `final_output`
3. 有最低限度 evidence 支撑当前交付部分
4. 明确列出缺口、限制或未满足点

## 8.3 `fail` 的最低证据要求

第一版建议至少满足以下其一：

1. final verification `fail` 且无法继续回到 `execute` 收敛
2. 最终没有形成正式可交付输出
3. 关键证据缺失到无法支撑结果成立

## 9. 与 lifecycle_state 的关系

本任务再次明确：

1. `lifecycle_state=completed` 不等于 `result_status=pass`
2. run 可以 `completed + partial`
3. run 也可能 `completed + fail`

因此：

1. 生命周期是否正常结束
2. 最终结果是否通过

必须继续分开建模。

## 10. 与 handoff 的关系

本任务与统一 `handoff` 结构直接对齐：

1. `handoff` 是 `result_status` 判断的重要依据之一
2. `goal`
3. `final_output`
4. `evidence_refs`
5. `graph_summary`
6. `final_node_ids`

都直接参与 `pass / partial / fail` 的最终判定。

## 11. 对其他任务的直接输入

`S11-T5` 直接服务：

1. `S11-T6` finalize / verification pipeline
2. `S11-T2` RunOutcome 定义
3. `S4-T3` result_status 语义
4. `S12-T3` closeout 事件对齐

同时它直接依赖：

1. `S11-T3` 统一 handoff 结构
2. `S11-T4` finalize / verification / outcome 闭环
3. `S4-T3` 统一状态图

## 12. 本任务结论摘要

可以压缩成 5 句话：

1. 第一版保留 `pass / partial / fail`
2. `partial` 允许作为明确说明后的最终交付结果
3. `result_status` 由 final verification 与 finalize 共同收敛
4. 不同结果态有不同最低证据要求
5. `completed` 仍不等于 `pass`
