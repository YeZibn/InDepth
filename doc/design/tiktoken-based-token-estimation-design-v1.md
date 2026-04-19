# Runtime Tiktoken Token Estimation 设计稿（V1）

更新时间：2026-04-19  
状态：V1 已落地首版

## 1. 背景与问题

当前 Runtime 的 token 计数主要依赖启发式估算：
1. `app/core/runtime/runtime_utils.py` 中的 `estimate_context_tokens(...)` 使用 CJK 字符数、英文词数、标点数和固定 envelope 开销估算上下文 token。
2. `app/core/memory/sqlite_memory_store.py` 中的 `_estimate_message_tokens(...)` 也维护了一套相似但独立的近似算法，用于 token budget compaction。

这带来几个问题：
1. 同一份上下文在“是否触发压缩”和“压缩后保留多少消息”两个阶段，可能得到不同口径的 token 结果。
2. `tool_calls`、JSON 结果、代码块、命令行输出、路径等内容的 token 密度与普通自然语言差异较大，启发式误差会放大。
3. 随着默认上下文窗口已提升到长上下文级别，误差会直接影响压缩触发时机和裁剪有效性。
4. 现有观测中的 `estimated_tokens` 是经验值，不便于和真实模型 tokenizer 语义对齐。

因此，需要把 Runtime 的 token 估算从启发式升级为基于 `tiktoken` 的真实 tokenizer 计数。

## 2. 目标

V1 目标：
1. 用 `tiktoken` 替换当前 Runtime 主链路中的启发式 token 估算。
2. 统一 Runtime 触发压缩与 SQLite Memory Store 裁剪预算的 token 计数口径。
3. 在不改动压缩策略语义的前提下，提高 token 预算判断的可信度。
4. 保持现有 `model_context_window_tokens=160000` 与 `compression_trigger_window_tokens=120000` 的双窗口语义不变。
5. 不做启发式降级，缺少 `tiktoken` 或模型映射异常时直接显式失败。

## 3. 非目标

V1 不做：
1. 不改动 `120000 / 160000` 双窗口设计与相关环境变量语义。
2. 不重构 `ContextCompressor` 的摘要提取逻辑。
3. 不引入 provider 侧精确 chat 计费对齐能力。
4. 不在本稿中实现“临界区启发式 + 原生 tokenizer 复核”的双层计数策略。
5. 不修改 `event` 工具链摘要生成逻辑。

说明：
1. `tiktoken` 可以显著提升“文本被 tokenizer 切分后的 token 数”准确性。
2. 但 provider 请求最终占用仍可能包含额外包装，因此双窗口安全带仍然合理。

## 4. 设计原则

1. 先统一计数口径，再讨论阈值微调。
2. 计数实现应尽量复用，避免 runtime 与 memory store 各自维护一套逻辑。
3. 优先采用接近 Chat Completions 标准语义的 token 计算方式，而不是自定义文本渲染近似。
4. 不做静默回退；计数失败应尽早暴露配置或实现问题。
5. 尽量最小改动接入点，减少对现有压缩、观测、测试的扰动。

## 5. 方案概览

### 5.1 核心思路

新增统一 token 计数模块，使用 `tiktoken` 进行消息级和上下文级计数：
1. 将单条 message 规范化渲染为稳定文本表示。
2. 使用 `tiktoken` 对该文本进行编码并取 `len(encoded)`。
3. 所有 Runtime token 相关判断都复用同一套计数入口。

即：
1. `estimate_context_tokens(...)` 不再直接使用正则启发式。
2. `SQLiteMemoryStore._estimate_message_tokens(...)` 不再单独维护近似逻辑。
3. 两者统一走共享的 `tiktoken` 计数函数。

### 5.2 标准计数语义

一般来说，上下文窗口里的 token 计算应遵循：
1. 输入上下文 token = 本次请求实际发送给模型、会参与模型推理的所有 prompt 部分 token 总和
2. 对 Chat Completions 来说，至少包括：
   - `messages`
   - `tools` / function schema
   - 与 prompt 构造直接相关的结构字段
3. 输出预算 token = `max_tokens` 或等价的生成上限
4. 总窗口约束 = `input_tokens + tools_tokens + reserved_output_tokens <= model_context_window_tokens`

对当前项目的 V1 约定：
1. midrun 压缩触发仍主要依据输入上下文 token 使用率
2. 输入上下文 token 采用 `tiktoken` 按 Chat Completions 标准 message 口径计算，`tools` 独立统计
3. 不再使用自定义 message 文本渲染格式作为主计数依据

V1 纳入计数的内容：
1. `messages` 全量内容
2. `tool_calls`
3. `tool_call_id`
4. `tools` schema（独立统计，不并入 `input_tokens`）

V1 暂不纳入独立预算核算但保留双窗口安全带的内容：
1. provider 内部实现细节带来的额外包装
2. 少数 OpenAI-compatible 服务的非标准扩展字段额外开销

因此，V1 的语义是：
1. 采用当前客户端可实现范围内最标准、最接近实际请求的 token 计算
2. 仍保留双窗口作为对 provider 侧隐式开销和输出空间的缓冲

### 5.3 双窗口保持不变

本稿明确保留现有语义：
1. `model_context_window_tokens=160000`
2. `compression_trigger_window_tokens=120000`

理由：
1. `tiktoken` 解决的是“如何更准确地数 token”。
2. 双窗口解决的是“什么时候进入压缩保护”和“模型理论容量是多少”。
3. 即使采用 `tiktoken`，仍需要为 provider 包装误差、输出空间和工具链额外膨胀预留安全余量。

因此，V1 只替换计数方法，不调整阈值策略。

## 6. 详细设计

### 6.1 新增统一计数模块

建议新增文件：
1. `app/core/runtime/token_counter.py`

建议提供如下接口：
1. `count_text_tokens(text: str) -> int`
2. `count_message_tokens(message: Dict[str, Any]) -> int`
3. `count_messages_tokens(messages: List[Dict[str, Any]]) -> int`

实现原则：
1. 模块内部统一获取 `tiktoken` encoding。
2. 计数方法尽量对齐 Chat Completions 标准 message 口径，而不是自行拼接自由文本。
3. `messages` 与 `tools` 分开计数。
4. `input_tokens` 表示 request `messages` token；`tools_tokens` 作为辅助观测字段保留。
4. 对空值、非法结构显式报错，不做静默吞掉。

建议接口扩展为：
1. `count_chat_messages_tokens(messages: List[Dict[str, Any]], model: str) -> int`
2. `count_chat_tools_tokens(tools: List[Dict[str, Any]], model: str) -> int`
3. `count_chat_input_tokens(messages: List[Dict[str, Any]], tools: List[Dict[str, Any]], model: str) -> int`
4. `build_request_token_metrics(...) -> Dict[str, Any]`

说明：
1. V1 采用“按 Chat Completions 请求结构计数”的格式。
2. 具体实现应参考 `tiktoken` 对 chat message 的标准计数方式，为每条 message 的 role/content/tool_calls/tool_call_id 计数。
3. `tools` 采用 function schema 的标准结构计数，而不是忽略或仅按 `len(json)//4` 近似。

### 6.2 `tiktoken` encoding 选择

建议优先使用：
1. `tiktoken.encoding_for_model(...)`

原因：
1. 当前 provider 已持有 `model_id`，可以直接用于 `encoding_for_model(...)`。
2. 这比手工指定基础 encoding 更接近“按目标模型计算 token”的标准方式。
3. 若模型名无法映射到 `tiktoken`，应直接报错并要求修正模型映射或显式适配。

### 6.3 Runtime 接入点

文件：
1. `app/core/runtime/runtime_utils.py`
2. `app/core/runtime/agent_runtime.py`

调整建议：
1. `estimate_context_tokens(...)` 改为调用共享 token counter。
2. `AgentRuntime` 在每一个 step 的 `model_provider.generate(...)` 之前，先统计本轮真实请求输入 token。
3. `AgentRuntime._estimate_context_tokens(...)` 改为复用共享 message counter，供 midrun compaction 复用。
4. `estimate_context_usage(...)` 保持不变，继续使用 `compression_trigger_window_tokens` 计算占用率。
5. 调用侧仍需把“本轮请求实际会发送的 tools”一并传入 token counter，用于 `tools_tokens` 和 `total_window_claim_tokens`。

这样可以做到：
1. 调用链最小改动
2. 中层策略代码无需感知 `tiktoken` 细节
3. step 级统计结果可直接进入 observability，用于后续阈值校准

补充：
1. `maybe_compact_mid_run(...)` 仍保留 `tools` 参数，用于观测当前 request 的完整窗口申领。
2. 每个 step 都要重新统计，因为 tool schema、历史摘要和最近消息都会动态变化。
3. `AgentRuntime` 需要同时维护 request 级 `input_tokens` 与 step 级 `step_input_tokens`。
4. `AgentRuntime` 是 step 语义和压缩策略的拥有者，因此统计入口应放在 `AgentRuntime`，而不是 provider。

### 6.4 SQLite Memory Store 接入点

文件：
1. `app/core/memory/sqlite_memory_store.py`

调整建议：
1. `_estimate_rows_tokens(...)` 内部改为复用共享 token counter。
2. `_estimate_message_tokens(...)` 改为薄封装，或直接删除并统一走共享实现。
3. `_compute_token_budget_cut_index(...)` 的算法不变，仅替换 token 来源。

这样可以保证：
1. 触发压缩前看到的 `estimated_tokens`
2. 压缩时计算 `target_keep_tokens` 后保留尾部区间所用的 token 值

都来自同一套计数口径。

### 6.5 依赖策略

文件：
1. `requirements.txt`
2. 新增 token counter 模块

建议：
1. 将 `tiktoken` 加入依赖。
2. token counter 内部对 import 失败直接抛错。
3. 对 `encoding_for_model(...)` 映射失败也直接抛错。

原因：
1. 本稿目标是把 token 估算升级为 `tiktoken` 标准路径，而不是保留旧逻辑兜底。
2. 若缺少依赖或模型映射不兼容，应该尽早暴露，而不是悄悄退回低精度估算。

### 6.6 可观测性

建议在压缩相关事件 payload 中新增：
1. `token_counter_kind`
2. 可选 `token_counter_encoding`

涉及事件：
1. `context_compression_started`
2. `context_compression_succeeded`
3. `context_compression_failed`（如计数异常）

作用：
1. 帮助确认当前运行使用的 tokenizer 与 encoding。
2. 便于后续评估阈值是否需要从 `120000` 上调。

## 7. 配置与兼容性

V1 建议：
1. 不新增用户可配置阈值字段
2. 不修改 `RuntimeCompressionConfig` 结构
3. 不修改已有双窗口读取逻辑

可选增强：
1. 后续若模型映射经常变动，可新增显式 `TOKEN_COUNTER_MODEL_ID` 或 `TOKEN_COUNTER_ENCODING`

但 V1 最小实现中并非必须。

## 8. 风险与缓解

1. `tiktoken` 计数结果与 provider 实际上下文占用仍有偏差。
- 缓解：保持 `compression_trigger_window_tokens < model_context_window_tokens` 的双窗口安全带不变。

2. message 渲染格式变化会改变 token 结果。
- 缓解：将渲染逻辑集中在单一模块中，禁止多处拼接。

3. 依赖缺失或模型映射失败导致运行失败。
- 缓解：在启动阶段做前置校验，尽早失败，并在错误信息中明确缺少 `tiktoken` 或模型不受支持。

4. 计数精度提升后，部分测试中对具体 token 值的断言会失效。
- 缓解：测试从“固定数值”迁移为“触发/不触发行为”和“结果字段存在性”断言。

## 9. 测试计划

新增或调整回归集：
1. `estimate_context_tokens_should_use_tiktoken_when_available`
2. `token_counter_should_fail_fast_when_tiktoken_unavailable`
3. `token_counter_should_fail_fast_when_model_encoding_unknown`
4. `sqlite_memory_store_should_share_same_token_counter_with_runtime`
5. `context_compression_events_should_report_token_counter_kind`
6. `token_budget_cut_should_use_tiktoken_counts`
7. `chat_input_token_count_should_include_tools_schema`

建议保留的兼容验证：
1. 双窗口默认值仍为 `160000 / 120000`
2. `estimate_context_usage(...)` 仍按 `compression_trigger_window_tokens` 计算
3. 现有 compaction 行为语义不变，仅计数口径改变

## 10. 落地步骤

1. 新增统一 token counter 模块。
2. 在 `requirements.txt` 中加入 `tiktoken`。
3. 基于 Chat Completions 标准 message / tools 口径实现统一 token counter。
4. 替换 `runtime_utils.py` 中的启发式 `estimate_context_tokens(...)`。
5. 替换 `sqlite_memory_store.py` 中的 `_estimate_message_tokens(...)` / `_estimate_rows_tokens(...)`。
6. 为 observability 增加 `token_counter_kind` / `token_counter_encoding` 等字段。
7. 更新相关测试和文档。

## 11. 预期收益

1. token 触发压缩的判断将明显比当前启发式更可靠。
2. Runtime 与 Memory Store 的 token 预算口径统一，减少前后行为不一致。
3. 后续若要重新校准 `compression_trigger_window_tokens`，将有更可信的基础。
4. 为未来升级到 provider 更精确的 chat token 计数留出清晰演进路径。
