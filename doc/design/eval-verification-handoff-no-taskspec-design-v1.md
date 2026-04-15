# Eval 去 TaskSpec 设计方案（Verification Handoff, V2）

更新时间：2026-04-15  
状态：Implemented（已落地）

## 1. 背景

当前评估链路同时存在两种输入：
1. `task_spec`（可选外部输入）
2. `RunOutcome`（运行结果输入）

问题：
1. 主链路（`BaseAgent`）默认不传 `task_spec`，导致评估目标与约束表达弱。
2. 评估输入分散，`task_spec` 与实际执行事实（工具调用、产物路径）容易脱节。
3. verifier 对“主链路声称完成了什么”缺乏结构化 handoff，过度依赖自然语言 `final_answer`。

## 2. 目标

1. 删除 `task_spec`，统一评估输入为 `RunOutcome`。
2. 新增 `verification_handoff`，由主链路在结束时产出结构化交接信息。
3. verifier 以 `verification_handoff` 为主，结合只读证据工具做核验。
4. 保持事件语义稳定：`verification_started / verification_passed|failed / task_judged`。

## 3. 非目标

1. 不调整 observability 事件名。
2. 不引入写操作验证工具（verifier 仍仅只读）。
3. 不修改 memory card 主链路。

## 4. 核心数据结构

在 `RunOutcome` 增加字段：

`verification_handoff: Dict[str, Any]`

建议最小结构：
1. `goal`: string
2. `constraints`: string[]
3. `expected_artifacts`: object[]
   - `path`: string
   - `must_exist`: bool
   - `non_empty`: bool
   - `contains`: string (optional)
4. `claimed_done_items`: string[]
5. `key_tool_results`: object[]
   - `tool`: string
   - `status`: "ok" | "error"
   - `summary`: string
6. `known_gaps`: string[]
7. `self_confidence`: number(0~1)

## 5. 运行时生成策略（Step 内生成，结束前消费）

`AgentRuntime.run` 在 step 收敛点生成 `verification_handoff`（循环外保留兜底）：
1. 在 step 中一旦进入终态（非 `awaiting_user_input`），立即生成 handoff。
2. 先由主链路规则生成 `fallback_handoff`（最小可用，确保无模型时可运行）。
3. 再由 BaseAgent 使用一次 LLM 生成结构化 handoff（JSON）：
   - 输入：`user_input/final_answer/stop_reason/runtime_status/tool_failures/fallback_handoff`
   - 输出：`goal/constraints/expected_artifacts/claimed_done_items/key_tool_results/known_gaps/self_confidence/soft_score_threshold/rubric`
4. 对 LLM 输出做 schema 与类型归一化；非法字段裁剪并回填默认值。
5. 若 LLM 失败（超时、非 JSON、空结构、异常），直接使用 `fallback_handoff`。
6. 在循环外评估前消费 handoff；若 step 内未生成（极端分支），则循环外兜底生成。
7. 最终 handoff 写入 `RunOutcome.verification_handoff` 供 verifier 消费。
8. 写入 observability 来源字段：
   - `verification_started.payload.handoff_source` = `llm | fallback_rule`
   - `task_judged.payload.verification_handoff_source` = `llm | fallback_rule`
9. 在 `task_judged.payload` 写入 `verification_handoff` 快照（结构化裁剪后），供 postmortem 展示“交付内容”。

要求：
1. 默认启用 LLM handoff 生成（生产链路）。
2. 始终保留规则回退，不因 LLM 异常阻塞评估。
3. mock/测试可关闭 LLM 生成以保持 deterministic。

## 6. Verifier 改造

### 6.1 Orchestrator

1. `evaluate` 签名改为：`evaluate(run_outcome: RunOutcome)`。
2. 删除 `TaskSpec` 相关逻辑。
3. LLM judge 链路开关改为 runtime 级开关（沿用 `enable_llm_judge`）。
4. soft 阈值来源改为 `run_outcome.verification_handoff.soft_score_threshold`（缺省 0.7）。

### 6.2 Deterministic verifiers

1. `StopReasonVerifier`、`ToolFailureVerifier` 只依赖 `RunOutcome`。
2. `ArtifactVerifier` 改为读取 `verification_handoff.expected_artifacts`。

### 6.3 VerifierAgent

1. 不再接收 `task_spec` 参数。
2. prompt 输入改为 `RunOutcome + verification_handoff`。
3. evidence roots 推断改为：
   - 从 `verification_handoff.expected_artifacts` 推断
   - `observability-evals/<task>__<run>`
   - `work`

## 7. API 变更

1. `AgentRuntime.run(...)` 删除 `task_spec` 参数。
2. `RunOutcome` 新增 `verification_handoff`。
3. 删除 `TaskSpec` 与 `ExpectedArtifact` dataclass。
4. `Verifier.verify(...)` 签名统一为 `verify(run_outcome: RunOutcome)`。

## 8. 兼容与迁移

1. 本次按“直接切换”处理，不保留 `task_spec` 兼容层。
2. 受影响测试：`test_eval_orchestrator.py`、`test_verifier_agent.py`、runtime 集成测试。
3. 文档同步更新：`doc/refer/eval-reference.md`、`doc/refer/runtime-reference.md`（已完成）。

## 9. 验收标准

1. 代码中不再存在 `TaskSpec.from_dict(...)` 调用。
2. 评估链路仅依赖 `RunOutcome`。
3. `task_judged` 仍稳定产出，包含 `verifier_breakdown`。
4. verifier 可从 `verification_handoff.expected_artifacts` 正常推断证据根。
5. 无 `verification_handoff` 时仍可安全降级评估，不阻塞主流程。
6. 可从事件准确统计 handoff 来源占比（`llm` vs `fallback_rule`）。
7. postmortem 新增“交付内容”区块，显示：
   - `claimed_done_items`
   - `expected_artifacts`
   - `known_gaps`
   - `verification_handoff_source`

## 10. 风险与缓解

风险：
1. 删除 `task_spec` 可能导致历史定制评估规则丢失。
2. LLM 生成 handoff 可能出现结构漂移或幻觉字段。
3. 新增一次模型调用带来时延与成本增加。

缓解：
1. 在 handoff 增加 `constraints/expected_artifacts` 字段，承接历史需求。
2. 采用“LLM 生成 + 规则回退”双轨，保证稳定性。
3. 增加针对“空 handoff / 非法 JSON / 字段类型错误”的回归测试。
4. 后续通过观测指标评估收益：误判率、平均耗时、token 成本。
