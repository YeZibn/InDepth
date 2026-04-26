# S10-T2 SubAgent 运行模型（V1）

更新时间：2026-04-24  
状态：Draft  
对应任务：`S10-T2`

## 1. 目标

本任务用于定义 `runtime-v2` 第一版中 subagent 的正式运行模型。

本任务不再讨论：

1. subagent 与 task graph 的正式绑定结构细节
2. subagent 角色模型细节
3. subagent 结果回流字段细节
4. subagent 失败、超时、取消策略细节

这里只回答四件事：

1. subagent 在 v2 中到底是什么
2. subagent 与主 runtime 的控制关系是什么
3. subagent 生命周期如何表达
4. 并行 subagent 在运行模型上如何成立

## 2. 正式结论

第一版正式结论如下：

1. `subagent` 是受主 runtime 控制的 worker
2. `subagent` 不是独立主链 runtime
3. `subagent` 必须先绑定主 `task graph` 中的显式 `node`，再允许创建和启动
4. `subagent` 第一版按一次性 worker 设计，不做跨 node 复用
5. 一个 `subagent` 只服务一个 node
6. 一个 node 在同一时刻最多绑定一个 `subagent`
7. `subagent` 生命周期采用显式动作链：
   - `create`
   - `configure`
   - `start`
   - `collect`
   - `destroy`
8. `create` 与 `configure` 必须分开，不合并
9. `subagent` 不直接修改 `TaskGraphState`
10. `subagent` 只产出结果，由主链 `step` 决定如何写回正式状态
11. 并行 `subagent` 通过主 graph 中多个并行 node 表达
12. 不允许把多个 subagent 的并发隐藏在单个 node 内部

## 3. SubAgent 的正式定位

第一版中，`subagent` 的正式定位是：

1. 被主 runtime 调度的受控 worker
2. 为特定 node 或特定局部工作服务的执行者
3. 不拥有 run 级主控制权的协作执行单元

这意味着：

1. `subagent` 不是第二个 `RuntimeOrchestrator`
2. `subagent` 不是 graph 外的自由运行体
3. `subagent` 的存在必须能被主链 runtime 观测、控制、回收

## 4. 为什么不是独立 Runtime

第一版明确不把 `subagent` 设计成独立主链 runtime。

原因如下：

1. `runtime-v2` 已经把主控制中心收敛为 `RuntimeOrchestrator`
2. 如果 `subagent` 也成为独立主链 runtime，会形成双重编排中心
3. 双重编排中心会让 graph 写回、resume、观测和失败归责同时复杂化
4. 第一版更重要的是把所有正式执行位置收回主 graph

因此第一版明确规定：

1. `subagent` 可以有自己的轻运行循环
2. 但它不拥有主链级 `prepare / execute / finalize` 控制权
3. 它只在主 runtime 授权的局部范围内运行

## 5. 与主 Runtime 的控制关系

第一版中，主 runtime 与 subagent 的关系如下：

### 主 runtime 负责

1. 决定是否需要 subagent
2. 决定把 subagent 绑定到哪个 node
3. 决定何时创建、配置、启动、回收、销毁
4. 决定 subagent 结果是否转成正式 `NodePatch / GraphPatch`
5. 决定是否继续执行、切换 node、进入 finalize

### subagent 负责

1. 接收明确授权的局部任务
2. 在受控范围内执行工作
3. 返回结果、证据、摘要或失败信息

### subagent 不负责

1. 决定主 graph 如何推进
2. 决定 phase 如何切换
3. 决定是否新增正式 node
4. 直接写回 `TaskGraphState`

## 6. 绑定前提

第一版规定：

1. `subagent` 必须先绑定 node，后创建实例
2. 不允许先创建一个游离实例，再事后寻找 graph 归属

原因如下：

1. `subagent` 的生命周期本身就属于正式执行骨架的一部分
2. graph 必须始终知道当前协作动作挂在哪个正式执行位置
3. 这样才能稳定表达 resume、failure attribution 和 observability

## 7. 一次性 Worker 模型

第一版采用一次性 worker 模型。

含义如下：

1. 一个 `subagent` 只服务一个 node
2. 一个 `subagent` 完成当前授权工作后就进入回收路径
3. 不做跨 node 复用
4. 不做长期常驻 worker 池

这样设计的原因是：

1. 避免上下文污染
2. 避免实例状态跨 node 残留
3. 避免 resume 时出现“旧实例是否还能继续用”的歧义
4. 避免第一版过早引入复杂实例管理问题

## 8. 基本约束

第一版保留以下强约束：

1. 一个 `subagent` 只服务一个 node
2. 一个 node 在同一时刻最多绑定一个 `subagent`
3. node 的执行归属、实例生命周期、结果回收都必须能在主链被追踪

这些约束的作用是：

1. 保持 graph 执行骨架单一
2. 防止 subagent 在 graph 外形成隐式共享状态
3. 为后续 `S10-T3/T5/T6` 留出稳定边界

## 9. 生命周期动作链

第一版 subagent 生命周期采用显式动作链：

1. `create`
2. `configure`
3. `start`
4. `collect`
5. `destroy`

这些动作的含义如下。

### 9.1 `create`

作用：

1. 创建 subagent 实例标识
2. 建立主 runtime 对该实例的正式控制关系

### 9.2 `configure`

作用：

1. 装配 role、能力、提示、依赖或受限权限
2. 让实例进入“可运行但尚未启动”的状态

第一版明确规定：

1. `create` 和 `configure` 必须分开
2. 不允许把“实例创建成功”和“执行配置完成”混成同一步

原因如下：

1. 两者失败语义不同
2. 两者观测点不同
3. 两者恢复策略也不同

### 9.3 `start`

作用：

1. 正式启动 subagent 执行被授权的工作
2. 进入运行中状态

### 9.4 `collect`

作用：

1. 回收执行结果
2. 回收证据与摘要
3. 为主链 step 提供后续写回判断输入

### 9.5 `destroy`

作用：

1. 结束实例生命周期
2. 清理不应继续保留的运行态
3. 防止实例在 graph 外继续漂浮

## 10. 写回边界

第一版明确规定：

1. `subagent` 不直接修改 `TaskGraphState`
2. `subagent` 只返回结果包
3. 主链 `step` 再根据结果决定是否生成正式 `NodePatch / GraphPatch`

这条边界非常关键，原因如下：

1. 避免 subagent 变成半个 orchestrator
2. 避免 graph 推进逻辑分散到主链之外
3. 保持正式状态写回入口唯一

## 11. 并行运行模型

第一版并行 subagent 的运行模型如下：

1. 并行是 graph 语义，不是单个 subagent 的私有语义
2. 若需要并行 subagent，应在主 graph 中显式创建多个并行 node
3. 每个并行 node 各自绑定自己的 subagent
4. fan-out / fan-in 仍由主 graph 表达

第一版明确不允许：

1. 一个 node 内部声明“我自己并行跑多个 subagent”
2. 在 graph 外维护隐藏并发结构

这样做的原因是：

1. 观测更清楚
2. 取消、超时、部分失败更容易表达
3. graph 仍然是唯一正式执行骨架

## 12. 与其他任务的关系

`S10-T2` 直接依赖：

1. `S3-T2` `RuntimeOrchestrator` 定义
2. `S4-T4` 极简 `RunContext` 结构
3. `S5-T6` task graph 跨动作挂载规则
4. `S10-T1` 当前 subagent 链路清单

`S10-T2` 直接服务：

1. `S10-T3` subagent 与主任务图的关系
2. `S10-T4` subagent 角色模型
3. `S10-T5` subagent 结果、证据、状态回流
4. `S10-T6` subagent 失败、超时、取消规则
5. `S10-T7` subagent skeleton

## 13. 本任务结论摘要

可以压缩成 6 句话：

1. `subagent` 在 v2 中是受主 runtime 控制的 worker
2. 它不是独立主链 runtime
3. `subagent` 必须先绑定 node，再允许创建与启动
4. 第一版按一次性 worker 设计，不做跨 node 复用
5. 生命周期采用 `create / configure / start / collect / destroy`
6. `subagent` 不直接写 graph，只返回结果，由主链 step 决定正式写回
