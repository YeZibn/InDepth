# Task Graph 实现说明

## 当前范围

当前 task graph 层已正式落地 graph 本体、node 本体、最小 patch 结构、store 接口和内存版 store。

当前已实现：

1. `TaskGraphStatus`
2. `NodeStatus`
3. `ResultRef`
4. `TaskGraphNode`
5. `NodePatch`
6. `TaskGraphPatch`
7. `TaskGraphState`
8. `TaskGraphStore`
9. `InMemoryTaskGraphStore`

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
2. `artifacts / evidence` 已升级为统一 `list[ResultRef]`
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

同时也完成了一个收紧点：

1. `TaskGraphPatch.node_updates` 已正式进入结构
2. `NodePatch` 已从过渡壳层收紧为正式字段级更新对象

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

## `NodePatch` 的作用

`NodePatch` 用于表达单个 node 的字段级部分更新。

当前字段包括：

1. `node_id`
2. `node_status`
3. `owner`
4. `dependencies`
5. `order`
6. `artifacts`
7. `evidence`
8. `notes`
9. `block_reason`
10. `failure_reason`

它当前承担两类职责：

1. 局部更新职责：
   表达单个 node 在一次 step 后有哪些运行时字段发生变化。
2. 更新边界职责：
   限制第一版 patch 只修改运行时可变字段，不重写 node 身份字段和核心语义字段。

## 当前 `NodePatch` 设计结论

当前这一步已经定稿的边界如下：

1. `NodePatch` 只负责运行时可变字段
2. 第一版不允许改：
   - `graph_id`
   - `name`
   - `kind`
   - `description`
3. `dependencies` 第一版允许整体替换
4. `notes` 第一版采用追加语义
5. `artifacts / evidence` 第一版采用基于 `ResultRef.ref_id` 的去重追加语义
6. `block_reason / failure_reason` 第一版采用覆盖语义
7. `None` 统一表达“不修改”

## 当前边界

当前 task graph 层明确不负责：

1. `TaskGraphStore` 的具体实现
2. graph patch 应用规则

这些内容会在模块 04 后续子任务中继续落地。

## `TaskGraphStore` 的作用

`TaskGraphStore` 用于定义 task graph 的最小读写边界。

当前接口包括：

1. `get_graph`
2. `save_graph`
3. `apply_patch`
4. `get_node`
5. `get_active_node`
6. `list_nodes`

## `ResultRef` 的作用

`ResultRef` 用于作为 `artifacts / evidence` 的统一最小引用结构。

当前字段包括：

1. `ref_id`
2. `ref_type`
3. `title`
4. `content`

它当前承担两类职责：

1. 引用职责：
   用统一结构表达执行产物或证据，而不再退回裸字符串。
2. 去重职责：
   为 `apply_patch(...)` 的追加式 merge 提供稳定的最小键位。

## `InMemoryTaskGraphStore.apply_patch(...)` 的当前合并语义

当前执行推进阶段，内存版 store 已正式落地以下最小 merge 规则：

1. `notes`
   - 只追加非空字符串
   - 不做文本去重
2. `artifacts`
   - 使用 `ResultRef[]`
   - 按 `ref_id` 去重追加
   - 不覆盖历史列表
3. `evidence`
   - 使用 `ResultRef[]`
   - 按 `ref_id` 去重追加
   - 不覆盖历史列表
4. `block_reason / failure_reason`
   - 仍采用覆盖写入

当前这一步明确：

1. 当前已实现合并语义
2. 当前已实现基础一致性校验
3. 当前已实现状态流转校验

它当前承担三类职责：

1. 状态持有职责：
   为 graph 提供正式的读取与写回边界。
2. patch 落点职责：
   为 `TaskGraphPatch` 提供正式应用入口。
3. 读取便利职责：
   为上层提供按 graph、按 node、按 active node 的稳定读取面。

## 当前 `TaskGraphStore` 设计结论

当前这一步已经定稿的边界如下：

1. `TaskGraphStore` 采用 `Protocol`
2. store 不承担调度、推理或自动修复能力
3. `apply_patch` 找不到 `graph_id` 时，后续实现应抛错，而不是返回 `None`
4. `save_graph` 返回 `None`
5. 当前接口层只定义契约，不提前实现内存策略或拷贝策略

## `InMemoryTaskGraphStore` 的作用

`InMemoryTaskGraphStore` 用于提供第一版最小可用的 graph 存储实现，服务本地运行链路与测试。

当前实现规则如下：

1. 内部使用 `dict[str, TaskGraphState]` 持有 graph
2. `save_graph` 采用整图覆盖保存
3. `apply_patch` 基于已有 graph 生成更新后的新快照
4. 新增 node 若出现重复 `node_id`，直接抛错
5. `node_updates` 若指向不存在 node，直接抛错
6. `active_node_id` 若指向更新后不存在的 node，直接抛错
7. `blocked` node patch 若缺少 `block_reason`，直接抛错
8. `failed` node patch 若缺少 `failure_reason`，直接抛错
9. `ResultRef.ref_id` 为空时，直接抛错
10. 当前执行推进阶段只允许以下状态流转：
    - `pending -> ready`
    - `ready -> running`
    - `running -> completed`
    - `running -> blocked`
    - `running -> failed`
    - `blocked -> ready`
11. 非法状态流转直接抛错
12. 当前实现采用快照语义，避免外部对象引用直接污染 store 内部状态

## 下一步

task graph 层下一步预计进入：

1. 进入下一模块边界讨论或更高层 step / store 协议收口
