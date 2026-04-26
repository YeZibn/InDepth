# S4-T6 状态库骨架设计（V1）

更新时间：2026-04-23  
状态：Draft  
对应任务：`S4-T6`

## 1. 目标

本任务用于定义 `runtime-v2` 第一版状态层的最小 package 骨架。

本任务不再发明新的正式状态对象，而是把前面已经确定的状态对象收敛成可落地的结构组织方式。

## 2. 正式结论

第一版状态库骨架采用以下原则：

1. 状态层只保留正式状态类型、patch 类型和轻接口
2. 状态层不吞入具体 runtime 实现
3. 状态层不吞入完整 closeout 产物
4. `TaskGraphStore` 只把接口放进状态层
5. 第一版不单独建立 `phase` 模块

## 3. 第一版 package 切分

第一版建议按 5 个区块组织：

1. `identity`
2. `runtime`
3. `task_graph`
4. `closeout`
5. `common`

## 4. `identity`

`identity` 用于放标识相关类型。

第一版建议至少包含：

1. `RunIdentity`
2. `RuntimeHostIdentity`
3. `run_id / task_id / session_id / graph_id / node_id` 对应的轻类型约束

这一层的作用是：

1. 让各状态对象统一依赖同一套标识定义
2. 避免 id 字段在不同模块中散写

## 5. `runtime`

`runtime` 用于放 run 级正式状态对象。

第一版建议至少包含：

1. `RunContext`
2. `RunLifecycle`
3. `RuntimeState`
4. `CompressionState`
5. `FinalizeReturnInput`
6. `ExternalSignalState`
7. `SignalRef`

这一层的作用是：

1. 承接 run 级主链路控制状态
2. 为 orchestrator / step / finalize 提供统一运行态读取入口

## 6. `task_graph`

`task_graph` 用于放 graph 级正式状态对象与 patch 接口。

第一版建议至少包含：

1. `TaskGraphState`
2. `TaskGraphNode`
3. `TaskGraphPatch`
4. `NodePatch`
5. `TaskGraphStore`

其中明确规定：

1. `TaskGraphStore` 在状态层只放接口
2. 具体实现不放在状态层

## 7. `closeout`

`closeout` 在状态层只放轻状态，不放完整 closeout 产物。

第一版建议只包含：

1. `VerificationState`
2. 相关轻量 `result_ref`

第一版明确不放：

1. `handoff`
2. `RunOutcome`
3. verifier pipeline 实现对象

原因是：

1. 它们属于 `S11` 的 closeout 结构
2. 不应反向污染运行中状态层

## 8. `common`

`common` 用于放跨模块都会用到的小类型。

第一版建议只放真正通用的小对象，例如：

1. `Ref`
2. `Timestamp`
3. 轻量 status type
4. 小型公用字面量约束

明确约束：

1. `common` 不允许变成杂物堆
2. 只有被两个及以上区块复用的小类型，才允许进入 `common`

## 9. 第一版不单独建立的模块

第一版状态库骨架中，以下模块暂不单独建立：

1. `phase`
2. `messages`
3. `events`
4. `memory`
5. `model`

原因如下：

1. `phase` 已被吸收进 `RunLifecycle`
2. `messages` 不属于正式控制状态
3. `events` 属于 observability，不属于状态主包
4. `memory` 不作为常驻运行态进入状态层
5. `model` 属于接入层，不属于状态层

## 10. Store 的边界

第一版明确规定：

1. 状态层可以定义 store 接口
2. 状态层不负责 store 的具体实现

以 `TaskGraphStore` 为例：

1. 接口定义属于状态层
2. 真正的内存实现、持久化实现、适配器实现属于 runtime / infra 层

这样做的原因是：

1. 保持状态层稳定
2. 避免状态包吞入 infra 细节

## 11. 推荐目录心智模型

第一版可以用下面这张心智图理解：

```text
state/
  identity/
  runtime/
  task_graph/
  closeout/
  common/
```

这不是要求当前就强制落成目录树，而是状态层骨架的正式组织原则。

## 12. 对外依赖关系

第一版依赖方向建议如下：

1. `runtime` 可以依赖 `identity`、`common`
2. `task_graph` 可以依赖 `identity`、`common`
3. `closeout` 可以依赖 `identity`、`common`
4. `runtime` 可以引用 `task_graph`
5. `task_graph` 不应反向依赖 `runtime`

## 13. 对后续任务的直接输入

`S4-T6` 直接服务：

1. `S3-T5/T6` runtime skeleton
2. `S5-T7` graph store/interface 落位
3. `S11` closeout 与运行态边界
4. `S12` 事件层与状态层解耦

## 14. 本任务结论摘要

可以压缩成 6 句话：

1. 第一版状态层只保留类型骨架、patch 和轻接口
2. 状态库按 `identity / runtime / task_graph / closeout / common` 五块组织
3. `TaskGraphStore` 只把接口放进状态层
4. `handoff / RunOutcome` 不进入状态库骨架
5. 第一版不单独建立 `phase` 模块
6. 状态层不吞入 runtime/infra 的具体实现
