# InDepth Memory 参考

更新时间：2026-04-12

## 1. 模块范围

当前记忆体系由两条链路组成：
1. Runtime 会话记忆（`SQLiteMemoryStore`）
2. 系统经验记忆（`SystemMemoryStore` + memory events）

相关代码：
- `app/core/memory/sqlite_memory_store.py`
- `app/core/memory/context_compressor.py`
- `app/core/memory/system_memory_store.py`
- `app/tool/runtime_memory_harvest_tool.py`
- `app/tool/memory_query_tool.py`
- `app/observability/store.py::SystemMemoryEventStore`

## 2. 架构图

### 2.1 模块架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          记忆体系架构                                     │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                      AgentRuntime                                 │   │
│  │                      _finalize_task_memory()                      │   │
│  └─────────────────────────────┬───────────────────────────────────┘   │
│                                │                                        │
│          ┌─────────────────────┼─────────────────────┐                │
│          ▼                     ▼                     ▼                │
│  ┌───────────────┐   ┌─────────────────────┐   ┌───────────────┐       │
│  │ Runtime       │   │ SystemMemoryStore   │   │ Context       │       │
│  │ MemoryStore   │   │                     │   │ Compressor    │       │
│  │               │   │  ┌─────────────┐   │   │               │       │
│  │ ┌───────────┐ │   │  │memory_card │   │   │ ┌───────────┐ │       │
│  │ │ messages  │ │   │  └─────────────┘   │   │ │ merge_    │ │       │
│  │ │ summaries │ │   │                    │   │ │ summary() │ │       │
│  │ └───────────┘ │   │  ┌─────────────┐   │   │ └───────────┘ │       │
│  │               │   │  │ event store│   │   │               │       │
│  │ ┌───────────┐ │   │  └─────────────┘   │   │ ┌───────────┐ │       │
│  │ │ compact() │ │   │                    │   │ │ validate_ │ │       │
│  │ └───────────┘ │   │                    │   │ │consistency│ │       │
│  └───────┬───────┘   └─────────────────────┘   │ └───────────┘ │       │
│          │                                         │               │
│          ▼                                         ▼               │
│  ┌───────────────┐                       ┌───────────────┐           │
│  │  SQLite       │                       │  结构化摘要    │           │
│  │  runtime_     │                       │  v1 JSON      │           │
│  │  memory_*.db  │                       │               │           │
│  └───────────────┘                       └───────────────┘           │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                     观测层 (Observability)                       │   │
│  │                                                                  │   │
│  │  emit_event() ──▶ events.jsonl (all events)                      │   │
│  │                   │                                              │   │
│  │              memory events ──▶ SystemMemoryEventStore            │   │
│  │                                       (SQLite)                   │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.2 消息读写流程

```
┌─────────────────────────────────────────────────────────────────────┐
│                       消息读取流程                                     │
│                                                                      │
│  get_recent_messages(conversation_id, limit)                          │
│         │                                                            │
│         ▼                                                            │
│  ┌─────────────────┐                                                 │
│  │ 查 summaries 表  │                                                 │
│  └────────┬────────┘                                                 │
│           │                                                          │
│           ▼                                                          │
│  ┌─────────────────────────────────────────────────────────────┐     │
│  │ summary_json 可解析?                                         │     │
│  │                                                              │     │
│  │  YES ──▶ 注入 role=system "结构化历史摘要(v1)" 提示          │     │
│  │                                                              │     │
│  │  LEGACY ──▶ 有 summary 文本? ──▶ 注入 legacy 摘要            │     │
│  │                                                              │     │
│  │  NO  ──▶ 跳过摘要拼接                                        │     │
│  └─────────────────────────────────────────────────────────────┘     │
│           │                                                          │
│           ▼                                                          │
│  拼接最近消息 (最近 limit 条，升序)                                    │
│           │                                                          │
│           ▼                                                           │
│  返回规范化消息列表                                                    │
│                                                                      │
│  规范化规则:                                                         │
│  - assistant + tool_calls_json ──▶ 还原 tool_calls                  │
│  - tool + tool_call_id ──▶ 保持 tool 消息                           │
│  - tool 无 tool_call_id ──▶ 降级为 assistant 文本                    │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                       消息写入流程                                     │
│                                                                      │
│  append_message(conversation_id, role, content, ...)                 │
│         │                                                            │
│         ▼                                                            │
│  写入 messages 表 (id, conversation_id, role, content,              │
│                  tool_call_id, tool_calls_json, created_at)         │
│         │                                                            │
│         ▼                                                            │
│  检查是否触发压缩                                                     │
│         │                                                            │
│         ├─── 达到压缩条件 ──▶ compact_mid_run()                      │
│         │                    │                                       │
│         │                    ├─── 提取旧消息 + 旧摘要               │
│         │                    ├─── ContextCompressor.merge_summary() │
│         │                    ├─── validate_consistency()            │
│         │                    ├─── UPSERT summaries 表              │
│         │                    └─── 删除已裁剪消息                     │
│         │                                                            │
│         └─── 未达到 ──▶ 仅写入消息                                    │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.3 压缩触发流程

```
_maybe_compact_mid_run()
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│  检查压缩条件 (按优先级)                                      │
│                                                              │
│  1. token_ratio >= strong_token_ratio?                     │
│     YES ──▶ trigger=token, mode=strong ──▶ 执行强力压缩       │
│                                                              │
│  2. consecutive_tool_calls >= tool_burst_threshold?         │
│     YES ──▶ trigger=event, mode=light ──▶ 执行轻量压缩       │
│                                                              │
│  3. round % round_interval == 0?                            │
│     YES ──▶ trigger=round, mode=light ──▶ 执行轻量压缩       │
│                                                              │
│  4. token_ratio >= light_token_ratio?                       │
│     YES ──▶ trigger=token, mode=light ──▶ 执行轻量压缩       │
│                                                              │
│  NO ──▶ 不压缩，继续执行                                      │
└─────────────────────────────────────────────────────────────┘
```

## 3. Runtime 会话记忆（SQLiteMemoryStore）

### 3.1 数据表

**messages 表**：
| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | INTEGER | 主键，自增 |
| `conversation_id` | TEXT | 会话 ID |
| `role` | TEXT | user/assistant/system/tool |
| `content` | TEXT | 消息内容 |
| `tool_call_id` | TEXT | 工具调用 ID（可选） |
| `tool_calls_json` | TEXT | 工具调用 JSON（可选） |
| `created_at` | TEXT | 创建时间 |

**summaries 表**：
| 字段 | 类型 | 说明 |
|------|------|------|
| `conversation_id` | TEXT | PK |
| `summary` | TEXT | 兼容文本摘要 |
| `schema_version` | TEXT | 摘要版本 |
| `summary_json` | TEXT | 结构化摘要 JSON |
| `last_anchor_msg_id` | INTEGER | 最后锚点消息 ID |
| `updated_at` | TEXT | 更新时间 |

### 3.2 读取行为

`get_recent_messages(conversation_id, limit)` 读取流程：

1. 先查 `summaries` 表
2. 若 `summary_json` 可解析，注入 `role=system` 的"结构化历史摘要(v1)"提示
3. 若无 JSON 但有 `summary` 文本，注入 legacy 摘要
4. 再拼接最近消息（升序）

消息规范化：
- assistant 且有 `tool_calls_json` → 还原 `tool_calls`
- tool 且有 `tool_call_id` → 保持 tool 消息
- tool 无 `tool_call_id` → 降级为 assistant 文本 `[history:tool] ...`

### 3.3 压缩入口

- `compact_mid_run(conversation_id, trigger, mode)`：运行时压缩
- `compact_final(conversation_id)`：任务结束时最终压缩
- `compact()` 兼容入口，转发到 `compact_final()`

## 4. 压缩实现（_compact_impl）

### 4.1 核心流程

```
_compact_impl(conversation_id, trigger, mode)
    │
    ├──▶ 检查消息数量是否达到 min_total
    │
    ├──▶ 计算裁剪点: cut = total - keep_recent
    │
    ├──▶ 取旧消息 + 旧摘要
    │
    ├──▶ ContextCompressor.merge_summary()
    │       │
    │       ├──▶ 提取 goal/constraints/decisions/artifacts
    │       │     open_questions/anchors
    │       │
    │       └──▶ 生成结构化摘要 v1
    │
    ├──▶ validate_consistency() ──▶ 一致性守护
    │
    ├──▶ UPSERT summaries 表
    │
    ├──▶ 删除已裁剪消息 (id <= last_anchor_msg_id)
    │
    └──▶ 返回压缩结果统计
```

### 4.2 返回字段

成功且 `applied=true` 时返回：
- `trigger`：触发原因（token/event/round）
- `mode`：压缩模式（light/strong）
- `before_messages`：压缩前消息数
- `after_messages`：压缩后消息数
- `dropped_messages`：删除的消息数
- `immutable_constraints_count`：不可变约束数
- `immutable_constraints_preview`：不可变约束预览
- `immutable_hits_count`：不可变约束命中数

## 5. 结构化摘要（ContextCompressor）

### 5.1 版本与主结构

版本：`v1`

```json
{
  "version": "v1",
  "task_state": {
    "goal": "当前任务目标",
    "progress": "已完成的工作",
    "next_step": "下一步计划",
    "completion": "完成度评估"
  },
  "decisions": [
    {"id": "d1", "content": "决策内容", "anchor": "对应消息ID"}
  ],
  "constraints": [
    {"id": "c1", "content": "必须遵守的约束", "immutable": true}
  ],
  "artifacts": [
    {"id": "a1", "path": "文件路径", "desc": "产出物描述"}
  ],
  "open_questions": [
    {"id": "q1", "content": "未解决的问题"}
  ],
  "anchors": [
    {"msg_id": "xxx", "type": "constraint/artifact/decision/history", "reason": "原因"}
  ],
  "compression_meta": {
    "trigger": "token/event/round",
    "mode": "light/strong",
    "compressed_at": "ISO时间戳"
  }
}
```

### 5.2 提取规则

| 字段 | 来源 | 提取条件 |
|------|------|---------|
| `constraints` | system 消息 或 命中关键词 | `必须/禁止/must/never/shouldn't` |
| `decisions` | assistant/tool 消息 | assistant 决策性输出 |
| `artifacts` | tool 消息 或 assistant | 路径/命令输出/文件内容 |
| `open_questions` | user 消息 | 包含 `?` 或 `？` |
| `anchors` | 所有旧消息 | 映射到原因类型 |

### 5.3 容量上限

| 字段 | 最大条数 |
|------|---------|
| decisions | 30 |
| constraints | 30 |
| artifacts | 50 |
| open_questions | 20 |
| anchors | 60 |

## 6. 一致性守护

### 6.1 验证规则

`validate_consistency(previous_summary, current_summary)`：

1. **goal 连续性**：旧 goal 非空时，新 goal 不能为空
2. **immutable 约束保留**：旧摘要中 `immutable=true` 的 constraint id 不得丢失

### 6.2 守护行为

当 `SQLiteMemoryStore.consistency_guard=True` 时：
- 校验失败会阻断压缩
- 返回 `success=false`
- `reason=consistency_check_failed`

## 7. 系统记忆（SystemMemoryStore）

### 7.1 数据库与表

数据库默认：`db/system_memory.db`

主表：`memory_card`

| 字段 | 类型 | 说明 |
|------|------|------|
| `card_id` | TEXT | PK，卡片唯一标识 |
| `scenario_stage` | TEXT | 场景阶段 |
| `confidence` | REAL | 置信度 |
| `payload_json` | TEXT | 完整卡片 JSON |
| `created_at` | TEXT | 创建时间 |
| `updated_at` | TEXT | 更新时间 |

### 7.2 关键接口

```python
class SystemMemoryStore:
    def upsert_card(self, card: Dict[str, Any]) -> None
    def get_card(self, card_id: str) -> Optional[Dict[str, Any]]
    def search_cards(
        self,
        stage: Optional[str] = None,
        query: Optional[str] = None,
        limit: int = 10,
        only_active: bool = True,
    ) -> List[Dict[str, Any]]
    def list_due_review_cards(
        self,
        within_days: int = 7,
        limit: int = 10,
    ) -> List[Dict[str, Any]]
```

### 7.3 检索逻辑

- 可按 `stage` 精确过滤
- `query` 按 token 做 `title/domain/trigger_hint/tags` 模糊匹配
- `only_active=True` 时过滤过期或非 active
- 结果附带 `retrieval_score`

## 8. 记忆沉淀策略

### 8.1 框架强制沉淀

`AgentRuntime._finalize_task_memory()` 在任务结束时总是尝试：

```python
# 1. upsert postmortem 经验卡
card_id = f"mem_task_{task_slug}_{run_slug}"
card = {
    "card_id": card_id,
    "stage": "postmortem",
    "risk_level": "P1" if task_status == "error" else "P3",
    "payload": {...}
}
SystemMemoryStore.upsert_card(card)

# 2. 追加记忆事件三连
emit_event(task_id=task_id, event_type="memory_triggered")
emit_event(task_id=task_id, event_type="memory_retrieved")
emit_event(task_id=task_id, event_type="memory_decision_made")
```

### 8.2 运行中候选捕获

工具：`capture_runtime_memory_candidate`

```python
def capture_runtime_memory_candidate(
    task_id: str,
    run_id: str,
    title: str,
    observation: str,
    ...
) -> Dict:
    # 写入 lifecycle.status=draft 的候选记忆卡
    # 同步落记忆事件三连
```

### 8.3 运行中查询

工具：`search_memory_cards`

```python
def search_memory_cards(
    query: str,
    stage: Optional[str] = None,
    limit: int = 5,
) -> Dict:
    # 只读查询
    # 返回 {success, count, cards}
```

## 9. 记忆观测落盘

`SystemMemoryEventStore` 三张表：

| 表名 | 用途 |
|------|------|
| `memory_trigger_event` | 记忆触发事件 |
| `memory_retrieval_event` | 记忆检索事件 |
| `memory_decision_event` | 记忆决策事件 |

事件写入由 `emit_event()` 自动分流：
- 非 memory 事件：只写 JSONL
- memory 事件：同时写 JSONL + SQLite（异常不阻塞主流程）

## 10. 明确行为约束

1. **默认不自动注入**：Runtime 默认不做"任务开始前系统记忆自动注入"
2. **异常不阻塞**：记忆链路异常不应中断主执行
3. **legacy 兼容**：legacy `summary` 文本仍可读，逐步迁移到 `summary_json`
4. **DB 按类型聚合**：
   - `db/runtime_memory_main_agent.db`
   - `db/runtime_memory_subagent_<role>.db`

## 11. 测试映射

| 测试文件 | 覆盖内容 |
|---------|---------|
| `tests/test_runtime_context_compression.py` | 压缩触发、摘要结构、一致性守护 |
| `tests/test_runtime_memory_harvest_tool.py` | 候选记忆捕获工具 |
| `tests/test_system_memory_store.py` | 系统记忆存储 |
| `tests/test_memory_observability_events.py` | 记忆观测事件 |
| `tests/test_runtime_eval_integration.py` | 默认不注入与任务结束沉淀 |
