# S3-T3 Phase Engine 接口定义（V1）

更新时间：2026-04-21  
状态：Draft  
对应任务：`S3-T3`

## 1. 目标

本任务用于定义 `runtime-v2` 的 phase engine 接口。

目标是：

1. 明确 `PreparePhase`、`ExecutePhase`、`FinalizePhase` 的统一接口
2. 让 phase 与 `RuntimeOrchestrator` 的职责边界稳定下来
3. 让后续 `S4-T3`、`S5-T3`、`S6-T3` 都能围绕同一套 phase 接口继续展开

## 2. 正式结论

本任务最终结论如下：

1. phase 统一保留一个主方法：`run(ctx)`
2. phase 的输入输出统一都是 `RunContext`
3. phase 允许改写 `RunContext`
4. phase 只改自己负责的状态域
5. phase 之间的切换权只属于 `RuntimeOrchestrator`

## 3. Phase 结构

第一版统一定义 3 个 phase：

1. `PreparePhase`
2. `ExecutePhase`
3. `FinalizePhase`

它们都实现统一接口：

```python
class Phase:
    def run(self, ctx: RunContext) -> RunContext: ...
```

第一版不再为每个 phase 额外设计不同的 `Result` 对象。

## 4. 为什么只保留一个主方法

保留单一 `run(ctx)` 方法的原因是：

1. 第一版先确保 phase 模型稳定
2. 避免 phase 设计一开始就变成复杂生命周期框架
3. 让 orchestrator 调用方式保持统一

后续如果有必要，再考虑补充：

1. `validate(ctx)`
2. `can_enter(ctx)`
3. `can_exit(ctx)`

但这些不属于第一版正式接口。

## 5. RunContext 在 phase 中的地位

`RunContext` 是 phase engine 的唯一正式上下文对象。

结论如下：

1. phase 统一接收 `RunContext`
2. phase 统一返回 `RunContext`
3. orchestrator 始终持有 run 级唯一主上下文

这意味着：

1. phase 不应自己发明另一套 phase-local 主对象
2. phase 的工作是消费并更新统一上下文

## 6. Phase 可修改的内容

phase 允许改写 `RunContext`，但必须遵守边界。

### PreparePhase 可改写

1. `phase_state`
2. `task_graph_state` 中的计划结果
3. prompt-build 之后进入主链路所需的 prepare 产物
4. `handoff` 的早期草稿信息

### ExecutePhase 可改写

1. `phase_state`
2. `task_graph_state`
3. `tool_results`
4. `tool_failures`
5. `lifecycle_state`
6. compression 相关运行状态

### FinalizePhase 可改写

1. `phase_state`
2. `final_answer`
3. `handoff`
4. `known_gaps`
5. `result_status`
6. `lifecycle_state`

## 7. Phase 不应修改的内容

为了避免状态污染，phase 需要遵守以下约束：

1. phase 不决定下一个 phase 是谁
2. phase 不直接控制 orchestrator 的 phase 切换
3. phase 不私自发明独立状态容器
4. phase 不直接持有完整 `messages`

## 8. Messages 与 Compression 的边界

基于本轮对接，正式结论如下：

### Messages

1. `messages` 不放入 `RunContext`
2. `messages` 视为 runtime 内部工作缓存或上下文载体
3. phase 可以间接使用消息系统，但 `RunContext` 不把完整消息历史作为核心字段持有

### Compression

compression 信息放入 `RunContext`，但只放运行保障状态，不放正文内容。

建议纳入 `RunContext` 的是：

1. `compression_state`
2. `compression_summary`
3. `context_budget`

不纳入 `RunContext` 的是：

1. 完整 message 列表
2. 压缩前后正文
3. 大段上下文原文

这意味着：

1. compression 属于主链路运行保障部分
2. 但 compression 的正文材料仍由消息系统 / memory 系统持有

## 9. Phase 切换权

phase 之间的切换权只属于 `RuntimeOrchestrator`。

也就是说：

1. phase 负责返回更新后的 `RunContext`
2. orchestrator 根据 `RunContext.phase_state` 和主流程规则决定是否进入下一阶段

第一版不采用：

1. phase 自己直接跳转 phase
2. phase 自己递归调用其他 phase

## 10. 与状态字段命名的对齐

本任务与当前状态命名对齐如下：

1. 使用 `lifecycle_state`
2. 使用 `result_status`
3. 不再使用 `runtime_state`
4. 不再使用 `runtime_status`

因此 phase engine 需要围绕：

1. `phase_state`
2. `lifecycle_state`
3. `result_status`

三类状态共同工作。

## 11. 对其他任务的直接输入

`S3-T3` 直接服务：

1. `S3-T4` step loop 最小职责定义
2. `S3-T5` runtime skeleton
3. `S4-T3` 统一状态图
4. `S5-T3` task graph 最小执行单元
5. `S6-T3` runtime 与工具语义耦合策略

同时它直接依赖：

1. `S3-T2` RuntimeOrchestrator 定义
2. `S4-T2` 核心状态对象定义

## 12. 本任务结论摘要

可以压缩成 5 句话：

1. phase engine 第一版统一采用 `run(ctx) -> RunContext`
2. phase 输入输出统一都是 `RunContext`
3. phase 可以改写上下文，但只改自己负责的状态域
4. phase 切换权只属于 `RuntimeOrchestrator`
5. `messages` 不进 `RunContext`，但 compression 运行状态进入 `RunContext`
