# S11-T3 统一 Handoff 结构定义（V1）

更新时间：2026-04-22  
状态：Draft  
对应任务：`S11-T3`

## 1. 目标

本任务用于定义 `runtime-v2` 第一版统一 `handoff` 的正式结构。

目标是：

1. 明确 `handoff` 只服务最终交付阶段
2. 明确 `handoff` 在进入 `finalize` 时生成
3. 明确 final verification 与 `RunOutcome` 共用同一份 `handoff`

## 2. 正式结论

本任务最终结论如下：

1. v1 不单独保留 `verification_handoff`
2. v1 只保留一个正式 `handoff`
3. `handoff` 在进入 `finalize` 时生成
4. final verification 直接消费这份 `handoff`
5. `RunOutcome.handoff` 保留同一份正式 `handoff`

## 3. Handoff 的角色

`handoff` 在 v1 中的定位是：

1. 最终结果交接包
2. final verification 的正式输入
3. `RunOutcome` 的正式组成部分

它不负责：

1. 中途 phase 交接
2. 中间 node 级验证
3. 承载完整主链路上下文

## 4. 生成时机

本任务明确规定：

1. `handoff` 不在 `execute` 中途生成
2. `handoff` 不只在 run 结束后补建
3. `handoff` 必须在进入 `finalize` 时生成

原因是：

1. final verification 需要稳定输入
2. verifier 不应回头消费主链路完整上下文
3. `RunOutcome` 应复用 finalize 期间已经收敛出的正式交接结果

## 5. 第一版最小结构

第一版建议 `handoff` 至少包含以下字段：

```ts
type Handoff = {
  handoff_id: string;
  run_id: string;
  task_id: string;
  graph_id: string;

  goal: string;
  final_output: string;

  evidence_refs: string[];
  artifact_refs: string[];

  graph_summary: string;
  final_node_ids: string[];

  verification_questions: string[];
};
```

## 6. 字段分组说明

## 6.1 identity

1. `handoff_id`
2. `run_id`
3. `task_id`
4. `graph_id`

作用：

1. 标识这份 handoff 属于哪次运行
2. 为 verification 与 outcome 提供稳定锚点

## 6.2 goal / output

1. `goal`
2. `final_output`

作用：

1. 明确最终要验证的目标
2. 明确当前准备交付的最终结果

## 6.3 evidence / artifacts

1. `evidence_refs`
2. `artifact_refs`

作用：

1. 给 verification 提供证据入口
2. 不把全量正文塞进 `handoff`

## 6.4 graph closeout

1. `graph_summary`
2. `final_node_ids`

作用：

1. 提供 graph 收敛概览
2. 指向最终结果所依赖的关键 nodes

## 6.5 verification focus

1. `verification_questions`

作用：

1. 明确 final verification 的检查焦点
2. 避免 verifier 做泛化审查

## 7. Verification Questions 的约束

第一版 `verification_questions` 虽然类型为 `string[]`，但生成策略应来自固定模板，而不是完全自由生成。

第一版重点围绕 4 个方向：

1. 最终结果是否满足 `goal`
2. 最终结果是否有足够证据支撑
3. 最终结果是否存在明显遗漏、冲突或伪完成
4. 当前 graph 是否达到可交付收敛状态

## 8. 第一版边界

第一版明确不进入 `handoff` 的内容包括：

1. 完整 message history
2. 完整 tool trace
3. 全量 task graph
4. 全量 evidence 正文
5. 中途 verification 专用包装对象

## 9. 对其他任务的直接输入

`S11-T3` 直接服务：

1. `S11-T4` finalize / verification / outcome 闭环
2. `S11-T2` RunOutcome 定义
3. `S3-T4` step 输出与 finalize 对接
4. `S12-T3` 证据链模型

同时它直接依赖：

1. `S5-T4` 执行图关系模型
2. `S3-T4` step / orchestrator 边界

## 10. 本任务结论摘要

可以压缩成 5 句话：

1. v1 只保留一个正式 `handoff`
2. `handoff` 在进入 `finalize` 时生成
3. final verification 与 `RunOutcome` 共用同一份 `handoff`
4. `handoff` 只承载最终交付验证所需的最小信息
5. 中途验证不再单独占用 handoff 结构
