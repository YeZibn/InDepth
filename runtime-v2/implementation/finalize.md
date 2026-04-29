# Finalize / Verification 实现说明

## 当前范围

当前 `FinalizePhase` 已从空壳升级为真实 finalize / verification 主链。

当前已实现：

1. `FinalizeGenerationResult`
2. `Handoff`
3. `VerificationResult`
4. `RuntimeVerifier`
5. `run_finalize_phase(...)` 的真实收口链
6. `FinalizeReflexion`
7. verification fail 后的最小 replan 回流

对应代码：

1. [src/rtv2/finalize/models.py](/Users/yezibin/Project/InDepth/runtime-v2/src/rtv2/finalize/models.py)
2. [src/rtv2/finalize/verifier.py](/Users/yezibin/Project/InDepth/runtime-v2/src/rtv2/finalize/verifier.py)
3. [src/rtv2/finalize/reflexion.py](/Users/yezibin/Project/InDepth/runtime-v2/src/rtv2/finalize/reflexion.py)
4. [src/rtv2/orchestrator/runtime_orchestrator.py](/Users/yezibin/Project/InDepth/runtime-v2/src/rtv2/orchestrator/runtime_orchestrator.py)
5. [tests/test_runtime_orchestrator.py](/Users/yezibin/Project/InDepth/runtime-v2/tests/test_runtime_orchestrator.py)

## 当前主流程

当前 `run_finalize_phase(...)` 的正式顺序如下：

1. 要求 `current_phase = FINALIZE`
2. 要求 graph 全部 `completed`
3. 调 finalize generator 生成：
   - `final_output`
   - `graph_summary`
4. 组装 `Handoff`
5. 调 `RuntimeVerifier.verify(...)`
6. verification `fail` 时进入 `FinalizeReflexion`
7. 根据最终动作收口为最终 `HostRunResult` 或回流 `prepare`

## Finalize Generator

当前 finalize generator 仍保留在 orchestrator 邻近层，没有单独再抽新的 generator 类。

当前特征如下：

1. 复用统一 `ModelProvider` 协议
2. 使用独立 `finalize_model_provider`
3. 禁止 tool call
4. 要求 JSON-only 输出
5. 第一版只返回：
   - `final_output`
   - `graph_summary`

当前它读取的上下文来源包括：

1. `run_identity.user_input`
2. `run_identity.goal`
3. graph snapshot
4. runtime memory
5. capability summary

## Handoff

当前 `Handoff` 最小结构为：

1. `goal`
2. `user_input`
3. `graph_summary`
4. `final_output`

当前第一版不额外携带：

1. `run_id`
2. `task_id`
3. 其他额外控制字段

## RuntimeVerifier

当前 verifier 是独立边界对象，不复用 execute 侧的 `ReActStepRunner`。

当前特征如下：

1. verifier 只消费 `Handoff`
2. verifier 只产出 `VerificationResult`
3. verifier 采用轻量 ReAct 风格
4. verifier 允许多轮内部循环
5. 当前最大轮数为 `20`
6. 当前禁止 tool call

当前 verifier 的回合语义是：

1. 若模型已能给出结论，则直接返回：
   - `result_status`
   - `summary`
   - `issues`
2. 若模型暂不下结论，可先返回：
   - `thought`
3. verifier 再进入下一轮受控继续验证

## FinalizeReflexion

当前 `FinalizeReflexion` 是 run 级 reflexion helper。

当前特征如下：

1. 只在 `final_verification_fail` 后触发
2. 复用统一 judge 基座
3. 读取主链三段 prompt 与 runtime memory 上下文
4. 第一版动作只允许：
   - `request_replan`
   - `finish_failed`

## 收口规则

### verification pass

当前收口为：

1. `run_lifecycle.result_status = "pass"`
2. `run_lifecycle.stop_reason = "finalize_passed"`
3. `HostRunResult.runtime_state = "completed"`
4. `HostRunResult.output_text = final_output`

### verification fail

当前收口为：

1. 先写入 `finalize_return_input`
2. 再进入 `FinalizeReflexion`
3. 若动作是 `request_replan`
   - 写入正式 `request_replan`
   - 回流 `prepare -> execute -> finalize`
4. 若动作是 `finish_failed`
   - `run_lifecycle.result_status = "fail"`
   - `run_lifecycle.stop_reason = "final_verification_failed"`
   - `HostRunResult.runtime_state = "failed"`
   - `HostRunResult.output_text = ""`

当前第一版不做：

1. `fail -> execute`
2. `retry_finalize`
3. 通用 run 级失败动作扩展

## 当前测试覆盖

当前已覆盖：

1. finalize prompt 合同
2. finalize phase 正常 pass 收口
3. finalize phase fail 收口
4. finalize fail -> run reflexion -> replan
5. finalize phase 只允许在 graph 全部 completed 时进入
6. host 主链对 finalize 输出的最小集成
