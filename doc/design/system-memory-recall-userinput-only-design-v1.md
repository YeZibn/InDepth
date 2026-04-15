# System Memory 差异需求讨论稿（Recall Strategy, V1）

更新时间：2026-04-14  
状态：Draft（讨论中）

## 1. 文档定位

本文件是**差异讨论稿（delta）**，仅记录相对基线方案的变更点。  
基线方案见：
- [system-memory-runtime-cycle-design-v1.md](/Users/yezibin/Project/InDepth/doc/design/system-memory-runtime-cycle-design-v1.md)

本稿不重复基线内容，避免两份文档混写。

## 2. 本次变更目标（仅召回）

目标：
1. 降低 `task_id` 命名噪声对召回结果的干扰。
2. 保持召回高精度优先，不追求召回量。
3. 维持现有事件闭环与可追踪性。

不在本稿讨论范围：
1. 不改 Runtime 会话记忆（`runtime_memory_*`）。
2. 不讨论 capture 路径。
3. 不讨论 run_end 强制沉淀机制。

## 3. 召回策略差异清单（相对基线）

1. `run_start` 召回仅使用 `user_input`
- 不使用 `task_id`
- 不使用 `stage` 过滤与 `stage` 打分加权
- recall query 只由 `user_input` token 生成

2. Top-K 与精度门槛保持（沿用基线）
- `Top-K <= 5`
- `min_score` 门槛保持启用（低分不注入）
- 未命中不阻塞主流程

3. 注入方式改为“轻注入”
- 每条只注入：`memory_id + recall_hint`
- 禁止整卡原文注入

4. 引入“内容概括字段”用于召回
- 新增字段：`recall_hint`
- 作为召回主语义入口，提升短输入场景命中质量
- 该字段直接用于启动轻注入（`memory_id + recall_hint`）

5. 新增完整记忆拉取工具
- 新 tool：`get_memory_card_by_id(memory_id)`
- 运行中若某条注入记忆被判断为关键，Agent 可按 id 拉取完整 memory card

## 4. 当前实现现状（用于对齐改造）

`SystemMemoryStore.search_cards()` 当前比较字段：
1. `title`
2. `recall_hint`
3. `domain`
4. `trigger_hint`
5. `tags_json`

当前行为：
1. 已不再按 `stage` 过滤。
2. 已不再使用 `stage` 打分加权。
3. 召回分数由文本相关性主导。

## 5. 讨论点（仅召回）

### 5.1 去掉 stage 的收益

1. 语义更贴近用户真实意图。
2. 避免 stage 识别误差造成漏召回。
3. 降低生命周期标签对语义匹配的硬约束。

### 5.2 去掉 stage 的风险

1. `user_input` 过短时，query 信息密度不足。
2. 跨阶段噪音可能上升（以前由 stage 约束拦截）。
3. 多轮任务中“后半段语义变化”仍可能需要后续增强（如二次召回）。

### 5.3 缓解建议

1. 对短输入启用兜底词策略（保留核心动词/对象词）。
2. 保留严格 `min_score`，宁可少召回。
3. 引入 `recall_hint` 字段作为高密度语义入口。
4. 先不引入中途自动二次召回，避免复杂度膨胀。

## 6. 召回模型方案（新增）

### 6.1 目标

在规则检索后增加轻量 LLM 重排（mini 模型），提升语义精度。

### 6.2 建议流程

1. 候选召回（SQLite）
- 使用 `user_input` 在 `title/recall_hint/domain/trigger_hint/tags` 做宽召回（例如 20 条）。

2. mini LLM 重排
- 输入：`user_input` + 每条卡片的 `title + recall_hint + trigger_hint`
- 输出：`relevance_score(0-1)` + `brief_reason`

3. 高精过滤与注入
- 取 Top-K（最多 5）
- 仅保留高于阈值的卡片注入 prompt

### 6.3 为什么先引入 recall_hint 再接 mini

1. 降低模型读取冗余字段成本。
2. 统一输入格式，便于可解释重排。
3. 未来可在无 LLM 模式下直接复用 recall_hint 做规则匹配。

### 6.4 title / recall_hint 生成逻辑（补充约束）

#### 6.4.1 title 生成目标

`title` 用于高信号检索，不用于记录运行上下文噪声；应表达“问题对象 + 关键动作/原则”。

建议规则：
1. 长度：建议 12-40 字（中文），不得超过 schema 上限。
2. 结构模板：`<问题对象/场景> + <关键动作/原则>`（可选附加 `<边界条件>`）。
3. 禁止包含：`task_id`、`run_id`、时间戳、"任务总结" 等流水线噪声词。
4. 同语义不同 run 生成结果应稳定（仅在语义变化时改写 title）。

示例：
1. 好：`支付重试前先校验幂等键`
2. 差：`任务 runtime_cli_xxx 总结`

#### 6.4.2 recall_hint 生成目标

`recall_hint` 用于启动轻注入，应直接给出“何时用 + 怎么做 + 注意什么”。

建议模板（四段）：
1. 问题：当前常见失败模式或目标。
2. 适用条件：在什么前提下可套用。
3. 建议动作：优先执行的 1-2 个关键动作。
4. 风险提示：误用后果或禁用边界。

建议规则：
1. 长度：存储 80-220 字；注入预览按 200 字截断。
2. 信息密度：至少包含“适用条件 + 建议动作”，禁止只写抽象口号。
3. 来源优先级：显式 `recall_hint` > legacy `summary` > 结构化字段组合生成。
4. 组合生成时优先取：`problem_pattern.symptoms[0]`、`constraints.applicable_if[0]`、`solution.steps[0]`、`anti_pattern.not_applicable_if[0]`，按模板拼接。

示例（推荐）：
`问题：支付重试导致重复扣款；适用：存在副作用写操作且可建立幂等键；动作：先写幂等记录再执行扣款；风险：未加唯一约束会在并发下重复扣款。`

#### 6.4.3 与当前实现差异

当前 fallback 仅由 `title + trigger_hint + first_step` 组合，缺少“适用条件/风险提示”维度。  
本稿建议将 fallback 升级为“四段模板组合”，并保留 200 字注入截断策略。

## 7. 完整记忆拉取工具（新增）

### 7.1 Tool 定义

`get_memory_card_by_id(memory_id: str, include_inactive: bool = false) -> Dict`

返回：
1. `success`
2. `card`（完整 memory card）
3. `not_found`（可选）

### 7.2 触发时机

1. run_start 轻注入后，Agent 识别某条记忆对当前决策关键。
2. 在执行过程中需要该条记忆的完整步骤、约束或证据时。

### 7.3 约束

1. 默认仅允许读取 `active` 且未过期卡片。
2. 单轮拉取次数建议限流（例如最多 3 次）。
3. 拉取失败不阻塞主流程。
4. 完整拉取应记录 retrieval 事件（`mode=full_fetch`）。

## 8. 召回事件与审计要求

1. 召回阶段事件链路：
- `memory_triggered`
- `memory_retrieved`
- `memory_decision_made`

2. 即使不使用 `task_id` 参与召回计算，事件中仍保留 `task_id/run_id` 作为审计主键。
3. 新 tool 完整拉取也应记入 retrieval 事件（建议附带 `mode=full_fetch`）。
4. 本稿不涉及 capture/finalize 事件语义变更。

## 9. 验收口径（仅召回）

1. 代码层：召回阶段不再读取 `task_id`/`stage` 参与过滤或打分。
2. 行为层：同一 `user_input` 在不同 `task_id` 下召回结果一致（在同库同数据前提下）。
3. 稳定性：召回异常/未命中不影响主任务执行。
4. 文档层：本稿只包含召回策略，无 capture/finalize 讨论内容。
5. 字段层：`recall_hint` 纳入召回输入与注入输出。
6. 工具层：支持按 `memory_id` 拉取完整记忆卡，并遵循 active/过期约束。
7. 生成层：`title` 不包含 task/run 噪声字段；`recall_hint` 满足“问题/条件/动作/风险”最小结构。

## 10. 默认决策（本稿建议落地值）

1. `min_score` 初始值：`0.65`
- 原因：维持“精确率优先”，降低跨场景噪音注入。

2. 新字段命名：`recall_hint`
- 原因：语义明确，直指“召回注入提示”用途。

3. `recall_hint` 约束与填充策略
- 长度：建议 80-200 字（中文）。
- 状态要求：`active` 必填，`draft` 可选。
- 模板：`问题 -> 适用条件 -> 建议动作 -> 风险提示`。

4. `title` 约束与填充策略
- 长度：建议 12-40 字（中文），表达“对象 + 动作/原则”。
- 禁止：`task_id/run_id/时间戳/任务总结` 等流程噪声词。
- 稳定性：同语义任务跨 run 应生成一致标题。

5. mini LLM 重排启用策略
- 默认：灰度开关启用（默认关闭）。
- 开关名建议：`ENABLE_MEMORY_RECALL_RERANKER`。
- 说明：先保留规则召回为主，逐步对比命中质量后再全量。

6. 极短输入兜底策略
- 默认开启轻量兜底扩词。
- 规则：当 `user_input` 提取 token < 2 时，补充固定通用词簇（如 `重试/失败/修复/回滚`）用于候选召回。

7. 完整记忆拉取工具
- 新增 `get_memory_card_by_id`，默认只读 active 且未过期。
- 记录 `full_fetch` retrieval 事件。

## 11. 落地顺序（建议）

1. Schema 与存储
- 为 `memory_card` 增加 `recall_hint` 字段（含迁移与回填策略）。

2. 召回检索
- 去除 `stage` 过滤与 `stage` 打分加权。
- 将 `recall_hint` 纳入检索字段。

3. 重排灰度
- 接入 mini LLM 重排链路，并受 `ENABLE_MEMORY_RECALL_RERANKER` 控制。

4. 新 tool 接入
- 增加 `get_memory_card_by_id` 并接入工具注册。

5. 指标观察
- 对比开启前后：命中率、采纳率、噪音率、注入条数。
