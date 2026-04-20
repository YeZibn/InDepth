# InDepth Eval 参考

更新时间：2026-04-20

## 1. 这层在解决什么问题

Eval 层的职责不是“再回答一次”，而是把 Runtime 主链路结束后的结果整理成可审计判断：

1. 这次运行是否真正完成了用户目标
2. 主链路的完成声明是否有证据支撑
3. 如果未完成，是硬失败、部分完成，还是过度宣称
4. 后续复盘时是否能追溯判定依据

## 2. 当前主流程

在当前实现里，Eval 位于 Runtime finalizing 之后。

完整顺序是：

1. Runtime 完成主执行循环
2. `finalizing(answer)` 产出给用户的最终回答
3. `finalizing(handoff)` 产出结构化 `verification_handoff`
4. Runtime 组装 `RunOutcome`
5. `EvalOrchestrator` 依次执行 verifier
6. 汇总成 `RunJudgement`
7. judgement 再进入 observability 与 postmortem

可以把它理解成：

`runtime execution -> final answer -> handoff -> eval -> judgement -> observability`

## 3. 关键代码

- `app/eval/schema.py`
- `app/eval/orchestrator.py`
- `app/eval/verification_handoff_service.py`
- `app/eval/verifiers/deterministic.py`
- `app/eval/verifiers/llm_judge.py`
- `app/eval/agent/verifier_agent.py`

## 4. RunOutcome

`RunOutcome` 是 Eval 的统一输入对象。

核心字段包括：

1. `task_id`
2. `run_id`
3. `user_input`
4. `final_answer`
5. `stop_reason`
6. `tool_failures`
7. `runtime_status`
8. `verification_handoff`

Eval 不直接深入 Runtime 内部状态机，而是统一消费这份结果对象。

## 5. verifier 链

当前 verifier 链分两层：

1. deterministic verifiers
   - 判断运行过程是否健康
   - 例如 stop reason、工具失败
2. optional LLM judge
   - 判断最终结果是否真正完成任务
   - 属于软判定

默认 deterministic verifier：

1. `StopReasonVerifier`
2. `ToolFailureVerifier`

可选软判定 verifier：

1. `LLMJudgeVerifier`

## 6. judgement 汇总

`EvalOrchestrator` 的汇总逻辑是：

1. 先看硬检查
   - 只要有 `hard=True` 且 `passed=False`，最终直接 `fail`
2. 再看软分数
   - 所有软检查分数求平均
   - 低于阈值时为 `partial`
   - 否则为 `pass`
3. 最后补充派生字段
   - `self_reported_success`
   - `verified_success`
   - `overclaim`
   - `confidence`

## 7. `verification_handoff` 的定位

`verification_handoff` 现在不是“只给 verifier 的附加说明”，而是 Runtime finalizing 阶段产出的核心结构化结果。

它的职责有两件：

1. 给 Eval 提供结构化事实
2. 给 System Memory 提供后续沉淀所需的 `memory_seed`

也就是说，handoff 是 verification 与 memory 的共同事实源。

## 8. handoff 如何生成

入口：

- `build_verification_handoff(...)`

当前实现顺序：

1. 先构造规则版 fallback handoff
2. 若启用 handoff LLM，则让模型基于 final 阶段上下文生成更完整 handoff
3. 对模型输出做 normalize
4. 若 LLM 失败，则回退到 fallback handoff

V1 的 handoff LLM 输入特点：

1. 不额外构造复杂 `handoff_context` 中间对象
2. 直接读取 final 阶段已有上下文消息
3. 再叠加 runtime facts：
   - `user_input`
   - `final_answer`
   - `stop_reason`
   - `runtime_status`
   - `tool_failures`
   - fallback handoff

## 9. handoff 的核心字段

当前 handoff 结构重点包括：

1. `goal`
2. `task_summary`
3. `final_status`
4. `expected_artifacts`
5. `key_evidence`
6. `claimed_done_items`
7. `key_tool_results`
8. `known_gaps`
9. `risks`
10. `recovery`
11. `memory_seed`
12. `self_confidence`
13. `soft_score_threshold`
14. `rubric`

其中最关键的两个字段组是：

### 9.1 verifier 视角

- `expected_artifacts`
- `key_evidence`
- `claimed_done_items`
- `known_gaps`
- `risks`

### 9.2 memory 视角

```json
{
  "memory_seed": {
    "title": "string",
    "recall_hint": "string",
    "content": "string"
  }
}
```

## 10. 为什么要显式拆成双 step

当前 finalizing 显式拆成：

1. `finalizing(answer)`
2. `finalizing(handoff)`

这样做的好处是：

1. 用户回答和系统交接分离，避免互相污染
2. handoff 可以保持严格 JSON
3. verifier 与 memory 拿到的是同一份结构化事实
4. answer step 与 handoff step 可以独立观测、独立回退

## 11. recovery 如何进入 Eval

如果运行中触发了 todo recovery，恢复信息会先进入 handoff，再被 Eval 消费。

当前典型链路是：

1. Runtime 记录 fallback / recovery 信息
2. 这些信息进入 `verification_handoff.recovery`
3. Eval 再用 handoff 做统一判定
4. judgement 最终写回 observability 与 postmortem

因此 recovery 现在不是散落在多个侧链，而是统一通过 handoff 汇总。

## 12. 和旧描述相比，当前有哪些变化

当前实现已经明确变化为：

1. handoff 不再只是 verifier 的补充材料
2. handoff 是 Runtime finalizing 的显式子阶段产物
3. memory 不再独立生成一套元数据主结构，而是直接消费 `memory_seed`
4. 正式经验沉淀发生在 Eval 之前已拿到 handoff 之后

## 13. 推荐理解

如果只记一件事，可以记这句：

`verification_handoff` 是 Runtime 在任务结束时产出的统一结构化交接单，Eval 用它做判断，System Memory 用它做沉淀。
