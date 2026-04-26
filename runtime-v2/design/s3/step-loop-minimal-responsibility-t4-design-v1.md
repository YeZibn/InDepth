# S3-T4 Step Loop 最小职责定义（V1）

更新时间：2026-04-22  
状态：Draft  
对应任务：`S3-T4`

## 1. 目标

本任务用于定义 `runtime-v2` 中 step loop 的最小职责。

目标是：

1. 明确 execute 期间每一轮 step 到底负责什么
2. 明确 step loop 如何读取 `RunContext`
3. 明确 step loop 与 `task graph / active node` 的交互边界
4. 避免 step loop 重新膨胀成 runtime 的第二个总控中心

## 2. 正式结论

本任务最终结论如下：

1. step loop 只负责“单步驱动”
2. `prompt build` 在进入 execute 前完成，不属于 step loop 的主职责
3. `compression` 允许在 step loop 中触发
4. step loop 可以通过主链路状态工具结果更新 `TaskGraphState`
5. step loop 关心 `messages`，但 `messages` 不进入 `RunContext`
6. step loop 每轮默认绑定一个 `active node`
7. step loop 负责推进当前 `active node`，不负责定义 graph 结构与调度规则

## 3. Step Loop 的最小职责

第一版 step loop 只保留 6 件事：

1. 读取当前 `RunContext`
2. 组装本轮模型输入
3. 调用模型
4. 处理 tool call 或 assistant 输出
5. 更新 `RunContext`
6. 判断是否继续下一轮 execute

这意味着：

1. step loop 是“单步驱动器”
2. 它不是 runtime 总控
3. 它不是 graph 规则中心

## 4. Step Loop 不负责什么

第一版明确规定，step loop 不直接负责：

1. phase 切换
2. task graph 结构定义
3. verification
4. memory seed 生成
5. prompt build 的前置召回逻辑

这些职责分别属于：

1. `RuntimeOrchestrator`
2. `TaskGraphState / graph rules`
3. post-chain verification
4. handoff / closeout
5. prompt build 阶段

## 5. RunContext 的分层读取

step loop 读取 `RunContext` 时，不应把它当作无结构大包，而应按层访问。

第一版建议分成 4 层：

## 5.1 主状态层

step loop 必须直接读取：

1. `lifecycle_state`
2. `phase_state`
3. `result_status`
4. `task_graph_state`
5. `stop_reason`
6. `final_answer`

作用：

1. 判断当前 run 是否还能继续
2. 判断当前 execute 是否成立
3. 判断当前 active node 是谁

## 5.2 执行摘要层

step loop 经常读取和写回：

1. `tool_results`
2. `tool_failures`
3. 最近一步执行摘要
4. 关键 `artifacts / evidence / notes`

作用：

1. 接住当前 step 的工具结果
2. 把 step 执行结果写回上下文

## 5.3 Prompt / Context 组装层

step loop 消费但不负责生成：

1. `base_prompt`
2. `phase_prompt`
3. `dynamic_injections`
4. 其他进入当前模型调用的上下文摘要

作用：

1. 组装本轮模型输入

## 5.4 运行保障层

step loop 为了能继续运行，需要读取：

1. `compression_state`
2. `compression_summary`
3. `context_budget`

作用：

1. 判断是否需要压缩
2. 判断上下文预算是否接近阈值

## 6. Messages 与 Compression 的边界

### Messages

本任务正式规定：

1. `messages` 不进入 `RunContext`
2. `messages` 视为 runtime 内部工作缓存
3. step loop 可以使用消息系统，但不把完整消息历史纳入核心状态

### Compression

compression 属于主链路运行保障步骤，因此：

1. compression 可以在 step loop 中触发
2. 但 `RunContext` 只持有 compression 的运行状态摘要
3. 不持有压缩前后正文和完整消息内容

## 7. Step 与 Task Graph 的交互

本任务的核心边界是：

`step loop 负责执行当前 active node 的单步推进，不负责定义 task graph 的结构与调度规则。`

## 7.1 Step Loop 的前提输入

每轮 step 开始时，至少要从 `RunContext` 里拿到：

1. 当前 `active_node`
2. 当前 `node_status`
3. graph 是否允许继续推进
4. 当前是否仍处在 `executing`

## 7.2 Step Loop 的执行目标

step loop 不是泛泛地“跑一轮模型”，而是：

`围绕当前 active node 推进一次最小执行闭环。`

因此第一版规定：

1. 每轮 step 默认只服务一个 `active node`
2. 不在一轮内并发处理多个 node

## 7.3 Step Loop 可以触发的 Task 侧变化

step loop 本身不制定 graph 规则，但可以通过工具结果或执行结果触发以下更新：

1. 当前 node 从 `ready -> running`
2. 当前 node 从 `running -> completed`
3. 当前 node 从 `running -> blocked`
4. 当前 node 从 `running -> failed`
5. 当前 node 写入 `artifacts`
6. 当前 node 写入 `evidence`
7. 当前 node 写入 `notes`

## 7.4 Step Loop 不应该做的事

第一版明确禁止：

1. step loop 自己决定 graph 拓扑
2. step loop 自己新增复杂依赖关系
3. step loop 跳过 graph 规则直接发明下一个 node
4. step loop 把调度规则硬编码在循环里

## 7.5 下一 Node 的选择权

本任务正式规定：

1. 当当前 node 结束后，下一 node 的选择权不属于 step loop
2. 下一 node 的选择由 task graph 状态推进规则决定
3. orchestrator / graph 层读取更新后的 `TaskGraphState`，再确定新的 `active node`

## 8. 对工具语义感知的依赖

step loop 与 `S6-T3` 对齐如下：

1. step loop 只对主链路状态工具保留最小语义感知
2. 对通用执行工具只消费统一 tool protocol
3. 对 `memory` / `search` / `subagent` 工具只做域级识别

## 9. 对其他任务的直接输入

`S3-T4` 直接服务：

1. `S3-T5` runtime skeleton
2. `S5-T4` 执行图关系模型
3. `S6-T4` 工具分域结构
4. `S11-T3` handoff 结构
5. `S12-T3` 证据链模型

同时它直接依赖：

1. `S3-T3` phase engine 接口
2. `S4-T3` 统一状态图
3. `S5-T3` 最小执行单元定义
4. `S6-T3` runtime 与工具语义耦合策略

## 10. 本任务结论摘要

可以压缩成 5 句话：

1. step loop 第一版只负责单步驱动
2. 它读取 `RunContext` 时必须按层访问，而不是无结构读取
3. `messages` 不进入 `RunContext`，但 compression 运行状态进入
4. 每轮 step 默认绑定一个 `active node`
5. step loop 推进当前 node，但不定义 task graph 的结构与调度规则
