# S5-T7 Task Graph Skeleton 与 Store 接口（V1）

更新时间：2026-04-23  
状态：Draft  
对应任务：`S5-T7`

## 1. 目标

本任务用于定义 `runtime-v2` 第一版中 task graph 的最小状态骨架与 store 接口。

本任务不再讨论：

1. node 的最小结构
2. node 状态推进规则
3. graph 的跨动作挂载规则
4. step 如何生成 graph 决策

这里只回答三件事：

1. task graph 正式状态本体至少包含什么
2. step 如何表达 graph 变更
3. store 至少需要哪些接口

## 2. 正式结论

本任务最终结论如下：

1. 第一版 task graph 保留最小状态本体 `TaskGraphState`
2. 第一版保留最小变更对象 `TaskGraphPatch`
3. 第一版保留最小读写接口 `TaskGraphStore`
4. `store` 不负责调度决策
5. 调度结果由 `step` 产出，`store` 只负责应用
6. 第一版保留极简 `graph_status`

## 3. `TaskGraphState`

第一版建议：

```ts
type TaskGraphState = {
  graph_id: string;
  nodes: TaskGraphNode[];
  active_node_id?: string;
  graph_status: "active" | "blocked" | "completed" | "abandoned";
  version: number;
};
```

## 4. 各字段定位

### 4.1 `graph_id`

作用：

1. 唯一标识当前 task graph

### 4.2 `nodes`

作用：

1. 持有正式 node 集合
2. 作为 graph 的核心内容

### 4.3 `active_node_id`

作用：

1. 标识当前主执行焦点
2. 表示当前主链路正在围绕哪个 node 推进

### 4.4 `graph_status`

第一版保留极简整图级状态：

1. `active`
2. `blocked`
3. `completed`
4. `abandoned`

它的定位不是重复 node 状态，而是提供一个整图级最快可读结论。

### 4.5 `version`

作用：

1. 表示 graph 状态版本
2. 便于后续 patch 应用、对账与状态演进

## 5. `graph_status` 的语义

### `active`

表示：

1. 当前图仍有主线在推进

### `blocked`

表示：

1. 当前图没有可继续推进的主线

### `completed`

表示：

1. 当前图整体已经收口

### `abandoned`

表示：

1. 当前图整体明确不再继续

## 6. `TaskGraphPatch`

第一版建议：

```ts
type TaskGraphPatch = {
  node_updates?: NodePatch[];
  new_nodes?: TaskGraphNode[];
  active_node_id?: string;
  graph_status?: "active" | "blocked" | "completed" | "abandoned";
  graph_notes?: string[];
};
```

## 7. `TaskGraphPatch` 的定位

它的作用是：

1. 承接 `step` 的正式 graph 修改结果
2. 让 orchestrator 能把 graph 变化结构化地交给 store
3. 避免 graph 修改散落在运行时各处

## 8. `TaskGraphStore`

第一版建议保留以下最小接口：

```ts
interface TaskGraphStore {
  get_graph(graph_id: string): TaskGraphState | null;
  save_graph(graph: TaskGraphState): void;
  apply_patch(graph_id: string, patch: TaskGraphPatch): TaskGraphState;
  get_active_node(graph_id: string): TaskGraphNode | null;
  get_node(graph_id: string, node_id: string): TaskGraphNode | null;
  list_nodes(graph_id: string): TaskGraphNode[];
}
```

## 9. Store 的职责边界

第一版 `store` 只负责：

1. 持有 graph 状态
2. 读取 graph 状态
3. 按 patch 应用 graph 变更
4. 返回最新 graph 快照

第一版 `store` 不负责：

1. 自动调度下一个 node
2. 决定哪个 node 成为 active node
3. 判断当前 node 应该 switch、abandon 还是 complete
4. 生成 patch

这些都属于 `step` 的职责。

## 10. Step 与 Store 的分工

第一版明确规定：

### `step`

负责：

1. 产生正式 graph 决策
2. 指定新的 `active_node_id`
3. 指定 `graph_status`
4. 指定 `node_updates`
5. 指定 `new_nodes`

### `store`

负责：

1. 应用上述结果
2. 保证 graph 写回一致
3. 输出更新后的 graph

## 11. 为什么不把 Store 做重

第一版不把 `store` 扩成重型 service，原因如下：

1. 避免把它做成第二个 orchestrator
2. 避免状态层吞掉主链路决策权
3. 先确保 graph 读写、patch 应用、结构一致性稳定

第一版因此不直接引入：

1. scheduler
2. selector
3. resolver
4. graph planner

## 12. 对后续任务的直接输入

`S5-T7` 直接服务：

1. `S3-T5/T6` runtime skeleton
2. `S4-T6` 状态库 skeleton
3. `S10` subagent graph 绑定
4. `S12` graph 事件与测试骨架

## 13. 本任务结论摘要

可以压缩成 6 句话：

1. 第一版 task graph 只保留最小 state / patch / store 三层
2. `TaskGraphState` 保留 `graph_status`
3. `graph_status` 只保留 `active / blocked / completed / abandoned`
4. `version` 保留
5. `step` 决定 graph 如何变化
6. `store` 只应用变化，不负责调度
