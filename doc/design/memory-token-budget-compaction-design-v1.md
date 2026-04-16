# InDepth Memory Token-Budget Compaction V1 设计稿

更新时间：2026-04-14
状态：V1 设计中（待实现）

## 1. 背景与问题

当前 Runtime 压缩触发是多因子（token/event/round），但实际裁剪策略仍以“保留最近 N 个 assistant 轮次（默认 8）”为主。

这会导致一个关键问题：
1. 即使触发了 `midrun` 压缩，裁剪后上下文仍可能超过 token 安全阈值。
2. 在“最近 8 轮本身很重”时，压缩会出现“反复触发但几乎无效”的现象。
3. `midrun/light` 在当前实现里主要体现在 metadata，实际裁剪深度差异不明显。

## 2. 目标

V1 目标：将“裁剪依据”从轮次优先，升级为 token 预算优先。

1. 压缩后保留消息应尽量落入目标 token 预算。
2. 在 `midrun` 模式下提供更激进的预算目标，显著降低 length 风险。
3. 保留关键语义安全边界（最小保留条数、工具调用配对不破坏、一致性守护不退化）。
4. 对调用侧尽量保持兼容，降低改造成本。

## 3. 非目标

1. V1 不引入模型原生 tokenizer（继续沿用 runtime 估算逻辑）。
2. V1 移除 round 触发，不再按固定步数触发压缩。
3. V1 不改变 system memory 机制（仅改 runtime memory 的裁剪策略）。

## 4. 方案概览

### 4.1 核心思路

将 `_compact_impl` 的裁剪点计算改为：
1. 先计算全部消息估算 token。
2. 按 mode 选定目标保留预算（`target_keep_tokens`）。
3. 从最新消息向前累加，直到达到预算上限，得到“需要保留的尾部区间”。
4. 对裁剪点做安全修正（避免切断 assistant-tool 对、保留最小消息条数）。
5. 将前缀压入结构化摘要并删除。

即：
- 触发是否发生：由 runtime 判定（不变）
- `token` 触发：由 token 预算裁剪并写入结构化摘要（新增）
- `event` 触发：优先做“工具链消息替换压缩”，不写入 summary（新增）

触发集合（V1）：
1. token 触发：`midrun` / `light`
2. event 触发：单次 `tool_calls` 条目数达到阈值

### 4.3 Event 触发专用策略（工具链消息替换）

目标：只压缩“最近连续工具调用段”，不污染全局 summary。

规则：
1. 识别最近连续工具调用段：
- 形态为 `assistant(tool_calls)` 与对应 `tool` 消息的连续链路。
2. `event` 压缩不走 summary：
- 不更新 `summaries.summary_json`。
3. 就地替换：
- 删除该连续链路中的原始 `assistant(tool_calls)` 与 `tool` 消息。
- 在 `messages` 中插入一条替代消息（建议 `role=assistant`）。
4. 替代消息内容：
- 工具序列与调用次数
- 成功/失败统计
- 关键结果摘要
- 失败原因摘要（如有）
5. 可追溯性：
- 替代消息使用固定前缀（如 `[tool-chain-compact]`）和结构化片段，便于后续解析。
- 原始细节保留在 observability 事件，不在对话上下文中保留全文。

### 4.2 预算策略（建议默认）

定义：
1. `context_window_tokens`：上下文窗口（现有，默认 16000）
2. `target_keep_ratio_light`：light 压缩后目标保留比例（新增，默认 0.55）
3. `target_keep_ratio_midrun`：midrun 压缩后目标保留比例（新增，默认 0.40）
4. `target_keep_ratio_finalize`：finalize 压缩目标比例（新增，默认 0.40）
5. `min_keep_messages`：无论如何至少保留的消息数（新增，默认 6）

预算计算：
1. `light`: `target_keep_tokens = context_window_tokens * target_keep_ratio_light`
2. `midrun`: `target_keep_tokens = context_window_tokens * target_keep_ratio_midrun`
3. `finalize`: `target_keep_tokens = context_window_tokens * target_keep_ratio_finalize`

## 5. 关键算法

### 5.1 裁剪点计算（Token Budget + 最新轮次优先）

输入：`rows`, `target_keep_tokens`, `min_keep_messages`

流程：
1. 先将消息按“轮次（turn）”分组，再从最新轮次向前计算。
2. turn 定义：以 `user` 消息为边界，一个 user 及其后续 assistant/tool 直到下一个 user，视为一轮。
3. 从最后一轮开始累计该轮总 token，直到首次超过 `target_keep_tokens`，确定保留区间。
4. 保证尾部至少有 `min_keep_messages` 条（按消息条数兜底）。
5. 若候选切点会把 `assistant(tool_calls)` 与其对应 `tool` 响应拆开，则向前/向后微调切点，保证成对保留。
6. 若最终切点 <= 0，返回 `nothing_to_cut`。

### 5.2 与一致性守护的关系

保持现有逻辑：
1. token 预算只决定“裁剪范围”。
2. 摘要合并后仍执行 `validate_consistency`。
3. 校验失败则整次压缩不落库。

补充：
1. `event` 的“消息替换压缩”不经过 summary 合并流程。
2. `event` 替换压缩不触发 `validate_consistency`；一致性守护只作用于 summary 路径（token/finalize）。

## 6. 接口与配置变更

### 6.1 配置新增（环境变量）

1. `COMPACTION_TARGET_KEEP_RATIO_LIGHT`（默认 0.55）
2. `COMPACTION_TARGET_KEEP_RATIO_MIDRUN`（默认 0.40）
3. `COMPACTION_TARGET_KEEP_RATIO_FINALIZE`（默认 0.40）
4. `COMPACTION_MIN_KEEP_MESSAGES`（默认 6）

### 6.2 配置兼容

1. 保留 `COMPACTION_KEEP_RECENT_TURNS`，但降级为兜底策略（仅在 token 预算异常或估算不可用时启用）。
2. 保留现有 `round_interval/light_token_ratio/midrun_token_ratio` 等触发参数。

### 6.3 方法签名（建议）

1. `compact_mid_run(conversation_id, trigger, mode, token_budget=None)`
2. `compact_final(conversation_id, token_budget=None)`
3. `_compact_event_tool_chain(conversation_id, ...)`（新增）
4. `_compact_impl(..., token_budget=None, min_keep_messages=...)`

调用方可不传，store 内按配置自动计算；传入时优先使用调用参数。

`compact_mid_run` 路由建议：
1. `trigger == "event"`：优先调用 `_compact_event_tool_chain`。
2. 若 event 压缩未命中可替换区间，则可回退到 token 预算裁剪（可配置）。

## 7. 可观测性增强

在 `context_compression_succeeded` 的 `result` 中新增：
1. `target_keep_tokens`
2. `actual_kept_tokens_est`
3. `trim_strategy="token_budget"`
4. `cut_adjustment_reason`（如 `tool_pair_guard` / `min_keep_guard`）

用于验证“触发后是否真正降到预算以内”。

`event` 替换压缩新增字段：
1. `trim_strategy="tool_chain_replace"`
2. `replaced_message_count`
3. `inserted_summary_message_id`（若可得）
4. `tool_chain_span`（起止消息 id）

## 8. 风险与缓解

1. Token 估算误差导致“看似达标、实际超限”。
- 缓解：保留安全余量（可选 `target_keep_tokens * 0.9` 内部目标）。

2. 过度压缩导致近期语境损失。
- 缓解：`min_keep_messages` + 一致性守护 + 工具配对保护。

3. 与历史测试强绑定“保留 8 轮”的断言冲突。
- 缓解：测试从“轮次固定”迁移为“预算达标 + 结构不破坏”断言。

## 9. 测试计划

新增/调整最小回归集：
1. `compact_mid_run_should_reduce_to_token_budget_light`
2. `compact_mid_run_should_reduce_to_token_budget_strong`
3. `compact_should_preserve_assistant_tool_pairing`
4. `compact_should_keep_min_messages_even_if_budget_tiny`
5. `compact_should_fallback_to_turn_strategy_when_budget_unavailable`
6. `compression_result_should_report_token_budget_metrics`
7. `event_compaction_should_replace_latest_tool_chain_messages`
8. `event_compaction_should_not_write_summary_json`
9. `event_compaction_should_keep_non_tool_context_unchanged`

## 10. 落地步骤

1. 增加配置项与默认值读取。
2. 在 `SQLiteMemoryStore` 实现 token-budget 裁剪算法。
3. 保留 `keep_recent_turns` 作为降级兜底。
4. 补充 observability 字段。
5. 更新测试与文档（`doc/refer/memory-reference.md`）。

## 11. 预期收益

1. 压缩“有效性”与触发原因一致：`midrun` 真正更强。
2. 降低长任务 length 停机与无效重复压缩概率。
3. 为后续接入模型级 tokenizer 提供稳定接口层。
