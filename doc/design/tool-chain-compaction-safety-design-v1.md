# InDepth Tool Chain Compaction Safety V1 设计稿

更新时间：2026-04-14
状态：V1 设计中（待实现）

## 1. 问题

当前 `event` 压缩会把连续工具调用段替换为一条摘要消息。若摘要丢失关键状态（如 `todo_id`），模型后续可能重复创建任务或使用错误 ID，导致执行漂移。

## 2. 目标

1. `event` 压缩继续降噪，但不破坏任务状态连续性。
2. 避免压缩关键状态工具链（todo/search guard 等）。
3. 压缩后替代消息可追溯、可复用，关键 ID 不截断。

## 3. 核心策略

### 3.1 状态工具豁免（不压缩）

默认豁免工具：
1. `create_task`
2. `get_next_task`
3. `update_task_status`
4. `init_search_guard`

规则：包含以上任一工具的工具单元，不参与 `event` 替换压缩。

### 3.2 最近窗口保护

新增保护：保留最近 `N` 个工具单元原文（默认 `N=1`）。

目的：避免“刚产生的状态”立即被折叠掉。

### 3.3 仅压缩可压缩区段

在“最近连续工具调用段”内按工具单元划分，选择可压缩且连续的区段进行替换，不跨越豁免单元。

### 3.4 结构化替代消息（保真）

替代消息包含：
1. `tools`: 工具名与次数
2. `stats`: success/failed
3. `key_ids`: 关键标识（`todo_id/task_id/run_id/...`）
4. `key_results`: 关键结果摘要
5. `failures`: 失败摘要

约束：
1. `key_ids` 不截断
2. 替代消息固定前缀：`[tool-chain-compact]`

## 4. 执行流程

```
compact_mid_run(trigger="event")
    │
    ├──▶ 定位最近连续工具调用段
    ├──▶ 切分为工具单元（assistant(tool_calls)+tool...）
    ├──▶ 应用豁免工具规则 + 最近窗口保护
    ├──▶ 选取可压缩连续区段
    ├──▶ 生成结构化替代消息
    ├──▶ 用 UPDATE 保留锚点消息位置（不改变时序）
    └──▶ DELETE 其余被替换消息
```

## 5. 非目标

1. V1 不引入跨 run 的状态缓存。
2. V1 不改变 token/finalize 路径（仍走 summary）。

## 6. 测试计划

1. `event_compaction_should_skip_stateful_tools`
2. `event_compaction_should_keep_recent_tool_unit_raw`
3. `event_compaction_should_preserve_key_ids_in_replacement_message`
4. `event_compaction_should_not_write_summary_json`

## 7. 预期收益

1. 显著降低 todo/search guard 场景的重复创建与 ID 漂移。
2. 保持 event 压缩的降噪收益。
3. 提升替代消息可解释性和运行稳定性。
