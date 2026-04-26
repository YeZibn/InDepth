# Task Graph 实现说明

## 当前范围

当前 task graph 层只正式落地了最小 graph 状态本体，还没有进入 node 正式结构、patch 机制和 store 行为。

当前已实现：

1. `TaskGraphStatus`
2. `TaskGraphState`

对应代码：

1. [src/rtv2/task_graph/models.py](/Users/yezibin/Project/InDepth/runtime-v2/src/rtv2/task_graph/models.py)
2. [tests/test_task_graph_state.py](/Users/yezibin/Project/InDepth/runtime-v2/tests/test_task_graph_state.py)

## 为什么先落 `TaskGraphState`

当前先落 `TaskGraphState`，原因是：

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

## 当前实现边界

当前实现还刻意保留了一个过渡点：

1. `nodes` 暂时使用过渡态 `list[Any]`

原因是：

1. `TaskGraphNode` 属于模块 03 的下一子任务
2. 当前不提前把 node 结构一起落地

## 当前边界

当前 task graph 层明确不负责：

1. `TaskGraphNode` 正式字段定义
2. `NodeStatus` 正式集合收口
3. `TaskGraphPatch`
4. `TaskGraphStore`
5. graph patch 应用规则

这些内容会在模块 03 后续子任务中继续落地。

## 下一步

task graph 层下一步预计进入：

1. `TaskGraphNode`
2. `TaskGraphStatus / NodeStatus` 的完整收口
3. 再进入 patch 与 store
