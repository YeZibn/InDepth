# Runtime Context Window Expansion And Finalize Policy 设计稿（V1）

更新时间：2026-04-18  
状态：V1 设计中（待实现）

## 1. 背景与问题

当前 Runtime 的压缩配置里，`context_window_tokens` 默认值为 `16000`，同时承担了两层含义：
1. 被当作“模型可用上下文窗口”的近似值。
2. 被当作“运行时压缩触发预算”的计算基数。

这在早期实现里是可行的，但在当前能力目标下已经出现明显问题：
1. `16000` 对现代长上下文模型而言过于保守，系统过早进入 token 压缩。
2. 单一字段混合了“模型物理上限”和“运行时安全预算”两种语义，导致调参时难以判断真正影响的是 provider 能力还是 Runtime 策略。
3. 当前 token 使用量估算仍是启发式，不是 provider 原生 tokenizer；若将单一窗口值直接调大，也会把压缩触发时机一并推迟，增加 length 风险。

同时，当前 `finalize` 压缩为默认开启的 destructive 行为：
1. Run 结束时，`finalize_memory_compaction(...)` 会调用 `compact_final(...)`。
2. `compact_final(...)` 会把早期消息写入 summary，并删除对应原始消息。
3. 这会削弱复盘、追问、错误定位和后续上下文延续时对原始消息的可追溯性。

对于以交互式研发和多轮任务为主的 InDepth Runtime 来说，这两个默认策略都偏保守：
1. 上下文预算偏小。
2. 收尾压缩偏激进。

因此，需要调整默认策略，使其更适配长上下文模型与交互式任务体验。

## 2. 目标

V1 目标：
1. 将默认上下文能力从 `16k` 级别提升到 `160k` 级别。
2. 将“模型上下文上限”和“压缩触发预算”拆分为独立配置。
3. 默认关闭 `finalize` destructive compaction。
4. 保留 `midrun` 与 `event` 压缩，继续作为运行期保护机制。
5. 保持对现有代码结构和观测体系的平滑兼容。

## 3. 非目标

V1 不做：
1. 不在本稿中引入“摘要生成但不删原消息”的 finalize 新模式。
2. 不重构 `summary_json` 结构与 `ContextCompressor` 的抽取逻辑。
3. 不引入 provider 原生 tokenizer。
4. 不在本稿中实现按需回溯原始消息的召回机制。
5. 不改动 `event` 工具链替换压缩算法。

说明：
1. “默认生成摘要不删除原消息”的能力是合理方向，但单独作为后续设计议题处理。
2. V1 先解决默认值和策略边界问题，避免一次性引入过多语义变化。

## 4. 设计原则

1. 模型能力边界与 Runtime 策略边界应分离。
2. 默认行为应优先保护交互体验与可追溯性，而不是优先节省消息存储。
3. 运行时压缩仍然需要保留安全余量，不能把启发式估算直接等同于 provider 硬上限。
4. 升级默认值时，应优先保证配置兼容和观测可解释性。

## 5. 方案概览

### 5.1 双窗口语义

将当前单一 `context_window_tokens` 拆为两类配置：

1. `model_context_window_tokens`
- 含义：模型理论上下文窗口上限。
- 用途：表达部署目标模型的能力边界，用于观测与未来风险判断。
- 建议默认值：`160000`

2. `compression_trigger_window_tokens`
- 含义：Runtime 计算上下文占用率和压缩触发阈值时使用的安全预算窗口。
- 用途：参与 `estimate_context_usage()` 等逻辑。
- 建议默认值：`120000`

理由：
1. 将模型能力提升到 `160k` 级别，符合当前目标。
2. 由于 token 使用量估算是启发式的，Runtime 触发预算不宜直接等于模型物理上限。
3. 预留一层安全带，能够降低“估算偏小导致实际超窗”的概率。

### 5.2 Finalize 默认关闭

新增 finalize 策略开关：
1. `enable_finalize_compaction`
- 含义：是否在 run 结束后执行 destructive finalize compaction。
- 建议默认值：`False`

调整后行为：
1. 默认情况下，run 结束时不再自动调用 `compact_final(...)`。
2. `compact_final(...)` 的实现仍保留，作为显式可选能力存在。
3. `midrun` 与 `event` 不受影响，继续保留。

### 5.3 兼容策略

当前已有环境变量：
1. `COMPACTION_CONTEXT_WINDOW_TOKENS`

V1 新增后建议兼容策略：
1. 优先读取 `MODEL_CONTEXT_WINDOW_TOKENS`
2. 优先读取 `COMPACTION_TRIGGER_WINDOW_TOKENS`
3. 若缺失，则回退读取 `COMPACTION_CONTEXT_WINDOW_TOKENS`
4. 若仍缺失，则使用新默认值

即：
1. 老配置仍可继续运行
2. 新部署可以逐步切换到双窗口配置
3. 文档中标记 `COMPACTION_CONTEXT_WINDOW_TOKENS` 为兼容保留字段

## 6. 详细设计

### 6.1 配置结构调整

文件：
1. `app/config/runtime_config.py`

建议将 `RuntimeCompressionConfig` 从：
1. `context_window_tokens: int`

调整为：
1. `model_context_window_tokens: int`
2. `compression_trigger_window_tokens: int`
3. `enable_finalize_compaction: bool`

其余字段保持不变：
1. `midrun_token_ratio`
2. `target_keep_ratio_midrun`
3. `target_keep_ratio_finalize`
4. `keep_recent_turns`
5. `tool_burst_threshold`
6. `compressor_kind`
7. `event_summarizer_kind`

建议环境变量：
1. `MODEL_CONTEXT_WINDOW_TOKENS`，默认 `160000`
2. `COMPACTION_TRIGGER_WINDOW_TOKENS`，默认 `120000`
3. `ENABLE_FINALIZE_COMPACTION`，默认 `False`

兼容读取规则建议：
1. `legacy_context_window = _env_int("COMPACTION_CONTEXT_WINDOW_TOKENS", 0, min_value=1024)`
2. `model_context_window_tokens`：
   - 优先 `MODEL_CONTEXT_WINDOW_TOKENS`
   - 其次 `legacy_context_window`
   - 最后默认 `160000`
3. `compression_trigger_window_tokens`：
   - 优先 `COMPACTION_TRIGGER_WINDOW_TOKENS`
   - 其次 `legacy_context_window`
   - 最后默认 `120000`

### 6.2 Runtime 使用率计算调整

文件：
1. `app/core/runtime/runtime_utils.py`
2. `app/core/runtime/agent_runtime.py`

当前：
1. `estimate_context_usage(estimated_tokens, context_window_tokens)`

调整建议：
1. `estimate_context_usage(...)` 继续保留当前方法签名风格，但实际调用处改传 `compression_trigger_window_tokens`
2. `AgentRuntime._estimate_context_usage(...)` 使用：
   - `self.compression_config.compression_trigger_window_tokens`

即：
1. 压缩触发只根据 Runtime 的安全预算判断。
2. `model_context_window_tokens` 不直接参与 midrun 触发计算。

### 6.3 Memory Store 装配调整

文件：
1. `app/core/bootstrap.py`
2. `app/agent/agent.py`
3. `app/agent/sub_agent.py`
4. `app/core/memory/sqlite_memory_store.py`

建议：
1. `SQLiteMemoryStore` 内部用于 token budget compaction 的窗口基数改为 `compression_trigger_window_tokens`
2. 若当前 store 内字段名仍保留 `context_window_tokens`，V1 可先做“语义迁移但实现最小化”：
   - 初始化时传入 `compression_trigger_window_tokens`
   - 文档与配置层统一改称“trigger window”
3. 若希望同步提升代码可读性，可直接将 store 构造参数重命名为：
   - `compression_trigger_window_tokens`

V1 推荐最小实现：
1. 配置层和 runtime 先完成“双窗口拆分”
2. store 仍可暂时内部复用 `context_window_tokens` 字段名承载 trigger window
3. 后续再做命名清理，不阻塞本次改造

### 6.4 Finalize 开关接线

文件：
1. `app/core/runtime/runtime_compaction_policy.py`
2. 相关 runtime/bootstrap 装配层

当前逻辑：
1. run 结束时若存在 `memory_store`，则调用 `compact_final(...)`

调整建议：
1. 在 `finalize_memory_compaction(...)` 中新增 `enable_finalize_compaction` 参数
2. 若为 `False`，则：
   - 保持 `final_answer` 写入逻辑不变
   - 跳过 `compact_final(...)`
3. 若为 `True`，保持当前行为

即：
1. 默认结束阶段不再裁掉历史消息
2. 需要旧行为的部署可显式开启

### 6.5 可观测性调整

建议在相关压缩事件 payload 中新增：
1. `compression_trigger_window_tokens`
2. `model_context_window_tokens`

原因：
1. 便于解释为什么在 `160k` 模型能力下，系统仍然会在更早阶段做压缩。
2. 避免后续误把“触发预算”理解为“模型真实上限”。

建议事件：
1. `context_compression_started`
2. `context_compression_succeeded`
3. 如有必要，可在后续新增“接近模型物理上限”的 warning event，但不作为 V1 必需项。

## 7. 默认值建议

V1 建议默认值：
1. `MODEL_CONTEXT_WINDOW_TOKENS=160000`
2. `COMPACTION_TRIGGER_WINDOW_TOKENS=120000`
3. `COMPACTION_MIDRUN_TOKEN_RATIO=0.82`
4. `ENABLE_FINALIZE_COMPACTION=false`
5. `COMPACTION_TARGET_KEEP_RATIO_MIDRUN=0.40`
6. `COMPACTION_TARGET_KEEP_RATIO_FINALIZE=0.40`

对应效果：
1. Runtime 将按 `120000 * 0.82 ≈ 98400` token 的估算占用开始触发 token 压缩。
2. 默认不再在 finalize 阶段删除历史消息。
3. `midrun` 和 `event` 仍承担运行期保护职责。

## 8. 影响分析

### 8.1 正向影响

1. 默认上下文能力从 `16k` 提升到 `160k` 级别，更匹配现代模型能力预期。
2. Runtime 压缩触发与模型能力边界语义分离，调参更清晰。
3. 默认关闭 finalize destructive compaction，可显著改善多轮研发任务的复盘和延续体验。
4. 保持 midrun/event 压缩不变，运行期安全性不会因关闭 finalize 而直接丢失。

### 8.2 潜在影响

1. 由于 finalize 默认关闭，SQLite 中消息留存量会增加。
2. 更大的 trigger window 会让 midrun 压缩触发变晚。
3. 若部署环境实际模型并不支持长上下文，而仍沿用 `160000` 配置，可能出现配置与 provider 能力不匹配的问题。

## 9. 风险与缓解

风险 1：双窗口配置增加理解成本。  
缓解：
1. 在文档中明确区分“模型上限”和“压缩预算”。
2. 在 observability 中同时暴露两个字段。

风险 2：trigger window 增大后，压缩触发过晚。  
缓解：
1. 采用 `120000` 而不是直接 `160000` 作为默认 trigger window。
2. 保留 `COMPACTION_MIDRUN_TOKEN_RATIO` 可配置。

风险 3：finalize 关闭后，历史消息增长过快。  
缓解：
1. 保留 `midrun` token compaction。
2. 保留 `event` 工具链折叠压缩。
3. 保留 `enable_finalize_compaction` 作为显式开关，供低存储模式使用。

风险 4：旧环境只配置 `COMPACTION_CONTEXT_WINDOW_TOKENS`，迁移后行为不一致。  
缓解：
1. 对 legacy 字段保持回退兼容。
2. 文档中标注迁移说明与优先级。

## 10. 测试计划

建议新增或调整以下回归：

1. `runtime_compression_config_should_load_dual_window_defaults`
2. `runtime_compression_config_should_fallback_to_legacy_context_window`
3. `estimate_context_usage_should_use_trigger_window_not_model_window`
4. `finalize_memory_compaction_should_skip_when_finalize_disabled`
5. `finalize_memory_compaction_should_call_compact_final_when_finalize_enabled`
6. `compression_observability_should_include_model_and_trigger_window`
7. `bootstrap_should_wire_trigger_window_into_memory_store`

## 11. 落地步骤

1. 在 `RuntimeCompressionConfig` 中新增双窗口与 finalize 开关配置。
2. 更新配置加载逻辑与 legacy 回退逻辑。
3. 调整 `AgentRuntime` 使用 trigger window 计算上下文占用率。
4. 调整 runtime finalize 流程，接入 `enable_finalize_compaction`。
5. 更新 bootstrap / agent / sub-agent 装配层。
6. 更新测试。
7. 更新 `README.md`、`doc/refer/config-reference.md`、`doc/refer/runtime-reference.md`、`doc/refer/memory-reference.md`。

## 12. 预期收益

1. Runtime 默认策略更符合长上下文模型和交互式研发场景。
2. 压缩配置语义更清晰，后续继续演进“原文回溯能力”时边界更干净。
3. 通过先关闭 finalize destructive compaction，为后续讨论“摘要保留但原文不删”留出稳定演进空间。
