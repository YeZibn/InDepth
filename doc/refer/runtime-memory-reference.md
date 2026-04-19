# InDepth Runtime 会话记忆参考

更新时间：2026-04-19

返回总览：
- [Memory 总览](./memory-reference.md)

## 1. 模块定位

Runtime 会话记忆负责“当前 task 的上下文管理”。

核心职责：
- 保存当前 task 的消息历史
- 在上下文过长时压缩历史
- 在读取上下文时把 summary 与最近消息重新组装出来
- 记录 step 级 token 事实，支撑压缩预算

核心特点：
- 强 task 绑定
- 高频读写
- 允许 destructive compaction
- 目标是“让当前任务继续跑下去”

不负责：
- 跨任务经验复用
- 用户长期偏好沉淀

## 2. 关键文件

- `app/core/memory/sqlite_memory_store.py`
- `app/core/memory/context_compressor.py`
- `app/core/memory/llm_context_compressor.py`
- `app/core/runtime/runtime_compaction_policy.py`
- `app/core/runtime/task_token_store.py`
- `app/core/runtime/token_counter.py`

## 3. 存储结构

### 3.1 消息存储

主存储在 `SQLiteMemoryStore`。

默认是按 agent 类型分库，例如：
- `db/runtime_memory_cli.db`
- `db/runtime_memory_main_agent.db`
- `db/runtime_memory_subagent_*.db`

核心表：

1. `messages`
   - 保存原始消息
   - 关键字段包括：
     - `conversation_id`
     - `role`
     - `content`
     - `tool_call_id`
     - `tool_calls_json`
     - `run_id`
     - `step_id`

2. `summaries`
   - 保存当前 task 已压缩出来的摘要
   - 关键字段包括：
     - `summary`
     - `schema_version`
     - `summary_json`
     - `last_anchor_msg_id`

### 3.2 Token ledger

step 级 token 事实不在 runtime memory DB 里，而是在单独的 ledger：

- `db/task_token_ledger.db`

核心表：

1. `task_token_step`
   - 每个 `(task_id, run_id, step)` 一条
   - 既保存 request 级 token，也保存 step 自身 token

2. `task_token_summary`
   - task 级聚合

当前最重要的字段：
- `input_tokens`
  - 当前 request 的 `messages` token
- `tools_tokens`
  - 当前 request 的 tools schema token
- `step_input_tokens`
  - 当前 step 自身 message 批次 token

## 4. 生命周期

### 4.1 写入

`AgentRuntime.run()` 在运行中持续写入：

1. 用户消息写入 `messages`
2. assistant 输出写入 `messages`
3. tool 结果写入 `messages`
4. 每个 step 的 token metrics 写入 `task_token_ledger`

### 4.2 读取

`SQLiteMemoryStore.get_recent_messages()` 会返回：

1. 已有 `summary_json` 渲染出的 system 摘要块
2. 最近原始消息

所以 runtime 读到的上下文不是“只读原文”，而是：

- 摘要 + 最近消息

### 4.3 压缩

压缩入口在：

- `app/core/runtime/runtime_compaction_policy.py`

实际执行在：

- `SQLiteMemoryStore.compact_mid_run(...)`
- `SQLiteMemoryStore.compact_final(...)`

## 5. 压缩语义

### 5.1 当前预算

当前结构化压缩默认采用：

- `live = 20%`
- `summary = 25%`
- `total = 45%`

其中：

1. live budget
   - 用于最近保留的原始 step
2. summary budget
   - 用于被折叠历史生成的新摘要

### 5.2 cut 单位

当前压缩优先按 step 切，不再默认按 turn 切。

做法是：

1. 先读取 `task_token_step`
2. 取每个 step 的 `step_input_tokens`
3. 从后往前累计
4. 到达 live budget 为止

如果拿不到 step anchor，才回退到旧的 turn 逻辑。

### 5.3 summary 约束

历史被折叠后只生成一份 summary。

这份 summary 会被限制在 summary budget 内，必要时会：
- 删除旧项
- 缩短字段
- 减少列表项数量
- 收缩 `task_state`

## 6. Token 口径

当前 Runtime 会话记忆使用 `tiktoken` 统一计数。

关键口径：

1. `input_tokens`
   - 只统计 request `messages`
2. `tools_tokens`
   - 单独统计 tools schema
3. `total_window_claim_tokens`
   - `input_tokens + tools_tokens + reserved_output_tokens`
4. `step_input_tokens`
   - 只统计该 step 自己的 message 批次

这四者不能混为一谈。

## 7. 观测

Runtime 会话记忆相关观测主要分两层：

1. request 级
   - `model_request_started`

2. 压缩级
   - `context_compression_started`
   - `context_compression_succeeded`
   - `context_compression_failed`
   - `context_consistency_check_failed`

这些事件当前会带出：
- request token
- live/summary 预算
- trim strategy
- cut 调整原因
- 实际保留 token
- summary token

详情见：
- [Observability 参考](./observability-reference.md)

## 8. 你应该用它来回答什么问题

Runtime 会话记忆最适合回答：

- 为什么这个 task 还能继续对话
- 当前上下文为什么会被压缩
- 这次压缩保留了哪些 step
- 当前 request token 是怎么估的

如果你的问题是下面这些，就不该先看这里：

- “历史经验为什么能跨任务召回”
  - 去看 [System 经验记忆](./system-memory-reference.md)
- “为什么以后都用中文回复我”
  - 去看 [User Preference 记忆](./user-preference-reference.md)
