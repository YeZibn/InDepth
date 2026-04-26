# S11-T2 RunOutcome 结构定义（V1）

更新时间：2026-04-21  
状态：Draft  
对应任务：`S11-T2`

## 1. 目标

本任务用于定义 `runtime-v2` 中 `RunOutcome` 的正式结构。

目标是：

1. 把 `RunOutcome` 定义为一次运行结束后的正式收敛对象
2. 让 `RunOutcome` 成为 orchestrator、verification、observability 之间的共同接口
3. 让 `handoff` 成为 verification 可直接消费的正式字段

## 2. 正式结论

本任务最终结论如下：

1. `RunOutcome` 是运行结束后的正式收敛对象
2. `RunOutcome` 不是运行中状态对象
3. `RunOutcome` 直接包含 `handoff`
4. verification 直接消费 `RunOutcome`，尤其直接消费其中的 `handoff`
5. 不额外设计单独的 verification DTO 层

## 3. RunOutcome 的角色

`RunOutcome` 的定位是：

1. 一次 run 结束后的标准输出
2. verification 的直接输入
3. 事件模型与 post-run 产物的结构化来源之一

它不负责：

1. 表达运行中状态推进
2. 替代 `RunContext`
3. 承载完整 task graph 或完整工具原始日志

## 4. 第一版建议结构

`RunOutcome` 第一版建议至少包含以下字段组：

## 4.1 identity

1. `task_id`
2. `run_id`
3. `session_id`

作用：

1. 标识这次运行属于哪个任务、哪个 run、哪个会话上下文

## 4.2 goal / input

1. `user_input`
2. `goal`

作用：

1. 保留原始任务输入
2. 提供 verification 和 postmortem 的目标基准

## 4.3 runtime result

1. `final_answer`
2. `runtime_state`
3. `runtime_status`
4. `stop_reason`

这里明确保留两类状态：

1. `runtime_state`
   表达运行态语义，例如 `completed` / `paused` / `failed`
2. `runtime_status`
   表达结果态语义，例如 `ok` / `error`

## 4.4 execution evidence

1. `tool_results`
2. `tool_failures`
3. `task_graph_summary`

这里的约束是：

1. `tool_results` 只保留关键摘要
2. 不把完整原始工具日志塞进 `RunOutcome`
3. `task_graph_summary` 只保留摘要，不嵌入整个 graph

## 4.5 handoff

1. `handoff`

本任务的关键结论就是：

1. `handoff` 是 `RunOutcome` 的正式字段
2. verification 直接消费这个字段
3. 不再额外设计第二层 handoff 包装结构

## 5. Handoff 的地位

在 v2 第一版中，`handoff` 的地位明确如下：

1. 它属于 `RunOutcome`
2. 它不是 verifier 外部临时拼装物
3. 它是 main chain closeout 的正式产物
4. 它直接作为 verification 的输入材料

这意味着：

1. orchestrator 或 finalize phase 负责生成 `handoff`
2. verification 读取 `RunOutcome.handoff`
3. event / postmortem 也可以基于同一份 handoff 对齐

## 6. 与运行中状态的关系

这里明确区分两类对象：

### 运行中

1. `RunContext`
2. `PhaseState`
3. `TaskGraphState`

### 运行结束后

1. `RunOutcome`

这个区分是必要的，因为：

1. 运行中对象解决“怎么推进”
2. `RunOutcome` 解决“怎么验证、怎么交接、怎么沉淀”

## 7. 与 verification 的关系

`RunOutcome` 与 verification 的关系直接定义如下：

```text
RuntimeOrchestrator / FinalizePhase
  -> RunOutcome
  -> Verification
```

verification 直接消费：

1. `RunOutcome.user_input`
2. `RunOutcome.goal`
3. `RunOutcome.final_answer`
4. `RunOutcome.runtime_state`
5. `RunOutcome.runtime_status`
6. `RunOutcome.stop_reason`
7. `RunOutcome.tool_failures`
8. `RunOutcome.task_graph_summary`
9. `RunOutcome.handoff`

其中：

1. `handoff` 是最关键的结构化输入
2. 但 verification 不只看 `handoff`，也看运行结果与关键执行摘要

## 8. 第一版边界约束

为避免后续结构膨胀，第一版明确 4 条规则：

1. `RunOutcome` 不承载完整 message history
2. `RunOutcome` 不承载完整 task graph
3. `RunOutcome` 不承载完整原始工具调用日志
4. `RunOutcome` 必须保留足够的 verification 关键输入

## 9. 对其他任务的直接输入

`S11-T2` 将直接服务：

1. `S11-T3` handoff 结构定义
2. `S11-T6` finalizing / verification 衔接流程
3. `S12-T2` 事件模型
4. `S12-T3` 证据链模型
5. `S3-T6` finalizing pipeline 主干

同时它直接依赖：

1. `S3-T2` RuntimeOrchestrator 定义
2. `S4-T2` 核心状态对象定义
3. `S6-T2` tool 协议

## 10. 本任务结论摘要

可以压缩成 5 句话：

1. `RunOutcome` 是运行结束后的正式收敛对象
2. `RunOutcome` 与运行中状态对象分离
3. `handoff` 是 `RunOutcome` 的正式字段
4. verification 直接消费 `RunOutcome`，尤其直接消费 `handoff`
5. `RunOutcome` 只保留关键执行摘要，不承载完整原始运行日志
