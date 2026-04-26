# S7-T5 Context Budget 策略（V1）

更新时间：2026-04-22  
状态：Draft  
对应任务：`S7-T5`

## 1. 目标

本任务用于定义 `runtime-v2` 第一版的 context budget 策略。

目标是：

1. 明确 budget control 只围绕上下文装载展开
2. 明确何时检测上下文压力
3. 明确 budget control 与 compression 的关系

## 2. 正式结论

本任务最终结论如下：

1. 第一版不单独设计 `token budget`
2. 第一版只保留 `context budget`
3. `context budget` 的主目标是保证主链路稳定可运行
4. `context budget` 只在每次 `step` 开始时检测
5. budget control 可以触发压缩或裁剪，但不直接决定业务语义

## 3. Context Budget 的定义

本任务中的 `context budget` 指：

1. 单次模型调用可用上下文窗口的预算
2. 当前输入上下文是否还能安全装入模型调用

它回答的问题是：

1. 当前 prompt 会不会超窗口
2. 是否需要压缩
3. 是否需要裁剪上下文

## 4. 为什么不设计 Token Budget

第一版明确不单独设计 `token budget`。

原因如下：

1. 当前主链路最核心的问题是单次调用是否装得下
2. 我们已经有 `compression_state.context_usage_ratio`
3. 成本治理和总量治理不属于当前主干最优先问题

因此：

1. 不额外引入整次 run 的总量 token 治理系统
2. 第一版只聚焦 request-level 上下文预算

## 5. 检测时机

本任务明确规定：

1. `context budget` 只在每次 `step` 开始时检测
2. 非 step 时刻不主动刷新

这意味着：

1. 不在每次 tool call 后动态刷新
2. 不在每次状态写回后到处挂检测逻辑

这样做的原因是：

1. 语义稳定
2. 实现简单
3. 与主链路节奏一致

## 6. 检测对象

本任务明确规定：

1. 检测对象是“当前 step 准备送入模型的上下文集合”
2. 不是全量历史消息
3. 不是整个 `RunContext`

它主要包括：

1. 当前 phase prompt
2. 当前 node 局部视图
3. recall 注入内容
4. 必要的返工输入
5. 当前 step 所需的最小上下文

## 7. 与 CompressionState 的关系

本任务与 `S4-T4` 直接对齐：

```ts
type CompressionState = {
  compressed: boolean;
  compressed_context_ref?: string;
  budget_status?: "healthy" | "tight" | "exceeded";
  context_usage_ratio?: number;
};
```

这里的关系是：

1. `context budget` 是策略层
2. `compression_state` 是状态记录层

也就是说：

1. budget control 负责判断当前压力
2. `compression_state` 负责记录判断结果

## 8. Budget Control 的动作边界

本任务明确规定：

1. budget control 可以决定是否压缩
2. budget control 可以决定是否裁剪上下文
3. budget control 不直接决定：
   - `next_phase`
   - `node_action`
   - `result_status`

也就是说：

1. 它是运行保障策略
2. 不是业务决策器

## 9. Budget Status

第一版建议继续使用：

1. `healthy`
2. `tight`
3. `exceeded`

建议理解如下：

### `healthy`

表示：

1. 当前上下文窗口压力可接受
2. 不需要额外压缩

### `tight`

表示：

1. 当前上下文接近上限
2. 本轮可能需要压缩或裁剪

### `exceeded`

表示：

1. 当前上下文已超过安全范围
2. 本轮必须压缩或裁剪后才能继续

## 10. Context Usage Ratio

本任务继续沿用：

1. `context_usage_ratio`

其含义是：

1. 当前 step 输入上下文占模型上下文窗口的比例

例如：

1. `0.25` 表示用了约 25%
2. `0.80` 表示用了约 80%

## 11. 与不同链路的关系

第一版建议：

1. `execute` 使用 execute 链路的 context budget 检测
2. `finalize` 使用 finalize 链路的 context budget 检测
3. final verification 使用 verifier 链路的 context budget 检测

也就是说：

1. 不同链路可以有不同 config
2. 但 budget control 原则保持一致

## 12. 第一版边界

第一版明确不建议：

1. 建独立 token 监控系统
2. 在运行中频繁动态调整 budget policy
3. 让 budget control 直接决定业务动作
4. 把 budget control 做成第二个 orchestrator

## 13. 对其他任务的直接输入

`S7-T5` 直接服务：

1. `S7-T6` model adapter skeleton
2. `S3-T5` step / orchestrator 契约实现
3. `S4-T4` compression_state 挂载
4. `S11-T6` finalize pipeline

同时它直接依赖：

1. `S7-T4` generation config 规则
2. `S4-T4` 极简 RunContext 结构
3. `S3-T5` StepResult 与 step 起点检测规则

## 14. 本任务结论摘要

可以压缩成 5 句话：

1. 第一版只保留 `context budget`
2. budget control 的目标是保证单次调用可装载
3. 它只在每次 `step` 开始时检测
4. 它可以触发压缩或裁剪，但不决定业务语义
5. `compression_state` 是 budget control 的状态记录层
