# S11-T7 Verification Skeleton（V1）

更新时间：2026-04-29  
状态：Draft  
对应任务：`S11-T7`

## 1. 目标

本任务用于定义 `runtime-v2` 第一版 verifier chain 的最小骨架。

目标是：

1. 明确 verifier 只服务 final verification
2. 明确 verifier 的输入输出边界
3. 让 verifier 与 finalize pipeline 正式对接

## 2. 正式结论

本任务最终结论如下：

1. verifier skeleton 只服务 final verification
2. 中途验证、测试、自查都归主链路 agent 自己处理
3. verifier 只消费统一 `handoff`
4. verifier 输出保持极简
5. verifier 不决定后续动作
6. verifier 第一版采用独立轻量 ReAct 架构
7. verifier 不复用 execute 当前的 `ReActStepRunner`
8. verifier 第一版允许多轮内部循环，但有轮数上限

## 3. Verifier 的定位

verifier 在 v1 中的定位是：

1. final verification 专用链路
2. 最终结果守门器
3. 独立 verifier agent

它不负责：

1. 中途 node 级验证
2. execute 阶段测试
3. 主链路自查
4. runtime 后续动作决策

## 4. 输入边界

本任务明确规定：

1. verifier 只认统一 `handoff`
2. verifier 不直接读取 `RunContext`
3. verifier 不回头消费 execute 全量上下文

因此：

1. verifier 的正式输入就是 `handoff`
2. `handoff` 是 verifier 的唯一主输入对象

## 5. 输出边界

第一版 verifier 输出保持极简：

```ts
type VerificationResult = {
  result_status: "pass" | "fail";
  summary: string;
  issues: string[];
};
```

本任务明确规定：

1. verifier 不直接输出 `partial`
2. verifier 不直接输出 `next_phase`
3. verifier 不直接输出 graph 动作
4. `issues` 在 `pass` 时允许为空列表

## 6. Verifier 不决定后续动作

本任务明确规定：

1. verifier 只负责给出验证结果
2. verification fail 后是回退 `execute`
3. 还是进入最终 `fail`
4. 或在 verification pass 后收敛成 `pass / partial`

这些都由 finalize pipeline 决定，不由 verifier 决定。

## 7. 推荐最小接口方向

第一版建议如下：

```ts
type Handoff = {
  goal: string;
  user_input: string;
  graph_summary: string;
  final_output: string;
};

interface VerifierChain {
  verify(handoff: Handoff): VerificationResult;
}
```

这条接口的重点不是字段最终名称，而是边界：

1. 输入只接 `handoff`
2. 输出只给 `VerificationResult`
3. 第一版 `handoff` 当前不额外携带 `run_id / task_id`

## 7.1 轻量 ReAct 边界

当前第一版补充结论如下：

1. verifier 采用轻量 ReAct 架构
2. 允许 verifier 内部进行多轮循环
3. 第一版最大轮数上限为 `20`
4. 第一版 verifier 当前不接 tool call
5. verifier 不产出 `StepResult`
6. verifier 不写 graph，不写 phase 决策

## 8. 与 Model Provider 的关系

本任务与 `S7` 对齐如下：

1. verifier 复用统一 `ModelProvider`
2. verifier 复用统一 adapter skeleton
3. verifier 不额外定义第二套 provider 协议

区别只在于：

1. prompt 输入是 verifier 专用
2. 调用位置是在 finalize 内部
3. verifier model provider 与 finalize model provider 当前分开挂载

## 9. 与 Finalize Pipeline 的关系

本任务与 `S11-T6` 直接对齐：

1. finalize 先生成 `handoff`
2. finalize 调用 verifier
3. verifier 返回 `VerificationResult`
4. finalize 根据结果决定：
   - 回退 `execute`
   - 还是构建 `RunOutcome`

## 10. 事件锚点

verifier skeleton 与事件模型直接对齐：

1. `final_verification_started`
2. `final_verification_passed`
3. `final_verification_failed`

## 11. 第一版边界

第一版明确不建议：

1. verifier 回头消费完整主链路上下文
2. verifier 输出过重结构
3. verifier 决定后续 runtime 动作
4. 把中途测试也塞进 verifier skeleton

## 12. 对其他任务的直接输入

`S11-T7` 直接服务：

1. `S11-T6` finalize pipeline 实现
2. `S7-T6` model adapter skeleton
3. `S12-T7` 测试 skeleton

同时它直接依赖：

1. `S11-T3` 统一 handoff
2. `S11-T4` finalize / verification / outcome 闭环
3. `S11-T6` finalize pipeline 规则

## 13. 本任务结论摘要

可以压缩成 5 句话：

1. verifier skeleton 只服务 final verification
2. 中途验证和测试都归主链路 agent 自己处理
3. verifier 只消费统一 `handoff`
4. verifier 只输出极简 `VerificationResult`
5. 后续动作由 finalize pipeline 决定，不由 verifier 决定
