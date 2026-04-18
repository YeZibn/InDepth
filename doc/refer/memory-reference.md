# InDepth Memory 参考

更新时间：2026-04-17

## 1. 模块范围

当前记忆体系由**三条链路**组成：

| 链路 | 用途 | 存储 | 数据特征 |
|------|------|------|----------|
| **Runtime 会话记忆** | 多轮对话上下文管理 | `db/runtime_memory_*.db` (SQLite) | 临时性、高频率读写 |
| **系统经验记忆** | 跨任务经验沉淀与检索 | `db/system_memory.db` (SQLite) | 结构化卡片、跨任务复用 |
| **用户偏好记忆** | **用户个人偏好持久化** | `memory/preferences/user-preferences.md` | 长期性、置信度追踪、来源可追溯 |

### 1.1 三条链路的关系

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         用户输入层                                       │
│                    （对话内容、显式偏好声明）                              │
└─────────────────────────────────┬───────────────────────────────────────┘
                                  │
              ┌───────────────────┼───────────────────┐
              ▼                   ▼                   ▼
    ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
    │ 用户偏好记忆     │  │ Runtime 会话记忆 │  │ 系统经验记忆     │
    │                 │  │                 │  │                 │
    │ • 兴趣、角色     │  │ • 多轮对话历史   │  │ • 任务经验卡片   │
    │ • 习惯、偏好     │  │ • 上下文压缩     │  │ • 最佳实践      │
    │ • 置信度追踪     │  │ • 实时读写      │  │ • 跨任务检索    │
    │                 │  │                 │  │                 │
    │ Markdown 单文件 │  │ SQLite 按 Agent │  │ SQLite 统一存储 │
    │ 原子写入        │  │ 类型分库        │  │ 按卡片检索      │
    └─────────────────┘  └─────────────────┘  └─────────────────┘
              │                   │                   │
              └───────────────────┼───────────────────┘
                                  ▼
                    ┌─────────────────────────┐
                    │    个性化提示词注入      │
                    │  （系统提示词组装阶段）   │
                    └─────────────────────────┘
```

### 1.2 为什么需要三条链路？

| 问题 | 解决方案 |
|------|---------|
| 上下文爆炸 | **Runtime Memory**：压缩历史，保留关键决策和约束 |
| 经验复用 | **System Memory**：沉淀任务经验，支持跨任务检索 |
| 个性化服务 | **User Preference**：记录用户偏好，实现千人千面 |

相关代码：
- `app/core/memory/sqlite_memory_store.py` - Runtime 记忆存储
- `app/core/memory/context_compressor.py` - 上下文压缩器
- `app/core/memory/system_memory_store.py` - 系统经验存储
- `app/core/memory/user_preference_store.py` - **用户偏好存储**
- `app/tool/runtime_memory_harvest_tool.py` - 候选记忆捕获工具
- `app/tool/memory_query_tool.py` - 记忆检索工具
- `app/observability/store.py::SystemMemoryEventStore` - 记忆事件落盘

## 2. 架构图

### 2.1 模块架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          记忆体系架构                                     │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                      AgentRuntime                                 │   │
│  │  ┌─────────────────────┐  ┌─────────────────────┐               │   │
│  │  │ _maybe_compact_mid_ │  │ _finalize_task_     │               │   │
│  │  │ run()               │  │ memory()            │               │   │
│  │  └──────────┬──────────┘  └──────────┬──────────┘               │   │
│  └─────────────┼─────────────────────────┼─────────────────────────┘   │
│                │                         │                             │
│                ▼                         ▼                             │
│  ┌─────────────────────────┐   ┌─────────────────────┐               │
│  │   RuntimeMemoryStore    │   │  SystemMemoryStore  │               │
│  │                         │   │                     │               │
│  │  ┌───────────────────┐ │   │  ┌───────────────┐  │               │
│  │  │ messages 表       │ │   │  │ memory_card 表│  │               │
│  │  │ summaries 表      │ │   │  └───────────────┘  │               │
│  │  └───────────────────┘ │   │                     │               │
│  │                         │   │  ┌───────────────┐  │               │
│  │  ┌───────────────────┐ │   │  │ event store   │  │               │
│  │  │ ContextCompressor │ │   │  │ (SQLite)      │  │               │
│  │  │ - merge_summary   │ │   │  └───────────────┘  │               │
│  │  │ - validate        │ │   │                     │               │
│  │  └───────────────────┘ │   │                     │               │
│  └───────────┬─────────────┘   └──────────┬──────────┘               │
│              │                              │                          │
│              ▼                              ▼                          │
│  ┌─────────────────────────┐   ┌─────────────────────┐               │
│  │ SQLite                  │   │ JSONL + SQLite     │               │
│  │ db/runtime_memory_*.db │   │ events.jsonl       │               │
│  └─────────────────────────┘   └─────────────────────┘               │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                   UserPreferenceStore (新增)                      │   │
│  │                                                                  │   │
│  │  ┌───────────────────┐        ┌─────────────────────────────┐   │   │
│  │  │  Markdown 解析器  │───────▶│ user-preferences.md         │   │   │
│  │  │  - 原子写入       │        │ - 用户偏好键值对            │   │   │
│  │  │  - 版本管理       │        │ - 置信度与来源追踪          │   │   │
│  │  └───────────────────┘        └─────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.2 数据流总览

```
用户输入
    │
    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     AgentRuntime.run() 循环                          │
│                                                                      │
│  ┌───────────────┐     ┌───────────────┐     ┌───────────────┐      │
│  │ 1. 模型推理   │────▶│ 2. 工具执行   │────▶│ 3. 消息写入   │      │
│  └───────────────┘     └───────────────┘     └───────┬───────┘      │
│                                                        │              │
│                                              ┌─────────▼─────────┐   │
│                                              │ 写入 messages 表   │   │
│                                              └─────────┬─────────┘   │
│                                                        │              │
│                                              ┌─────────▼─────────┐   │
│                                              │ 检查是否需要压缩   │   │
│                                              │ _maybe_compact    │   │
│                                              └───────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
    │
    ▼
任务结束
    │
    ├──▶ compact_final() ──▶ 最终压缩
    │
    ├──▶ _finalize_task_memory()
    │       │
    │       ├──▶ upsert postmortem 经验卡
    │       │
    │       └──▶ emit memory 事件三连
    │
    └──▶ 返回 final_answer
```

## 3. Runtime 会话记忆（SQLiteMemoryStore）

### 3.1 数据库与表

数据库路径：`db/runtime_memory_{agent_type}.db`

| Agent 类型 | 数据库文件 |
|-----------|-----------|
| 主 Agent | `db/runtime_memory_main_agent.db` |
| SubAgent general | `db/runtime_memory_subagent_general.db` |
| SubAgent researcher | `db/runtime_memory_subagent_researcher.db` |
| SubAgent builder | `db/runtime_memory_subagent_builder.db` |
| SubAgent reviewer | `db/runtime_memory_subagent_reviewer.db` |
| SubAgent verifier | `db/runtime_memory_subagent_verifier.db` |

**messages 表**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | INTEGER | 主键，自增 |
| `conversation_id` | TEXT | 会话 ID（即 task_id） |
| `role` | TEXT | user/assistant/system/tool |
| `content` | TEXT | 消息内容 |
| `tool_call_id` | TEXT | 关联的 tool call ID（可选） |
| `tool_calls_json` | TEXT | assistant 消息中的 tool_calls（可选） |
| `created_at` | TEXT | 创建时间 |

**summaries 表**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `conversation_id` | TEXT | 主键 |
| `summary` | TEXT | 人类可读摘要文本 |
| `schema_version` | TEXT | 摘要版本（v0_legacy/v1） |
| `summary_json` | TEXT | 结构化摘要 JSON |
| `last_anchor_msg_id` | INTEGER | 最后锚点消息 ID（裁剪分界） |
| `updated_at` | TEXT | 更新时间 |

### 3.2 读取流程（get_recent_messages）

```python
def get_recent_messages(self, conversation_id: str, limit: int = 100) -> List[Dict[str, Any]]:
```

**完整读取流程**：

```
get_recent_messages(conversation_id, limit=100)
         │
         ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 1. 查询 summaries 表                                                  │
│    SELECT summary, summary_json FROM summaries                      │
│    WHERE conversation_id = ?                                         │
└─────────────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 2. 摘要注入判断                                                        │
│                                                                      │
│    summary_json 可解析?                                               │
│    ├── YES ──▶ 注入 system 消息:                                     │
│    │            role=system, content=ContextCompressor.render_       │
│    │            summary_prompt(summary_json)                         │
│    │                                                                   │
│    ├── LEGACY (有 summary 文本但无 JSON)?                             │
│    │   └── YES ──▶ 注入 legacy system 消息                           │
│    │                                                                   │
│    └── NO ──▶ 跳过摘要拼接                                            │
└─────────────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 3. 查询 messages 表                                                   │
│    SELECT * FROM messages                                            │
│    WHERE conversation_id = ?                                         │
│    ORDER BY id ASC                                                   │
│    LIMIT ?                                                           │
└─────────────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 4. 消息规范化                                                          │
│                                                                      │
│    assistant + tool_calls_json ──▶ 还原 tool_calls 字段              │
│    tool + tool_call_id ──▶ 保持 tool 消息                            │
│    tool 无 tool_call_id ──▶ 降级为 assistant "[history:tool]..."   │
└─────────────────────────────────────────────────────────────────────┘
         │
         ▼
返回消息列表
```

### 3.3 写入流程（append_message）

```python
def append_message(
    self,
    conversation_id: str,
    role: str,
    content: str,
    tool_call_id: str = "",
    tool_calls: Optional[List[Dict]] = None,
) -> None:
```

**完整写入流程**：

```
append_message(conversation_id, role, content, ...)
         │
         ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 1. 写入 messages 表                                                   │
│                                                                      │
│    INSERT INTO messages                                              │
│    (conversation_id, role, content, tool_call_id, tool_calls_json)   │
│    VALUES (?, ?, ?, ?, ?)                                           │
│                                                                      │
│    tool_calls_json = json.dumps(tool_calls) 如果有 tool_calls        │
└─────────────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 2. 检查压缩触发                                                       │
│                                                                      │
│    _maybe_compact_mid_run()?                                         │
│    ├── YES ──▶ compact_mid_run(trigger, mode)                       │
│    │            │                                                   │
│    │            ├── trigger=event: 工具链替换压缩（替代摘要可走独立 LLM）│
│    │            └── trigger=token/finalize: summary 压缩路径         │
│    │                                                                   │
│    └── NO ──▶ 仅写入消息                                             │
└─────────────────────────────────────────────────────────────────────┘
```

### 3.4 压缩触发条件

**触发入口**：`AgentRuntime._maybe_compact_mid_run()`

| 优先级 | 条件 | trigger | mode | 说明 |
|-------|------|---------|------|------|
| 1 | `token_ratio >= midrun_token_ratio` | token | midrun | 运行中 token 压缩 |
| 2 | `current_tool_calls_count >= tool_burst_threshold` | event | event | 单次 tool_calls 条目触发 |

**默认值**：

| 参数 | 默认值 | 环境变量 |
|------|--------|---------|
| `midrun_token_ratio` | 0.82 | `COMPACTION_MIDRUN_TOKEN_RATIO`（兼容旧 `COMPACTION_STRONG_TOKEN_RATIO`） |
| `tool_burst_threshold` | 5 | `COMPACTION_TOOL_BURST_THRESHOLD` |
| `target_keep_ratio_midrun` | 0.40 | `COMPACTION_TARGET_KEEP_RATIO_MIDRUN`（兼容旧 `COMPACTION_TARGET_KEEP_RATIO_STRONG`） |
| `target_keep_ratio_finalize` | 0.40 | `COMPACTION_TARGET_KEEP_RATIO_FINALIZE` |
| `min_keep_turns` | 3 | `COMPACTION_MIN_KEEP_TURNS` |
| `compressor_kind` | `auto` | `COMPACTION_COMPRESSOR_KIND` |
| `compressor_llm_max_tokens` | 1200 | `COMPACTION_COMPRESSOR_LLM_MAX_TOKENS` |
| `event_summarizer_kind` | `auto` | `COMPACTION_EVENT_SUMMARIZER_KIND` |
| `event_summarizer_max_tokens` | 280 | `COMPACTION_EVENT_SUMMARIZER_MAX_TOKENS` |

### 8.3 压缩器类型

- `rule`
  - 使用 `ContextCompressor`，按规则提取 `task_state / constraints / decisions / artifacts`
- `llm`
  - 使用 `LLMContextCompressor` 生成同结构 `summary_json`
  - 输出版本号为 `v1_llm`
  - 若模型报错、非 JSON、或与旧摘要不一致，则自动回退到规则压缩
- `auto`
  - 真实 provider 下走 `llm`
  - `MockModelProvider` 下走 `rule`，保证测试稳定和可复现

### 8.3.1 Event 替代摘要器类型

- `rule`
  - 使用本地规则生成 `[tool-chain-compact]` 替代消息
- `llm`
  - 对被替换的工具链区段构造轻量 payload，调用独立 event summarizer 生成 `summary/key_results/failures`
  - `tools/stats/key_ids` 仍由程序生成，避免关键 ID 漂移
  - 若模型报错、非 JSON、或 `summary` 为空，则自动回退规则摘要
- `auto`
  - 真实 provider 下优先使用 mini 模型
  - `MockModelProvider` 下自动回退 `rule`

### 8.4 压缩器观测字段

`compact_mid_run()` / `compact_final()` 返回结果会额外暴露以下字段：

- `compressor_kind_requested`
- `compressor_kind_applied`
- `compressor_fallback_used`
- `compressor_failure_reason`

`event` 工具链替换压缩还会额外暴露：

- `tool_chain_summary_requested`
- `tool_chain_summary_applied`
- `tool_chain_summary_fallback_used`
- `tool_chain_summary_fallback_reason`
- `tool_chain_summary_model`

`summary_json.compression_meta` 也会同步写入这些字段，便于后续排查“请求 LLM 但最终回退到规则压缩”的情况。
| `keep_recent_turns` | 8 | `COMPACTION_KEEP_RECENT_TURNS`（预算不可用兜底） |
| `model_context_window_tokens` | 160000 | `MODEL_CONTEXT_WINDOW_TOKENS` |
| `compression_trigger_window_tokens` | 120000 | `COMPACTION_TRIGGER_WINDOW_TOKENS` |
| `enable_finalize_compaction` | False | `ENABLE_FINALIZE_COMPACTION` |
| `context_window_tokens` | trigger window alias | 内部兼容字段，等价于 `compression_trigger_window_tokens` |
| `consistency_guard` | True | `COMPACTION_CONSISTENCY_GUARD` |

## 4. 压缩实现（_compact_impl）

### 4.1 核心流程

```python
def _compact_impl(
    self,
    conversation_id: str,
    mode: str,      # midrun / event / finalize
    trigger: str,   # token / event / finalize
    force: bool,
    min_total: int,
) -> Dict[str, Any]:
```

**完整流程**：

```
_compact_impl(conversation_id, mode, trigger, force, min_total)
         │
         ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 1. 检查消息总数                                                       │
│                                                                      │
│    total = len(all_messages)                                         │
│    if not force and total < max(min_total, 1):                      │
│        return {success: True, applied: False, reason: "below_       │
│        threshold"}                                                    │
└─────────────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 2. 计算裁剪点（基于 token 预算）                                         │
│                                                                      │
│ target_keep_tokens = compression_trigger_window_tokens * keep_ratio │
│    cut_idx = _compute_token_budget_cut_index(                        │
│        all_messages, target_keep_tokens, min_keep_turns             │
│    )                                                                 │
│                                                                      │
│    turn 定义：相邻 user 消息之间为一轮（无 user 时按 assistant 分段）    │
└─────────────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 3. 提取旧消息                                                         │
│                                                                      │
│    old_rows = all_messages[:cut_idx]  # 要压缩的消息                  │
│    new_rows = all_messages[cut_idx:]  # 保留的消息                   │
└─────────────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 4. 读取已有摘要                                                        │
│                                                                      │
│    existing = SELECT summary_json FROM summaries                    │
│                WHERE conversation_id = ?                             │
│                                                                      │
│    existing_json = load_summary_json(existing)                       │
│    if not existing_json and existing_text:                          │
│        # Legacy 兼容                                                 │
│        existing_json = {"version": "v0_legacy", ...}                │
└─────────────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 5. 合并摘要                                                            │
│                                                                      │
│    merged_json = compressor.merge_summary(                           │
│        previous=existing_json,                                       │
│        messages=old_messages,                                       │
│        mode=mode,                                                   │
│        trigger=trigger,                                              │
│        before_messages=total,                                        │
│        after_messages=total - len(old_rows),                         │
│        dropped_messages=len(old_rows),                               │
│    )                                                                │
└─────────────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 6. 一致性校验（可选）                                                  │
│                                                                      │
│    if consistency_guard and not validate_consistency(existing_json,  │
│                                                        merged_json): │
│        return {success: False, reason: "consistency_check_failed"}  │
└─────────────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 7. 持久化                                                             │
│                                                                      │
│    # UPSERT summaries 表                                             │
│    INSERT INTO summaries (...)                                        │
│    ON CONFLICT(conversation_id) DO UPDATE SET ...                    │
│                                                                      │
│    # 删除已压缩消息                                                   │
│    DELETE FROM messages                                              │
│    WHERE conversation_id = ? AND id <= last_anchor_msg_id            │
└─────────────────────────────────────────────────────────────────────┘
         │
         ▼
返回压缩结果
```

### 4.2 Token 预算裁剪算法

```python
def _compute_token_budget_cut_index(
    self,
    rows: List[MessageRow],
    target_keep_tokens: int,
    min_keep_turns: int,
) -> int:
    """按最新 turn 向前累计 token，返回需要裁剪的前缀边界。"""
    if target_keep_tokens <= 0 or not rows:
        return 0

    turn_ranges = split_turn_ranges(rows)  # [(start_idx, end_idx), ...]
    keep_from = len(rows)
    kept_tokens = 0

    # 从最新 turn 开始往前累计
    for start, end in reversed(turn_ranges):
        turn_tokens = estimate_tokens(rows[start:end])
        if keep_from == len(rows):
            keep_from = start
            kept_tokens = turn_tokens
            continue
        if kept_tokens + turn_tokens > target_keep_tokens:
            break
        keep_from = start
        kept_tokens += turn_tokens

    # 最小保留轮次 + tool pair 保护
    keep_from = adjust_for_min_keep_and_tool_pair(rows, keep_from, min_keep_turns)
    return keep_from
```

补充说明：
- 当前压缩下限已按“轮次”保护，而不是按消息条数保护
- `min_keep_turns=3` 表示无论 token 预算多小，都至少保留最近 3 轮原文
- 轮次定义沿用当前实现：有 `user` 时按相邻 `user` 分段；无 `user` 时按 `assistant` 分段

### 4.3 Event 工具链替换压缩

```
compact_mid_run(trigger="event")
    │
    ├──▶ 定位最近连续工具调用段
    │      assistant(tool_calls) + tool + ...
    │
    ├──▶ 切分为工具单元（assistant(tool_calls)+其后 tool）
    │
    ├──▶ 过滤状态工具单元（默认不压缩）：
    │      plan_task / get_next_task / update_task_status / init_search_guard
    │
    ├──▶ 保留最近 N 个工具单元原文（默认 N=1）
    │
    ├──▶ 对可压缩连续区段做就地替换：
    │      先构造工具链 payload
    │      再生成 [tool-chain-compact] 替代摘要
    │      - `rule`: 本地规则摘要
    │      - `llm/auto`: 独立 event summarizer（默认优先 mini 模型）
    │      UPDATE 锚点消息为 [tool-chain-compact] 摘要
    │      DELETE 同区段其余消息
    │
    ├──▶ 摘要中包含 key_ids（todo_id/task_id/...）且不截断
    │
    └──▶ 不写 summaries（summary_json 不变）
```

### 4.4 返回字段

成功时返回：
```python
{
    "success": True,
    "applied": True,
    "trigger": "token",          # 触发原因
    "mode": "light",             # 压缩模式
    "before_messages": 100,       # 压缩前消息数
    "after_messages": 25,          # 压缩后消息数
    "dropped_messages": 75,       # 删除的消息数
    "immutable_constraints_count": 5,
    "immutable_constraints_preview": ["c_10", "c_23", ...],
    "immutable_hits_count": 8,
    "target_keep_tokens": 8800,
    "actual_kept_tokens_est": 7421,
    "trim_strategy": "token_budget",
    "cut_adjustment_reason": "tool_pair_guard",   # 可空
}
```

`event` 替换压缩返回（示例）：
```python
{
    "success": True,
    "applied": True,
    "trigger": "event",
    "mode": "light",
    "trim_strategy": "tool_chain_replace",
    "replaced_message_count": 6,
    "tool_chain_summary_requested": "llm",
    "tool_chain_summary_applied": "llm",
    "tool_chain_summary_fallback_used": False,
    "tool_chain_summary_model": "gpt-*-mini",
    "tool_chain_span": {"start_message_id": 101, "end_message_id": 106},
}
```

失败时返回：
```python
{
    "success": False,
    "applied": False,
    "reason": "consistency_check_failed",  # 或 "below_threshold"
    "total": 15,
}
```

## 5. 结构化摘要（ContextCompressor）

### 5.1 版本与主结构

当前版本：`v1`

```json
{
  "version": "v1",
  "task_state": {
    "goal": "当前任务目标（从首条 user 消息提取）",
    "progress": "最新 assistant 进展",
    "next_step": "下一步计划",
    "completion": 0.6
  },
  "decisions": [
    {
      "id": "d_10",
      "what": "决策内容摘要",
      "why": "runtime progress",
      "turn": 5,
      "confidence": "medium"
    }
  ],
  "constraints": [
    {
      "id": "c_3",
      "rule": "必须遵守的约束内容",
      "source": "system",      // system 或 user
      "immutable": true
    }
  ],
  "artifacts": [
    {
      "id": "a_15",
      "type": "tool_result",   // tool_result 或 file
      "ref": "call_id 或 msg:id",
      "summary": "产物摘要",
      "turn": 7
    }
  ],
  "open_questions": [
    {
      "id": "q_8",
      "question": "未解决的问题",
      "owner": "main",
      "status": "open"         // open 或 resolved
    }
  ],
  "compression_meta": {
    "mode": "light",
    "trigger": "token",
    "before_messages": 100,
    "after_messages": 30,
    "dropped_messages": 70,
    "immutable_hits_count": 3,
    "immutable_hits": [...],
    "timestamp": "2024-01-01T10:00:00+08:00"
  }
}
```

### 5.2 提取规则详解

#### constraints（约束）

**来源**：
1. 所有 `role=system` 的消息
2. 包含 immutable keyword 的任意消息

**Immutable Keywords**：
```python
IMMUTABLE_KEYWORDS = [
    "必须", "禁止", "不可", "务必", "审批",
    "权限", "安全", "密钥", "deadline",
    "must", "never",
]
```

**提取逻辑**：
```python
def _extract_constraints(self, messages):
    out = []
    for msg in messages:
        role = msg.get("role", "").strip().lower()
        content = msg.get("content", "").strip()
        if role == "system" or self._contains_immutable_keyword(content):
            msg_id = msg.get("id", 0)
            out.append({
                "id": f"c_{msg_id}",
                "rule": content[:300],
                "source": "system" if role == "system" else "user",
                "immutable": True,
            })
    return out
```

#### decisions（决策）

**来源**：role=assistant 或 role=tool 的消息

**限制**：最多保留 12 条（最后 12 条）

```python
def _extract_decisions(self, messages):
    out = []
    for msg in messages:
        role = msg.get("role", "").strip().lower()
        if role not in {"assistant", "tool"}:
            continue
        content = msg.get("content", "").strip()
        if content:
            msg_id = msg.get("id", 0)
            out.append({
                "id": f"d_{msg_id}",
                "what": content[:180],
                "why": "runtime progress",
                "turn": msg.get("turn", 0),
                "confidence": "medium",
            })
    return out[-12:]  # 只保留最后 12 条
```

#### artifacts（产物）

**来源**：
1. `role=tool` 的所有消息
2. `role=assistant` 且包含 `/`、`db/` 或 `Return code:` 的消息

**限制**：最多保留 15 条（最后 15 条）

```python
def _extract_artifacts(self, messages):
    out = []
    for msg in messages:
        role = msg.get("role", "").strip().lower()
        content = msg.get("content", "").strip()
        msg_id = msg.get("id", 0)

        if role == "tool":
            out.append({
                "id": f"a_{msg_id}",
                "type": "tool_result",
                "ref": msg.get("tool_call_id") or f"msg:{msg_id}",
                "summary": content[:180],
                "turn": msg.get("turn", 0),
            })
        elif role == "assistant" and ("/" in content or "db/" in content or "Return code:" in content):
            out.append({
                "id": f"a_{msg_id}",
                "type": "file",
                "ref": f"msg:{msg_id}",
                "summary": content[:180],
                "turn": msg.get("turn", 0),
            })
    return out[-15:]
```

#### open_questions（待解决问题）

**来源**：`role=user` 且内容包含 `?` 或 `？` 的消息

**限制**：最多保留 12 条（最后 12 条）

### 5.3 合并规则（merge_summary）

```python
def merge_summary(
    self,
    previous: Optional[Dict],
    messages: List[Dict],
    mode: str,
    trigger: str,
    before_messages: int,
    after_messages: int,
    dropped_messages: int,
) -> Dict[str, Any]:
```

**合并策略**：
1. `task_state`：`previous` + `messages` 混合更新
2. 列表字段（decisions/constraints/artifacts/open_questions）：
   - 先追加 previous 中不重复的项
   - 再追加从 messages 提取的新项
   - 按 ID 去重
   - 截断到上限

**容量上限**：

| 字段 | 最大条数 |
|------|---------|
| decisions | 30 |
| constraints | 30 |
| artifacts | 50 |
| open_questions | 20 |

### 5.4 渲染提示（render_summary_prompt）

```python
def render_summary_prompt(self, summary: Dict) -> str:
    """将结构化摘要转换为人类可读的提示文本。"""
```

**输出示例**：
```
结构化历史摘要(v1)：
- 目标: 用户请求帮我写一个 Python 脚本
- 进展: 已完成基础框架搭建
- 下一步: 添加命令行参数解析

- 不可违反约束:
  - 必须在 Linux 和 Mac 都可运行
  - 禁止使用第三方库

- 已做决策:
  - 使用 argparse | 原因: runtime progress
  - 使用 pathlib 替代 os.path | 原因: runtime progress

- 待确认:
  - 是否需要支持 Python 2.7?

- 关键产物索引:
  - msg:12 | 帮我写一个 Python 脚本
```

## 6. 一致性守护

### 6.1 校验规则

```python
def validate_consistency(
    self,
    previous: Optional[Dict],
    current: Dict,
) -> bool:
```

**校验项**：

| 规则 | 说明 | 触发条件 |
|------|------|---------|
| Goal 连续性 | 旧 goal 非空时，新 goal 不能为空 | `previous.task_state.goal` 存在且非空 |
| Immutable 保留 | 旧摘要中的 immutable constraints 不得丢失 | `previous.constraints` 中有 `immutable=true` 的项 |

**具体逻辑**：

```python
# 1. Goal 连续性
prev_goal = previous.get("task_state", {}).get("goal", "").strip()
cur_goal = current.get("task_state", {}).get("goal", "").strip()
if prev_goal and not cur_goal:
    return False  # 违反：旧 goal 丢失

# 2. Immutable 保留
prev_immutables = [c for c in previous.get("constraints", [])
                   if c.get("immutable")]
if prev_immutables:
    cur_ids = {c.get("id") for c in current.get("constraints", [])}
    for c in prev_immutables:
        if c.get("id") not in cur_ids:
            return False  # 违反：immutable constraint 丢失
return True
```

### 6.2 守护行为

| 配置 | 校验失败行为 |
|------|------------|
| `consistency_guard=True` | 阻断压缩，返回 `success=False` |
| `consistency_guard=False` | 忽略校验，继续压缩 |

### 6.3 使用场景

**适合开启的场景**：
- 任务有严格约束（如安全、权限要求）
- 不允许中途丢失关键决策

**适合关闭的场景**：
- 探索性任务，约束可能动态变化
- 调试阶段，需要观察压缩行为

## 7. 系统记忆（SystemMemoryStore）

### 7.1 数据库与表

数据库路径：`db/system_memory.db`

**memory_card 表**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `card_id` | TEXT | 主键，卡片唯一标识 |
| `scenario_stage` | TEXT | 场景阶段 |
| `confidence` | REAL | 置信度 |
| `payload_json` | TEXT | 完整卡片 JSON |
| `created_at` | TEXT | 创建时间 |
| `updated_at` | TEXT | 更新时间 |

### 7.2 卡片结构

```json
{
  "card_id": "mem_task_xxx_yyy",
  "stage": "postmortem",
  "confidence": 0.8,
  "title": "任务总结标题",
  "domain": "技术实现",
  "trigger_hint": "什么情况下应检索此卡",
  "risk_level": "P1",
  "payload": {
    "task_id": "...",
    "run_id": "...",
    "final_answer": "...",
    "judgement": {...},
    "events_summary": "...",
    "lessons": ["...","..."]
  },
  "tags": ["python", "api"],
  "active": true
}
```

### 7.3 核心接口

```python
class SystemMemoryStore:
    def upsert_card(self, card: Dict[str, Any]) -> None:
        """插入或更新记忆卡。"""

    def get_card(self, card_id: str) -> Optional[Dict[str, Any]]:
        """按 card_id 精确查询。"""

    def search_cards(
        self,
        stage: Optional[str] = None,
        query: Optional[str] = None,
        limit: int = 10,
        only_active: bool = True,
    ) -> List[Dict[str, Any]]:
        """模糊检索记忆卡。"""

    def list_due_review_cards(
        self,
        within_days: int = 7,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """列出需要 review 的记忆卡。"""
```

### 7.4 检索逻辑

```python
def search_cards(self, stage, query, limit, only_active):
    sql = "SELECT * FROM memory_card WHERE 1=1"
    params = []

    if stage:
        sql += " AND scenario_stage = ?"
        params.append(stage)

    if only_active:
        sql += " AND active = 1"

    if query:
        # 简单的 token 匹配
        # 匹配 title, domain, trigger_hint, tags
        tokens = query.lower().split()
        token_pattern = " OR ".join([
            "(title LIKE ? OR domain LIKE ? OR trigger_hint LIKE ?)"
            for _ in tokens
        ])
        sql += f" AND ({token_pattern})"
        for token in tokens:
            like = f"%{token}%"
            params.extend([like, like, like])

    sql += " ORDER BY updated_at DESC LIMIT ?"
    params.append(limit)

    rows = conn.execute(sql, params).fetchall()
    return [self._row_to_card(row) for row in rows]
```

## 8. 记忆生命周期策略

### 8.1 任务开始高精度召回（自动）

`AgentRuntime.run()` 在首次模型请求前执行 system memory 召回注入：

```python
def _inject_system_memory_recall(self, task_id, run_id, user_input, messages):
    emit_event(..., event_type="memory_triggered", payload={"source": "runtime_start_recall"})

    # 候选池（active + 未过期）
    rows = system_memory.search_cards(query="", only_active=True, limit=50)

    # 最终由 LLM 按 user_input + title 选 Top-K
    selected = rerank_by_llm(user_input=user_input, titles=rows)[:5]

    # 命中逐条记 retrieval，最后记 decision
    # 未命中只记 decision=skipped，不阻塞主流程
    return inject_light_block(messages, selected)  # memory_id + recall_hint
```

规则：
1. Top-K 最多 5 条。
2. 未命中不阻塞主流程。
3. 注入内容为 `memory_id + recall_hint`，不拼接整卡原文。

### 8.2 任务结束强制沉淀

`AgentRuntime._finalize_task_memory()` 在每次 `run()` 结束时**总是执行**：

```python
def _finalize_task_memory(self, task_id: str, task_status: str, ...):
    # 1. 构建 postmortem 卡片
    card_id = f"mem_task_{task_slug}_{run_slug}"
    card = {
        "card_id": card_id,
        "stage": "postmortem",
        "confidence": 0.5,
        "title": f"任务 {task_id} 总结",
        "domain": "general",
        "trigger_hint": f"task_id={task_id}",
        "risk_level": "P1" if task_status == "error" else "P3",
        "payload": {
            "task_id": task_id,
            "run_id": run_id,
            "final_answer": final_answer,
            "judgement": judgement,
            "events_summary": events_summary,
            "lessons": lessons,
        },
        "active": True,
    }

    # 2. 写入系统记忆
    system_memory.upsert_card(card)

    # 3. 发射记忆事件三连（用于观测）
    emit_event(task_id, run_id, event_type="memory_triggered", ...)
    emit_event(task_id, run_id, event_type="memory_retrieved", ...)
    emit_event(task_id, run_id, event_type="memory_decision_made", ...)
```

### 8.3 运行中候选捕获（tool 显式调用）

工具：`capture_runtime_memory_candidate`

```python
def capture_runtime_memory_candidate(
    task_id: str,
    run_id: str,
    title: str,
    observation: str,
    stage: str = "lifecycle",
    confidence: float = 0.5,
) -> Dict[str, Any]:
    card = {..., "id": f"mem_candidate_{slug(...)}", "lifecycle": {"status": "draft", ...}}
    system_memory.upsert_card(card)
    emit_event(..., event_type="memory_triggered", payload={"source_event": "runtime_memory_harvest_skill"})
    emit_event(..., event_type="memory_retrieved", ...)
    emit_event(..., event_type="memory_decision_made", ...)
    return {"success": True, "id": card["id"]}
```

### 8.4 运行中检索

工具：`search_memory_cards`

```python
def search_memory_cards(
    query: str,
    stage: Optional[str] = None,
    limit: int = 5,
) -> Dict[str, Any]:
    cards = system_memory.search_cards(
        stage=stage,  # backward compatibility
        query=query,
        limit=limit,
    )
    return {
        "success": True,
        "count": len(cards),
        "cards": cards,
    }
```

工具：`get_memory_card_by_id`

```python
def get_memory_card_by_id(memory_id: str, include_inactive: bool = False, ...) -> Dict[str, Any]:
    card = system_memory.get_card(memory_id, only_active=not include_inactive)
    return {"success": True, "found": bool(card), "card": card}
```

## 9. 记忆观测落盘

### 9.1 三张事件表

| 表名 | 字段 | 用途 |
|------|------|------|
| `memory_trigger_event` | event_id, event_time, task_id, run_id, stage, context_id, risk_level, payload_json | 记忆触发事件 |
| `memory_retrieval_event` | event_id, event_time, task_id, run_id, trigger_event_id, memory_id, score, payload_json | 记忆检索事件 |
| `memory_decision_event` | event_id, event_time, task_id, run_id, trigger_event_id, memory_id, decision, reason, payload_json | 记忆决策事件 |

### 9.2 写入规则

```python
def emit_event(...):
    # 1. 写入 JSONL（所有事件）
    with open("events.jsonl", "a") as f:
        f.write(json.dumps(record) + "\n")

    # 2. 写入 SQLite（仅 memory 事件）
    if event_type in ("memory_triggered", "memory_retrieved", "memory_decision_made"):
        try:
            _write_memory_event_to_sqlite(record)
        except Exception:
            pass  # 异常不阻塞主流程
```

## 10. 明确行为约束

| 约束 | 说明 |
|------|------|
| 启动自动召回 | Runtime 在首次模型请求前执行 system memory 召回（LLM 基于 title 主判定，最多 5 条） |
| capture 显式调用 | 运行中候选记忆 capture 保持 tool 调用，不做 Runtime 隐式自动写卡 |
| 轻注入结构 | 启动注入统一为 `memory_id + recall_hint` |
| 完整拉取工具 | 运行中可用 `get_memory_card_by_id` 按 id 拉取完整卡片 |
| 异常不阻塞 | 记忆链路异常不应中断主执行 |
| Legacy 兼容 | legacy `summary` 文本仍可读，逐步迁移到 `summary_json` |
| DB 按类型聚合 | 每个 Agent 类型有独立的 runtime memory 数据库 |
| token 预算优先 | `token/finalize` 路径按预算裁剪，`keep_recent_turns` 仅作兜底 |
| event 就地替换 | `event` 路径删除连续工具段并插入替代消息，不写 `summary_json` |

## 11. 用户偏好存储（UserPreferenceStore）

### 11.1 定位

`UserPreferenceStore` 提供**单层、单文件的 Markdown 格式**用户偏好存储，与 Runtime Memory 和 System Memory 形成互补：

| 维度 | UserPreferenceStore | RuntimeMemoryStore | SystemMemoryStore |
|------|---------------------|-------------------|-------------------|
| **存储内容** | 用户个人偏好 | 会话上下文 | 任务经验卡片 |
| **存储格式** | Markdown 单文件 | SQLite | SQLite |
| **数据来源** | 用户声明/LLM提取 | 对话消息 | 任务执行沉淀 |
| **使用场景** | 个性化提示词注入 | 多轮对话管理 | 跨任务经验检索 |
| **置信度追踪** | ✅ 有 | ❌ 无 | ❌ 无 |
| **来源追踪** | ✅ 有（source字段） | ❌ 无 | ❌ 无 |

### 11.2 存储位置

默认路径：`memory/preferences/user-preferences.md`

### 11.3 数据结构

```markdown
# User Preferences

meta:
- version: 1
- updated_at: 2026-04-16T00:36:16+08:00
- enabled: true

## preferences

### interest_topics
- value: [编程, AI]
- source: llm_extract_v1
- confidence: 0.96
- updated_at: 2026-04-16T00:36:16+08:00
- note: evidence=用户提到喜欢编程

### job_role
- value: 程序员
- source: explicit_user
- confidence: 0.98
- updated_at: 2026-04-16T00:36:16+08:00
- note: 用户自我介绍
```

### 11.4 核心 API

```python
from app.core.memory.user_preference_store import UserPreferenceStore

store = UserPreferenceStore()

# 检查启用状态
if store.is_enabled():
    # 获取所有偏好
    prefs = store.list_preferences()
    
    # 插入/更新偏好
    store.upsert_preference(
        key="coding_style",
        value="简洁优先",
        source="explicit_user",  # 或 "llm_extract_v1"
        confidence=0.95,
        note="用户明确说明"
    )
    
    # 获取单个偏好
    pref = store.get_preference("interest_topics")
    
    # 删除偏好
    store.delete_preference("old_preference")
```

### 11.5 特性

1. **原子写入**：使用临时文件 + `os.replace` 避免写入损坏
2. **自动初始化**：文件不存在时自动创建默认结构
3. **容错解析**：解析失败时返回安全默认值
4. **值类型支持**：支持字符串和列表两种值类型

### 11.6 使用场景

1. **LLM 提取用户偏好**：对话中自动识别用户兴趣、角色等信息
2. **用户显式设置**：用户直接声明的偏好（如"我喜欢简洁的代码"）
3. **个性化提示词注入**：在 Agent 系统提示词中注入用户偏好上下文

详见独立文档：`user-preference-reference.md`

## 12. 测试映射

| 测试文件 | 覆盖内容 |
|---------|---------|
| `tests/test_runtime_context_compression.py` | 压缩触发、摘要结构、一致性守护、裁剪算法 |
| `tests/test_runtime_memory_harvest_tool.py` | 候选记忆捕获工具 |
| `tests/test_system_memory_store.py` | 系统记忆存储 CRUD、检索 |
| `tests/test_memory_observability_events.py` | 记忆观测事件 SQLite 落盘 |
| `tests/test_runtime_eval_integration.py` | 启动召回注入、任务结束沉淀 |
| `tests/test_user_preference_store.py` | 用户偏好存储 CRUD |
| `tests/test_user_preference_runtime.py` | 用户偏好运行时集成 |
