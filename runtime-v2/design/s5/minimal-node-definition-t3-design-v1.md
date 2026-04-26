# S5-T3 最小执行单元 Node 定义（V1）

更新时间：2026-04-21  
状态：Draft  
对应任务：`S5-T3`

## 1. 目标

本任务用于定义 `runtime-v2` 中 task graph 的最小执行单元。

正式结论是：

1. v2 的最小执行单元统一命名为 `node`
2. 第一版不再引入比 `node` 更小的正式执行单元
3. task graph 的推进、选择、执行、恢复都围绕 `node` 展开

## 2. 正式结论

本任务最终结论如下：

1. `node` 是 v2 第一版唯一正式最小执行单元
2. `dependencies` 是 node 的一等字段
3. `owner` 进入 node
4. `artifacts` 和 `evidence` 进入 node
5. `node_status` 第一版使用 7 个正式状态

## 3. Node 的最小结构

第一版建议 `node` 至少包含以下字段组。

## 3.1 identity

1. `node_id`
2. `graph_id`
3. `name`

作用：

1. 唯一标识节点
2. 标识节点归属的 task graph
3. 提供最小可读名称

## 3.2 semantic

1. `kind`
2. `description`

作用：

1. 标识节点是什么类型的工作
2. 提供节点执行语义说明

## 3.3 execution

1. `node_status`
2. `owner`
3. `dependencies`

作用：

1. 表示节点当前执行状态
2. 表示节点由谁执行
3. 表示节点依赖哪些前置节点

## 3.4 positioning

1. `order`

作用：

1. 在图内提供稳定排序
2. 便于 graph 调度、展示与恢复

第一版先不额外引入更复杂的层级定位字段。

## 3.5 output

1. `artifacts`
2. `evidence`
3. `notes`

作用：

1. 记录节点产物
2. 记录节点证据
3. 记录执行备注与补充说明

## 4. Node Status 正式集合

第一版 `node_status` 正式集合如下：

1. `pending`
2. `ready`
3. `running`
4. `blocked`
5. `paused`
6. `completed`
7. `failed`

这是第一版正式状态集合，不额外扩展。

## 4.1 状态语义

### `pending`

表示：

1. 节点已存在
2. 但前置条件尚未满足

### `ready`

表示：

1. 节点已经可以被主链路选中执行
2. graph 调度无需再次推断其是否可运行

### `running`

表示：

1. 节点当前正在执行

### `blocked`

表示：

1. 节点当前无法继续推进
2. 且这是明确阻塞，不是简单未轮到

### `paused`

表示：

1. 节点执行被暂停

### `completed`

表示：

1. 节点执行完成

### `failed`

表示：

1. 节点执行失败

## 5. 为什么不用更多状态

第一版不直接把以下状态纳入正式集合：

1. `partial`
2. `awaiting_input`
3. `timed_out`
4. `abandoned`

原因如下：

### `partial`

更像结果表达，不适合作为 node 主状态。

### `awaiting_input`

更适合作为阻塞原因，而不是主状态。

### `timed_out`

更适合作为失败原因，而不是主状态。

### `abandoned`

更像迁移、重规划、兼容期语义，不作为第一版核心 node 状态。

## 6. 辅助原因字段

为了避免状态集合膨胀，第一版引入两个辅助原因字段：

1. `block_reason`
2. `failure_reason`

### block_reason

示例：

1. `awaiting_input`
2. `dependency_unmet`
3. `resource_unavailable`

### failure_reason

示例：

1. `timeout`
2. `tool_error`
3. `validation_failed`

结论：

1. 主状态集合保持稳定
2. 更细原因通过辅助字段表达

## 7. owner 的地位

`owner` 是 node 的一等字段。

第一版保留它的原因是：

1. main-chain 可能直接执行节点
2. subagent 可能执行节点
3. verifier 或其他独立链路后续也可能拥有节点职责

因此：

1. 执行者不是外部附属信息
2. 它应成为 node 的正式字段

## 8. artifacts / evidence 的地位

本任务明确规定：

1. `artifacts` 进入 node
2. `evidence` 进入 node

原因是：

1. 节点不仅表示“要做什么”
2. 还要表达“做出了什么”和“凭什么认为做到了”

这对后续：

1. `S11` verification
2. `S12` 证据链
3. graph resume / replay

都很重要。

## 9. 对其他任务的直接输入

`S5-T3` 直接服务：

1. `S5-T4` 执行图关系模型
2. `S6-T3` runtime 与工具语义耦合策略
3. `S11-T3` handoff 结构
4. `S12-T3` 证据链模型

同时它直接依赖：

1. `S4-T3` 统一状态图
2. `S5-T2` task graph 命名决策

## 10. 本任务结论摘要

可以压缩成 5 句话：

1. v2 的唯一正式最小执行单元是 `node`
2. `dependencies`、`owner`、`artifacts`、`evidence` 都进入 node
3. `node_status` 第一版采用 7 个正式状态
4. `awaiting_input`、`timeout` 等细原因通过辅助字段表达
5. task graph 的调度与恢复都围绕 node 展开
