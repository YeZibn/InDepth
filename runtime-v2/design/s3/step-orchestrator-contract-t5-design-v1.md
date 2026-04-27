# S3-T5 Step / Orchestrator 契约（V1）

更新时间：2026-04-27  
状态：Draft  
对应任务：`S3-T5`

## 1. 目标

本任务用于定义 `runtime-v2` 第一版 `step`、`orchestrator` 与 `StepResult` 的正式契约。

目标是：

1. 明确 `step` 是当前 `active_node` 的执行者与判断者
2. 明确 `orchestrator` 是控制器，负责接收并提交 `StepResult`
3. 明确 `StepResult` 是 execute 执行推进的正式收口结构

## 2. 正式结论

本任务最终结论如下：

1. `step` 是当前 `active_node` 的执行者与判断者
2. `step` 可以内部采用 ReAct 执行方式
3. `tool / llm / skill` 只提供中间材料，不直接改 graph
4. `patch` 是 `StepResult` 的一部分，不是独立 tool
5. `orchestrator` 负责接收 `StepResult`、做一致性校验并执行 patch
6. 当前阶段只开放执行推进，不开放图结构重规划

## 3. Step 的角色

`step` 在 v1 中负责：

1. 读取当前正式上下文
2. 推进当前 `active_node`
3. 在内部执行 observe / think / act 闭环
4. 调用 `tool / llm / skill` 获取中间材料
5. 生成当前 node 的最终执行产出
6. 将本轮结果收敛为正式 `StepResult`

`step` 不负责：

1. 直接落正式 graph 状态
2. 直接修改 `RunContext`
3. 让 tool 直接改 graph
4. 在当前阶段重规划 graph 结构

## 4. Orchestrator 的角色

`orchestrator` 在 v1 中的角色是控制器。

它负责：

1. 驱动 `step`
2. 接收 `StepResult`
3. 校验 `StepResult` 是否与当前执行阶段约束一致
4. 应用 `patch`
5. 维护正式状态一致性
6. 把更新后的 graph 回写正式上下文

它不负责：

1. 代替 `step` 生成业务结论
2. 让 tool 直接落正式 graph 状态
3. 在当前阶段替 `step` 发明图结构变更

## 5. StepResult 最小正式接口

```ts
type ResultRef = {
  ref_id: string;
  ref_type: string;
  title?: string;
  content?: string;
};

type NodePatch = {
  node_status?: "ready" | "running" | "blocked" | "completed" | "failed";
  block_reason?: string;
  failure_reason?: string;
  append_notes?: string[];
  append_artifacts?: ResultRef[];
  append_evidence?: ResultRef[];
};

type StepResult = {
  output_text?: string;
  status: "completed" | "blocked" | "failed";
  patch?: NodePatch;
  artifacts?: ResultRef[];
  evidence?: ResultRef[];
  block_reason?: string;
  failure_reason?: string;
};
```

这里补充一条当前正式对接结论：

1. `ResultRef` 是当前执行推进阶段中 `artifacts / evidence` 的统一最小引用结构
2. 当前不再沿用 `string` 作为正式 `artifacts / evidence` 承载类型
3. 后续若需要拆分更细的 `ArtifactRef / EvidenceRef`，也应在 `ResultRef` 基础上演进，而不是回退到裸字符串

## 6. 当前阶段的核心分层

当前阶段正式规定：

1. `tool / llm / skill` 负责提供中间材料
2. `step` 负责把中间材料收敛成最终 `StepResult`
3. `patch` 是 `StepResult` 的一部分，不是独立 tool
4. `orchestrator` 负责接收 `StepResult` 并统一提交 patch

## 7. StepResult 状态规则

本任务明确规定：

1. `StepResult.status` 第一版只保留：
   - `completed`
   - `blocked`
   - `failed`
2. 当前不引入：
   - `running`
   - `partial`
   - `cancelled`
3. `completed` 表示本轮 step 已完成收口
4. `blocked` 表示本轮 step 当前无法继续推进
5. `failed` 表示本轮 step 已进入失败态

## 8. StepResult 与 patch 的一致性

本任务明确规定：

1. `StepResult.status` 是 step 对本轮执行结果的主声明
2. `patch` 是该结果在 graph 上的正式落地表达
3. 二者原则上必须语义一致
4. 发生冲突时，由 orchestrator 显式报错，不做隐式修正

第一版允许的特殊情况如下：

1. `status = completed` 且 `patch = None`
2. `status = failed` 且 `patch = None`，作为异常兜底路径

第一版默认不允许：

1. `status = blocked` 且 `patch = None`
2. `status = blocked` 但没有 `block_reason`
3. `status = failed` 但没有 `failure_reason`

## 9. 当前阶段 patch 权限范围

本任务明确规定：

1. 当前阶段只开放执行推进 patch
2. `patch` 只作用于当前 `active_node`
3. 允许直接修改的字段只有：
   - `node_status`
   - `block_reason`
   - `failure_reason`
   - `notes`
   - `artifacts`
   - `evidence`
4. 当前不开放：
   - `new_nodes`
   - `dependencies`
   - `owner`
   - `order`
   - 通用 `active_node_id` 切换

同时补充当前模块边界：

1. 当前模块只处理执行推进 patch 提交链
2. 不进入图结构重规划
3. 不要求当前模块内实现 `StepResult`
4. 但默认未来 `StepResult.patch` 的 graph 变更部分，应收敛为正式 `TaskGraphPatch`

## 10. 追加字段语义

本任务明确规定：

1. `notes` 采用追加语义
2. `artifacts` 采用追加语义
3. `evidence` 采用追加语义
4. `block_reason / failure_reason` 作为当前态字段覆盖写入

## 11. Phase 与 StepResult 的关系

当前阶段补充约束如下：

1. `StepResult` 属于当前 phase 的输出
2. 当前阶段不要求 step 直接决定 phase
3. `StepResult` 在当前 phase 语义下必须自洽
4. 当前重点是 execute 内部执行推进，不扩展更大控制面

## 12. Node 状态迁移约束

本任务当前直接沿用以下关键迁移：

1. `pending -> ready`
2. `ready -> running`
3. `running -> blocked`
4. `blocked -> ready`
5. `running -> completed`
6. `running -> failed`

同时明确规定：

1. 当前阶段只收紧执行推进所需流转
2. 图重规划相关流转留待后续单独设计

## 13. 后续扩展边界

以下能力仍保留为后续专题，不在本轮执行推进契约内落地：

1. `switch`
2. `abandon`
3. `followup_nodes`
4. 图结构重规划
5. 更完整的 phase 控制决策

当前同时明确：

1. `TaskGraphStore.apply_patch(...)` 是执行推进阶段的正式 graph 提交边界
2. 它不仅负责 merge，也负责基础一致性校验与状态流转校验

## 14. 对其他任务的直接输入

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

## 15. 本任务结论摘要

可以压缩成 5 句话：

1. `step` 是唯一主判断中心
2. `step` 可以内部使用 ReAct，但 graph 只接收最终 `StepResult`
3. `patch` 是 `StepResult` 的一部分，不是独立 tool
4. `orchestrator` 负责校验并提交 patch
5. 当前阶段只开放执行推进，不开放图结构重规划
