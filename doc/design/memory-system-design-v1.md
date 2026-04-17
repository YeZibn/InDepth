# InDepth Memory V1 设计归档

更新时间：2026-04-12
状态：V1 已落地（可继续迭代）

> 说明：本文件为历史设计归档，具体实现与默认值以 `doc/refer/config-reference.md`、`doc/refer/runtime-reference.md` 为准。

## 1. 目标

将记忆压缩从“仅 run 结束后触发”升级为“run 内可控触发 + run 后归档”，并保证：
1. 关键约束不丢失（L0 不可压缩）。
2. 压缩过程可观测、可回滚、可回归。
3. 长任务上下文长度可控，降低 length 风险与成本。

## 2. 分层模型（L0-L3）

1. L0：不可压缩核心约束
- system 指令
- 用户硬约束（必须/禁止/截止时间/权限）
- 安全审批相关规则

2. L1：近期高相关消息
- 最近 N 条对话/工具结果（默认保留）

3. L2：历史过程
- 决策、产物、进展等结构化摘要

4. L3：低价值噪声
- 重复、无效重试、低相关内容

## 3. 触发机制

触发优先级：midrun token > 事件 > 轮次 > run 结束

1. token 触发
- `light`: ratio >= 0.70
- `midrun`: ratio >= 0.82

2. 轮次触发
- 每 4 步尝试一次轻压缩

3. 事件触发
- 连续工具调用达到 3 次触发事件压缩

## 4. 当前配置默认值

- `ENABLE_MID_RUN_COMPACTION=true`
- `COMPACTION_ROUND_INTERVAL=4`
- `COMPACTION_LIGHT_TOKEN_RATIO=0.70`
- `COMPACTION_MIDRUN_TOKEN_RATIO=0.82`
- `COMPACTION_CONTEXT_WINDOW_TOKENS=16000`
- `COMPACTION_KEEP_RECENT_TURNS=8`
- `COMPACTION_TOOL_BURST_THRESHOLD=5`
- `COMPACTION_CONSISTENCY_GUARD=true`

## 5. 结构化摘要 Schema（V1）

核心字段：
- `task_state`: goal/progress/next_step/completion
- `decisions`
- `constraints`（含 immutable）
- `artifacts`
- `open_questions`
- `compression_meta`（mode/trigger/规模变化/immutable命中）

## 6. 一致性守护

1. 开关：`COMPACTION_CONSISTENCY_GUARD`
2. 开启时：压缩后执行一致性检查，失败即回滚本次压缩。
3. 关闭时：不拦截，直接落地压缩结果。

## 7. 可观测性事件

新增：
- `context_compression_started`
- `context_compression_succeeded`
- `context_compression_failed`
- `context_consistency_check_failed`

`started` 事件包含：
- `estimated_tokens`
- `context_usage_ratio`
- `trigger`
- `mode`

## 8. 数据落地与兼容

1. `summaries` 表新增：
- `schema_version`
- `summary_json`
- `last_anchor_msg_id`

2. 兼容旧版本：
- 旧 `summary` 文本仍可读取
- 新版本优先写 `summary_json`

## 9. 已实现清单

1. run 内触发压缩：已实现。
2. 结构化压缩器：已实现。
3. immutable 命中明细：已实现。
4. 一致性守护开关透传：已实现（CLI / BaseAgent / SubAgent）。
5. 新增压缩测试：已实现。

## 10. 下一步建议（V1.x）

1. 将 token 估算器替换为模型相关 tokenizer（减少估算误差）。
2. 增加压缩质量回归集（成功率/约束违背率/成本）。
3. 增加不可压缩规则白名单可配置化（而不是仅关键词）。
