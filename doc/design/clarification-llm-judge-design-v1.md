# Clarification LLM Judge 设计稿（V1）

更新时间：2026-04-15  
状态：Implemented（已完成）

当前落地状态（2026-04-15）：
1. LLM 主判 + heuristic fallback 已接入 `finish_reason=stop` 的澄清判定链路。
2. `clarification_judge_started/completed/fallback` 可观测事件已落地。
3. CLI 澄清态展示已增强：`[需要澄清]` 前缀 + 补充输入引导文案。
4. CLI 新增 `/new [label]` 快捷命令，可在当前模式下结束旧任务并开启新任务。
5. 相关回归测试已通过（`test_main_agent`、`test_runtime_eval_integration`）。

## 1. 背景

当前 `is_clarification_request` 使用关键词 + 问号启发式判定。该策略实现简单，但误判率较高：
1. 容易把普通问候、确认性语句误判为 `clarification_requested`。
2. 中英文混合、委婉表达、上下文依赖场景下鲁棒性不足。
3. 规则维护成本随语言变体上升，且难以覆盖新表达。

## 2. 目标

1. 将“是否为澄清请求”交由 LLM 语义判定。
2. 在不破坏现有 runtime 状态机的前提下，平滑替换启发式主路径。
3. 保留失败兜底，确保模型异常时 runtime 不阻塞。
4. 提供可观测指标，支持后续阈值调优与回归分析。

## 3. 非目标

1. 不改动 `run()` 对外返回类型（继续返回字符串）。
2. 不在 V1 引入多分类意图体系（仅二分类：澄清 / 非澄清）。
3. 不调整现有 `clarification_requested` 事件名与主流程事件顺序。

## 4. 方案概览

在 `finish_reason == "stop" && content 非空` 时，新增一步 LLM 判定：
1. 输入：当前 assistant 输出 `content`，可选附带最近 1 轮 user 输入。
2. 输出：结构化 JSON（强约束）。
3. runtime 根据 JSON 字段决定是否进入 `awaiting_user_input`。

判定优先级：
1. LLM 判定结果（主路径）。
2. 启发式规则（兜底，仅 LLM 失败或输出非法时启用）。

## 5. 接口与协议

### 5.1 新增内部方法

建议在 `AgentRuntime` 新增：
1. `_is_clarification_request_llm(content: str, user_input: str = "") -> tuple[bool, float, str]`
2. `_build_clarification_judge_config() -> GenerationConfig`

### 5.2 LLM 输出协议

要求模型仅输出 JSON，对齐以下 schema：

```json
{
  "is_clarification_request": true,
  "confidence": 0.92,
  "reason": "assistant asks user to provide missing requirement details"
}
```

字段约束：
1. `is_clarification_request`：布尔，必填。
2. `confidence`：`[0,1]` 浮点，可选，默认 `0.5`。
3. `reason`：简短字符串，可选。

解析策略：
1. 使用现有 `parse_json_dict(...)`。
2. 缺字段或类型错误判为“协议失败”。

### 5.3 判定阈值

V1 建议：
1. 当 `is_clarification_request == true` 且 `confidence >= 0.60`，判定为澄清请求。
2. 当 `is_clarification_request == true` 但 `confidence < 0.60`，按非澄清处理（保守防误停）。
3. 当无 `confidence` 时按 `0.5` 处理。

## 6. Runtime 集成点

集成在当前分支：`agent_runtime.py` 的 `finish_reason == "stop"` 路径。

执行顺序：
1. 主模型得到 `content`。
2. 调用 `_is_clarification_request_llm(...)`。
3. 若判定为澄清：
- `runtime_state = awaiting_user_input`
- 发 `clarification_requested`
- 跳过 verification。
4. 若判定为非澄清：
- 按现有 `completed/failed` 流程执行。

## 7. Prompt 设计（Judge）

Judge system prompt 约束：
1. 你是二分类判定器，不做任务执行。
2. 仅判断 assistant 文本是否在“向用户索取缺失信息后才能继续执行”。
3. “礼貌提问/反问/确认语气”不等同澄清请求。
4. 只输出 JSON，不输出 markdown。

few-shot 建议覆盖：
1. 真澄清："请确认输出语言和截止时间"。
2. 非澄清："你好，有什么我可以帮你的？"。
3. 非澄清："我已完成，是否需要我继续优化？"。
4. 边界：包含问号但实质是结果说明。

## 8. 兜底与容错

任一情况触发兜底启发式：
1. judge 模型调用异常。
2. judge 输出无法解析为有效 JSON。
3. judge 耗时超时（建议 2s~3s 可配置）。

兜底行为：
1. 调用现有 `is_clarification_request(...)` 规则。
2. 发 `clarification_judge_fallback` 事件（新增，便于观测质量）。

## 9. 配置与开关

建议新增配置项（默认值）：
1. `runtime.enable_llm_clarification_judge = true`
2. `runtime.clarification_judge_confidence_threshold = 0.60`
3. `runtime.clarification_judge_timeout_ms = 2500`
4. `runtime.enable_clarification_heuristic_fallback = true`

测试友好性：
1. 对 `MockModelProvider` 默认可关闭 LLM judge（与现有模式一致）。
2. 单测中可注入脚本化 judge 输出，确保可重复。

## 10. CLI 交互增强（Clarification UX）

目标：在 `awaiting_user_input` 状态下，CLI 让用户明确感知“这是澄清提问”，并降低补充输入成本。

### 10.1 展示规范

当 runtime 判定为澄清请求时，CLI 建议按以下格式输出：
1. 状态前缀行：`[需要澄清]`
2. Agent 提问正文（原始问题文本）。
3. 辅助提示：`请直接回复补充信息，我会在当前任务中继续。`

示例：

```text
[需要澄清]
请确认输出语言和截止时间。
请直接回复补充信息，我会在当前任务中继续。
```

### 10.2 连续对话行为

1. 用户下一次输入默认作为澄清补充，不要求额外命令。
2. 同一 `run_id` 恢复执行（保持既有 `resume_from_waiting` 机制）。
3. 若用户输入 `/new`（或等价切换任务命令），则显式结束当前澄清上下文并新建任务。

### 10.3 错误与边界提示

1. 若用户在澄清态输入空文本，CLI 给出轻提示而不触发新一轮模型调用。
2. 若再次返回澄清问题，重复上述 `[需要澄清]` 展示格式，避免用户误判为最终结果。
3. 若恢复后进入终态，按现有 `Runtime: ...` 输出，不再显示澄清前缀。

## 11. 可观测性

新增/增强事件建议：
1. `clarification_judge_started`
- payload: `step`, `content_preview`
2. `clarification_judge_completed`
- payload: `decision`, `confidence`, `source=llm`, `latency_ms`
3. `clarification_judge_fallback`
- payload: `reason`, `fallback_decision`, `source=heuristic`

核心指标：
1. LLM 判定覆盖率（非 fallback 占比）。
2. fallback 触发率。
3. 澄清判定后用户补充率（有效性 proxy）。
4. 误停率（人工抽样或后验规则评估）。

## 12. 测试计划

新增测试用例：
1. `llm_judge_true_should_enter_awaiting_user_input`
2. `llm_judge_false_should_continue_terminal_flow`
3. `llm_judge_invalid_json_should_fallback_to_heuristic`
4. `llm_judge_exception_should_fallback_to_heuristic`
5. `low_confidence_true_should_not_block_flow`
6. `event_should_include_judge_source_and_confidence`

回归要求：
1. 现有 `clarification_requested` / `verification_skipped` 用例继续通过。
2. 现有 run-resume 行为不变（同 run_id 恢复）。

补充 CLI 交互用例：
1. `cli_should_show_clarification_prefix_when_awaiting_user_input`
2. `cli_should_resume_same_run_after_user_reply_in_clarification_state`
3. `cli_should_clear_clarification_state_on_new_task_command`

## 13. 灰度与回滚

灰度建议：
1. Phase A（Shadow）：LLM 仅打点，不影响决策；与启发式并行比对。
2. Phase B（Canary）：10% 流量启用 LLM 主判。
3. Phase C（Full）：全量启用，保留 fallback。

回滚策略：
1. 关闭 `enable_llm_clarification_judge`，立即回到纯启发式。
2. 保留事件打点，便于离线复盘后再上线。

## 14. 风险与边界

1. 新增一次模型调用带来时延与成本上升。
2. LLM 可能受 prompt 漂移影响，需持续监控。
3. 若阈值设定过低，仍可能误停；过高则漏判。

缓解：
1. 独立小模型/mini 模型用于 judge。
2. 强制 JSON 输出 + 解析校验。
3. 先 shadow 再放量，基于真实数据调阈值。
