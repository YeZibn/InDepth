# S4-T4 极简 RunContext 结构（V1）

更新时间：2026-04-22  
状态：Draft  
对应任务：`S4-T4`

## 1. 目标

本任务用于定义 `runtime-v2` 第一版极简 `RunContext` 的正式结构。

目标是：

1. 收缩 `RunContext`，只保留主链路长期需要的正式状态
2. 去掉不必要的常驻运行对象
3. 为 `step`、`orchestrator`、`finalize` 提供统一最小上下文

## 2. 正式结论

本任务最终结论如下：

1. `RunContext` 第一版采用 4 个一级区块
2. `RunContext` 不保留 `messages`
3. `RunContext` 不保留 `execution_summary`
4. `RunContext` 不常驻挂载 memory / preference runtime state
5. `verification_state` 按需出现，不默认预创建

## 3. 一级结构

第一版建议结构如下：

```ts
type RunContext = {
  run_identity: RunIdentity;
  run_lifecycle: RunLifecycle;
  runtime_state: RuntimeState;
  domain_state: DomainState;
};
```

## 4. Run Identity

```ts
type RunIdentity = {
  run_id: string;
  task_id: string;
  session_id: string;
  user_input: string;
  goal?: string;
};
```

作用：

1. 标识本次 run
2. 提供主链路和 finalize 的目标锚点

## 5. Run Lifecycle

```ts
type RunLifecycle = {
  lifecycle_state: string;
  current_phase: "prepare" | "execute" | "finalize";
  result_status?: string;
  stop_reason?: string;
};
```

作用：

1. 表达 run 当前处在哪个生命周期阶段
2. 表达 run 最终结果判定

## 6. Runtime State

```ts
type RuntimeState = {
  active_node_id?: string;
  compression_state?: CompressionState;
  external_signal_state?: ExternalSignalState;
  finalize_return_input?: FinalizeReturnInput;
};
```

本任务明确规定：

1. `active_node_id` 若存在，则必须对应一个 `running` node
2. `finalize_return_input` 用于承接 final verification fail 的返工输入

## 6.1 Compression State

```ts
type CompressionState = {
  compressed: boolean;
  compressed_context_ref?: string;
  budget_status?: "healthy" | "tight" | "exceeded";
  context_usage_ratio?: number;
};
```

规则如下：

1. `context_usage_ratio` 只在每次 `step` 开始时计算
2. 它表示当前 step 输入上下文的窗口占比
3. 不单独设计 token 监控子系统

## 6.2 External Signal State

```ts
type ExternalSignalState = {
  pending_user_reply?: SignalRef;
  pending_verification_result?: SignalRef;
  pending_subagent_result?: SignalRef;
  pending_async_tool_result?: SignalRef;
};

type SignalRef = {
  signal_id: string;
  source_type: "user" | "verification" | "subagent" | "tool";
  ref: string;
  arrived_at: string;
};
```

规则如下：

1. pending signal 存在即表示待消费
2. 消费后直接删除
3. signal 只保存引用，不保存完整内容

## 6.3 Finalize Return Input

```ts
type FinalizeReturnInput = {
  verification_summary: string;
  verification_issues: string[];
};
```

作用：

1. 承接 final verification fail 的问题
2. 作为下一轮 `execute` 的正式输入

## 7. Domain State

```ts
type DomainState = {
  task_graph_state: TaskGraphState;
  verification_state?: VerificationState;
};
```

## 7.1 Verification State

```ts
type VerificationState = {
  verification_status?: "pending" | "running" | "completed" | "failed";
  latest_result_ref?: string;
};
```

规则如下：

1. `verification_state` 是可选字段
2. 默认不预创建
3. 首次进入 final verification 流程时创建
4. 一旦创建，本次 run 内保留到结束

## 8. 明确移除的内容

本任务明确从正式 `RunContext` 中移除：

1. `messages`
2. `execution_summary`
3. `active_graph_id`
4. `phase_state`
5. `memory_runtime_state`
6. `preference_runtime_state`

## 9. 设计理由

本任务收成极简结构的核心原因是：

1. 主链路尽量直接消费正式上下文
2. 不再额外制造摘要中间层
3. recall / save 类能力不再伪装成常驻子系统
4. `RunContext` 只保留真正需要长期挂载的状态

## 10. 对其他任务的直接输入

`S4-T4` 直接服务：

1. `S3-T4` step loop 读取边界
2. `S3-T5` step / orchestrator 契约
3. `S11-T4` finalize fail 回灌 execute
4. `S12-T2` 事件与状态对齐

同时它直接依赖：

1. `S4-T2` 核心状态对象集合
2. `S5-T4` 执行图关系模型
3. `S11-T4` finalize / verification / outcome 闭环

## 11. 本任务结论摘要

可以压缩成 5 句话：

1. `RunContext` 第一版只保留 4 个一级区块
2. `messages` 和 `execution_summary` 都不进入正式结构
3. `compression_state` 和 `external_signal_state` 都保持极简
4. final verification fail 通过 `finalize_return_input` 回灌 `execute`
5. memory / preference runtime state 不再常驻挂载
