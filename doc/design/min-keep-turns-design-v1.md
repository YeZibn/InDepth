# Runtime Min-Keep Turns 设计稿（V1）

更新时间：2026-04-17  
状态：Implemented（已落地）

## 1. 背景与问题

当前 Runtime token-budget 压缩使用 `min_keep_messages` 作为下限保护：
1. 目标保留预算由 `target_keep_ratio_midrun/finalize` 决定。
2. 若按预算裁剪后，尾部原始消息少于 `min_keep_messages`，则强行至少保留若干条消息。

这个策略的主要问题在于“消息条数”并不等于“上下文轮次”：
1. 一轮对话可能包含 `user + assistant + tool + tool` 多条消息。
2. 在 tool-heavy 场景下，保留 6 条消息可能只是一小段工具链，而不是 2~3 轮完整上下文。
3. 这会让压缩后的近期上下文边界不稳定，出现“保留了不少消息，但语义上仍像被截断”的体验。

因此，需要把压缩下限从“最少保留 N 条消息”切换为“最少保留 N 轮”。

## 2. 目标

本方案目标：
1. 将 Runtime token-budget 压缩的下限保护从 `min_keep_messages` 改为 `min_keep_turns`。
2. 默认至少保留最近 3 轮原始上下文。
3. 保持当前 turn 切分规则不变，降低实现改动面。
4. 删除旧消息条数语义，统一只保留按轮次配置。

## 3. 非目标

本次不做：
1. 不重写 turn 的定义规则。
2. 不改造 `event` 工具链替换压缩。
3. 不改变 `target_keep_ratio_midrun/finalize` 的默认值。
4. 不引入按 `run_id` 分段压缩。

## 4. 方案概览

### 4.1 新字段

新增/替换：
1. `min_keep_turns: int = 3`

### 4.2 turn 定义

沿用现有 `_split_turn_ranges(...)` 规则：
1. 若会话中存在 `user` 消息，则相邻 `user` 边界之间视为一轮。
2. 若不存在 `user` 消息，则按 `assistant` 分段兜底。

因此，“最少保留 3 轮”表示：
1. 优先保留最近 3 个 `user` 分段对应的上下文。
2. 在无 `user` 场景下，保留最近 3 个 `assistant` 分段。

### 4.3 裁剪算法调整

当前算法：
1. 先按 turn 逆向累计 token，得到候选 `keep_from`
2. 再用 `min_keep_messages` 做消息条数兜底

调整后：
1. 先按 turn 逆向累计 token，得到候选 `keep_from`
2. 若保留下来的 turn 数少于 `min_keep_turns`
3. 则将 `keep_from` 调整到“最近 `min_keep_turns` 轮的起始位置”
4. 最后继续执行 tool pairing guard

即：
1. token 预算仍决定“理想保留范围”
2. `min_keep_turns` 决定“最小语义完整度下限”

## 5. 详细设计

### 5.1 SQLiteMemoryStore

需要修改：
1. 构造参数 `min_keep_messages` -> `min_keep_turns`
2. `_compute_token_budget_cut_index(...)` 的第三个参数改为 `min_keep_turns`
3. 早停判断从“消息数不足”改为“轮次数不足”
4. 下限保护从“最近 N 条消息”改为“最近 N 轮”

建议返回原因同步更新：
1. `below_min_keep_messages` -> `below_min_keep_turns`

### 5.2 RuntimeCompressionConfig

需要修改：
1. dataclass 字段 `min_keep_messages` -> `min_keep_turns`
2. `load_runtime_compression_config()` 仅读取 `COMPACTION_MIN_KEEP_TURNS`

默认值：
1. `min_keep_turns = 3`

### 5.3 接线层

需要同步更新：
1. `app/agent/agent.py`
2. `app/agent/sub_agent.py`
3. `app/core/bootstrap.py`

即：
1. `SQLiteMemoryStore(...)` 改传 `min_keep_turns=compression_config.min_keep_turns`

## 6. 风险与缓解

风险 1：相比“6 条消息”，3 轮可能保留更多 token。  
缓解：
1. 当前 `target_keep_ratio_midrun/finalize=0.40` 已较保守
2. `min_keep_turns` 只是下限，不会覆盖大多数正常预算场景

风险 2：删除旧配置后，历史环境变量不再生效。  
缓解：
1. 文档中明确只保留 `COMPACTION_MIN_KEEP_TURNS`
2. 部署侧同步替换旧变量

## 7. 测试计划

至少覆盖：
1. `RuntimeCompressionConfig` 默认暴露 `min_keep_turns=3`
2. 当预算很小但最近有 3 轮时，仍应至少保留 3 轮
3. 既有压缩回归继续通过

## 8. 实现结果

已按本稿落地：
1. Runtime 压缩下限已切换为 `min_keep_turns`
2. 默认值已改为 `3`
3. 旧 `COMPACTION_MIN_KEEP_MESSAGES` 语义已删除
4. 相关代码、测试与参考文档已同步更新
