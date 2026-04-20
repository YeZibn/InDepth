# System Memory Runtime Cycle 设计方案（V1）

更新时间：2026-04-14  
状态：Superseded（已过时，保留作历史记录）

> 注意：本文档描述的是早期方案，包含“运行中 capture 候选记忆”“旧版检索/卡片设计”等已被替换的内容。
> 当前实现请以 [`finalizing-handoff-driven-memory-design-v1.md`](/Users/yezibin/Project/InDepth/doc/design/finalizing-handoff-driven-memory-design-v1.md) 为准。

当前落地状态（2026-04-14）：
1. Phase 1 已落地：run 开始召回注入 + run 结束强制沉淀。
2. run 中 capture 继续采用 tool 显式调用（`capture_runtime_memory_candidate`）。

## 1. 背景与目标

当前 `memory_card` 主要通过工具/skill 触发，Runtime 结束阶段有强制沉淀，但“开始召回、中途捕获、结束沉淀”的生命周期仍不完整。

本方案目标：
1. 不改动 Runtime 会话记忆（`runtime_memory_*`、`messages/summaries`）。
2. 仅重构 System Memory（`db/system_memory.db`）在 Runtime 中的触发与注入策略。
3. 建立统一三段闭环：
   - run 开始：高精度召回（最多 5 条）并注入 prompt
   - run 过程中：按信号捕获候选记忆
   - run 结束：强制总结沉淀任务记忆

## 2. 范围与非目标

范围内：
1. `SystemMemoryStore` 的检索/写入调用时机重构。
2. `AgentRuntime` 内新增 system memory 生命周期钩子。
3. 记忆事件三连（`memory_triggered/retrieved/decision_made`）语义收敛与持续落库。

非目标：
1. 不调整 `SQLiteMemoryStore` 数据结构与压缩策略。
2. 不替换 `memory_card` schema。
3. 不依赖 skill 才能触发主链路（skill 可保留为人工入口）。
4. 不将 run 中 capture 内聚为 Runtime 隐式自动写卡。

## 3. 设计原则

1. 精确率优先于召回率：宁缺毋滥。
2. 未命中不阻塞主执行：召回失败时直接继续 run。
3. 记忆注入必须摘要化：禁止整卡原文大段注入。
4. 生命周期可审计：每个阶段都有事件记录和可解释决策。

## 4. 运行时三段流程

### 4.1 阶段 A：run 开始召回（Top-K <= 5）

触发时机：
1. `task_started` 后、首次模型请求前。

检索策略（当前实现）：
1. 仅检索 `status='active'` 且未过期卡片作为候选池。
2. 候选池最终由 LLM（mini）基于 `user_input + title` 进行 Top-K 判定。
3. 规则检索不再承担最终决策职责。
4. 最多注入 5 条；可为 0 条（允许空召回）。

注入方式：
1. 生成“系统记忆召回轻注入块”注入 system prompt 后缀。
2. 每条卡仅保留：`memory_id + recall_hint`。
3. 统一 token 预算上限（避免挤压主上下文）。

事件：
1. `memory_triggered`（source=`runtime_start_recall`）。
2. `memory_retrieved`（每条命中卡 1 条，含 `memory_id/score`）。
3. `memory_decision_made`（`accepted/rejected/skipped` + reason）。

### 4.2 阶段 B：run 过程中捕获（capture）

触发时机（任一满足）：
1. Agent 在执行中显式判断存在可复用经验并调用 capture tool。
2. 关键错误或失败重试后出现稳定修复路径。
3. 明确形成“可复用步骤 + 适用边界 + 风险信号”。
4. 高价值决策点（成本高、风险高、可迁移）。

捕获策略：
1. 默认写入 `draft` 候选卡（避免直接污染 `active` 集）。
2. 对同任务同标题进行去重 upsert，防止重复卡爆炸。
3. 明确记录 evidence（来源 run/task、验证时间）。
4. 保持 tool 显式调用语义，Runtime 不做隐式自动 capture。

事件：
1. `memory_triggered`（source=`runtime_capture`）。
2. `memory_retrieved`（指向写入/更新后的候选卡，可用固定高分）。
3. `memory_decision_made`（`captured` 或 `ignored` + reason）。

### 4.3 阶段 C：run 结束强制沉淀

触发时机：
1. `task_finished` 流程中必执行（现有能力保留并标准化）。

沉淀策略：
1. 生成 `postmortem` 类型任务结果卡（`mem_task_*`）。
2. 根据 `runtime_status` 设置风险等级与 confidence。
3. 填充最小闭环字段：问题概述、复用建议、失败信号、证据来源。

事件：
1. `memory_triggered`（source=`runtime_forced_finalize`）。
2. `memory_retrieved`（关联最终卡，score=1.0）。
3. `memory_decision_made`（`accepted`，reason=`framework forced finalization`）。

## 5. 排序与阈值建议（精确率优先）

建议排序策略：
1. 候选召回：active + 未过期。
2. 最终排序：LLM 语义打分（`user_input + title`）。

建议门槛：
1. `recall_top_k = 5`
2. `recall_min_score = 0.65`（低于阈值不注入）
3. `injection_token_budget`：单次注入固定预算（建议 300-500 tokens）

## 6. 与现有架构的衔接

新增组件建议：
1. `RuntimeSystemMemoryManager`（新）
   - `recall_for_run_start(...)`
   - `finalize_on_run_end(...)`
2. `AgentRuntime` 仅负责 `run_start` 与 `run_end` 两个生命周期点调用 manager。
3. `SystemMemoryStore` 继续承担数据 CRUD，不承担策略判定。

保留组件：
1. `capture_runtime_memory_candidate` tool：作为 run 中 capture 的唯一主路径。
2. `search_memory_cards` tool：保留为人工检索/调试入口（title-only 规则检索）。
3. `get_memory_card_by_id` tool：按 `memory_id` 拉取完整记忆卡。
4. `memory_card_cli.py`：保留为离线治理入口。

## 7. 风险与缓解

风险：
1. 启动注入误召回导致模型偏航。
2. 中途 capture 过多造成低质量草稿堆积。
3. 事件三连语义不一致导致指标失真。

缓解：
1. 严格 `min_score` + LLM title 判定阈值控制。
2. capture 加去重与限流（每 run 最多 N 条候选）。
3. 统一事件 reason 枚举并固化 source 字段规范。

## 8. 实施计划（建议两阶段）

### Phase 1（最小可用）
1. 在 Runtime 开始阶段接入召回与摘要注入（Top-K<=5 + min_score）。
2. 保留现有结束沉淀逻辑，补齐统一事件 source/reason。
3. 新增集成测试：未命中不阻塞、命中注入格式、三连事件完整性。

### Phase 2（质量提升）
1. 保持 capture tool 路径，补充参数规范与触发准则（减少随意调用）。
2. 增加 capture 去重、每 run 配额、低价值过滤。
3. 增加治理指标：命中率、采纳率、噪音率、新鲜度。

## 9. 验收标准

1. `runtime_memory_*` 库结构和行为无回归。
2. `system_memory.db` 能稳定产生三段事件闭环。
3. 启动召回注入最多 5 条，且低分卡不注入。
4. 任务结束必有 `postmortem` 记忆卡沉淀。
5. 任一 memory 异常不影响主任务完成。

## 10. 待确认决策

1. stage 不匹配时是否允许降级召回（默认否）。
2. `recall_min_score` 初始值是否采用 0.65。
3. run 中 capture 的单次/单任务配额上限。
4. draft -> active 的治理流程是否引入人工审核门禁。
