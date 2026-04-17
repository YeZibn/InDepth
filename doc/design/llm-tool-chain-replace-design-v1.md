# Runtime LLM Tool Chain Replace 设计稿（V1）

更新时间：2026-04-17  
状态：Implemented（已落地）

## 0. 实现结果

已按本稿落地：
1. `event` 路径的 `Tool chain replace` 已支持 `rule / llm / auto` 三种摘要器模式。
2. `auto` 模式下，真实 provider 默认优先使用 mini 模型生成工具链替代摘要。
3. `MockModelProvider` 下默认自动回退规则摘要，保证测试稳定性。
4. `stateful tool` 豁免、最近窗口保护、锚点替换等安全边界保持不变。
5. 新增观测字段：`tool_chain_summary_requested / applied / fallback_* / model`。

## 1. 背景与问题

当前 Runtime 的 `event` 压缩，也就是 `Tool chain replace`，由规则逻辑完成：
1. 在 `event` 模式下定位最近连续工具调用段。
2. 将该区段切分为工具单元。
3. 跳过 `todo/search guard` 等状态工具单元。
4. 用固定模板生成 `[tool-chain-compact]` 替代消息。

当前实现稳定、可控，但存在几个问题：
1. 语义抽象能力有限。规则只能聚合 `tools/stats/key_ids/failures`，很难表达“这串工具调用真正完成了什么”。
2. 对异构工具结果适配差。不同工具返回结构差异很大，纯规则方案很难在不持续加 heuristic 的情况下提炼高质量摘要。
3. 摘要内容偏机械。后续模型读到的是“调用统计”，而不是“执行结果语义”，对下一步决策帮助有限。
4. 扩展成本高。每新增一种工具结果模式，就要继续补 `_extract_key_identifiers / _compact_preview_json` 一类规则。

因此，`Tool chain replace` 适合升级为“LLM 驱动的结构化替代消息生成”，并优先使用 mini 模型控制额外成本。

## 2. 目标

V1 目标：
1. 将 `event` 路径的 `Tool chain replace` 摘要生成从规则实现升级为 LLM 实现。
2. 默认使用 `mini_model_id` 对工具链进行压缩，避免与主推理链争抢大模型预算。
3. 保留现有“最近窗口保护 / stateful tools 豁免 / 锚点替换”机制，不改变压缩边界判定。
4. 保留规则生成器作为强回退路径，确保 LLM 失败不会阻断 runtime。
5. 让替代消息从“统计摘要”升级为“面向后续决策的高信号执行摘要”。

## 3. 非目标

V1 不做：
1. 不改变 `event` 触发时机，仍由 `consecutive_tool_calls >= tool_burst_threshold` 决定。
2. 不取消 stateful tool 豁免规则。
3. 不把 `midrun/finalize` 结构化 summary 压缩逻辑合并到同一 prompt。
4. 不改变当前 SQLite 消息存储模型。
5. 不引入异步后台压缩；V1 仍然是同步调用。

## 4. 设计原则

1. LLM 只负责“如何总结这段工具链”，不负责“哪些消息允许被替换”。
2. 压缩边界必须继续由确定性规则控制，避免 LLM 误删关键状态。
3. mini 模型优先，失败自动回退到现有规则实现。
4. 替代消息仍保持单条 assistant message，兼容现有 memory 读写链路。
5. 摘要面向后续模型消费，而不是面向用户展示。

## 5. 方案概览

### 5.1 保留规则边界，替换摘要生成器

V1 不改以下步骤：
1. `_find_latest_tool_chain_span(...)`
2. `_split_tool_chain_units(...)`
3. `_select_event_compaction_unit_span(...)`
4. `event_stateful_tools` 豁免

只替换这一步：
1. `_build_tool_chain_summary(...)`

也就是说，压缩区段仍由规则选定，但区段内容的摘要由 mini LLM 生成。

### 5.2 默认走 mini 模型

项目当前已经有：
1. `RuntimeModelConfig.mini_model_id`
2. 多处 `build_*_config()` 通过 `provider_options["model"] = mini_id` 覆盖模型

因此 V1 推荐复用现有模式：
1. `Tool chain replace` 专用 LLM config 默认显式覆盖为 `mini_model_id`
2. 若 `mini_model_id` 不可用，则回退到当前 provider 默认模型
3. 若模型调用或解析失败，则回退到规则摘要生成

### 5.3 输出仍是文本替代消息

V1 不改变 `messages` 表结构，不新增 `event_summary_json` 字段。

LLM 输出目标仍是一段固定前缀文本：

```text
[tool-chain-compact] 已压缩连续工具调用段。
- summary: ...
- key_results: ...
- key_ids: ...
- failures: ...
```

与当前版本相比，差异在于：
1. `summary` 由 LLM 生成，表达“这段工具链做成了什么”
2. `key_results / key_ids / failures` 仍由代码补充并约束

这样做的原因：
1. 不破坏当前替换逻辑
2. 保留现有可读性和可追踪性
3. 让 LLM 只负责最擅长的语义压缩部分

## 6. 详细设计

### 6.1 新增组件：LLM Tool Chain Summarizer

建议新增一个轻量组件，例如：
1. `app/core/memory/llm_tool_chain_replacer.py`
2. 或 `app/core/memory/tool_chain_replace_summarizer.py`

职责：
1. 接收被替换工具链区段 `chain_rows`
2. 序列化为适合 mini LLM 的输入
3. 调用 provider 生成语义摘要
4. 对输出做清洗与长度限制
5. 失败时回退到规则摘要生成

建议接口：

```python
def build_tool_chain_replacement_message(
    chain_rows: List[_MessageRow],
    model_provider: Optional[ModelProvider],
    use_llm: bool,
) -> str:
    ...
```

或更清晰地拆成：
1. `RuleToolChainSummarizer`
2. `LLMToolChainSummarizer`
3. `build_tool_chain_summarizer(...)`

### 6.2 输入数据结构

为了避免把整段原始 JSON 无脑塞给 mini 模型，建议先做轻量归一化。

建议输入给模型的数据：
1. `tool_names`
2. `success_count / failed_count`
3. `executions`
   - `tool`
   - `success`
   - `error`
   - `payload_preview`
   - `key_ids`
4. `raw_result_samples`
5. `stateful_guard_applied`

其中：
1. `payload_preview` 由代码预先从结果中抽短片段
2. `key_ids` 由规则先提取，不能完全依赖模型
3. 每条 execution 建议截断到固定大小，避免 mini prompt 膨胀

示例输入：

```json
{
  "task": "Summarize the compressed tool chain for future runtime context injection.",
  "tool_chain": {
    "tools": ["read_file", "read_file", "bash"],
    "stats": {"success": 2, "failed": 1},
    "executions": [
      {
        "tool": "read_file",
        "success": true,
        "payload_preview": "path=app/core/runtime/tool_execution.py; content preview=..."
      },
      {
        "tool": "bash",
        "success": false,
        "error": "1 failed, 12 passed",
        "payload_preview": "stdout preview=..."
      }
    ]
  }
}
```

### 6.3 输出格式

V1 建议 LLM 不直接生成整段最终文本，而是先输出一个很小的 JSON：

```json
{
  "summary": "读取了两个核心文件并尝试运行相关测试，测试失败暴露出压缩链路中的 1 个回归点。",
  "key_results": [
    "定位到 runtime tool execution 与 memory compaction 两处实现",
    "测试执行失败，失败信息与压缩链路相关"
  ],
  "failures": [
    "1 failed, 12 passed"
  ]
}
```

然后由程序把最终替代消息拼出来：

```text
[tool-chain-compact] 已压缩连续工具调用段。
- tools: read_filex2, bashx1
- stats: success=2, failed=1
- summary: 读取了两个核心文件并尝试运行相关测试，测试失败暴露出压缩链路中的 1 个回归点。
- key_ids: path=app/core/runtime/tool_execution.py
- key_results: 定位到 runtime tool execution 与 memory compaction 两处实现 | 测试执行失败，失败信息与压缩链路相关
- failures: 1 failed, 12 passed
```

这样做有三个好处：
1. 结构边界更稳，便于解析和回退。
2. `tools/stats/key_ids` 继续由代码控制，不受模型幻觉影响。
3. LLM 只负责真正难做的语义压缩字段。

### 6.4 Prompt 设计

建议 system prompt 强调：
1. 你的任务是为 runtime 生成后续可消费的工具链压缩摘要。
2. 不是给用户写报告。
3. 必须保留执行结果、失败原因、关键产物线索。
4. 不要编造不存在的文件、ID、结论。
5. 只输出 JSON。

建议 user prompt 提供：
1. 工具链统计信息
2. 每次 execution 的简短结构化片段
3. 输出 schema
4. 压缩规则

建议规则：
1. `summary` 1 句，描述“做了什么 + 结果如何”
2. `key_results` 最多 3 条
3. `failures` 最多 3 条
4. 如果没有失败，`failures` 返回空数组
5. 严禁输出 Markdown fence

### 6.5 mini 模型配置

建议新增一个专用配置构造函数，风格对齐现有：
1. `build_tool_chain_replace_config()`

推荐配置：
1. `temperature = 0.0`
2. `max_tokens = 220 ~ 320`
3. `provider_options["model"] = mini_model_id`

说明：
1. `Tool chain replace` 需要的是高约束、小输出、低成本推理，非常适合 mini 模型。
2. 若 `mini_model_id` 为空，则不强制失败，退化为 provider 默认模型。
3. 若 provider 是 `MockModelProvider`，测试中可以按现有 LLM compressor 经验做自动降级。

### 6.6 回退策略

LLM 失败时必须无条件回退规则实现。

回退触发条件：
1. 模型请求异常
2. 返回空字符串
3. JSON 解析失败
4. 缺少 `summary`
5. `summary` 为空或明显无效

回退行为：
1. 调用当前规则 `_build_tool_chain_summary(...)`
2. 保证 `event` 压缩主流程继续完成
3. 在可观测性中记录：
   - `tool_chain_summary_requested = llm`
   - `tool_chain_summary_applied = rule`
   - `tool_chain_summary_fallback_reason = ...`

### 6.7 可观测性

建议在 `context_compression_succeeded` 的 `result` 中新增：
1. `tool_chain_summary_requested`
2. `tool_chain_summary_applied`
3. `tool_chain_summary_fallback_used`
4. `tool_chain_summary_fallback_reason`
5. `tool_chain_summary_model`

示例：
1. 请求 `llm_mini`，实际应用 `llm_mini`
2. 请求 `llm_mini`，但回退到 `rule`

### 6.8 与现有 event 安全策略的关系

当前 `tool-chain-compaction-safety` 方案仍应保留：
1. stateful tool 豁免
2. 最近窗口保护
3. 锚点消息替换

原因：
1. LLM 提升的是“摘要质量”，不是“压缩安全边界”
2. 哪些工具可以被压缩，必须继续由规则决定
3. 否则风险会从“摘要质量不足”升级为“状态语义损坏”

## 7. 实现落点建议

建议改动点：

1. [`app/core/memory/sqlite_memory_store.py`](/Users/yezibin/Project/InDepth/app/core/memory/sqlite_memory_store.py)
   - 把 `_build_tool_chain_summary(...)` 拆成规则版生成器
   - 在 `_compact_event_tool_chain(...)` 中注入 LLM 摘要器

2. `app/core/memory/`
   - 新增 `build_tool_chain_replace_config()`
   - 新增 `LLMToolChainSummarizer`

3. [`app/config/runtime_config.py`](/Users/yezibin/Project/InDepth/app/config/runtime_config.py)
   - 视需要新增开关：
     - `event_compressor_kind`
     - 或更轻量地复用 `compressor_kind`，但不推荐直接复用同一字段

4. [`app/core/bootstrap.py`](/Users/yezibin/Project/InDepth/app/core/bootstrap.py)
   - 构造 runtime 时注入 event tool-chain summarizer

## 8. 配置建议

V1 推荐新增独立配置，而不是直接沿用 `COMPACTION_COMPRESSOR_KIND`。

建议环境变量：
1. `COMPACTION_EVENT_SUMMARIZER_KIND`
   - 可选值：`rule | llm | auto`
   - 默认：`auto`
2. `COMPACTION_EVENT_SUMMARIZER_MAX_TOKENS`
   - 默认：`280`

推荐默认行为：
1. `auto`
   - 真实 provider：优先 `llm`，且显式指定 `mini_model_id`
   - `MockModelProvider`：默认 `rule`

原因：
1. `midrun/finalize` 的 `summary_json` 压缩与 `event` 的 tool-chain replace 语义不同
2. 二者应允许独立观测、独立回退、独立调参

## 9. 风险与缓解

风险 1：mini 模型摘要过于泛化，丢掉关键执行结论。  
缓解：
1. `tools/stats/key_ids` 继续由程序补写
2. 只把 `summary/key_results/failures` 交给模型生成
3. 缺字段或弱输出直接回退规则版

风险 2：event 压缩本来是“轻量本地操作”，改成 LLM 后增加时延。  
缓解：
1. 使用 mini 模型
2. 严格控制输入截断
3. 仅在真正命中 `event` 压缩时调用

风险 3：测试稳定性下降。  
缓解：
1. 默认 `auto`
2. `MockModelProvider` 下自动回退规则版
3. 增加显式 LLM event summarizer 单测，而不是改坏既有测试

风险 4：模型编造不存在的关键 ID。  
缓解：
1. `key_ids` 不由模型生成
2. 关键 ID 一律来自程序提取
3. LLM 只负责语义摘要

## 10. 测试计划

建议至少覆盖：

1. `event_tool_chain_replace_uses_llm_summary_when_auto_and_real_provider`
2. `event_tool_chain_replace_falls_back_to_rule_on_invalid_json`
3. `event_tool_chain_replace_falls_back_to_rule_on_empty_summary`
4. `event_tool_chain_replace_keeps_stateful_tool_guard`
5. `event_tool_chain_replace_uses_mini_model_override`
6. `event_tool_chain_replace_preserves_key_ids_from_rule_extractor`

## 11. 预期收益

1. 替代消息从“统计摘要”升级为“执行语义摘要”，更利于后续模型决策。
2. 减少对工具专属 heuristic 的持续堆叠。
3. 在保持当前安全边界的同时，引入更高质量的 `event` 压缩结果。
4. 由于使用 mini 模型，新增成本和时延可控。
