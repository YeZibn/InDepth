# S5-T5 Task Graph 状态推进规则（V1）

更新时间：2026-04-27  
状态：Draft  
对应任务：`S5-T5`

## 1. 目标

本任务用于定义 `runtime-v2` 第一版中 task graph 的正式状态推进规则。

本任务不再讨论：

1. `node` 的最小结构
2. graph 的正式关系模型
3. orchestrator 与 step 的职责边界总论

这里只回答四件事：

1. `node_status` 允许如何流转
2. 谁能触发正式状态流转
3. followup node 如何进入状态机
4. `switch` 与 `abandon` 如何区分

## 2. 正式结论

本任务最终结论如下：

1. 第一版 `node_status` 正式集合扩展为 8 个
2. 正式状态流转只能由 `step` 决定
3. `failed -> ready` 允许
4. 当前阶段只先落执行推进，不落图结构重规划
5. 当前阶段 `step` 只允许回写节点执行结果字段
6. `switch`、`abandon` 与 followup nodes 留待后续模块落地

## 3. 正式 Node Status 集合

第一版正式 `node_status` 使用以下 8 个状态：

1. `pending`
2. `ready`
3. `running`
4. `blocked`
5. `paused`
6. `completed`
7. `failed`
8. `abandoned`

其中：

1. `abandoned` 是正式主状态
2. 不再只作为备注语义存在

## 4. 允许的状态流转

第一版允许以下正式流转：

1. `pending -> ready`
2. `ready -> running`
3. `running -> completed`
4. `running -> failed`
5. `running -> blocked`
6. `running -> paused`
7. `running -> abandoned`
8. `blocked -> ready`
9. `paused -> ready`
10. `failed -> ready`

## 5. 默认不允许的流转

第一版默认不允许以下流转：

1. `pending -> running`
2. `pending -> completed`
3. `ready -> completed`
4. `completed -> *`
5. `abandoned -> *`

核心原则如下：

1. 节点必须先进入 `ready`，才能正式开始执行
2. 节点必须先进入 `running`，才能正式结束
3. `completed` 是封口终态
4. `abandoned` 是迁移终态

## 6. `failed -> ready` 的语义

第一版明确允许：

1. `failed -> ready`

它的语义不是：

1. 覆盖失败历史
2. 否认之前失败发生过

它的语义是：

1. 当前 node 在新的判断下重新具备推进条件
2. 旧失败记录仍然保留在 `failure_reason`、`notes`、`evidence` 中

## 7. 状态流转的唯一决策者

第一版明确规定：

1. 正式 `node_status` 流转只能由 `step` 决定

这意味着：

1. orchestrator 不做二次判断
2. orchestrator 只执行 `StepResult`
3. 工具结果不能直接改正式 graph state
4. subagent 结果不能直接改正式 graph state
5. verification 结果不能直接改正式 graph state

这些链路都只能：

1. 提供输入
2. 提供证据
3. 提供局部结果

最后是否形成正式 `NodePatch / GraphPatch`，只能由 `step` 决定。

## 8. 当前阶段允许的 patch 字段

当前执行推进阶段，`step` 只允许通过 patch 修改以下字段：

1. `node_status`
2. `block_reason`
3. `failure_reason`
4. `notes`
5. `artifacts`
6. `evidence`

同时明确：

1. `notes / artifacts / evidence` 采用追加语义
2. `block_reason / failure_reason` 采用当前态覆盖语义
3. `artifacts / evidence` 的正式承载结构为统一 `ResultRef`
4. 当前不再把 `artifacts / evidence` 视为裸字符串数组设计

## 9. 当前阶段暂不开放的结构修改

当前阶段明确不开放以下 graph 修改能力：

1. `new_nodes`
2. `dependencies`
3. `owner`
4. `order`
5. 通用 `active_node_id` 切换

空图初始化新增最小 node 仍可作为 orchestrator 内建路径存在，但不视为通用 step 图重规划能力。

当前补充一条模块 08 对接结论：

1. 当前执行推进阶段的 patch 提交链，只处理节点执行结果类字段
2. 图结构修改继续留到后续模块单独设计与实现

## 10. Followup Nodes 的接入规则

第一版允许：

1. 一次新增一个 followup node 数组

但必须满足以下规则：

1. 新增 node 必须与现有 graph 有正式关系
2. 不允许新增孤立 node
3. 不允许系统自动补依赖关系
4. `dependencies` 必须显式写出

### 10.1 初始状态规则

第一版默认：

1. 新增 followup node 初始状态为 `pending`

但允许：

1. 若 `step` 明确判断该 node 当前已具备执行条件，可直接写成 `ready`

## 11. `switch` 的语义

第一版 `switch` 定义如下：

1. 当前 node 暂停推进
2. 主焦点切换到另一个 node

对应状态效果：

1. 当前 node 进入 `paused`
2. 目标 node 进入执行主线

`switch` 不表示：

1. 当前 node 已永久终止
2. 当前 node 的工作被正式迁移完毕

## 12. `abandon` 的语义

第一版 `abandon` 定义如下：

1. 当前 node 明确不再继续
2. 工作主线正式迁移到承接目标

对应状态效果：

1. 当前 active node 进入 `abandoned`
2. 必须指定唯一承接目标

## 12.1 承接目标规则

第一版明确规定：

1. `abandon` 必须有且只有一个承接目标

承接目标可以是：

1. 已有 node
2. 本轮新增 followup nodes 中的一个 node

但注意：

1. 本轮新增的 followup nodes 可以是数组
2. 真正承接当前 node 主线的目标只能有一个

## 13. `switch` 与 `abandon` 的区别

第一版明确区分如下：

### `switch`

语义：

1. 暂停并切焦点

结果：

1. 当前 node 仍可能回来继续
2. 当前 node 状态变为 `paused`

### `abandon`

语义：

1. 终止并迁移主线

结果：

1. 当前 node 不再继续
2. 当前 node 状态变为 `abandoned`
3. 必须指定唯一承接目标

## 14. 对后续任务的直接输入

`S5-T5` 直接服务：

1. `S3-T4` step loop 决策输出
2. `S4-T3` 统一状态图
3. `S5-T7` task graph skeleton
4. `S11` closeout 中的 node 结果表达

## 15. 本任务结论摘要

可以压缩成 6 句话：

1. 第一版 `node_status` 正式集合扩成 8 个
2. 正式状态流转只能由 `step` 决定
3. `failed -> ready` 允许
4. 当前阶段先只落执行推进，不落结构重规划
5. 节点执行结果 patch 只开放有限字段
6. `switch / abandon / followup nodes` 留待后续模块再正式落地
