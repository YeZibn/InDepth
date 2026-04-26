# S4-T2 核心状态对象集合定义（V1）

更新时间：2026-04-21  
状态：Draft  
对应任务：`S4-T2`

## 1. 目标

`runtime-v2` 第一版先确立 2 个运行中核心状态对象：

1. `RunContext`
2. `TaskGraphState`

同时明确运行结束后的独立收敛产物：

1. `RunOutcome`

这组对象的目标是：

1. 给 `RuntimeOrchestrator` 提供统一状态底座
2. 让 lifecycle、task graph、tool、verification 能围绕同一套状态流对齐
3. 避免继续把关键运行状态隐式编码在 message 或 prompt 中

## 2. 设计结论

本任务最终结论如下：

1. `RunContext` 作为 run 级顶层聚合状态对象存在
2. `RunContext` 第一版采用极简正式结构
3. `PhaseState` 不再作为第一版正式核心对象单列存在
4. 原 `PhaseState` 的最小必要信息并入 `RunLifecycle`
5. `TaskGraphState` 继续作为正式执行骨架状态对象存在
6. `RunOutcome` 不并入运行中核心状态对象，而作为运行结束后的独立收敛产物

## 3. 核心对象定义

## 3.1 RunContext

`RunContext` 是一次 run 的唯一主状态容器。

它的角色是：

1. 由 `RuntimeOrchestrator` 创建并持有
2. 在 prepare / execute / finalize 全程流转
3. 聚合本次运行所需的主要状态

`RunContext` 第一版正式结构如下：

```ts
type RunContext = {
  run_identity: RunIdentity;
  run_lifecycle: RunLifecycle;
  runtime_state: RuntimeState;
  domain_state: DomainState;
};
```

第一版明确规定：

1. `RunContext` 只保留主链长期需要的正式状态
2. `RunContext` 不再追求“把所有运行材料都挂进去”
3. `RunContext` 不保留 `messages`
4. `RunContext` 不保留 `execution_summary`
5. `RunContext` 不常驻挂载 memory / preference runtime state

### 3.1.1 `RunLifecycle`

第一版中，原 `PhaseState` 的最小必要信息统一并入 `RunLifecycle`。

最小结构如下：

```ts
type RunLifecycle = {
  lifecycle_state: string;
  current_phase: "prepare" | "execute" | "finalize";
  result_status?: string;
  stop_reason?: string;
};
```

也就是说：

1. 第一版不再单列 `PhaseState`
2. phase 控制信息统一通过 `RunLifecycle` 表达
3. 这足以支撑 orchestrator 第一版主链控制

## 3.2 TaskGraphState

`TaskGraphState` 是 v2 的正式执行骨架状态对象。

第一版建议直接包含：

1. `graph_id`
2. `graph_status`
3. `nodes`
4. `active_node_id`
5. `active_node_status`
6. `resume_cursor`
7. `pending_nodes`
8. `blocked_nodes`
9. `completed_nodes`

其中最关键的结论是：

1. `TaskGraphState` 必须直接包含 `active_node`
2. execute 阶段不应再从消息或外部文件重新推测当前执行位置

这也是 task graph 替代当前 todo/runtime 混合控制语义的关键。

## 4. 核心对象的关系

第一版运行中核心对象关系可以概括为：

```text
RunContext
  └─ TaskGraphState
```

含义是：

1. `RunContext` 是总容器
2. `RunLifecycle` 负责生命周期与 phase 视角
3. `TaskGraphState` 负责执行骨架视角

其中：

1. phase 切换由 `RuntimeOrchestrator` 驱动
2. task graph 推进由 execute / prepare 等阶段更新
3. 最终所有状态都回收到 `RunContext`

## 5. RunOutcome 的位置

`RunOutcome` 第一版不并入运行中核心状态对象集合。

这里明确区分两类对象：

### 运行中状态

1. `RunContext`
2. `TaskGraphState`

### 运行结束产物

1. `RunOutcome`

这样分开的原因是：

1. `RunContext` 解决“运行时怎么推进”
2. `RunOutcome` 解决“运行结束后如何判定和交接”
3. 如果过早把两者合并，会让运行态和收尾态重新耦合

## 6. 第一版边界约束

为避免后面重新长歪，第一版建议明确 4 条边界：

1. 关键运行状态必须先进入 `RunContext`，再决定是否进入 message 或 handoff
2. `RunLifecycle` 只负责 lifecycle / phase 级控制信息
3. `TaskGraphState` 不负责 verifier / memory / prompt 细节
4. `RunOutcome` 只在运行结束后生成，不作为运行中状态容器使用
5. `tool_results / handoff / known_gaps / final_answer` 不再作为 `RunContext` 一级正式字段默认常驻

## 7. 对其他任务的直接输入

`S4-T2` 直接服务：

1. `S3-T3` phase engine 接口
2. `S3-T5` runtime skeleton
3. `S5-T3` 最小执行单元定义
4. `S11-T2` run outcome 结构
5. `S12-T2` 事件模型

`S4-T2` 直接依赖：

1. `S3-T2` RuntimeOrchestrator 定义
2. `S5-T2` task graph 命名决策

## 8. 本任务结论摘要

可以压缩成 5 句话：

1. `RunContext` 是 run 级唯一主状态容器，并采用极简正式结构
2. 第一版不再单列 `PhaseState`，phase 控制信息统一并入 `RunLifecycle`
3. `TaskGraphState` 是正式执行骨架，必须直接包含 active node
4. 运行中核心状态系统由 `RunContext + TaskGraphState` 构成
5. `RunOutcome` 是运行结束产物，不并入运行中核心状态对象
