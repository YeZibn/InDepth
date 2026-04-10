# System Memory Blueprint (PoC)

本目录用于把经验沉淀从“文档库存”升级为“可检索 + 可触发 + 可评估收益”的系统记忆。

## 目录

- `memory_card.schema.json`: 经验卡统一数据契约（可校验）
- `memory_card.example.json`: 经验卡实例（可作为录入模板）
- `metrics_sqlite.sql`: SQLite 版指标 SQL（可直接跑在 `db/system_memory.db`）

## 1) 信息模型落地

经验卡采用结构化字段，最关键的是以下 6 组：

1. 检索字段：`domain/tags/scenario/problem_pattern`
2. 触发字段：`scenario.stage/problem_pattern.risk_level`
3. 执行字段：`solution.steps/constraints/anti_pattern`
4. 证据字段：`evidence.source_links/verified_at`
5. 治理字段：`owner/lifecycle`
6. 收益字段：`impact.baseline/impact.after`

## 2) 运行策略（当前）

1. 任务开始不做记忆注入。
2. 运行中由 `memory-knowledge-skill` 自主捕获候选记忆（`capture_runtime_memory_candidate`）。
3. 任务结束由框架强制沉淀最终任务记忆。

## 3) 指标闭环落地

先跑 6 个过程指标，再看 3 个北极星指标：

- 过程指标：命中率、采纳率、噪音率、新鲜度、覆盖率、有效率
- 北极星指标：缺陷率下降、交付周期下降、重复事故率下降

`metrics_sqlite.sql` 提供了可直接执行的查询模板。

## 4) 与现有仓库对齐建议

你当前项目已有：

- 结构化记忆存储与检索：`app/core/memory/system_memory_store.py`
- 可观测事件：`app/observability`

建议的最小改造路径：

1. 以 `memory_card` 作为唯一运行态记忆载体。
2. 在 `app/observability/events.py` 增加三类事件：`memory_triggered`、`memory_retrieved`、`memory_decision_made`。
3. 运行中通过 skill 工具捕获候选记忆并记录事件。
4. 每周跑一次 `metrics_sqlite.sql` 并处理低价值/过期记忆。

当前代码接入（已实现）：

- 结构化存储：`app/core/memory/system_memory_store.py`（`memory_card` SQLite CRUD + 检索）
- 事件落库：`app/observability/store.py::SystemMemoryEventStore`
- 主链路沉淀：`app/core/runtime/agent_runtime.py`（任务结束强制沉淀）
- CLI：`app/skills/memory-knowledge-skill/scripts/memory_card_cli.py`
- Runtime 获取：`app/skills/memory-knowledge-skill/SKILL.md` + `app/tool/runtime_memory_harvest_tool.py`（运行中自主捕获候选记忆）

Runtime 规则（当前）：

- 任务开始不做记忆注入
- 运行中由 skill 自主决策是否捕获候选记忆
- 任务结束由框架强制沉淀最终任务记忆

## 5) 本周启动清单

1. 补充 10 条高质量 `memory_card` 样例。
2. 在真实任务中验证候选捕获 skill 的触发质量。
3. 每周审查一次 draft 记忆并升级/淘汰。
4. 运行 `metrics_sqlite.sql` 并追踪噪音率与采纳率。
