# InDepth Observability Event Whitelist 对齐设计稿 V1

更新时间：2026-04-18  
状态：Implemented

## 1. 背景

当前观测链路存在一个明显错位：

1. 代码中已经真实发射了一批新的 `event_type`
2. 但 `app/observability/schema.py` 中的 `EVENT_TYPES` 白名单没有同步更新
3. `emit_event(...)` 会把未入白名单的事件统一归一化成 `unknown_event_type`

这会导致两个直接后果：

1. postmortem trace 中丢失关键语义，只能看到 `unknown_event_type`
2. `aggregate_task_metrics(...)` 的 `event_type_breakdown` 被污染，恢复链路与用户偏好链路统计失真

## 2. 问题定义

当前问题不是“事件有没有发出来”，而是“事件发出来后是否被观测层保留为稳定语义”。

也就是说：

1. 业务层已经发射事件
2. 存储层也确实落盘了
3. 但 schema 层把它们压平成了 `unknown_event_type`

因此这属于 observability schema 漏同步，而不是业务发射漏埋点。

## 3. 影响范围

当前确认受影响的链路主要有三类：

1. todo / recovery
   - `task_fallback_recorded`
   - `task_recovery_planned`
   - `todo_recovery_auto_planned`
   - `followup_subtasks_appended`
   - `subtask_updated`
   - `subtask_reopened`
   - `task_updated`
   - `todo_binding_missing_warning`
   - `todo_orphan_failure_detected`

2. search guard
   - `search_budget_auto_overridden`

3. user preference lifecycle
   - `user_preference_recall_succeeded`
   - `user_preference_recall_failed`
   - `user_preference_extract_started`
   - `user_preference_extract_succeeded`
   - `user_preference_extract_failed`
   - `user_preference_capture_succeeded`
   - `user_preference_capture_failed`

## 4. 设计目标

1. 让真实发射的事件类型进入白名单，避免被归一化成 `unknown_event_type`
2. 不改变现有 `emit_event(...)` 的未知事件兜底机制
3. 不修改 postmortem / metrics 的核心逻辑，只修正它们的输入语义
4. 为后续新增事件提供一条可回归验证的测试基线

## 5. 非目标

1. 本稿不重做 observability metrics 指标体系
2. 本稿不新增新的 postmortem 展示逻辑
3. 本稿不调整 memory 事件入 SQLite 的范围
4. 本稿不取消 `unknown_event_type` 的兜底能力

## 6. 最小落地方案

### 6.1 更新白名单

将当前代码里已真实发射、但尚未纳入 `EVENT_TYPES` 的事件补入 `app/observability/schema.py`。

### 6.2 保持兜底逻辑

`emit_event(...)` 仍然保留：

1. 对真正未知事件归一化为 `unknown_event_type`
2. 在 payload 中保留 `_original_event_type`

这样可以保证：

1. schema 对齐后，已知业务事件获得稳定语义
2. 后续新漏埋点仍不会破坏主流程

### 6.3 增加回归测试

新增测试覆盖两件事：

1. 本轮补入白名单的事件不再被归一化成 `unknown_event_type`
2. 未知事件仍会继续被归一化

## 7. 验收口径

至少满足以下条件：

1. 受影响的 17 个事件全部进入 `EVENT_TYPES`
2. 这些事件通过 `emit_event(...)` 后，落盘的 `event_type` 保持原值
3. 非白名单事件仍会被归一化成 `unknown_event_type`
4. observability 文档中的事件总表与实现保持一致

## 8. 一句话总结

本次修复的本质不是新增埋点，而是把已经真实存在的 observability 语义从 `unknown_event_type` 中解压出来，让 postmortem 和统计重新看到真实过程。
