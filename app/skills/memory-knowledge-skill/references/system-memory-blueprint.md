# System Memory Blueprint (V1)

本目录描述当前已经落地的轻量 system memory 方案，而不是早期的候补记忆或重字段卡片设计。

## 目录

- `memory_card.schema.json`: 当前 `memory_card` 轻量数据契约
- `memory_card.example.json`: 当前卡片样例
- `metrics_sqlite.sql`: 基于现有 SQLite 表结构的指标 SQL

## 1) 当前设计目标

当前 V1 设计优先解决三件事：

1. 让正式经验只在任务结束后沉淀
2. 让 verification 与 memory 共用同一份 handoff 事实源
3. 让 `memory_card` 保持轻量，便于后续接向量索引

## 2) 当前运行策略

1. 任务开始时做 system memory recall
2. recall 默认只轻量注入：
   - `memory_id`
   - `recall_hint`
3. 如有需要，再按 id 拉取完整卡片
4. 任务结束时，Runtime 显式执行：
   - `finalizing(answer)`
   - `finalizing(handoff)`
5. 正式 memory 仅从 `verification_handoff.memory_seed` 派生

## 3) 当前卡片模型

`memory_card` 只保留这些字段：

1. `id`
2. `title`
3. `recall_hint`
4. `content`
5. `status`
6. `updated_at`
7. `expire_at`

这表示当前系统不再把 `memory_type`、`domain`、`scenario_stage`、`payload_json` 作为主表必备字段。

## 4) 当前事实源

正式 memory 的唯一主来源是：

```json
{
  "verification_handoff": {
    "memory_seed": {
      "title": "string",
      "recall_hint": "string",
      "content": "string"
    }
  }
}
```

如果 `memory_seed` 为空，当前 run 不会生成正式 memory card。

## 5) 当前代码接入点

- 结构化存储：`app/core/memory/system_memory_store.py`
- recall 生命周期：`app/core/runtime/system_memory_lifecycle.py`
- handoff 生成：`app/eval/verification_handoff_service.py`
- finalizing 编排：`app/core/runtime/agent_runtime.py`
- CLI：`app/skills/memory-knowledge-skill/scripts/memory_card_cli.py`
- 事件落库：`app/observability/store.py::SystemMemoryEventStore`

## 6) 观测闭环

当前保留三类 system memory 事件：

1. `memory_triggered`
2. `memory_retrieved`
3. `memory_decision_made`

这些事件主要用于：

1. recall 链路观测
2. 持久化链路审计
3. KPI 与 postmortem 分析

## 7) 现阶段不包含什么

当前 V1 明确不包含：

1. 默认主链路中的运行中候补记忆写入
2. 向量检索
3. 重字段 memory_card 主表
4. 复杂的 handoff context builder

## 8) 推荐治理动作

1. 持续补充高质量 `memory_card` 样例
2. 审查过期或低价值卡片
3. 跟踪 recall 命中率、采纳率和噪音率
4. 后续如接向量索引，优先复用当前轻量卡片作为索引输入
