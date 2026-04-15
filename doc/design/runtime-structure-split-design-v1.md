# AgentRuntime 结构拆分设计方案（V1）

更新时间：2026-04-15  
状态：Implemented（已完成）

当前落地状态（2026-04-15）：
1. Phase 1 已落地：`runtime_utils.py` 下沉纯工具函数。
2. Phase 2 已落地：`verification_handoff.py` 拆分 handoff 构建与归一化逻辑。
3. Phase 3 已落地：`system_memory_lifecycle.py` 拆分 recall/finalize/metadata 生命周期逻辑。
4. Phase 4 已落地：`tool_execution.py` 拆分 tool 调用闭环与 capture 参数增强逻辑。

## 1. 背景与问题

当前 `app/core/runtime/agent_runtime.py` 约 1550+ 行，集中承载了多类职责：
1. Runtime 主循环与停止条件。
2. Native tool-calling 执行与失败聚合。
3. Verification handoff 构建与 LLM 生成。
4. System memory 启动召回与结束沉淀。
5. 各类通用工具函数（预览、JSON 解析、token 估算、文本规则判断）。

带来的问题：
1. 变更风险高：局部改动容易影响不相关逻辑。
2. 可测试性弱：难以对单一职责做隔离单测。
3. 阅读/评审成本高：主流程与策略细节交织。

## 2. 目标

1. 按职责拆分 `agent_runtime.py`，降低单文件复杂度。
2. 保持 `AgentRuntime` 对外行为与接口不变（兼容现有调用方与测试）。
3. 为后续扩展（如新 recall 策略、新 verifier handoff 规则）提供清晰挂载点。

## 3. 非目标

1. 不改 Runtime 协议（`run(...)` 输入输出语义不变）。
2. 不改现有 event schema 与 event_type 命名。
3. 不在本次引入新的功能开关或策略变更。

## 4. 拆分原则

1. 主流程最小化：`AgentRuntime.run()` 仅保留编排逻辑。
2. 策略下沉：memory/verification/tool-call 细节下沉到独立模块。
3. 兼容优先：先“搬运重组”，后“语义优化”。
4. 可回滚：每阶段可独立回滚到单文件实现。

## 5. 目标目录结构（V1）

建议在 `app/core/runtime/` 下新增子模块：

1. `agent_runtime.py`
- 保留 `AgentRuntime` 类与对外入口。
- 只保留主循环、状态机骨架、依赖装配。

2. `tool_execution.py`
- 负责 tool_calls 执行链路：参数解析、事件上报、结果回填、失败聚合。
- 包含 `capture_runtime_memory_candidate` 参数增强逻辑。

3. `verification_handoff.py`
- 负责 fallback handoff 构造、LLM 生成、规范化与配置构建。

4. `system_memory_lifecycle.py`
- 负责 run-start recall 注入、run-end finalize 沉淀。
- 包含 recall rerank、memory block 渲染、memory metadata 生成。

5. `runtime_utils.py`
- 放置纯工具函数：`_preview`、`_parse_json_dict`、`_slug`、token 估算等。

> 说明：V1 可以先用“模块级函数 + 轻量 context 参数”实现，避免一次性引入过多类抽象。

## 6. 职责映射（从当前方法迁移）

### 6.1 保留在 `AgentRuntime`
1. `run(...)` 主循环。
2. `_build_system_prompt(...)`（或转为 utils 后由 run 调用）。
3. Runtime 级状态字段维护（`last_runtime_state` 等）。

### 6.2 迁移到 `tool_execution.py`
1. `_handle_native_tool_calls(...)`
2. `_enrich_capture_memory_tool_args(...)`

### 6.3 迁移到 `verification_handoff.py`
1. `_build_verification_handoff(...)`
2. `_build_rule_verification_handoff(...)`
3. `_generate_verification_handoff_llm(...)`
4. `_normalize_verification_handoff(...)`
5. `_normalize_handoff_str_list(...)`
6. `_normalize_expected_artifacts(...)`
7. `_normalize_key_tool_results(...)`
8. `_clamp_float(...)`
9. `_build_verification_handoff_config(...)`

### 6.4 迁移到 `system_memory_lifecycle.py`
1. `_inject_system_memory_recall(...)`
2. `_build_recall_query(...)`
3. `_render_memory_recall_block(...)`
4. `_rerank_memory_candidates_llm(...)`
5. `_finalize_task_memory(...)`
6. `_generate_memory_card_metadata_llm(...)`
7. `_build_memory_reranker_config(...)`
8. `_build_memory_metadata_config(...)`
9. `_build_semantic_memory_title(...)`
10. `_extract_title_topic(...)`

### 6.5 迁移到 `runtime_utils.py`
1. `_parse_json_dict(...)`
2. `_preview(...)`
3. `_preview_json(...)`
4. `_estimate_context_tokens(...)`
5. `_estimate_context_usage(...)`
6. `_is_clarification_request(...)`
7. `_extract_missing_info_hints(...)`
8. `_extract_finish_reason_and_message(...)`
9. `_slug(...)`

## 7. 依赖组织方式（避免循环引用）

建议方式：
1. 新模块不 import `AgentRuntime`。
2. 通过“显式参数注入”传递所需依赖：
- `model_provider`
- `tool_registry`
- `memory_store`
- `system_memory_store`
- `trace` 回调
- `emit_event` 函数（可直接复用现有）

3. `AgentRuntime` 作为 orchestrator 调用子模块函数，统一维护运行态。

## 8. 实施计划（分阶段）

### Phase 1：工具函数下沉（低风险）
1. 新建 `runtime_utils.py`，迁移纯函数。
2. `AgentRuntime` 改为调用 utils。
3. 跑全量 runtime 相关测试，确保行为不变。

### Phase 2：verification handoff 拆分
1. 新建 `verification_handoff.py`。
2. 将 handoff 构造/归一化/LLM 生成迁移。
3. 保持 `AgentRuntime` 调用入口不变。

### Phase 3：system memory 生命周期拆分
1. 新建 `system_memory_lifecycle.py`。
2. 迁移 recall/finalize/metadata 逻辑。
3. 对 recall 与 finalize 增补回归测试。

### Phase 4：tool execution 拆分
1. 新建 `tool_execution.py`。
2. 迁移 tool 调用闭环。
3. 完成后 `agent_runtime.py` 重点保留主循环与状态机。

## 9. 验收标准

1. 行为兼容：现有测试全部通过（特别是 `tests/test_runtime_*.py`）。
2. 结构目标：`agent_runtime.py` 行数显著下降（建议 < 700 行）。
3. 职责边界清晰：主循环、memory、verification、tool execution 可独立阅读。
4. 无回归：
- clarification suspend/resume 行为一致
- 事件链路顺序一致
- memory recall/finalize 结果一致

## 10. 风险与缓解

风险：
1. 拆分后参数传递增多，易漏传上下文。
2. 事件字段或 stop_reason 在迁移中发生细微偏差。
3. 局部方法移动后 mock/patch 路径变化导致测试脆弱。

缓解：
1. 先迁纯函数，再迁有副作用逻辑。
2. 为关键链路加“等价性断言”测试（event_type、runtime_state、stop_reason）。
3. 每个 Phase 单独提交，确保可逐步回滚。

## 11. 待确认决策

1. V1 是否采用“函数式模块”还是直接引入 `RuntimeServices` 类封装依赖。
2. `run(...)` 内部是否保留私有 helper（如 `_build_handoff_if_needed`）还是统一放到 orchestrator helper 文件。
3. `runtime_utils.py` 是否拆为 `text_utils` 与 `json_utils`（V1 建议先不拆）。
