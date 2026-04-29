# S11-T6 Finalize Pipeline 规则（V1）

更新时间：2026-04-29  
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
2. 第一版 `finalize` 只在 graph 全部 `completed` 时进入
3. final verification fail 当前直接结束 run，不做回退动作
4. `partial` 暂不进入第一版实现
5. finalize closeout 后仍需预留记忆接入挂点

## 3. 进入 Finalize 的触发条件

当前第一版正式规定：

1. 只有当 graph 全部 `completed` 时，才允许进入 `finalize`
2. `blocked / failed / 无可继续推进` 当前都不进入 `finalize`
3. `finalize` 不是任意时刻都可进入
4. 它应是一次“正式交付尝试”

## 4. Finalize Pipeline 正式顺序

第一版推荐正式顺序如下：

```text
enter finalize
  -> generate final_output + graph_summary
  -> build handoff
  -> run final verification
     -> pass -> determine result_status -> build RunOutcome -> close run
     -> fail -> close run as failed
```

## 5. 分步规则

## 5.1 Build Handoff

规则如下：

1. 进入 `finalize` 后先生成统一 `handoff`
2. `handoff` 是 final verification 的正式输入
3. 没有 `handoff` 不允许进入 verification
4. 第一版 `handoff` 最小正式结构收口为：
   - `goal: str`
   - `user_input: str`
   - `graph_summary: str`
   - `final_output: str`
5. 第一版 `handoff` 当前不保留：
   - `run_id`
   - `task_id`
   - 其他额外标识字段
6. `handoff` 中的 `final_output` 与 `graph_summary` 第一版都由 finalize LLM 基于统一上下文生成

## 5.2 Run Final Verification

规则如下：

1. verifier 使用独立链路
2. verifier 只验证最终结果
3. verifier 消费统一 `handoff`
4. verifier 返回 `VerificationResult`
5. 第一版 `VerificationResult` 最小结构收口为：
   - `result_status: pass | fail`
   - `summary: str`
   - `issues: list[str]`
6. `issues` 在 `pass` 时允许为空列表
7. `VerificationResult.summary / issues` 第一版先只用于 finalize 内部判定与收口，不额外挂到复杂状态位
8. verifier 第一版是独立边界对象，不内联成 orchestrator 私有逻辑
9. verifier 第一版采用轻量 ReAct 架构，但不复用 execute 当前的 `ReActStepRunner`
10. verifier 第一版允许多轮内部循环，但最大轮数上限固定为 `20`
11. verifier 第一版当前不接：
    - tool call
    - memory 写入
    - graph 动作
    - next phase 决策

## 5.2.1 Finalize Generator 与 Verifier 的挂载边界

当前第一版补充结论如下：

1. `finalize generator` 与 `verifier` 不应混成同一内部 helper
2. `finalize generator` 第一版可先保留在 orchestrator 邻近层
3. `verifier` 第一版必须保持独立边界对象
4. `finalize_model_provider` 与 `verifier_model_provider` 从第一版开始分开注入
5. 两条链第一版都禁止 tool call，并要求 JSON-only 输出

## 5.3 Determine Result Status

规则如下：

1. `result_status` 由 verification 与 finalize 共同收敛
2. 第一版当前只允许结果为：
   - `pass`
   - `fail`
3. `partial` 暂不进入第一版实现

## 5.4 Build RunOutcome

规则如下：

1. 只有 verification `pass` 后，才允许正式构建 `RunOutcome`
2. `handoff` 进入 `RunOutcome.handoff`
3. `final_answer`、`result_status`、`stop_reason` 在此阶段正式收敛
4. 第一版可先将 host-facing `output_text` 直接收口为 `final_output`
5. 第一版当前不单独引入新的 `RunOutcome` 代码模型
6. 当前先由 `run_finalize_phase(...)` 直接组装 `HostRunResult`
7. finalize `pass` 时第一版收口为：
   - `HostRunResult.runtime_state = "completed"`
   - `HostRunResult.output_text = final_output`
   - `run_lifecycle.result_status = "pass"`
   - `run_lifecycle.stop_reason = "finalize_passed"`

## 6. Verification Fail 的回退规则

当前第一版改为：

1. verification fail 直接结束当前 run
2. 当前不回退 `execute`
3. 当前不直接进入 `replan`
4. 当前也不引入 `replan` 判定器
5. `final_verification_fail` 相关回流逻辑整体后置到后续模块
6. host-facing 当前收口为：
   - `output_text = ""`
   - `runtime_state = "failed"`
   - `result_status = "fail"`
   - `stop_reason = "final_verification_failed"`

`FinalizeReturnInput` 结构仍保留为后续回流设计预留：

```ts
type FinalizeReturnInput = {
  verification_summary: string;
  verification_issues: string[];
};
```

## 7. 当前不展开部分

当前第一版先不展开：

1. `execute -> finalize -> execute` 回退闭环
2. `verification fail -> replan` 判定闭环
3. finalize 重试上限
4. `partial`

## 9. 最终 Fail 出口

第一版建议以下情况可进入最终 `fail`：

1. final verification fail
2. 最终未形成可交付输出
3. 关键证据始终不足，无法支撑结果成立

这意味着：

1. `fail` 必须有正式退出条件
2. 第一版当前直接以 verification fail 作为失败出口

## 10. Partial 的当前边界

本任务当前明确：

1. `partial` 暂不进入第一版实现
2. 后续若重新引入，仍只允许在 verification `pass` 时出现

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

1. `finalize` 第一版只在 graph 全部 `completed` 时进入
2. final verification fail 当前直接结束，不做回退动作
3. `partial` 暂不进入第一版实现
4. finalize 必须有明确最终 fail 出口
5. finalize closeout 后必须预留记忆接入挂点
