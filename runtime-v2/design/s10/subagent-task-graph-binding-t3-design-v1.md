# S10-T3 SubAgent 与主任务图关系（V1）

更新时间：2026-04-24  
状态：Draft  
对应任务：`S10-T3`

## 1. 目标

本任务用于定义 `runtime-v2` 第一版中 subagent 与主 `task graph` 的正式关系。

本任务不再讨论：

1. subagent 的运行模型整体定义
2. subagent 角色模型细节
3. subagent 结果包字段细节
4. subagent 失败、超时、取消策略细节

这里只回答五件事：

1. subagent 是否必须绑定 node
2. subagent 生命周期动作如何进入 graph
3. subagent 执行的工作如何在 graph 中表达
4. subagent 结果如何写回 graph
5. 并行 subagent 如何通过 graph 表达

## 2. 正式结论

第一版正式结论如下：

1. `subagent` 必须绑定显式 `node`，不能脱离主 graph 独立存在
2. `subagent` 生命周期动作本身就是正式 `node`
3. 第一版生命周期动作最少拆成：
   - `create`
   - `configure`
   - `start`
   - `collect`
   - `destroy`
4. `subagent` 执行的实际工作仍通过普通 `node` 表达
5. 第一版不引入独立于主 graph 的第二套子图结构
6. `node` 增加正式字段 `owner` 表达执行归属
7. `owner = "main"` 表示主链执行
8. `owner = "subagent:<id>"` 表示由指定 `subagent` 执行
9. `owner` 只表达执行归属，不表达 node 类型、状态或调度策略
10. `subagent` 不直接写 `TaskGraphState`
11. `subagent` 只返回结果，由主链 `step` 决定是否生成 `NodePatch / GraphPatch`
12. 并行 `subagent` 通过多个并行 `node` 表达
13. 不允许把多个 subagent 的并发隐藏在单个 `node` 内部

## 3. 绑定模型

第一版采用单向绑定模型：

```text
node -> subagent_ref
```

含义如下：

1. 主 graph 中的某个正式 node 可以引用一个 subagent
2. subagent 的存在必须能追溯到主 graph 中的正式执行位置
3. 不采用“subagent 持有自己的一棵正式子图”的设计

原因如下：

1. `task graph` 已经是 v2 的唯一正式执行骨架
2. 如果 subagent 再持有第二棵正式子图，会形成双重执行骨架
3. 双重执行骨架会直接增加 resume、observability、failure attribution 的复杂度

## 4. 为什么必须绑定 Node

第一版明确规定：

1. `subagent` 不能作为 graph 外的漂浮能力存在
2. `subagent` 必须先落到显式 node 上，才能成为正式协作动作

原因如下：

1. subagent 会影响主执行骨架
2. subagent 有完整生命周期
3. subagent 的结果、失败、回收都必须能回到 graph
4. 主 runtime 必须始终知道当前协作动作挂在哪个正式位置

## 5. 生命周期动作如何入图

第一版规定，subagent 生命周期动作本身就是正式 node。

最小动作链如下：

1. `create`
2. `configure`
3. `start`
4. `collect`
5. `destroy`

这些动作进入 graph 的含义是：

1. subagent 不是一次普通 tool 调用
2. subagent 的编排动作本身就是正式工作
3. 每一步都必须能被追踪、观测、暂停、恢复和归责

第一版不允许：

1. 只在一个模糊的“run_subagent”动作里包住全部生命周期
2. 把生命周期动作藏在 graph 外部的 manager 状态里

## 6. 工作执行层如何表达

第一版中，subagent 真正执行的工作仍然通过普通 node 表达。

含义如下：

1. graph 上仍然只有正式 node
2. 不引入 `SubagentTaskGraph`
3. 某个工作 node 是否由 subagent 执行，通过 `owner` 表达

也就是说：

1. node 仍然是 node
2. 只是执行者不一定是主链
3. 工作归属通过执行者字段显式表达

## 7. `owner` 字段

第一版正式增加字段：

```ts
owner: "main" | `subagent:${string}`
```

### 7.1 `owner = "main"`

表示：

1. 当前 node 由主链 runtime 执行

### 7.2 `owner = "subagent:<id>"`

表示：

1. 当前 node 由指定 `subagent` 执行

### 7.3 `owner` 的边界

第一版明确规定：

1. `owner` 只表达执行归属
2. `owner` 不表达 node 类型
3. `owner` 不表达 node 状态
4. `owner` 不表达调度策略

这样做的原因是：

1. 保持字段语义单一
2. 防止把 subagent 语义污染到 node 基础结构中
3. 保持 `S5` 与 `S10` 的边界稳定

## 8. 写回规则

第一版明确规定：

1. `subagent` 不直接修改 `TaskGraphState`
2. `subagent` 只返回结果包
3. 主链 `step` 再根据结果决定是否生成正式 `NodePatch / GraphPatch`

这条边界是硬规则。

原因如下：

1. 避免 subagent 变成半个 orchestrator
2. 避免 graph 推进逻辑散落到主链外部
3. 保持正式状态写回入口唯一

因此第一版不允许：

1. subagent 直接返回正式 `GraphPatch`
2. subagent 直接宣布新增 node
3. subagent 直接切换 active node

## 9. 并行关系如何表达

第一版中，并行 subagent 通过主 graph 的并行 node 表达。

规则如下：

1. 一个并行分支对应一个正式 node
2. 每个并行 node 各自绑定自己的 subagent
3. fan-out / fan-in 继续通过 graph 关系表达

第一版明确不允许：

1. 一个 node 内部隐式并行启动多个 subagent
2. 在 graph 外维护隐藏并发树

原因如下：

1. 并行是 graph 语义，不是 subagent 私有语义
2. 这样更容易表达取消、超时、部分失败
3. observability 和恢复边界也更清楚

## 10. 第一版不做的事情

第一版中，`S10-T3` 明确不做以下设计：

1. 不引入独立 `subagent graph`
2. 不引入 graph 外的并行管理器作为正式执行骨架
3. 不让 subagent 拥有正式 graph 写权限
4. 不让 `owner` 同时承担 node type 或状态语义

## 11. 与其他任务的关系

`S10-T3` 直接依赖：

1. `S5-T6` task graph 跨动作挂载规则
2. `S10-T1` 当前 subagent 链路清单
3. `S10-T2` subagent 运行模型

`S10-T3` 直接服务：

1. `S10-T4` subagent 角色模型
2. `S10-T5` subagent 结果、证据、状态回流
3. `S10-T6` subagent 失败、超时、取消规则
4. `S10-T7` subagent skeleton
5. `S12` subagent 事件与观测对齐

## 12. 本任务结论摘要

可以压缩成 6 句话：

1. `subagent` 必须绑定显式 node，不能脱离主 graph 存在
2. subagent 生命周期动作本身就是正式 node
3. subagent 的实际工作仍通过普通 node 表达，不引入第二套子图
4. `owner` 是正式执行归属字段，第一版取值为 `main` 或 `subagent:<id>`
5. subagent 不直接写 graph，只返回结果，由主链 step 决定正式写回
6. 并行 subagent 通过多个并行 node 表达，不允许隐藏在单个 node 内部
