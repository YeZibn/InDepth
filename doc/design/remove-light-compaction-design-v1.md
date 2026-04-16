# Runtime 移除轻压缩设计稿（V1）

更新时间：2026-04-16  
状态：已落地（2026-04-16）

当前落地状态（2026-04-16）：
1. 已移除 mid-run `light` token 压缩触发与配置项。
2. 已保留 `token/strong`、`event`、`finalize` 三类压缩路径。
3. 已更新核心实现与相关回归测试。
4. 已将 `target_keep_ratio_strong` 与 `target_keep_ratio_finalize` 默认值统一调整为 `0.40`。

## 1. 背景与问题

当前 Runtime 中途压缩存在两档 token 压缩模式：
1. `light`：上下文占用达到 `light_token_ratio` 时触发。
2. `strong`：上下文占用达到 `strong_token_ratio` 时触发。

但在当前实现里，这两档模式的差异主要只有“压缩后保留比例不同”：
1. 两者都走同一条 `summary_json` 生成链路。
2. 两者都使用同一套结构化字段抽取逻辑。
3. 两者都执行同样的一致性守护与摘要落库流程。

这带来几个问题：
1. 概念成本偏高。调用侧、测试和配置都要理解两档 token 压缩，但语义差异有限。
2. 调试成本偏高。线上出现压缩行为时，需要区分 `light/strong`，但很多结果只体现为“删多一点或少一点”。
3. 配置面冗余。`light_token_ratio` 与 `target_keep_ratio_light` 增加了调参面，但收益有限。
4. 策略表达不够真实。当前并不存在“轻压缩策略”和“强压缩策略”两套摘要器，只有同一策略下的不同裁剪深度。

## 2. 目标

本方案目标：
1. 移除中途 `light` token 压缩模式。
2. 保留 `strong` 作为唯一 token 压缩模式。
3. 保留 `event` 工具链替换压缩，不影响其现有职责。
4. 保留 `finalize` 结束阶段压缩，不影响任务收尾沉淀。
5. 降低配置、日志、测试和理解复杂度。

## 3. 非目标

本次不做：
1. 不改造 `summary_json` 的字段结构与提取规则。
2. 不改造 `event` 工具链压缩算法。
3. 不引入新的 tokenizer 或更精确的 token 估算。
4. 不重构 `finalize` 的触发时机与摘要落库格式。
5. 不在本稿中引入新的“分层摘要策略”替代 `light`。

## 4. 设计原则

1. 中途 token 压缩应只有一个明确语义：已经接近上下文风险边界，需要进行真正有效的裁剪。
2. `event` 压缩继续承担“工具链折叠”的职责，不与 token 压缩混淆。
3. 优先减少无效配置与分支判断，而不是保留未来可能使用的空概念。
4. 用户可观察到的行为应更容易解释：中途要么不压缩，要么进入唯一的 token 压缩档位。

## 5. 方案概览

### 5.1 触发模型调整

中途压缩触发从当前：
1. `usage >= strong_token_ratio` -> `token/strong`
2. `consecutive_tool_calls >= tool_burst_threshold` -> `event/light`
3. `usage >= light_token_ratio` -> `token/light`

调整为：
1. `usage >= strong_token_ratio` -> `token/strong`
2. `consecutive_tool_calls >= tool_burst_threshold` -> `event`
3. 其他情况 -> 不做中途压缩

即：
1. 删除 `light_token_ratio` 触发分支。
2. 中途 token 压缩只在达到强阈值时触发。

### 5.2 模式集合调整

调整后 Runtime 压缩模式保留为三类：
1. `token/strong`：唯一中途 token 压缩模式。
2. `event`：最近连续工具链替换压缩。
3. `finalize`：run 结束后的摘要沉淀压缩。

说明：
1. `event` 的 `mode` 字段不再需要表达 `light` 语义，建议统一记录为 `event` 或保留兼容占位但不再代表轻压缩。
2. `ContextCompressor.merge_summary(...)` 无需新增模式；其关注点仍是 `trigger/mode` 元数据记录。

### 5.3 保留预算调整

当前预算：
1. `light` -> `target_keep_ratio_light`
2. `strong` -> `target_keep_ratio_strong`
3. `finalize` -> `target_keep_ratio_finalize`

调整后预算：
1. 中途 token 压缩仅使用 `target_keep_ratio_strong`
2. `finalize` 继续使用 `target_keep_ratio_finalize`

也就是说：
1. 删除 `target_keep_ratio_light` 配置及其读取。
2. `_resolve_target_keep_tokens(mode=...)` 不再处理 `light` 分支。

## 6. 详细改动建议

### 6.1 Runtime 触发策略

文件：
1. `app/core/runtime/runtime_compaction_policy.py`

建议改动：
1. 删除 `usage >= light_token_ratio` 分支。
2. `event` 触发不再赋值 `mode="light"`，建议改为：
   - `trigger="event"`
   - `mode="event"`
3. 当 `usage < strong_token_ratio` 且未命中 `event` 时，直接返回原始 `messages`。

结果：
1. 中途 token 压缩只剩一个阈值判断。
2. `context_compression_started/succeeded` 事件中不再出现 `token/light`。

### 6.2 配置收敛

文件：
1. `app/config/runtime_config.py`

建议改动：
1. 从 `RuntimeCompressionConfig` 中移除：
   - `light_token_ratio`
   - `target_keep_ratio_light`
2. 删除对应环境变量读取：
   - `COMPACTION_LIGHT_TOKEN_RATIO`
   - `COMPACTION_TARGET_KEEP_RATIO_LIGHT`
3. 保留：
   - `COMPACTION_STRONG_TOKEN_RATIO`
   - `COMPACTION_TARGET_KEEP_RATIO_STRONG`
   - `COMPACTION_TARGET_KEEP_RATIO_FINALIZE`

兼容策略建议：
1. V1 代码层不再使用 light 配置。
2. 若环境中仍设置 legacy `COMPACTION_LIGHT_TOKEN_RATIO`，默认忽略，不报错。
3. 文档中明确其已废弃，后续版本再彻底清理。

### 6.3 Store 预算逻辑

文件：
1. `app/core/memory/sqlite_memory_store.py`

建议改动：
1. 构造函数移除 `target_keep_ratio_light` 参数。
2. `_resolve_target_keep_tokens()` 改为：
   - `mode == "strong"` -> `target_keep_ratio_strong`
   - `mode == "finalize"` -> `target_keep_ratio_finalize`
   - 其他 token 模式默认回退到 `target_keep_ratio_strong` 或明确拒绝非法 mode
3. 删除与 `light` 相关的分支和测试断言。

### 6.4 调用装配层

文件：
1. `app/agent/agent.py`
2. `app/agent/sub_agent.py`
3. `app/core/bootstrap.py`

建议改动：
1. `SQLiteMemoryStore(...)` 初始化时不再传 `target_keep_ratio_light`。
2. 保持其他参数不变。

### 6.5 可观测性与文档

需要同步更新：
1. `doc/refer/memory-reference.md`
2. `README.md`
3. 相关设计稿中仍提到 `light/strong` 双档位的部分

事件语义调整建议：
1. `context_compression_started` 的 `mode` 只应出现：
   - `strong`
   - `event`
   - `finalize`（如有结束阶段记录）
2. 历史观测数据允许保留旧值，不做迁移。

## 7. 影响分析

### 7.1 正向影响

1. 运行时行为更易解释：中途 token 压缩只有一个清晰入口。
2. 配置面缩小，减少调参混乱。
3. 测试矩阵缩小，维护成本下降。
4. 代码分支减少，后续再演进真正的“多策略压缩”时更干净。

### 7.2 潜在影响

1. 失去“70% 就先压一轮”的预防性压缩能力。
2. 某些长任务会更晚进入 token 压缩。
3. 在 `70% ~ strong_token_ratio` 区间内，上下文增长会更多依赖 `event` 工具链压缩和自然收敛。

## 8. 风险与缓解

风险 1：中途压缩触发变晚，可能增加接近 length 风险的概率。  
缓解：
1. 保持 `strong_token_ratio` 可配置。
2. 如果观测到风险升高，可直接下调 `COMPACTION_STRONG_TOKEN_RATIO`，用一个阈值替代原来的双阈值。

风险 2：某些依赖“较早压缩”的任务，历史消息保留时间变长。  
缓解：
1. 保留现有 token-budget 裁剪算法不变。
2. 保留 `event` 工具链替换压缩，优先吸收高频工具噪音。

风险 3：已有测试、文档、日志面板依赖 `light` 字段。  
缓解：
1. 先更新断言为“不再出现 `light`”。
2. 历史数据不迁移，只更新新增运行的语义。

## 9. 测试计划

建议新增或调整以下回归：

1. `mid_run_should_not_compact_when_usage_below_strong_threshold`
2. `mid_run_should_compact_with_token_strong_when_usage_reaches_strong_threshold`
3. `mid_run_should_prefer_event_compaction_for_tool_burst_below_strong_threshold`
4. `resolve_target_keep_tokens_should_not_require_light_ratio`
5. `runtime_compression_config_should_not_expose_light_fields`
6. `compression_observability_should_not_emit_light_mode`

需要同步删除或重写：
1. 任何断言 `token/light` 的测试
2. 任何断言 `target_keep_ratio_light` 或 `light_token_ratio` 的测试

## 10. 落地步骤

1. 编写并评审本设计稿。
2. 删除 runtime 触发层中的 `light` 分支。
3. 删除配置结构与默认值中的 `light` 字段。
4. 删除 `SQLiteMemoryStore` 中的 `light` 保留比例参数与逻辑。
5. 更新 agent/bootstrap 装配代码。
6. 更新文档与测试。
7. 观察一轮 runtime 压缩事件，确认不再产出 `token/light`。

## 11. 预期结果

落地后，Runtime 压缩语义将收敛为：
1. 工具连发多时，做 `event` 工具链折叠。
2. 上下文真正逼近风险阈值时，做唯一的 `token/strong` 压缩。
3. run 结束时，做 `finalize` 摘要沉淀。

一句话概括：
1. 删除“少删一点”的伪双档位，只保留一个真正有语义的中途 token 压缩模式。
