# Task Graph 实现说明

## 当前范围

当前 task graph 层已正式落地 graph 本体、node 本体和最小 patch 结构，但还没有进入 store 行为。

当前已实现：

1. `TaskGraphStatus`
2. `NodeStatus`
3. `TaskGraphNode`
4. `NodePatch`
5. `TaskGraphPatch`
6. `TaskGraphState`

对应代码：

1. [src/rtv2/task_graph/models.py](/Users/yezibin/Project/InDepth/runtime-v2/src/rtv2/task_graph/models.py)
2. [tests/test_task_graph_state.py](/Users/yezibin/Project/InDepth/runtime-v2/tests/test_task_graph_state.py)

## 为什么先落 `TaskGraphState`

当前先落 `TaskGraphState` 和 `TaskGraphNode`，原因是：

1. `DomainState.task_graph_state` 还处在过渡态引用，下一步最自然就是先把 graph 壳层收紧。
2. 如果现在直接进入 patch 或 store，会把状态定义和状态变更机制混在一起。
3. 先把整图级状态结构钉住，后续 `TaskGraphNode`、store 和 orchestrator 才有稳定依赖面。

## `TaskGraphState` 的作用

`TaskGraphState` 用于表达一张正式 task graph 的最小长期状态。

当前字段包括：

1. `graph_id`
2. `nodes`
3. `active_node_id`
4. `graph_status`
5. `version`

它当前承担三类职责：

1. graph 本体职责：
   承接整张执行图的正式状态壳层。
2. 主焦点职责：
   用 `active_node_id` 表达当前主链围绕哪个 node 推进。
3. 演进锚点职责：
   用 `version` 为后续 patch / store 接入预留正式版本位。

## 当前设计结论

当前这一步已经定稿的边界如下：

1. `nodes` 第一版先保持 `list` 结构，不提前切到索引字典。
2. `active_node_id` 保留在 `TaskGraphState` 中，不只放在 runtime 快捷态里。
3. `graph_status` 第一版固定为：
   - `active`
   - `blocked`
   - `completed`
   - `abandoned`
4. `version` 从第一版就进入正式结构。

## `TaskGraphNode` 的作用

`TaskGraphNode` 用于表达 task graph 中的最小正式执行单元。

当前字段包括：

1. `node_id`
2. `graph_id`
3. `name`
4. `kind`
5. `description`
6. `node_status`
7. `owner`
8. `dependencies`
9. `order`
10. `artifacts`
11. `evidence`
12. `notes`
13. `block_reason`
14. `failure_reason`

它当前承担四类职责：

1. 身份职责：
   用 `node_id / graph_id / name` 固定节点归属与可读标识。
2. 语义职责：
   用 `kind / description` 表达节点要做什么。
3. 执行职责：
   用 `node_status / owner / dependencies / order` 表达节点当前推进条件与执行归属。
4. 结果职责：
   用 `artifacts / evidence / notes` 承接节点产物、证据与备注。

## 当前设计结论补充

当前 `TaskGraphNode` 已定稿的边界如下：

1. `owner` 第一版直接使用 `str`
2. `artifacts / evidence` 第一版使用 `list[str]`
3. `dependencies` 第一版只保存依赖 `node_id` 列表
4. `block_reason / failure_reason` 从第一版进入正式结构
5. `NodeStatus` 当前按 8 个正式状态收口：
   - `pending`
   - `ready`
   - `running`
   - `blocked`
   - `paused`
   - `completed`
   - `failed`
   - `abandoned`

## 当前实现边界

当前这一步已经收紧了一个过渡点：

1. `TaskGraphState.nodes` 已从过渡态 `list[Any]` 收紧为 `list[TaskGraphNode]`

同时也新增了一个过渡点：

1. `TaskGraphPatch.node_updates` 已正式进入结构
2. 但 `NodePatch` 当前仍是过渡壳层，只固定 `node_id`

## `TaskGraphPatch` 的作用

`TaskGraphPatch` 用于表达一次 `step` 对 task graph 的正式修改结果。

当前字段包括：

1. `node_updates`
2. `new_nodes`
3. `active_node_id`
4. `graph_status`

它当前承担三类职责：

1. 变更收口职责：
   把一次 step 对 graph 的正式修改结果收口成统一对象。
2. graph 写回职责：
   为后续 store 提供统一的 patch 输入。
3. 边界约束职责：
   明确第一版 patch 只承接正式状态修改，不扩成 graph 操作命令。

## 当前 `TaskGraphPatch` 设计结论

当前这一步已经定稿的边界如下：

1. `node_updates` 保留为数组
2. `new_nodes` 直接使用完整 `TaskGraphNode`
3. `active_node_id` 用 `None` 表达“不修改”
4. `graph_status` 用 `None` 表达“不修改”
5. 第一版明确不引入：
   - `graph_notes`
   - `remove_nodes`
   - `replace_nodes`
   - `version_bump`
   - 调度控制字段

## 当前边界

当前 task graph 层明确不负责：

1. `NodePatch` 的完整字段级更新范围
2. `TaskGraphStore`
3. graph patch 应用规则

这些内容会在模块 03 后续子任务中继续落地。

## 下一步

task graph 层下一步预计进入：

1. `NodePatch`
2. `TaskGraphStore`
3. 内存版 `TaskGraphStore`
