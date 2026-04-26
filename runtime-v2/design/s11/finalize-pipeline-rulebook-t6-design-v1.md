# S11-T6 Finalize Pipeline 规则（V1）

更新时间：2026-04-22  
状态：Draft  
对应任务：`S11-T6`

## 1. 目标

本任务用于定义 `runtime-v2` 第一版 `finalize` pipeline 的正式执行规则。

目标是：

1. 明确何时允许进入 `finalize`
2. 明确 `finalize -> verification -> outcome` 的顺序
3. 明确 verification fail 后如何回退
4. 明确最终失败出口
5. 为后续记忆接入预留挂点

## 2. 正式结论

本任务最终结论如下：

1. 进入 `finalize` 必须满足正式触发条件
2. final verification fail 后允许多次回退 `execute -> finalize`
3. `partial` 只允许在 verification pass 时出现
4. `finalize` 必须存在最终失败出口
5. 第一版保留 finalize 重试上限概念，但不在设计层写死数值
6. finalize closeout 后必须预留记忆接入挂点

## 3. 进入 Finalize 的触发条件

第一版建议至少满足以下条件之一：

1. 当前主链路已经形成可交付 `final_output`
2. 当前 graph 已无必须继续推进的关键 `running / ready` node
3. `step` 明确判断当前 run 应进入最终收口尝试

本任务明确规定：

1. `finalize` 不是任意时刻都可进入
2. 它应是一次“正式交付尝试”

## 4. Finalize Pipeline 正式顺序

第一版推荐正式顺序如下：

```text
enter finalize
  -> build handoff
  -> run final verification
     -> pass -> determine result_status -> build RunOutcome -> close run
     -> fail -> build finalize_return_input -> back to execute
```

## 5. 分步规则

## 5.1 Build Handoff

规则如下：

1. 进入 `finalize` 后先生成统一 `handoff`
2. `handoff` 是 final verification 的正式输入
3. 没有 `handoff` 不允许进入 verification

## 5.2 Run Final Verification

规则如下：

1. verifier 使用独立链路
2. verifier 只验证最终结果
3. verifier 消费统一 `handoff`
4. verifier 返回 `VerificationResult`

## 5.3 Determine Result Status

规则如下：

1. `result_status` 由 verification 与 finalize 共同收敛
2. 允许结果为：
   - `pass`
   - `partial`
   - `fail`

但本任务明确规定：

1. `partial` 只允许在 verification `pass` 时出现
2. verification `fail` 时不直接收成 `partial`

## 5.4 Build RunOutcome

规则如下：

1. 只有 verification `pass` 后，才允许正式构建 `RunOutcome`
2. `handoff` 进入 `RunOutcome.handoff`
3. `final_answer`、`result_status`、`stop_reason` 在此阶段正式收敛

## 6. Verification Fail 的回退规则

本任务明确规定：

1. verification fail 不直接结束 run
2. verification fail 默认回退到 `execute`
3. fail 问题通过 `finalize_return_input` 正式回灌

推荐结构如下：

```ts
type FinalizeReturnInput = {
  verification_summary: string;
  verification_issues: string[];
};
```

写入后执行：

1. `current_phase -> execute`
2. 下一轮 `step` 读取这份返工输入继续修正

## 7. 多次 Finalize 回退

第一版明确允许：

1. `execute -> finalize -> execute`
2. `execute -> finalize -> execute -> finalize`

也就是说：

1. final verification 不是一次性闸门
2. 它可以成为主链路多轮收口尝试的一部分

## 8. Finalize 重试上限

本任务明确规定：

1. 第一版保留“重试上限”概念
2. 但不在设计文档中写死具体数值
3. 具体数值留给实现配置层决定

这样做的原因是：

1. runtime 需要有明确失败出口
2. 但不同任务类型对重试容忍度可能不同

## 9. 最终 Fail 出口

第一版建议以下情况可进入最终 `fail`：

1. final verification fail 且达到 finalize 重试上限
2. 最终未形成可交付输出
3. 关键证据始终不足，无法支撑结果成立

这意味着：

1. `fail` 必须有正式退出条件
2. 不能让 run 无限在 `execute / finalize` 间循环

## 10. Partial 的限制

本任务再次明确：

1. `partial` 只在 verification `pass` 时允许
2. `partial` 表示“有限完成 + 正式说明”
3. 它不是 verification fail 的宽松替代

## 11. Memory Hook 预留

本任务明确规定：

1. finalize closeout 后必须预留记忆接入挂点
2. 第一版先不让记忆写入进入结果判定主链路

建议预留两个挂点：

1. `post_finalize_memory_extract`
2. `post_outcome_memory_write`

推荐语义如下：

### `post_finalize_memory_extract`

输入来源：

1. `handoff`
2. `RunOutcome`
3. 必要时的 `finalize_return_input` 历史

作用：

1. 提取 system memory / preference 候选

### `post_outcome_memory_write`

输入来源：

1. 已提取的 memory items

作用：

1. 正式写入 memory / preference store

本任务明确规定：

1. 这两个挂点先只做预留
2. 不参与当前 `result_status` 判定
3. 不阻塞 `RunOutcome` 生成

## 12. 与事件模型的关系

本任务与 `S12` 对齐如下：

1. `handoff_built`
2. `final_verification_started`
3. `final_verification_passed`
4. `final_verification_failed`
5. `finalize_return_prepared`
6. `run_outcome_built`

都应成为 finalize pipeline 的正式事件锚点。

## 13. 对其他任务的直接输入

`S11-T6` 直接服务：

1. `S11-T7` verification skeleton
2. `S11-T2` RunOutcome 实现
3. `S4-T4` finalize_return_input 挂载
4. `S12-T3` closeout 事件对齐
5. `S8` 后续 memory 挂点接入

同时它直接依赖：

1. `S11-T3` 统一 handoff
2. `S11-T4` finalize / verification / outcome 闭环
3. `S11-T5` result_status 与证据要求

## 14. 本任务结论摘要

可以压缩成 5 句话：

1. `finalize` 只有在满足正式触发条件时才能进入
2. final verification fail 后允许回退 `execute` 继续修正
3. `partial` 只允许在 verification pass 时出现
4. finalize 必须有重试上限与最终 fail 出口
5. finalize closeout 后必须预留记忆接入挂点
