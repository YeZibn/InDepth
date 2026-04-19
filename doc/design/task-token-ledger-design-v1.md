# Task Token Ledger 设计稿（V1）

更新时间：2026-04-19  
状态：V1 已落地首版

## 1. 背景与问题

当前 Runtime 已具备两类 token 相关能力：
1. step 级请求前 token 统计：在每个 step 的 `model_provider.generate(...)` 前，按当前 request 的 `messages` 计算输入 token，并单独统计 `tools` schema token。
2. task 级上下文压缩：按当前 `task_id` 仍保留在上下文中的消息集合计算 token，并在接近 `compression_trigger_window_tokens` 时触发压缩。

但系统仍缺少一类能力：
1. 无法直接得到“一个 task 到目前为止总共消耗了多少 token”。
2. 无法稳定回答“这个 task 的 token 是在哪几个 step 明显上涨的”。
3. 当前 observability 里虽有 step 级事件，但没有专门的 token ledger 存储与 task 级累计结果。

当前还存在两个问题：
1. 压缩算法仍主要从 message 集合反推“保留多少历史”，语义上不够贴近 step。
2. “当前 task 活跃上下文 token”与“task 累计 token”还没有被明确拆成两套数据模型。

因此，需要补一条独立的 token ledger 链路，用于记录 task 内每个 step 的 token 明细，并聚合出 task 级总 token；同时为后续按 step 进行压缩决策提供事实基础。

## 2. 目标

V1 目标：
1. 为每个 task 记录 step 级 token 明细。
2. 基于 step 明细聚合出 task 级 token 总量。
3. 使用 SQLite 落盘，支持后续查询与统计。
4. 明确 `turn = step`，后续压缩决策以 step 为最小保留单元。
5. 采用结构化压缩预算：`20%` 活跃输入预算 + `25%` 摘要预算。
6. 明确区分“当前活跃上下文 token”和“task 累计 token”。

## 3. 非目标

V1 不做：
1. 不引入 run 级聚合。
2. 不在本稿中实现完整的 step-based compaction 重构。
3. 不改变 `tiktoken` 计数口径。
4. 不实现复杂 BI/报表能力。
5. 不把 token ledger 混入 `events.jsonl` 作为唯一事实源。

说明：
1. `run_id` 仍会作为 step 明细的归属字段保留下来，便于追溯。
2. 但聚合层不单独维护 run 级统计，只维护 task 级累计结果。

## 4. 设计原则

1. 压缩视角与成本视角分离。
2. `turn = step`，step 是最小记录粒度，也是后续压缩的最小保留单元。
3. task 是聚合粒度，不增加 run 中间层。
4. SQLite 作为事实存储，避免仅靠事件流回放计算。
5. request 观测与 step 压缩预算必须分成两套口径，不能混算。

## 5. 核心概念

### 5.1 三类 token 语义

1. `current_step_request_tokens`
- 含义：当前 step 真正要发给模型的 request token
- 组成：`request_messages_tokens + tools_tokens + reserved_output_tokens`
- 用途：step 级观测与窗口保护

2. `step_input_tokens`
- 含义：某个 step 自身携带的消息 token，只统计该 step 归属的 message 批次
- 组成：该 step 下 user / assistant / tool message 的可加总 token，不含 `tools` schema，也不含固定注入项
- 用途：后续按 step 累计 `20%` 活跃保留预算

3. `current_task_context_tokens`
- 含义：当前 task 仍保留在上下文里的 token
- 用途：压缩触发与上下文安全控制

4. `task_cumulative_tokens`
- 含义：一个 task 从开始到现在所有 step 累积消耗的 token
- 用途：成本统计与任务画像

### 5.2 `turn = step`

在本稿中统一采用：
1. `turn` 不再指 message 分段或 user 边界分段
2. `turn = step`
3. 每个 step 是一次独立的模型请求单元，也是后续压缩时的最小保留单元

因此：
1. “保留多少轮” = “保留多少个 step”
2. token ledger 的 step 明细天然就是未来压缩算法的事实输入

### 5.2 为什么不需要 run 级聚合

当前方案判断：
1. 压缩策略是以 `task_id` 为上下文主键，不以 `run_id` 为主键。
2. 业务目标是统计“一个 task 的总 token”，而不是比较 run 之间的 token。
3. step 明细中已经带 `run_id`，后续若需要按 run 回溯，仍可在查询层完成。

因此，V1 只保留：
1. step 明细
2. task 聚合

而不落单独的 run summary。

### 5.3 结构化压缩预算

当前认可的压缩预算语义为：
1. 总压缩目标仍为 `compression_trigger_window_tokens * 0.45`
2. 其中拆成两部分：
   - `live_budget_ratio = 0.20`
   - `summary_budget_ratio = 0.25`

也就是：
1. **活跃输入预算（20%）**
   - 用于容纳：
     - 固定注入项（system / skill / recall / prepare 注入 / 当前 request 必需外壳）
     - 仍保留原文的最近 step
2. **摘要预算（25%）**
   - 用于容纳被折叠历史生成的新 summary

以默认窗口为例：
1. `compression_trigger_window_tokens = 120000`
2. 活跃输入预算：`120000 * 0.20 = 24000`
3. 摘要预算：`120000 * 0.25 = 30000`
4. 总压缩后预算：`54000`

补充说明：
1. 活跃输入预算中的固定注入项不可压缩，应先真实计算。
2. 活跃 step 可用预算 = 活跃输入预算 - 固定注入项 token。
3. 被保留 step 的预算累计，直接使用每个 step 的 `step_input_tokens` 求和。
3. 摘要必须受 `summary_budget` 上限约束，避免“历史虽被折叠但 summary 膨胀”。

## 6. 数据模型

### 6.1 Step 明细表

建议新增表：
1. `task_token_step`

字段建议：

| 字段 | 类型 | 说明 |
|------|------|------|
| `task_id` | TEXT | task 主键维度 |
| `run_id` | TEXT | 归属 run，用于追溯 |
| `step` | INTEGER | step 序号 |
| `model` | TEXT | 本 step 使用的模型 |
| `encoding` | TEXT | `tiktoken` encoding 名称 |
| `token_counter_kind` | TEXT | 当前固定为 `tiktoken` |
| `messages_tokens` | INTEGER | 当前 request 的 `messages` token |
| `tools_tokens` | INTEGER | 当前 request 的 tools schema token |
| `step_input_tokens` | INTEGER | 当前 step 自身 message 批次 token |
| `input_tokens` | INTEGER | 当前 request 输入 token，当前等于 `messages_tokens` |
| `reserved_output_tokens` | INTEGER | 本 step 预留输出预算 |
| `total_window_claim_tokens` | INTEGER | `input_tokens + tools_tokens + reserved_output_tokens` |
| `context_usage_ratio` | REAL | `input_tokens / compression_trigger_window_tokens` |
| `compression_trigger_window_tokens` | INTEGER | 本 step 触发预算 |
| `model_context_window_tokens` | INTEGER | 本 step 模型理论窗口 |
| `created_at` | TEXT | 记录时间 |

主键建议：
1. `(task_id, run_id, step)`

原因：
1. step 在同一个 task 内未必全局唯一
2. 同一个 task 可能存在多个 run 的 step=1

### 6.2 Task 聚合表

建议新增表：
1. `task_token_summary`

字段建议：

| 字段 | 类型 | 说明 |
|------|------|------|
| `task_id` | TEXT | 主键 |
| `total_step_input_tokens` | INTEGER | task 按 step 聚合的累计输入 token |
| `total_input_tokens` | INTEGER | task 累计 request 输入 token |
| `total_reserved_output_tokens` | INTEGER | task 累计预留输出 |
| `total_window_claim_tokens` | INTEGER | task 累计窗口申领总量 |
| `peak_step_input_tokens` | INTEGER | 单 step 最大 `step_input_tokens` |
| `peak_input_tokens` | INTEGER | 单 step 最大 request 输入 token |
| `peak_total_window_claim_tokens` | INTEGER | 单 step 最大窗口申领 |
| `step_count` | INTEGER | task 累计 step 数 |
| `last_run_id` | TEXT | 最近一次写入来源 run |
| `last_step` | INTEGER | 最近一次写入来源 step |
| `updated_at` | TEXT | 更新时间 |

说明：
1. task 聚合只存聚合结果，不存每 step 数组。
2. step 数组语义由 `task_token_step` 表承担。
3. 后续若要做 step-based compaction，可基于该表直接决定“保留哪些 step”。

## 7. 写入时机

### 7.1 写入入口

建议入口：
1. `AgentRuntime.run()`

具体时机：
1. 在每个 step 中，完成 `request_metrics = self._build_request_token_metrics(...)`
2. 发出 `model_request_started` 事件后，先写入 request 快照
3. step 完成后，再用同一行 upsert 补写 `step_input_tokens`
4. 同步更新 `task_token_summary`
5. 然后进入下一 step / 收尾

选择该时机的原因：
1. request 级观测与真实请求一一对应
2. step 自身 token 只有在该 step message 批次确定后才能精确补写
3. 即使模型请求失败，请求快照仍已记录；若 step 自身没有新增 message，则 `step_input_tokens` 可为 0

### 7.2 与压缩的关系

V1 中，token ledger 先承担事实记录职责：
1. request 快照 token 落盘
2. step 自身 token 落盘
3. task 级累计 token 聚合落盘

后续压缩算法可基于该 ledger 演进为：
1. 从最新 step 往前累计活跃 step token
2. 在 `live_budget` 内决定保留多少 step
3. 对超出的更早 step 生成一次 summary
4. 约束该 summary 不超过 `summary_budget`

也就是说：
1. 当前稿件先建设 ledger
2. 压缩策略后续再切到 ledger 驱动

### 7.3 Upsert 规则

step 明细写入：
1. 若 `(task_id, run_id, step)` 不存在，则插入
2. 若已存在，则覆盖更新当前快照

task 聚合写入：
1. 每次 step 写入后，增量更新
2. 更新逻辑：
   - `total_step_input_tokens += step_input_tokens`
   - `total_input_tokens += input_tokens`
   - `total_reserved_output_tokens += reserved_output_tokens`
   - `total_window_claim_tokens += total_window_claim_tokens`
   - `peak_step_input_tokens = max(old, step_input_tokens)`
   - `peak_input_tokens = max(old, input_tokens)`
   - `peak_total_window_claim_tokens = max(old, total_window_claim_tokens)`
   - `step_count += 1`

补充：
1. 若担心重复写入同一 step 导致累计翻倍，可先检查 step 记录是否已存在。
2. 更稳妥做法是：
   - 先读旧 step
   - 计算 delta
   - 再更新 summary

## 8. 压缩计算口径（后续演进目标）

### 8.1 压缩判断算什么 token

压缩相关计算不应看 task 累计 token，而应看：
1. **下一次真实请求输入 token**

即：
1. 当前 request 若不压缩时的 `before_request_input_tokens`
2. 压缩后重新构造请求得到的 `after_request_input_tokens`

其中：
1. `before_request_input_tokens` 用于判断是否接近窗口
2. `after_request_input_tokens` 用于验证压缩是否达到预算目标

### 8.2 保留多少 step 怎么算

在 `turn = step` 的定义下：
1. 不再按 message-turn 或 user-turn 决定 cut 点
2. 而是按 step 作为保留单元

计算思路：
1. 先计算固定注入项 token
2. 得到 `available_live_step_budget = live_budget - injected_tokens`
3. 从最新 step 往前累计 step token
4. 直到接近 `available_live_step_budget`
5. 保留这些最新 step
6. 更早 step 进入待摘要集合

### 8.3 是否为多个候选集合多次生成 summary

结论：
1. 不应为多个候选集合反复生成 summary
2. 正确顺序应为：
   - 先选定保留 step 集合
   - 再对被折叠集合生成一次 summary

即：
1. 候选评估阶段只做 token 预算计算
2. 最终确定 cut 后只生成一次 summary
3. 仅当生成后重算仍超预算时，才进入下一轮压缩

## 9. 查询语义

### 9.1 查询单个 task 的累计 token

读取：
1. `SELECT * FROM task_token_summary WHERE task_id = ?`

可直接得到：
1. task 总输入 token
2. task 总窗口申领 token
3. 最大 step token
4. step 总数

### 9.2 查询单个 task 的 step 轨迹

读取：
1. `SELECT * FROM task_token_step WHERE task_id = ? ORDER BY created_at ASC`

可直接得到：
1. 每一步 token 明细
2. token 峰值在哪一步出现
3. 哪一步 tools schema 开销异常高

### 9.3 为什么不依赖 events.jsonl 聚合

原因：
1. JSONL 更适合观测回放，不适合频繁查询累计值。
2. 基于事件回放算 task 总 token 成本高，且容易受日志清理影响。
3. SQLite 更适合作为 token ledger 的稳定事实表。

## 10. 模块划分

建议新增：
1. `app/core/runtime/task_token_store.py`

职责：
1. 初始化 `task_token_step` / `task_token_summary`
2. 提供 `record_step_metrics(...)`
3. 提供 `get_task_token_summary(task_id)`
4. 提供 `list_task_token_steps(task_id)`

`AgentRuntime` 职责：
1. 负责收集 step token metrics
2. 调用 `TaskTokenStore.record_step_metrics(...)`

这样分工后：
1. `AgentRuntime` 仍负责运行时编排
2. token ledger 的持久化逻辑独立封装

## 11. 可观测性关系

当前 `model_request_started` 事件继续保留：
1. 它是 step token metrics 的观测出口
2. SQLite ledger 是结构化事实存储

两者关系：
1. `model_request_started`：面向 request 级 observability
2. `task_token_step / task_token_summary`：面向 step 自身 token 累计统计和查询

因此，V1 采用“双写”：
1. 发事件
2. 写 SQLite

## 12. 风险与缓解

1. 同一 step 重复写入导致 task summary 重复累计
- 缓解：summary 更新前先读取旧 step 记录，按 delta 更新

2. token ledger 写入失败影响主流程
- 缓解：建议与 observability 一样，ledger 写入失败不阻断模型请求主流程，但应记录错误事件或 trace

3. SQLite 表持续增长
- 缓解：step 表按 task 查询为主，增长可接受；后续可再设计归档策略

4. 用户误把 task 累计 token 当成当前上下文 token
- 缓解：文档与字段命名中明确区分：
  - `input_tokens`
  - `current_task_context_tokens`
  - `total_input_tokens`

5. 活跃 step 与固定注入项未分开，导致 `20% live` 预算被误用
- 缓解：压缩实现时必须先单独统计固定注入项 token，再给 step 分配剩余 live budget

6. 为多个候选集合反复生成 summary，造成 token 波动与成本抖动
- 缓解：候选阶段不生成 summary，只在 cut 确定后生成一次

## 13. 测试计划

新增最小回归集：
1. `task_token_store_records_step_metrics`
2. `task_token_store_updates_task_summary`
3. `task_token_store_uses_delta_when_rewriting_same_step`
4. `agent_runtime_writes_task_token_step_before_model_generate`
5. `task_token_summary_aggregates_multiple_runs_under_same_task`
6. `step_based_compaction_budget_reserves_25_percent_for_live_context`
7. `step_based_compaction_budget_reserves_15_percent_for_summary`
8. `compaction_selects_steps_before_generating_summary`

## 14. 落地步骤

1. 新增 `TaskTokenStore`
2. 定义 SQLite schema
3. 在 `AgentRuntime` 的 step 请求前接入写入
4. 为同一 step 重写实现 delta 更新
5. 增加测试
6. 更新 refer 文档
7. 后续再基于 ledger 重构 step-based compaction

## 15. 预期收益

1. 可以直接回答“这个 task 总共用了多少 token”
2. 可以定位“哪个 step 导致 token 激增”
3. 为“按 step 保留、按 20%/25% 结构化预算压缩”提供事实基础
4. 不混淆上下文安全与成本累计
5. 为后续 task 成本画像、配额统计和性能分析提供稳定基础
