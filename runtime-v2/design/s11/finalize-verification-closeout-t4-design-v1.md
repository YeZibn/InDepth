# S11-T4 Finalize / Verification / Outcome 闭环（V1）

更新时间：2026-04-22  
状态：Draft  
对应任务：`S11-T4`

## 1. 目标

本任务用于定义 `runtime-v2` 第一版中 `finalize`、final verification 与 `RunOutcome` 的收敛闭环。

目标是：

1. 明确 verification 只在 final 前发生
2. 明确 verification fail 后如何回到 `execute`
3. 明确 `RunOutcome` 只在 final verification 通过后生成

## 2. 正式结论

本任务最终结论如下：

1. v1 不保留中途独立 verification phase
2. phase 第一版收缩为 `prepare / execute / finalize`
3. final verification 只验证最终结果
4. final verification 消费统一 `handoff`
5. verification fail 后回退到 `execute`
6. `RunOutcome` 只在 verification pass 后正式生成

## 3. 总体闭环

第一版推荐闭环如下：

```text
execute
  -> finalize
  -> build handoff
  -> final verification
     -> pass -> build RunOutcome -> end run
     -> fail -> write finalize_return_input -> back to execute
```

## 4. Finalize 的角色

`finalize` 在 v1 中不是“必然结束阶段”，而是：

1. 最终交付尝试阶段
2. handoff 收敛阶段
3. final verification 触发阶段
4. `RunOutcome` 构建阶段

这意味着：

1. 进入 `finalize` 不代表 run 必然结束
2. verification fail 后仍可回到 `execute`

## 5. Finalize 内部步骤

第一版建议 `finalize` 期间按以下顺序执行：

1. 生成正式 `handoff`
2. 使用 `handoff` 触发 final verification
3. 获取 `VerificationResult`
4. 若通过，则构建 `RunOutcome`
5. 若失败，则回退到 `execute`

## 6. Verification 的定位

本任务正式规定：

1. verification 不再作为中途主 phase
2. verification 不再处理中间 node 级检查
3. 中间检查、测试、自查都归 `step`
4. final verification 只验证最终结果

因此：

1. verifier 使用独立链路
2. verifier 不继承主链路全量上下文
3. verifier 只消费统一 `handoff` 和按需证据引用

## 7. VerificationResult 最小结构

第一版建议 `VerificationResult` 保持极简：

```ts
type VerificationResult = {
  result_status: "pass" | "fail";
  summary: string;
  issues?: string[];
};
```

其中：

1. `pass` 表示最终结果可交付
2. `fail` 表示需要回到 `execute` 修正
3. `issues` 是下一轮执行的返工输入

## 8. Verification Fail 的回流方式

本任务明确规定：

1. verification fail 不通过 `external_signal_state` 回流
2. verification fail 结果直接写入正式返工输入
3. 返工输入作为下一轮 `execute` 的上下文来源

推荐结构如下：

```ts
type FinalizeReturnInput = {
  verification_summary: string;
  verification_issues: string[];
};
```

写入后执行：

1. `current_phase -> execute`
2. 下一轮 `step` 直接读取这份返工输入

## 9. RunOutcome 的生成时机

本任务明确规定：

1. `RunOutcome` 不在进入 `finalize` 时立即生成
2. `RunOutcome` 不在 verification 前生成
3. 只有 final verification `pass` 后，才正式生成 `RunOutcome`

这意味着：

1. `handoff` 先于 `RunOutcome`
2. verification 通过后，`handoff` 进入 `RunOutcome.handoff`

## 10. 对 phase 的直接影响

本任务对 phase 结构的影响如下：

1. phase 第一版只保留 `prepare`
2. phase 第一版只保留 `execute`
3. phase 第一版只保留 `finalize`
4. verification 不再作为独立主 phase

## 11. 对其他任务的直接输入

`S11-T4` 直接服务：

1. `S11-T2` RunOutcome 定义
2. `S4-T2` RunContext 极简结构
3. `S3-T4` step / orchestrator 控制边界
4. `S12-T2` finalize / verification 事件

同时它直接依赖：

1. `S11-T3` 统一 handoff 结构
2. `S5-T4` 执行图关系模型

## 12. 本任务结论摘要

可以压缩成 5 句话：

1. v1 只有 final verification，没有中途 verification phase
2. `finalize` 是最终交付尝试阶段，不保证一次结束
3. `handoff` 先生成，verification 再消费
4. verification fail 后直接把问题回灌到 `execute`
5. verification pass 后才正式生成 `RunOutcome`
