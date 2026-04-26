# S5-T4 执行图关系模型（V1）

更新时间：2026-04-22  
状态：Draft  
对应任务：`S5-T4`

## 1. 目标

本任务用于收敛 `runtime-v2` 第一版中 task graph 的正式关系模型。

本任务重点不是把 graph 做重，而是明确：

1. 哪些关系属于图内正式结构
2. 哪些关系不进入图，而交给主链路运行时判断

## 2. 正式结论

本任务最终结论如下：

1. v1 图内正式关系只保留 `dependencies`
2. `parallel` 暂不进入 v1 正式关系模型
3. `blocking` 不作为静态 graph edge
4. `blocking` 由主链路 LLM 在 step 期间做运行时关系确认
5. v1 新增一个轻量运行时决策对象 `NodeExecutionDecision`

## 3. 图内保留的正式关系

第一版 task graph 内只保留最小显式关系：

1. `dependencies`

它的职责只有一个：

1. 表达 node 在结构上的前置依赖

也就是说：

1. 哪些 node 必须先完成
2. 当前 node 在结构上依赖谁

这些信息应直接来自 graph 本身，而不是由 LLM 临时推断。

## 4. 暂不进入图内的关系

第一版以下关系不进入正式 graph 结构：

1. `parallel-group`
2. `blocking-edge`

原因如下：

1. `parallel` 会显著抬高图模型复杂度
2. 当前阶段更需要主链路上下文能力，而不是提前把关系建死
3. `blocking` 往往是语义性判断，不是纯结构拓扑关系

## 5. blocking 的归属

第一版 `blocking` 定义为运行时判断结果，而不是 graph edge。

它表达的是：

1. 当前 node 虽然已经进入执行链路
2. 但在当前上下文下不应继续推进

因此：

1. `dependency` 解决“结构上先后关系”
2. `blocking` 解决“当前语境下是否应继续”

`blocked` 进入 `node_status`，但 `blocking` 不进入 graph 关系模型。

## 6. blocking 如何获得

第一版采用两段式获取方式。

## 6.1 结构态读取

runtime 在 step 开始时先从状态中读取：

1. `active_node`
2. `dependencies` 满足情况
3. 当前 graph 摘要
4. 最近执行结果摘要
5. 外部输入信号状态

这一层不要求 LLM 创造关系，只负责读取和整理。

## 6.2 主链路语义判定

随后由主链路 LLM 基于上述输入做正式判断：

1. 是否继续执行当前 node
2. 是否进入 `blocked`
3. `block_reason` 是什么
4. `blocked_by` 是谁
5. `resume_signal` 是什么

也就是说：

1. blocking 是主链路的运行时决策
2. 不是 task graph 的静态结构

## 7. NodeExecutionDecision

为了让主链路判断可落地，第一版引入轻量运行时决策对象：

```ts
type NodeExecutionDecision = {
  action: "continue" | "block" | "complete" | "fail" | "switch";
  block_reason?: string;
  blocked_by?: "user" | "verification" | "system" | "tool" | "dependency";
  resume_signal?: string;
  target_node_id?: string;
  rationale?: string;
};
```

它的定位是：

1. 承接主链路对当前 node 的执行判断
2. 为 runtime 回写 `node_status` 提供结构化输入
3. 不替代 graph 本身

## 8. 推荐的判定输入包

为了避免主链路在判定时自己“找数据”，运行时应先组装一个轻量输入包。

建议至少包含：

1. `node_snapshot`
2. `dependency_status`
3. `recent_artifacts`
4. `recent_evidence`
5. `pending_external_signals`
6. `run_goal`
7. `current_phase`

结论是：

1. runtime 负责准备判定上下文
2. 主链路负责输出结构化决策

## 9. 对其他任务的直接输入

`S5-T4` 直接服务：

1. `S3-T4` step loop 最小职责
2. `S4-T3` 统一状态图
3. `S11-T3` handoff 结构
4. `S12-T3` 证据链模型

同时它直接依赖：

1. `S5-T2` task graph 命名决策
2. `S5-T3` 最小 node 定义
3. `S3-T3` phase engine 接口

## 10. 本任务结论摘要

可以压缩成 5 句话：

1. v1 graph 内只保留 `dependencies` 作为正式关系
2. `parallel` 暂不进入 v1 正式结构
3. `blocking` 不做 graph edge，而是运行时判断结果
4. 主链路 LLM 基于结构态和上下文做 blocking 确认
5. 运行时通过 `NodeExecutionDecision` 承接这份判断
