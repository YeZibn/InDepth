# S1-T4 Prompt 与状态边界规则（V1）

更新时间：2026-04-22  
状态：Draft  
对应任务：`S1-T4`

## 1. 目标

本任务用于定义 `runtime-v2` 第一版中 prompt 与正式状态模型的边界规则。

目标是：

1. 明确哪些状态允许进入 prompt
2. 明确哪些状态不能直接平铺注入 prompt
3. 避免 prompt 再次变成隐式主状态容器

## 2. 正式结论

本任务最终结论如下：

1. prompt 只消费最小正式状态视图，不消费整个 `RunContext`
2. graph 全图信息不直接进入主 prompt
3. `execute` 只读取当前 `active_node` 的局部图视图
4. graph 全图如有需要，只允许通过工具查看
5. recall 属于 `dynamic injection`，memory write 不进入 prompt 主链路

## 3. 不允许的做法

第一版明确禁止：

1. 把完整 `RunContext` 平铺注入 prompt
2. 把完整 `TaskGraphState` 平铺注入 prompt
3. 把完整 message history 作为正式状态替代品
4. 把 `handoff` 当 execute 常驻输入

## 4. Execute Prompt 允许消费的最小状态

第一版 `execute` prompt 建议只允许直接消费：

1. `run_identity.user_input`
2. `run_identity.goal`
3. `run_lifecycle.current_phase`
4. `runtime_state.active_node_id`
5. 当前 `active_node` 的局部视图
6. 必要时的 `finalize_return_input`

其中：

1. `finalize_return_input` 只在 verification fail 回退后出现
2. 当前 node 局部视图优先于 graph 全图摘要

## 5. 当前 Node 局部视图

第一版建议当前 node 局部视图至少包含：

1. 当前 node 的 `name`
2. 当前 node 的 `description`
3. 当前 node 的 `node_status`
4. 当前 node 的 `artifacts`
5. 当前 node 的 `evidence`
6. 当前 node 的 `notes`
7. 当前 node 的直接依赖摘要

这样做的原因是：

1. `step` 的职责是推进当前 `active_node`
2. 它不需要每次都看到整个 graph

## 6. Graph 全图信息的规则

本任务明确规定：

1. graph 全图信息不直接进入主 prompt
2. 如果主链路确实需要更多 graph 信息
3. 应通过正式工具查看，而不是通过大块注入

也就是说：

1. graph 总览是可查询的
2. 不是常驻注入的

## 7. Handoff 的边界

本任务与 `S1-T3` 直接对齐：

1. `handoff` 不进入普通 `execute` prompt
2. `handoff` 只进入 `finalize / verification / outcome` 链路
3. verification fail 后回灌 execute 的是 `finalize_return_input`

## 8. Dynamic Injection 的边界

第一版 `dynamic injection` 主要承接：

1. memory recall
2. preference recall
3. skill metadata
4. 必要的 prepare 产物注入

本任务明确规定：

1. recall 结果可以进入 `dynamic injection`
2. memory write 不进入主 prompt
3. preference write 不进入主 prompt

也就是说：

1. prompt 层只消费 recall
2. save/write 属于 finalize 后置挂点

## 9. Finalize Prompt 的状态消费

第一版 `finalize` prompt 允许消费：

1. `goal`
2. 当前已形成的最终输出候选
3. 关键 evidence refs
4. graph 收敛摘要
5. `final_node_ids`

它的职责是：

1. 生成正式 `handoff`
2. 进入 final verification

## 10. 边界总原则

本任务的总原则可以压缩成一句话：

`prompt 只消费为当前阶段决策所必需的最小正式状态视图，不承担主状态存储职责。`

## 11. 对其他任务的直接输入

`S1-T4` 直接服务：

1. `S1-T5` prompt assembly
2. `S3-T5` step / orchestrator 契约
3. `S4-T4` 极简 RunContext 结构
4. `S11-T6` finalize pipeline
5. `S8` 后续记忆接入

同时它直接依赖：

1. `S1-T2` prompt 分层结构
2. `S1-T3` handoff prompt contract
3. `S4-T4` 极简 RunContext

## 12. 本任务结论摘要

可以压缩成 5 句话：

1. prompt 不直接吃整个 `RunContext`
2. execute 只消费当前 node 的局部图视图
3. graph 全图如有需要，只允许通过工具查看
4. `handoff` 不进入普通 execute prompt
5. recall 进入 `dynamic injection`，write 不进入 prompt 主链路
