# S3-T5 Step / Orchestrator 契约（V1）

更新时间：2026-04-22  
状态：Draft  
对应任务：`S3-T5`

## 1. 目标

本任务用于定义 `runtime-v2` 第一版 `step`、`orchestrator` 与 `StepResult` 的正式契约。

目标是：

1. 明确 `step` 是唯一主判断中心
2. 明确 `orchestrator` 是控制器，只执行 `StepResult`
3. 明确 `StepResult` 必须完整到足以让控制器无需二次判断

## 2. 正式结论

本任务最终结论如下：

1. `step` 是当前 `active_node` 的执行者与判断者
2. `orchestrator` 是控制器，只负责执行 `StepResult`
3. `phase` 切换由 `step` 决定
4. `StepResult` 必须足够完整，令 orchestrator 无需再判断
5. `step` 允许增量扩展 graph，但不允许重写已有 node 定义

## 3. Step 的角色

`step` 在 v1 中负责：

1. 读取当前正式上下文
2. 推进当前 `active_node`
3. 生成当前 node 的执行产出
4. 判断当前 node 接下来怎么走
5. 决定下一步 `phase`
6. 必要时追加多个 `followup_nodes`

`step` 不负责：

1. 直接修改已有 node 定义
2. 直接落正式 graph 状态
3. 直接修改 `RunContext`

## 4. Orchestrator 的角色

`orchestrator` 在 v1 中的角色是控制器。

它负责：

1. 驱动 `step`
2. 接收 `StepResult`
3. 应用 `node_patch`
4. 执行 `node_decision`
5. 执行 `runtime_control`
6. 维护正式状态一致性

它不负责：

1. 对 `StepResult` 做二次语义判断
2. 重新决定 phase
3. 重新决定 node 去向

## 5. StepResult 最小正式接口

```ts
type NodePatch = {
  append_artifacts?: string[];
  append_evidence?: string[];
  append_notes?: string[];
};

type NodeExecutionDecision = {
  node_action: "continue" | "block" | "complete" | "fail" | "switch" | "abandon";
  target_node_id?: string;
  block_reason?: string;
  blocked_by?: "user" | "verification" | "system" | "tool" | "dependency";
  resume_signal?: string;
};

type RuntimeControlDecision = {
  next_phase?: "prepare" | "execute" | "finalize";
  consume_signals?: Array<
    "user_reply" | "verification_result" | "subagent_result" | "async_tool_result"
  >;
};

type FollowupNodeRequest = {
  node_id: string;
  name: string;
  description?: string;
  kind?: string;
  depends_on: string[];
};

type StepResult = {
  node_patch?: NodePatch;
  node_decision: NodeExecutionDecision;
  runtime_control?: RuntimeControlDecision;
  followup_nodes?: FollowupNodeRequest[];
};
```

## 6. NodePatch 规则

本任务明确规定：

1. `NodePatch` 只作用于当前 `active_node`
2. `NodePatch` 只允许追加
3. `artifacts / evidence / notes` 第一版都先用 `string[]`
4. 不允许覆盖、删除、重排已有内容

## 7. NodeDecision 规则

## 7.1 switch

本任务明确规定：

1. `switch` 表示当前 node 暂停推进
2. `switch` 不代表当前 node 结束
3. `switch` 必须给出 `target_node_id`
4. orchestrator 执行 `switch` 时：
   - 当前 node -> `paused`
   - 目标 node -> `running`
   - `active_node_id` 切换到目标 node

## 7.2 abandon

本任务明确规定：

1. `abandon` 表示当前 node 被正式放弃
2. `abandon` 不等于 `fail`
3. `abandon` 后当前 node -> `abandoned`
4. `abandon` 必须给出后续承接目标

承接目标至少满足以下其一：

1. 提供 `target_node_id`
2. 提供 `followup_nodes`

## 8. Followup Nodes 规则

本任务明确规定：

1. `step` 有权读取当前 graph
2. `step` 可以一次追加多个 `followup_nodes`
3. `followup_nodes` 使用正式机器 `node_id`
4. `depends_on` 必填
5. `depends_on` 可引用已有 node
6. `depends_on` 可引用同批新增 node
7. `followup_nodes` 允许形成局部 DAG
8. `followup_nodes` 不允许形成环
9. 不允许生成孤立 node

落图后初始状态规则如下：

1. 依赖已满足 -> `ready`
2. 依赖未满足 -> `pending`

如果 `target_node_id` 指向新增 node，则该目标在落图后必须可执行。

## 9. Phase 与 StepResult 的关系

本任务明确规定：

1. `StepResult` 属于当前 phase 的输出
2. `runtime_control.next_phase` 由 `step` 决定
3. orchestrator 不再补充 phase 判断
4. `StepResult` 在当前 phase 语义下必须自洽

## 10. Node 状态迁移约束

本任务直接沿用以下关键迁移：

1. `pending -> ready`
2. `ready -> running`
3. `running -> paused`
4. `paused -> ready`
5. `running -> blocked`
6. `blocked -> ready`
7. `running -> completed`
8. `running -> failed`
9. `running -> abandoned`

同时明确规定：

1. `active_node_id` 若存在，必须对应一个 `running` node

## 11. 对其他任务的直接输入

`S3-T5` 直接服务：

1. `S4-T4` 极简 RunContext 结构
2. `S5-T4` 执行图关系模型
3. `S11-T3` 统一 handoff
4. `S11-T4` finalize 闭环
5. `S12-T2` 事件模型

同时它直接依赖：

1. `S3-T2` RuntimeOrchestrator 定义
2. `S3-T4` step loop 最小职责
3. `S5-T3` 最小 node 定义
4. `S5-T4` 执行图关系模型

## 12. 本任务结论摘要

可以压缩成 5 句话：

1. `step` 是唯一主判断中心
2. `orchestrator` 是控制器，只执行 `StepResult`
3. `StepResult` 必须完整到无需控制器补判断
4. `step` 允许增量扩展 graph，但不修改已有 node 定义
5. `switch / abandon / followup_nodes` 构成第一版 graph 推进主接口
