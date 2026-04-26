# S5-T2 Task Graph 命名决策（V1）

更新时间：2026-04-21  
状态：Draft  
对应任务：`S5-T2`

## 1. 目标

本任务用于做出 `runtime-v2` 在任务编排与执行骨架上的正式命名决策。

结论目标只有一个：

`runtime-v2` 中不再保留旧的 `todo` / `subtask` 命名体系，统一切换到 `task graph` / `node` 命名体系。

## 2. 正式结论

本任务的正式结论如下：

1. v2 正式术语统一使用 `task graph`
2. v2 正式接口中完全剔除旧的 `todo` 命名
3. 最小执行单元统一命名为 `node`
4. 旧命名只允许存在于迁移层或兼容层
5. 文档、状态对象、工具名、主流程命名全部统一到新体系

## 3. 命名替换规则

## 3.1 领域命名

以下替换为 v2 正式命名：

1. `todo` -> `task graph`
2. `subtask` -> `node`

这意味着：

1. v2 不再把执行骨架称为 todo
2. v2 不再把最小执行单元称为 subtask

## 3.2 状态与字段命名

以下状态/字段统一切换：

1. `todo_id` -> `graph_id`
2. `active_todo` -> `active_graph`
3. `active_todo_id` -> `active_graph_id`
4. `active_subtask` -> `active_node`
5. `active_subtask_id` -> `active_node_id`
6. `active_subtask_number` -> `active_node_index` 或 `active_node_order`

这里的核心原则是：

1. v2 状态对象只暴露 graph / node 语义
2. 不允许旧 `todo` 字段继续进入正式状态模型

## 3.3 工具命名

v2 正式工具名统一切换如下：

1. `plan_task` -> `plan_task_graph`
2. `update_task_status` -> `update_node_status`
3. `update_subtask` -> `update_node_status`
4. `get_next_task` -> `get_next_node`
5. `reopen_subtask` -> `reopen_node`
6. `append_followup_subtasks` -> `append_followup_nodes`
7. `generate_task_report` -> `generate_task_graph_report`

工具命名规则如下：

1. 图级操作使用 `task_graph`
2. 节点级操作使用 `node`
3. 不再保留 `todo` 或 `subtask` 作为正式工具名

## 4. 兼容策略边界

本任务明确规定：

1. v2 正式接口层不保留旧名
2. 如果需要兼容旧调用，只能通过单独 compat / migration adapter 实现
3. compat 层不应反向污染 v2 核心命名

也就是说：

1. v2 文档只写新名
2. v2 状态对象只使用新字段
3. v2 工具注册只暴露新工具名
4. 旧名映射只存在于迁移期间

## 5. 这样做的原因

统一彻底切换，而不是保留双名体系，原因有 4 个：

1. 当前 `todo` 语义已经不足以表达正式执行图
2. `subtask` 会把 v1 的 markdown 任务列表语义继续带入 v2
3. 双命名会让 prompt、state、tool、verification 全部变得混乱
4. v2 的目标是重建底座，而不是在旧术语上继续打补丁

## 6. 对其他任务的直接影响

`S5-T2` 的命名决策将直接影响：

1. `S4-T2` 中 `TaskGraphState` 的字段命名
2. `S3-T2` 中 orchestrator 对执行骨架的依赖命名
3. `S6-T2` 中工具协议和工具分域命名
4. `S11-T2` 中 run outcome / handoff 对执行骨架的表达方式
5. `S12-T2` 中事件模型字段命名

## 7. 后续约束

从本任务开始，后续 v2 文档与设计中建议遵守以下约束：

1. 不再把 v2 核心执行骨架写成 `todo`
2. 不再把 v2 最小执行单元写成 `subtask`
3. 如果必须提到旧术语，必须明确标注为“历史兼容名”

## 8. 本任务结论摘要

可以压缩成 5 句话：

1. v2 正式执行骨架统一叫 `task graph`
2. v2 最小执行单元统一叫 `node`
3. 旧 `todo` / `subtask` 命名不再进入 v2 正式接口
4. 工具名、字段名、状态名全部切换到 graph / node 体系
5. 旧名只允许存在于迁移层
