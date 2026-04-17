# Runtime LLM Context Compressor 设计稿（V1）

更新时间：2026-04-17  
状态：Implemented（已落地）

## 1. 背景与问题

当前 Runtime 上下文压缩主要由本地规则压缩器完成：
1. `ContextCompressor.merge_summary(...)` 基于启发式规则提取 `task_state / decisions / constraints / artifacts / open_questions`。
2. `event` 路径只做最近工具链消息替换，不进入结构化摘要。
3. `midrun/finalize` 路径都会把旧消息压成 `summary_json`，并在后续作为 system 摘要注入。

当前规则压缩存在几个明显问题：
1. 语义抽取能力弱。很多字段只是对最近消息做截断，而不是进行真正的压缩总结。
2. 信息噪音高。工具返回、失败文案、重复进展容易被直接塞进 `decisions/constraints/artifacts`。
3. 结构质量不稳定。`constraints`、`decisions`、`open_questions` 的归类高度依赖简单关键词或角色判断。
4. 用户意图保持不足。复杂多轮任务里，“真正目标 / 已完成部分 / 下一步”经常不能被准确表达。
5. 规则扩展成本高。每发现一类新问题，都要继续叠加 heuristic。

因此，需要把 `midrun/finalize` 的结构化摘要主链路升级为可配置的 LLM 压缩器。

## 2. 目标

V1 目标：
1. 为 Runtime memory 引入一个可配置的压缩器选择机制。
2. 支持 `rule` 与 `llm` 两类压缩器，并提供 `auto` 自动选择模式。
3. 在 `midrun/finalize` 路径中允许使用 LLM 生成 `summary_json`。
4. 保留现有 `event` 工具链折叠逻辑，不在 V1 改造。
5. 保留规则压缩器作为可靠回退路径，确保 LLM 失败不阻断主流程。

## 3. 非目标

V1 不做：
1. 不改变 `event` 压缩的数据结构和策略。
2. 不引入新的 runtime memory 表结构。
3. 不重写 `render_summary_prompt(...)` 的输出格式。
4. 不把压缩逻辑移到独立服务；仍在当前进程内完成。
5. 不把所有 memory 生命周期都改成 LLM，仅改 `summary_json` 生成主链路。

## 4. 设计原则

1. LLM 压缩必须是“增强”，不是“单点风险”。
2. 配置必须可控，且支持平滑回退。
3. 压缩结果必须继续遵守当前 `summary_json` 结构边界，避免对读取链路产生破坏性影响。
4. 在测试与本地离线场景中，不应强依赖真实模型可用性。

## 5. 方案概览

### 5.1 压缩器模式

新增压缩器配置：
1. `rule`：始终使用现有规则压缩器。
2. `llm`：优先使用 LLM 压缩器；若失败则回退规则压缩器。
3. `auto`：在有可用真实模型 provider 时使用 LLM；在测试/Mock provider 等场景下自动回退规则压缩器。

推荐默认：
1. `compressor_kind = auto`

原因：
1. 对真实运行环境可自动启用 LLM 压缩。
2. 对现有基于 `MockModelProvider` 的测试，不会引入额外 scripted output 负担。

### 5.2 压缩器抽象

将当前 `ContextCompressor` 从“唯一实现”改为“默认规则实现”。

建议抽象：
1. 保留 `ContextCompressor` 作为规则压缩器。
2. 新增 `LLMContextCompressor`：
   - 继承或包装 `ContextCompressor`
   - 复用 `render_summary_prompt / summary_to_text / load_summary_json / validate_consistency`
   - 只替换 `merge_summary(...)` 的实现
3. 新增工厂或构造逻辑，根据 `RuntimeCompressionConfig` 选择压缩器。

## 6. 详细设计

### 6.1 新增配置项

建议在 `RuntimeCompressionConfig` 中新增：
1. `compressor_kind: str`
2. `compressor_llm_max_tokens: int`

建议环境变量：
1. `COMPACTION_COMPRESSOR_KIND`
   - 可选值：`auto | rule | llm`
   - 默认：`auto`
2. `COMPACTION_COMPRESSOR_LLM_MAX_TOKENS`
   - 默认：`1200`

说明：
1. V1 不额外引入独立“压缩模型 ID”配置，默认直接复用当前 runtime 的 `model_provider`。
2. 若未来需要独立压缩模型，可在 V2 再引入 `COMPACTION_COMPRESSOR_MODEL_ID`。

### 6.2 LLM 压缩器接线位置

建议修改点：
1. `SQLiteMemoryStore` 不再在内部硬编码 `ContextCompressor()`。
2. `SQLiteMemoryStore.__init__` 新增参数：
   - `compressor: Optional[ContextCompressor] = None`
3. 若未传入，则默认使用规则压缩器。
4. 由 `BaseAgent / SubAgent / create_runtime()` 在构造 `SQLiteMemoryStore` 时，根据 `compression_config + model_provider` 构建压缩器。

即：
1. model provider 先创建
2. compression config 加载
3. build compressor
4. 将 compressor 注入 `SQLiteMemoryStore`
5. 同一个 provider 同时服务于 runtime 主推理与 LLM 压缩

### 6.3 LLM 压缩器输入

LLM 压缩器的输入建议包含：
1. `previous_summary`：已有的结构化摘要（若有）
2. `messages`：本次准备裁掉的旧消息
3. `mode`：`midrun` 或 `finalize`
4. `trigger`：`token` 或 `finalize`
5. `before_messages / after_messages / dropped_messages`

为了降低 prompt 膨胀，建议对 `messages` 做轻量预处理：
1. 保留 `id / turn / role / tool_call_id / content`
2. 对超长内容做有限截断（如单条 1000~1500 chars）
3. 保留 tool JSON 原文的核心片段，而不是再套额外 heuristic 摘要

### 6.4 LLM 输出约束

LLM 应只输出 JSON，对齐当前 summary 结构：

```json
{
  "version": "v1_llm",
  "task_state": {
    "goal": "",
    "progress": "",
    "next_step": "",
    "completion": 0.0
  },
  "decisions": [],
  "constraints": [],
  "artifacts": [],
  "open_questions": []
}
```

要求：
1. 输出必须是单个 JSON object。
2. 顶层字段缺失时由代码补齐。
3. `compression_meta` 不由模型生成，由程序在结果外层补写。
4. 允许 `version = "v1_llm"`，但渲染逻辑仍兼容 `v1` 结构。

### 6.5 LLM Prompt 策略

建议 system prompt 明确四点：
1. 目标是“压缩上下文”，不是写面向用户的总结。
2. 必须保留硬约束、关键产物、已完成进展和下一步。
3. 需要尽可能去重、去噪、抽象重复工具输出。
4. 严格输出 JSON，不要 Markdown，不要解释。

建议 user prompt 提供：
1. `previous_summary`
2. `messages_to_compress`
3. `mode/trigger`
4. 字段语义说明
5. 输出 schema

### 6.6 回退策略

LLM 压缩器必须具备强回退能力。

回退触发条件：
1. 模型调用异常
2. 返回为空
3. JSON 解析失败
4. 顶层结构不合法
5. 生成结果未通过一致性要求

回退行为：
1. 直接调用规则压缩器 `ContextCompressor.merge_summary(...)`
2. 不阻断本次压缩流程
3. 可通过 observability 记录 `compressor_kind_requested` 与 `compressor_kind_applied`

### 6.7 一致性守护

当前 `validate_consistency(...)` 逻辑保留。

建议执行顺序：
1. 先用 LLM 生成候选摘要
2. 代码补齐字段与 `compression_meta`
3. 运行 `validate_consistency(previous, candidate)`
4. 如果失败：
   - 不直接让整个压缩失败
   - 先回退到规则压缩器重试
5. 若规则压缩也失败，再按现有逻辑返回 `consistency_check_failed`

这样可以避免 LLM 偶发遗漏 immutable constraints 时，整次压缩完全失效。

## 7. 数据与兼容

### 7.1 数据结构兼容

不新增 DB 字段：
1. `summary_json` 仍写入现有 `summaries.summary_json`
2. `summary` 仍存渲染后的文本
3. `schema_version` 仍写 `merged_json["version"]`

兼容原则：
1. 旧 `v1` 结构继续可读
2. 新 `v1_llm` 结构字段不变，只在 `version` 上体现来源

### 7.2 运行时兼容

为了兼容现有测试与本地环境：
1. `compressor_kind=auto` 时：
   - 若 `model_provider.__class__.__name__ == "MockModelProvider"`，自动回退 `rule`
2. `compressor_kind=llm` 时：
   - 即使在 Mock provider 场景，也允许显式测试 LLM 压缩器
3. `compressor_kind=rule` 时：
   - 行为应与当前版本保持一致

## 8. 可观测性建议

建议在 `context_compression_started/succeeded/failed` 的 payload.result 中新增：
1. `compressor_kind_requested`
2. `compressor_kind_applied`
3. `compressor_fallback_used`
4. `compressor_failure_reason`（若有）

示例：
1. 请求 `llm`，实际回退到 `rule`
2. 请求 `auto`，实际使用 `llm`

这能帮助观察：
1. LLM 压缩器命中率
2. 回退率
3. 是否存在高频 JSON 解析失败或一致性失败

## 9. 风险与缓解

风险 1：LLM 输出不稳定，导致压缩结构不可靠。  
缓解：
1. 严格 JSON schema 约束
2. 解析失败自动回退规则压缩
3. 一致性检查失败自动回退规则压缩

风险 2：压缩本身引入额外 token 成本。  
缓解：
1. 仅在 `midrun/finalize` 真实触发后调用
2. 只发送待压缩旧消息，而不是整个完整上下文
3. 控制 `compressor_llm_max_tokens`

风险 3：复用同一 model provider 会影响主流程推理时延。  
缓解：
1. V1 先接受同步调用成本
2. 若后续观察到明显时延问题，再考虑轻量模型或独立 provider

风险 4：测试脆弱性上升。  
缓解：
1. 默认 `auto`
2. Mock provider 下默认回退规则压缩
3. 为 LLM 压缩器新增单独测试，而不是改写所有旧测试

## 10. 测试计划

建议新增最小回归：
1. `llm_compressor_should_merge_summary_from_model_output`
2. `llm_compressor_should_fallback_to_rule_on_invalid_json`
3. `llm_compressor_should_fallback_to_rule_on_consistency_failure`
4. `compressor_factory_should_use_rule_when_kind_rule`
5. `compressor_factory_should_use_llm_when_kind_llm`
6. `compressor_factory_should_auto_fallback_for_mock_provider`
7. `sqlite_memory_store_should_accept_injected_compressor`
8. `runtime_should_wire_model_provider_into_memory_compressor`

保留现有测试不变：
1. 现有 `ContextCompressor` 相关压缩测试继续存在，用于验证规则回退路径
2. 现有 `event` 压缩测试不受影响

## 11. 落地步骤

1. 新增设计稿并评审。
2. 为 `RuntimeCompressionConfig` 增加压缩器配置。
3. 抽出压缩器工厂与 `LLMContextCompressor`。
4. 修改 `SQLiteMemoryStore` 支持注入压缩器。
5. 修改 `BaseAgent / SubAgent / create_runtime()` 的构造流程，先建 provider，再建 compressor，再建 store。
6. 补充 LLM 压缩器回归测试。
7. 更新 `README.md` 与 `doc/refer/*`。

## 12. 预期结果

落地后，Runtime memory 的 `midrun/finalize` 摘要链路将具备：
1. 更强的语义压缩能力
2. 更低的噪音比例
3. 更清晰的“目标 / 进展 / 下一步 / 约束 / 关键产物”表达
4. 仍然保留规则压缩作为稳定兜底

一句话总结：
1. 将当前 heuristic summary 升级为“可配置、可回退、默认自动选择”的 LLM 压缩器体系。

## 13. 实现状态

已按 V1 设计完成落地：
1. 新增 `LLMContextCompressor`，用于 `midrun/finalize` 的结构化摘要生成。
2. 新增 `build_context_compressor(...)`，支持 `auto / rule / llm` 三种模式。
3. `SQLiteMemoryStore` 支持注入压缩器，并在压缩结果中暴露 `compressor_kind_requested / compressor_kind_applied / compressor_fallback_used / compressor_failure_reason`。
4. `BaseAgent / SubAgent / create_runtime()` 已完成压缩器接线。
5. 已补充测试覆盖：
   - `auto` 在 `MockModelProvider` 下回退规则压缩
   - LLM 压缩成功写入 `v1_llm`
   - 非 JSON 输出回退规则压缩
   - 一致性校验失败回退规则压缩
