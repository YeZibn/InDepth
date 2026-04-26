# S6-T4 工具分域结构（V1）

更新时间：2026-04-22  
状态：Draft  
对应任务：`S6-T4`

## 1. 目标

本任务用于定义 `runtime-v2` 第一版正式工具分域结构。

目标是：

1. 让工具域和当前主链路结构对齐
2. 明确不同工具域分别挂在哪一段链路
3. 避免 capability、state、closeout、旁路能力继续混杂

## 2. 正式结论

本任务最终结论如下：

1. v1 工具分成 5 个正式域
2. 工具分域围绕 `step / task graph / finalize / sidecar` 组织
3. 主链路只对 graph 状态工具保留显式语义感知
4. finalize / handoff 相关工具单独成域
5. memory / search / subagent 保持旁路域，不进入主状态流核心

## 3. 第一版正式分域

第一版建议采用以下 5 个正式域：

1. `execution`
2. `task_graph`
3. `closeout`
4. `memory_search`
5. `subagent`

## 4. 各域定义

## 4.1 execution

这一域承载通用执行能力。

典型工具包括：

1. `bash`
2. `read_file`
3. `write_file`
4. `get_current_time`

这一域的特点是：

1. 服务 `step` 执行
2. 不直接推进 graph 主状态
3. runtime 不对其做业务语义感知

## 4.2 task_graph

这一域承载 graph / node 的正式状态工具。

典型工具包括：

1. `plan_task_graph`
2. `update_node_status`
3. `get_next_node`
4. `reopen_node`
5. `append_followup_nodes`

这一域的特点是：

1. 它直接作用于 `TaskGraphState`
2. 它直接影响 `active_node`
3. runtime 对这一域保留显式语义感知

## 4.3 closeout

这一域承载进入 `finalize` 后的正式收尾工具。

典型工具包括：

1. `build_handoff`
2. `run_final_verification`
3. `build_run_outcome`

这一域的特点是：

1. 它服务最终交付闭环
2. 它不参与中途 node 推进
3. 它直接对接 `handoff`、`VerificationResult`、`RunOutcome`

## 4.4 memory_search

这一域承载 recall / retrieval 类旁路能力。

典型工具包括：

1. memory recall 工具
2. preference recall 工具
3. search 工具

这一域的特点是：

1. 服务上下文补充
2. 不直接推进 graph
3. runtime 只做域级识别，不做深入语义处理

## 4.5 subagent

这一域承载协作型旁路能力。

典型工具包括：

1. subagent 创建工具
2. subagent 执行工具
3. subagent 结果收集工具

这一域的特点是：

1. 服务协作执行
2. 不直接替代主链路 graph 状态工具
3. runtime 第一版只做域级识别

## 5. 为什么不再拆 node 独立域

前面的协议文档中使用过：

1. `task_graph`
2. `node`

但按当前主链路设计，第一版更适合把它们合并到一个正式域：

1. `task_graph`

原因是：

1. `node` 级动作本质上仍属于 graph 正式状态推进
2. `StepResult`、`active_node`、`followup_nodes` 都围绕同一执行骨架工作
3. 第一版不需要把 graph 和 node 再拆成两个并行工具中心

因此：

1. `meta.category` 第一版建议统一使用 `task_graph`
2. 不再额外保留 `node` 作为单独正式域名

## 6. 与当前主链路的挂载关系

可以用下面这张图理解：

```text
prepare / execute step
  -> execution
  -> task_graph
  -> memory_search
  -> subagent

finalize
  -> closeout
```

含义是：

1. `execution`、`task_graph`、`memory_search`、`subagent` 主要服务 `step`
2. `closeout` 主要服务 `finalize`

## 7. 与 StepResult 的关系

当前 `StepResult` 包含：

1. `node_patch`
2. `node_decision`
3. `runtime_control`
4. `followup_nodes`

因此工具域要和它对齐：

### `execution`

主要支撑：

1. `node_patch`
2. 局部证据与产物收集

### `task_graph`

主要支撑：

1. `node_decision`
2. `followup_nodes`
3. `active_node` 切换

### `closeout`

主要支撑：

1. `handoff`
2. `VerificationResult`
3. `RunOutcome`

## 8. 与 Handoff / Finalize 的关系

本任务明确规定：

1. `handoff` 的生成属于 `closeout` 域
2. final verification 属于 `closeout` 域
3. `RunOutcome` 的构建属于 `closeout` 域

这意味着：

1. `closeout` 是正式收尾域
2. 它不再散落在 runtime 其他工具集合里

## 9. 与 runtime 语义感知的关系

基于 `S6-T3`，当前正式规定如下：

1. runtime 对 `task_graph` 域保留显式语义感知
2. runtime 对 `execution` 域只做协议处理
3. runtime 对 `closeout` 域做收尾级流程感知
4. runtime 对 `memory_search` / `subagent` 只做域级识别

这里的“收尾级流程感知”是指：

1. runtime 知道 `handoff` 何时生成
2. runtime 知道 verification 何时触发
3. runtime 知道 `RunOutcome` 何时收敛

但 runtime 不深入理解 verifier 内部细节。

## 10. `meta.category` 建议值

第一版建议正式收敛为：

1. `execution`
2. `task_graph`
3. `closeout`
4. `memory_search`
5. `subagent`

并同步收缩旧建议：

1. 不再单独保留 `node`
2. 不再把 `memory` 和 `search` 拆成两个正式主域

## 11. 对其他任务的直接输入

`S6-T4` 直接服务：

1. `S6-T5` tool call 进入状态流 / 事件流 / 证据链的路径
2. `S6-T6` tool registry skeleton
3. `S3-T5` step / orchestrator 契约
4. `S11-T4` finalize / verification / outcome 闭环
5. `S12-T3` runtime / closeout 事件对齐

同时它直接依赖：

1. `S6-T2` 统一 tool protocol
2. `S6-T3` runtime 与工具语义耦合策略
3. `S3-T5` StepResult 结构
4. `S11-T3` 统一 handoff 结构

## 12. 本任务结论摘要

可以压缩成 5 句话：

1. v1 工具正式分成 `execution / task_graph / closeout / memory_search / subagent` 五域
2. `task_graph` 是唯一主状态流核心工具域
3. `closeout` 独立承载 handoff、verification、outcome 收尾能力
4. `memory_search` 和 `subagent` 保持旁路域定位
5. 工具分域必须和当前 `step -> finalize` 主链路保持一致
